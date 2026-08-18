"""FastAPI application for the local ChatEvent Observatory."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict

from .adapters import (
    normalize_discourse_post,
    normalize_github_event,
    normalize_gitea_issue,
    normalize_zulip_message_event,
)
from .catalog import PlatformSpec, list_platform_specs
from .dashboard import DASHBOARD_HTML
from .model import CaptureMode, ChatEvent
from .store import EventStore, StoredEvent
from .subscription import Subscription


class EventWriteResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    created: bool
    dedupe_key: str
    seen_count: int


class EventPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[StoredEvent]
    count: int


class PlatformPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[PlatformSpec]
    count: int


def default_database_path() -> Path:
    configured = os.environ.get("CHATEVENT_DB")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".chatevent" / "events.db"


def create_app(*, db_path: str | Path | None = None) -> FastAPI:
    store = EventStore(db_path or default_database_path())
    app = FastAPI(
        title="ChatEvent Observatory",
        version="0.1.0.dev0",
        description="Capture, normalize, inspect, and debug collaboration events.",
    )
    app.state.store = store

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def dashboard() -> str:
        return DASHBOARD_HTML

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "database": str(store.path)}

    @app.get("/api/schema/event")
    def event_schema() -> dict[str, Any]:
        return ChatEvent.model_json_schema()

    @app.get("/api/schema/subscription")
    def subscription_schema() -> dict[str, Any]:
        return Subscription.model_json_schema()

    @app.get("/api/platforms", response_model=PlatformPage)
    def list_platforms() -> PlatformPage:
        items = list(list_platform_specs())
        return PlatformPage(items=items, count=len(items))

    @app.post("/api/subscriptions", response_model=Subscription, status_code=201)
    def save_subscription(subscription: Subscription) -> Subscription:
        return store.save_subscription(subscription)

    @app.get("/api/subscriptions", response_model=list[Subscription])
    def list_subscriptions(enabled: bool | None = None) -> list[Subscription]:
        return store.list_subscriptions(enabled=enabled)

    @app.get("/api/subscriptions/{subscription_id}", response_model=Subscription)
    def get_subscription(subscription_id: str) -> Subscription:
        subscription = store.get_subscription(subscription_id)
        if subscription is None:
            raise HTTPException(status_code=404, detail="subscription not found")
        return subscription

    @app.post("/api/events", response_model=EventWriteResult, status_code=202)
    def record_event(event: ChatEvent) -> EventWriteResult:
        return _record(event)

    def _record(event: ChatEvent) -> EventWriteResult:
        stored, created = store.record_event(event)
        return EventWriteResult(
            created=created,
            dedupe_key=event.dedupe_key,
            seen_count=stored.seen_count,
        )

    @app.post("/webhooks/zulip", response_model=EventWriteResult, status_code=202)
    def record_zulip_webhook(
        payload: dict[str, Any], subscription_id: str | None = None
    ) -> EventWriteResult:
        try:
            event = normalize_zulip_message_event(
                payload,
                subscription_id=subscription_id,
                site_url=os.environ.get("ZULIP_SITE"),
                capture_mode=CaptureMode.EVENT_QUEUE,
            )
        except Exception as error:  # pragma: no cover - exercised through HTTP response
            raise HTTPException(status_code=422, detail=str(error)) from error
        return _record(event)

    @app.post("/webhooks/discourse", response_model=EventWriteResult, status_code=202)
    def record_discourse_webhook(
        payload: dict[str, Any], subscription_id: str | None = None
    ) -> EventWriteResult:
        try:
            event = normalize_discourse_post(
                payload,
                subscription_id=subscription_id,
                base_url=os.environ.get("DISCOURSE_BASE_URL"),
                capture_mode=CaptureMode.WEBHOOK,
            )
        except Exception as error:  # pragma: no cover - exercised through HTTP response
            raise HTTPException(status_code=422, detail=str(error)) from error
        return _record(event)

    @app.post("/webhooks/gitea", response_model=EventWriteResult, status_code=202)
    def record_gitea_webhook(
        payload: dict[str, Any], subscription_id: str | None = None
    ) -> EventWriteResult:
        try:
            event = normalize_gitea_issue(
                payload,
                subscription_id=subscription_id,
                capture_mode=CaptureMode.WEBHOOK,
            )
        except Exception as error:  # pragma: no cover - exercised through HTTP response
            raise HTTPException(status_code=422, detail=str(error)) from error
        return _record(event)

    @app.post("/webhooks/github", response_model=EventWriteResult, status_code=202)
    def record_github_webhook(
        payload: dict[str, Any],
        subscription_id: str | None = None,
        x_github_event: str | None = Header(default=None, alias="X-GitHub-Event"),
    ) -> EventWriteResult:
        if x_github_event == "ping":
            return EventWriteResult(dedupe_key="github:ping", created=False, seen_count=0)
        try:
            event = normalize_github_event(
                x_github_event or "push",
                payload,
                subscription_id=subscription_id,
                capture_mode=CaptureMode.WEBHOOK,
            )
        except Exception as error:  # pragma: no cover - exercised through HTTP response
            raise HTTPException(status_code=422, detail=str(error)) from error
        return _record(event)

    @app.get("/api/events", response_model=EventPage)
    def list_events(
        source: str | None = None,
        kind: str | None = None,
        subscription_id: str | None = None,
        q: str | None = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> EventPage:
        items = store.list_events(
            source=source,
            kind=kind,
            subscription_id=subscription_id,
            query=q,
            limit=limit,
        )
        return EventPage(items=items, count=len(items))

    @app.get("/api/events/{dedupe_key:path}", response_model=StoredEvent)
    def get_event(dedupe_key: str) -> StoredEvent:
        event = store.get_event(dedupe_key)
        if event is None:
            raise HTTPException(status_code=404, detail="event not found")
        return event

    @app.get("/api/stats")
    def stats() -> dict[str, Any]:
        return store.stats()

    return app
