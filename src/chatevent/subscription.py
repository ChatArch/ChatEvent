"""Subscription specification for monitored platform targets."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)

from .model import (
    ActionDescriptor,
    CaptureMode,
    CarrierTarget,
    JsonValue,
    action_from_kind,
    target_from_string,
    utc_now,
)


class Subscription(BaseModel):
    """Describe which external target should be observed and how."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: uuid4().hex, min_length=1)
    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    scope: CarrierTarget | None = None
    label: str | None = None
    owner_user_id: str | None = None
    event_kinds: list[str] = Field(default_factory=lambda: ["*"], min_length=1)
    actions: list[ActionDescriptor] = Field(default_factory=list)
    capture_modes: list[CaptureMode] = Field(
        default_factory=lambda: [CaptureMode.API_CURSOR], min_length=1
    )
    filters: dict[str, JsonValue] = Field(default_factory=dict)
    labels: list[str] = Field(default_factory=list)
    enabled: bool = True
    created_at: AwareDatetime = Field(default_factory=utc_now)
    updated_at: AwareDatetime = Field(default_factory=utc_now)
    last_event_at: AwareDatetime | None = None
    last_cursor: str | None = None
    last_error: str | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @property
    def is_temporary(self) -> bool:
        return self.metadata.get("temporary") is True

    @property
    def expires_at(self) -> datetime | None:
        value = self.metadata.get("expires_at")
        if not isinstance(value, str) or not value.strip():
            return None
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("metadata.expires_at must include timezone information")
        return parsed.astimezone(timezone.utc)

    def is_expired(self, *, now: datetime | None = None) -> bool:
        expires_at = self.expires_at
        if expires_at is None:
            return False
        current = now or utc_now()
        return current.astimezone(timezone.utc) >= expires_at

    @field_validator("id", "source", "target")
    @classmethod
    def identity_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("owner_user_id")
    @classmethod
    def normalize_owner_user_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("created_at", "updated_at", "last_event_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value.astimezone(timezone.utc)

    @field_validator("event_kinds")
    @classmethod
    def normalize_event_kinds(cls, values: list[str]) -> list[str]:
        normalized = list(
            dict.fromkeys(value.strip() for value in values if value.strip())
        )
        if not normalized:
            raise ValueError("must contain at least one event kind")
        return normalized

    @field_validator("capture_modes")
    @classmethod
    def normalize_capture_modes(cls, values: list[CaptureMode]) -> list[CaptureMode]:
        return list(dict.fromkeys(values))

    @field_validator("actions")
    @classmethod
    def normalize_actions(cls, values: list[ActionDescriptor]) -> list[ActionDescriptor]:
        unique: dict[str, ActionDescriptor] = {}
        for value in values:
            unique.setdefault(value.kind, value)
        return list(unique.values())

    @model_validator(mode="after")
    def derive_structured_selectors(self) -> "Subscription":
        if self.scope is None:
            self.scope = target_from_string(self.source, self.target)
        if not self.actions and self.event_kinds != ["*"]:
            self.actions = [action_from_kind(kind) for kind in self.event_kinds]
        if self.actions and self.event_kinds == ["*"]:
            self.event_kinds = [action.kind for action in self.actions]
        return self


def zulip_topic_target(stream: str, topic: str) -> str:
    """Return ChatEvent's canonical Zulip topic target string."""

    stream = stream.strip()
    topic = topic.strip()
    if not stream or not topic:
        raise ValueError("stream and topic must not be empty")
    return f"stream:{stream}/topic:{topic}"


def temporary_zulip_topic_watch(
    *,
    stream: str,
    topic: str,
    assignment_id: str,
    interval_seconds: int,
    expires_at: datetime | None = None,
    ttl_seconds: int | None = None,
    hot_until: datetime | None = None,
    reason: str,
    subscription_id: str | None = None,
    owner_user_id: str | None = None,
) -> Subscription:
    """Build a first-class temporary Zulip stream/topic watch.

    The watch is scoped only to platform selectors.  Assignment-specific sender,
    tag, and confirmation policy intentionally belongs to the consumer of the
    normalized events, not to ChatEvent capture.
    """

    normalized_assignment_id = assignment_id.strip()
    normalized_reason = reason.strip()
    if not normalized_assignment_id:
        raise ValueError("assignment_id must not be empty")
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")
    if expires_at is None:
        if ttl_seconds is None or ttl_seconds <= 0:
            raise ValueError("expires_at or positive ttl_seconds is required")
        expires_at = utc_now() + timedelta(seconds=ttl_seconds)
    expires_at = expires_at.astimezone(timezone.utc)
    hot_until = (hot_until or expires_at).astimezone(timezone.utc)
    return Subscription(
        id=subscription_id
        or f"zulip-topic-{normalized_assignment_id.replace(':', '-').replace('/', '-')}",
        source="zulip",
        target=zulip_topic_target(stream, topic),
        label=f"Temporary Zulip topic watch for {normalized_assignment_id}",
        owner_user_id=owner_user_id,
        event_kinds=["message.created"],
        capture_modes=[CaptureMode.API_CURSOR, CaptureMode.POLL],
        filters={"stream": stream.strip(), "topic": topic.strip()},
        labels=["zulip", "topic-watch", "temporary"],
        metadata={
            "temporary": True,
            "assignment_id": normalized_assignment_id,
            "interval_seconds": interval_seconds,
            "expires_at": expires_at.isoformat(),
            "hot_until": hot_until.isoformat(),
            "reason": normalized_reason,
            "content_policy": "topic-scoped-message-content",
            "policy_boundary": "platform-scope-only; consumer filters sender/assignment policy",
        },
    )
