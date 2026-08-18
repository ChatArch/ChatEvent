"""Extension protocol for event capture adapters."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from .model import CaptureMode, ChatEvent


class EventMonitor(Protocol):
    """An asynchronous source of normalized events."""

    source: str
    mode: CaptureMode

    def events(self, *, cursor: str | None = None) -> AsyncIterator[ChatEvent]:
        """Yield new events, optionally continuing from a source cursor."""

        ...

