"""Pydantic event specification shared by platform adapters."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
)


class CaptureMode(str, Enum):
    """How an event entered the capture layer.

    ``push``/``pull`` are legacy coarse buckets retained for existing stored
    events and subscriptions. New integrations should use the platform-specific
    acquisition modes below: webhooks, event queues, API cursors, polling, or
    explicit backfill/synthetic/demo events.
    """

    WEBHOOK = "webhook"
    EVENT_QUEUE = "event_queue"
    API_CURSOR = "api_cursor"
    POLL = "poll"
    MANUAL_BACKFILL = "manual_backfill"
    GATEWAY_FORWARD = "gateway_forward"
    TEST_FIXTURE = "test_fixture"
    SYNTHETIC = "synthetic"

    # Legacy compatibility for previously recorded events/subscriptions.
    PUSH = "push"
    PULL = "pull"


def utc_now() -> datetime:
    """Return an aware UTC timestamp."""

    return datetime.now(timezone.utc)


class ChatEvent(BaseModel):
    """A platform-neutral event envelope.

    Event IDs only need to be stable within a source. Normalized platform data
    stays in ``payload`` while ``raw_payload`` preserves the source message for
    debugging and future adapter improvements.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    occurred_at: AwareDatetime
    captured_at: AwareDatetime = Field(default_factory=utc_now)
    capture_mode: CaptureMode
    subscription_id: str | None = None
    actor_id: str | None = None
    conversation_id: str | None = None
    subject_id: str | None = None
    subject_type: str | None = None
    url: str | None = None
    cursor: str | None = None
    payload: dict[str, JsonValue] = Field(default_factory=dict)
    raw_payload: JsonValue | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)

    @field_validator("id", "source", "kind")
    @classmethod
    def identity_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("occurred_at", "captured_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))

    @property
    def dedupe_key(self) -> str:
        """Return the default stable key used to suppress duplicate delivery."""

        return f"{self.source}:{self.id}"

    def to_dict(self) -> dict[str, JsonValue]:
        """Return a JSON-compatible representation of the envelope."""

        return self.model_dump(mode="json")
