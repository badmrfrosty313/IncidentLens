"""Input limits. Every limit can be overridden with an environment variable."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


@dataclass(frozen=True)
class Limits:
    # Decoded UTF-8 size of the submitted log content.
    max_input_bytes: int = 20 * 1024 * 1024
    # Parsed + malformed records. Inputs above this are rejected, never truncated.
    max_events: int = 100_000
    # Physical lines longer than this are clipped (plaintext) or rejected (JSON).
    max_line_chars: int = 16_384
    # Stored message length after redaction.
    max_message_chars: int = 2_000
    # Continuation lines (stack traces) folded into one plaintext record.
    max_continuation_lines: int = 50
    # Events returned to the client for the log viewer.
    max_returned_events: int = 5_000
    max_malformed_samples: int = 10

    @classmethod
    def from_env(cls) -> "Limits":
        d = cls()
        return cls(
            max_input_bytes=_int_env("INCIDENTLENS_MAX_INPUT_BYTES", d.max_input_bytes),
            max_events=_int_env("INCIDENTLENS_MAX_EVENTS", d.max_events),
            max_line_chars=_int_env("INCIDENTLENS_MAX_LINE_CHARS", d.max_line_chars),
            max_message_chars=_int_env("INCIDENTLENS_MAX_MESSAGE_CHARS", d.max_message_chars),
            max_continuation_lines=d.max_continuation_lines,
            max_returned_events=_int_env("INCIDENTLENS_MAX_RETURNED_EVENTS", d.max_returned_events),
            max_malformed_samples=d.max_malformed_samples,
        )


DEFAULT_LIMITS = Limits.from_env()
