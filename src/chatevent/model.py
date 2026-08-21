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
    model_validator,
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


class CarrierTarget(BaseModel):
    """Where an action is carried, without constraining platform-specific shapes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: str = Field(min_length=1)
    key: str = Field(min_length=1)
    display: str | None = None
    url: str | None = None
    parent: "CarrierTarget | None" = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("type", "key")
    @classmethod
    def required_text_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("display", "url")
    @classmethod
    def optional_text_is_stripped(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    def chain(self) -> list["CarrierTarget"]:
        """Return parent-to-child target chain for display and matching."""

        items: list[CarrierTarget] = []
        current: CarrierTarget | None = self
        while current is not None:
            items.append(current)
            current = current.parent
        return list(reversed(items))


class ActionDescriptor(BaseModel):
    """A normalized action selector/description that stays extensible."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str = Field(min_length=1)
    object_type: str | None = None
    verb: str | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("kind")
    @classmethod
    def kind_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("object_type", "verb")
    @classmethod
    def optional_text_is_stripped(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


def action_from_kind(kind: str, *, object_type: str | None = None) -> ActionDescriptor:
    """Build a best-effort action descriptor from a dotted event kind."""

    normalized = kind.strip()
    if not normalized:
        raise ValueError("kind must not be empty")
    parts = normalized.split(".")
    inferred_object = object_type or (".".join(parts[:-1]) if len(parts) > 1 else None)
    return ActionDescriptor(kind=normalized, object_type=inferred_object, verb=parts[-1])


class ActorDescriptor(BaseModel):
    """Who initiated the action, including an optional platform-specific role."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str | None = None
    type: str | None = None
    display: str | None = None
    role: str | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("id", "type", "display", "role")
    @classmethod
    def optional_text_is_stripped(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


def _target_type_for_prefix(source: str, prefix: str) -> str:
    if source == "x" and prefix in {"user", "handle"}:
        return "x_user"
    if source == "x" and prefix in {"post", "status"}:
        return "x_post"
    if prefix == "topic":
        return "zulip_topic" if source == "zulip" else "discourse_topic"
    if prefix == "stream":
        return "zulip_stream"
    if prefix == "category":
        return "discourse_category"
    return prefix


def _repo_parent(repo_key: str) -> CarrierTarget:
    return CarrierTarget(type="repo", key=repo_key, display=repo_key)


def target_from_string(source: str, target: str | None) -> CarrierTarget | None:
    """Parse common canonical target strings into a flexible target chain.

    Unknown forms intentionally fall back to a generic ``scope`` or prefixed
    target so future integrations can keep using the model without core changes.
    """

    if not target:
        return None
    text = target.strip()
    if not text:
        return None
    source = source.strip().lower()

    if text.startswith("stream:") and "/topic:" in text:
        stream, topic = text.removeprefix("stream:").split("/topic:", 1)
        stream_target = CarrierTarget(type="zulip_stream", key=stream, display=stream)
        return CarrierTarget(
            type="zulip_topic",
            key=f"{stream}/{topic}",
            display=topic,
            parent=stream_target,
        )
    if text.startswith("narrow:"):
        pieces = dict(
            part.split("=", 1)
            for part in text.removeprefix("narrow:").split(",")
            if "=" in part
        )
        stream = pieces.get("stream")
        topic = pieces.get("topic")
        if stream and topic:
            stream_target = CarrierTarget(type="zulip_stream", key=stream, display=stream)
            return CarrierTarget(
                type="zulip_topic",
                key=f"{stream}/{topic}",
                display=topic,
                parent=stream_target,
            )

    if text.startswith("pull_request:") and "#" in text:
        value = text.removeprefix("pull_request:")
        repo, number = value.rsplit("#", 1)
        return CarrierTarget(type="pull_request", key=value, display=f"PR #{number}", parent=_repo_parent(repo))
    if text.startswith("issue:") and "#" in text:
        value = text.removeprefix("issue:")
        repo, number = value.rsplit("#", 1)
        return CarrierTarget(type="issue", key=value, display=f"Issue #{number}", parent=_repo_parent(repo))
    if text.startswith("repo:"):
        repo = text.removeprefix("repo:")
        return _repo_parent(repo)
    if source in {"github", "gitea"} and "/" in text and ":" not in text:
        return _repo_parent(text)
    if ":" in text:
        prefix, key = text.split(":", 1)
        target_type = _target_type_for_prefix(source, prefix)
        return CarrierTarget(type=target_type, key=key, display=key)
    return CarrierTarget(type="scope", key=text, display=text)


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
    action: ActionDescriptor | None = None
    target: CarrierTarget | None = None
    actor: ActorDescriptor | None = None
    actor_role: str | None = None
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

    @model_validator(mode="after")
    def fill_action_descriptor(self) -> "ChatEvent":
        if self.action is None:
            object.__setattr__(
                self,
                "action",
                action_from_kind(self.kind, object_type=self.subject_type),
            )
        if self.target is None and self.subject_id and self.subject_type:
            parent = target_from_string(self.source, self.conversation_id)
            object.__setattr__(
                self,
                "target",
                CarrierTarget(
                    type=self.subject_type,
                    key=self.subject_id,
                    display=self.subject_id,
                    parent=parent,
                ),
            )
        if self.actor is None and (self.actor_id or self.actor_role):
            object.__setattr__(
                self,
                "actor",
                ActorDescriptor(id=self.actor_id, type="user" if self.actor_id else None, role=self.actor_role),
            )
        elif self.actor is not None:
            if self.actor_id is None and self.actor.id:
                object.__setattr__(self, "actor_id", self.actor.id)
            if self.actor_role is None and self.actor.role:
                object.__setattr__(self, "actor_role", self.actor.role)
        return self

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
