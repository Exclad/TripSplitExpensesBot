from __future__ import annotations

from dataclasses import dataclass


try:
    from telegram import ForceReply
except ImportError:  # pragma: no cover - tests use this lightweight fallback.

    @dataclass(frozen=True)
    class ForceReply:  # type: ignore[no-redef]
        selective: bool = True
        input_field_placeholder: str | None = None
        force_reply: bool = True


def force_reply(placeholder: str) -> ForceReply:
    return ForceReply(selective=True, input_field_placeholder=placeholder[:64])
