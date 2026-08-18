"""Subscription specification for monitored platform targets."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
)

from .model import CaptureMode, JsonValue, utc_now


class Subscription(BaseModel):
    """Describe which external target should be observed and how."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: uuid4().hex, min_length=1)
    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    label: str | None = None
    event_kinds: list[str] = Field(default_factory=lambda: ["*"], min_length=1)
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

    @field_validator("id", "source", "target")
    @classmethod
    def identity_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

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
