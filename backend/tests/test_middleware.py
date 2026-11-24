"""BodySizeLimitMiddleware tested with a raw ASGI harness (no web framework needed)."""

import asyncio
import json

from app.middleware import BodySizeLimitMiddleware


async def _echo_app(scope, receive, send):
    body = b""
    while True:
        msg = await receive()
        body += msg.get("body", b"")
        if not msg.get("more_body"):
            break
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": str(len(body)).encode()})


async def _call(app, chunks, headers=None):
    sent = []
    queue = list(chunks)

    async def receive():
        body = queue.pop(0) if queue else b""
        return {"type": "http.request", "body": body, "more_body": bool(queue)}

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "headers": headers or [], "method": "POST", "path": "/"}
    await app(scope, receive, send)
    start = next(m for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return start["status"], body


def run(coro):
    return asyncio.run(coro)


def test_small_body_passes_through():
    app = BodySizeLimitMiddleware(_echo_app, 100)
    status, body = run(_call(app, [b"x" * 50]))
    assert (status, body) == (200, b"50")


def test_declared_content_length_over_limit_is_rejected_without_reading():
    app = BodySizeLimitMiddleware(_echo_app, 100)
    status, body = run(_call(app, [b"x" * 10], headers=[(b"content-length", b"5000")]))
    assert status == 413 and json.loads(body)["code"] == "input_too_large"


def test_chunked_body_over_limit_is_rejected_while_streaming():
    app = BodySizeLimitMiddleware(_echo_app, 100)
    status, _ = run(_call(app, [b"x" * 60, b"x" * 60]))
    assert status == 413


def test_lying_content_length_does_not_bypass_the_limit():
    app = BodySizeLimitMiddleware(_echo_app, 100)
    status, _ = run(_call(app, [b"x" * 500], headers=[(b"content-length", b"10")]))
    assert status == 413


def test_non_http_scopes_are_ignored():
    called = []

    async def inner(scope, receive, send):
        called.append(scope["type"])

    run(BodySizeLimitMiddleware(inner, 1)({"type": "lifespan"}, None, None))
    assert called == ["lifespan"]
