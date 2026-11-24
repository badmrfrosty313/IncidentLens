"""Pure-ASGI request body size guard (no framework imports, so it is unit-testable alone)."""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

Scope = dict[str, Any]
Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]


class BodySizeLimitMiddleware:
    """Reject request bodies above ``max_body_bytes`` with 413 before they are buffered.

    Checks Content-Length up front and counts streamed bytes for chunked uploads.
    """

    def __init__(self, app: Callable[..., Awaitable[None]], max_body_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = dict(scope.get("headers", [])).get(b"content-length")
        if declared is not None:
            try:
                too_big = int(declared) > self.max_body_bytes
            except ValueError:
                too_big = False
            if too_big:
                await self._reject(send)
                return

        received = 0
        overflow = False
        started = False

        async def limited_receive() -> dict[str, Any]:
            # Do not raise from here: FastAPI wraps any exception raised while reading the body in an
            # HTTP 400, so a chunked upload over the limit would be reported as "bad request". Report a
            # disconnect to the app instead and replace whatever it answers with a 413 below.
            nonlocal received, overflow
            if overflow:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_bytes:
                    overflow = True
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message: dict[str, Any]) -> None:
            nonlocal started
            if overflow:
                if not started:
                    started = True
                    await self._reject(send)
                return  # swallow the app's own (400/500) response
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except Exception:
            if not overflow:
                raise
        if overflow and not started:
            await self._reject(send)

    async def _reject(self, send: Send) -> None:
        body = json.dumps(
            {"code": "input_too_large", "detail": f"Request body exceeds the {self.max_body_bytes:,} byte limit."}
        ).encode()
        await send({"type": "http.response.start", "status": 413,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
