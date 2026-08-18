"""Normalized event model shared by platform adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping


class CaptureMode(str, Enum):
    """How an event entered the capture layer."""

    PUSH = "push"
    PULL = "pull"


@dataclass(frozen=True, slots=True)
class ChatEvent:
    """A platform-neutral event envelope.

    Event IDs only need to be stable within a source. Platform-specific data
    stays in ``payload`` so the core model can evolve independently of SDKs.
    """

    id: str
    source: str
    kind: str
    occurred_at: datetime
    capture_mode: CaptureMode
    payload: Mapping[str, Any] = field(default_factory=dict)
    actor_id: str | None = None
    conversation_id: str | None = None
    url: str | None = None
    cursor: str | None = None

    def __post_init__(self) -> None:
        for name in ("id", "source", "kind"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")

    @property
    def dedupe_key(self) -> str:
        """Return the default stable key used to suppress duplicate delivery."""

        return f"{self.source}:{self.id}"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible representation of the envelope."""

        return {
            "id": self.id,
            "source": self.source,
            "kind": self.kind,
            "occurred_at": self.occurred_at.isoformat(),
            "capture_mode": self.capture_mode.value,
            "payload": dict(self.payload),
            "actor_id": self.actor_id,
            "conversation_id": self.conversation_id,
            "url": self.url,
            "cursor": self.cursor,
        }

