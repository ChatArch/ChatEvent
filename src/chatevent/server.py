"""FastAPI application for the local ChatEvent Observatory."""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict

from . import __version__
from .adapters import (
    normalize_discourse_post,
    normalize_github_event,
    normalize_gitea_issue,
    normalize_zulip_message_event,
)
from .auth import UserRecord, UserRole, generate_arch_token, token_digest
from .catalog import PlatformSpec, list_platform_specs
from .dashboard import DASHBOARD_HTML
from .model import CaptureMode, ChatEvent
from .state import default_database_path, load_admin_token, state_paths
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
    latest_captured_at: datetime | None = None
    next_since: datetime | None = None


class PlatformPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[PlatformSpec]
    count: int


class DeleteResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deleted: bool
    id: str


class SessionStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    admin_required: bool
    authenticated: bool
    user: UserRecord | None = None
    legacy_admin: bool = False


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    display_name: str | None = None
    role: UserRole = "member"
    enabled: bool = True


class UserCreateResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user: UserRecord
    token: str


def create_app(*, db_path: str | Path | None = None) -> FastAPI:
    store = EventStore(db_path or default_database_path())
    app = FastAPI(
        title="ChatEvent Observatory",
        version=__version__,
        description="Capture, normalize, inspect, and debug collaboration events.",
    )
    app.state.store = store
    admin_token = load_admin_token()

    def admin_required() -> bool:
        return bool(admin_token or store.list_users())

    def bootstrap_admin(legacy: bool) -> UserRecord:
        return UserRecord(
            id="bootstrap-admin" if legacy else "local-admin",
            username="bootstrap-admin" if legacy else "local-admin",
            display_name="Bootstrap administrator" if legacy else "Local administrator",
            role="admin",
        )

    def resolve_identity(header_value: str | None) -> tuple[UserRecord | None, bool]:
        if header_value:
            if admin_token and secrets.compare_digest(header_value, admin_token):
                return bootstrap_admin(True), True
            user = store.get_user_by_token_hash(token_digest(header_value))
            if user is not None:
                return user, False
        if not admin_required():
            return bootstrap_admin(False), False
        return None, False

    def require_authenticated(header_value: str | None) -> UserRecord:
        identity, _legacy = resolve_identity(header_value)
        if identity is None:
            raise HTTPException(status_code=401, detail="login required")
        return identity

    def require_admin_token(header_value: str | None) -> UserRecord:
        identity = require_authenticated(header_value)
        if identity.role != "admin":
            raise HTTPException(status_code=403, detail="admin role required")
        return identity

    def can_read_subscription(subscription: Subscription, identity: UserRecord | None) -> bool:
        if identity is None:
            return subscription.owner_user_id is None
        if identity.role == "admin":
            return True
        return subscription.owner_user_id == identity.id

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def dashboard() -> str:
        return DASHBOARD_HTML

    @app.get("/api/health")
    def health() -> dict[str, str]:
        paths = state_paths(create=False)
        return {
            "status": "ok",
            "database": str(store.path),
            "chatarch_home": str(paths.chatarch_home),
            "state_dir": str(paths.state_dir),
        }

    @app.get("/api/session", response_model=SessionStatus)
    def session_status(
        x_chatevent_admin_token: str | None = Header(
            default=None, alias="X-ChatEvent-Admin-Token"
        ),
    ) -> SessionStatus:
        identity, legacy = resolve_identity(x_chatevent_admin_token)
        return SessionStatus(
            admin_required=admin_required(),
            authenticated=identity is not None,
            user=identity,
            legacy_admin=legacy,
        )

    @app.get("/api/users", response_model=list[UserRecord])
    def list_users(
        x_chatevent_admin_token: str | None = Header(
            default=None, alias="X-ChatEvent-Admin-Token"
        ),
    ) -> list[UserRecord]:
        require_admin_token(x_chatevent_admin_token)
        return store.list_users()

    @app.post("/api/users", response_model=UserCreateResult, status_code=201)
    def create_user(
        payload: UserCreate,
        x_chatevent_admin_token: str | None = Header(
            default=None, alias="X-ChatEvent-Admin-Token"
        ),
    ) -> UserCreateResult:
        require_admin_token(x_chatevent_admin_token)
        token = generate_arch_token()
        user = store.save_user(
            UserRecord(
                username=payload.username,
                display_name=payload.display_name,
                role=payload.role,
                enabled=payload.enabled,
            ),
            token_hash=token_digest(token),
        )
        return UserCreateResult(user=user, token=token)

    @app.delete("/api/users/{user_id}", response_model=DeleteResult)
    def delete_user(
        user_id: str,
        x_chatevent_admin_token: str | None = Header(
            default=None, alias="X-ChatEvent-Admin-Token"
        ),
    ) -> DeleteResult:
        require_admin_token(x_chatevent_admin_token)
        deleted = store.delete_user(user_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="user not found")
        return DeleteResult(deleted=True, id=user_id)

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
    def save_subscription(
        subscription: Subscription,
        x_chatevent_admin_token: str | None = Header(
            default=None, alias="X-ChatEvent-Admin-Token"
        ),
    ) -> Subscription:
        identity = require_authenticated(x_chatevent_admin_token)
        if identity.role != "admin":
            existing = store.get_subscription(subscription.id)
            if existing is not None and existing.owner_user_id != identity.id:
                raise HTTPException(status_code=403, detail="subscription belongs to another user")
            subscription = subscription.model_copy(update={"owner_user_id": identity.id})
        return store.save_subscription(subscription)

    @app.get("/api/subscriptions", response_model=list[Subscription])
    def list_subscriptions(
        enabled: bool | None = None,
        x_chatevent_admin_token: str | None = Header(
            default=None, alias="X-ChatEvent-Admin-Token"
        ),
    ) -> list[Subscription]:
        identity, _legacy = resolve_identity(x_chatevent_admin_token)
        items = store.list_subscriptions(enabled=enabled)
        return [item for item in items if can_read_subscription(item, identity)]

    @app.get("/api/subscriptions/{subscription_id}", response_model=Subscription)
    def get_subscription(
        subscription_id: str,
        x_chatevent_admin_token: str | None = Header(
            default=None, alias="X-ChatEvent-Admin-Token"
        ),
    ) -> Subscription:
        subscription = store.get_subscription(subscription_id)
        if subscription is None or not can_read_subscription(
            subscription, resolve_identity(x_chatevent_admin_token)[0]
        ):
            raise HTTPException(status_code=404, detail="subscription not found")
        return subscription

    @app.delete("/api/subscriptions/{subscription_id}", response_model=DeleteResult)
    def delete_subscription(
        subscription_id: str,
        x_chatevent_admin_token: str | None = Header(
            default=None, alias="X-ChatEvent-Admin-Token"
        ),
    ) -> DeleteResult:
        identity = require_authenticated(x_chatevent_admin_token)
        existing = store.get_subscription(subscription_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="subscription not found")
        if identity.role != "admin" and existing.owner_user_id != identity.id:
            raise HTTPException(status_code=403, detail="subscription belongs to another user")
        deleted = store.delete_subscription(subscription_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="subscription not found")
        return DeleteResult(deleted=True, id=subscription_id)

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
        payload: dict[str, Any],
        subscription_id: str | None = None,
        x_discourse_event: str | None = Header(default=None, alias="X-Discourse-Event"),
    ) -> EventWriteResult:
        if x_discourse_event and not (payload.get("event_name") or payload.get("discourse_event")):
            payload = {**payload, "event_name": x_discourse_event}
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
        since: datetime | None = None,
        from_: Annotated[datetime | None, Query(alias="from")] = None,
        to: datetime | None = None,
        days: Annotated[float | None, Query(gt=0, le=365)] = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> EventPage:
        if since is not None and (since.tzinfo is None or since.utcoffset() is None):
            raise HTTPException(
                status_code=422,
                detail="since must include timezone information, for example 2026-08-18T10:00:02Z",
            )
        if from_ is not None and (from_.tzinfo is None or from_.utcoffset() is None):
            raise HTTPException(
                status_code=422,
                detail="from must include timezone information, for example 2026-08-18T00:00:00Z",
            )
        if to is not None and (to.tzinfo is None or to.utcoffset() is None):
            raise HTTPException(
                status_code=422,
                detail="to must include timezone information, for example 2026-08-19T00:00:00Z",
            )
        days_from = None
        if days is not None:
            days_from = datetime.now(timezone.utc) - timedelta(days=days)
        captured_from_candidates = [value for value in (from_, days_from) if value is not None]
        captured_from = max(captured_from_candidates) if captured_from_candidates else None
        if captured_from is not None and to is not None and captured_from > to:
            raise HTTPException(status_code=422, detail="from/days lower bound must not be after to")
        items = store.list_events(
            source=source,
            kind=kind,
            subscription_id=subscription_id,
            query=q,
            captured_since=since,
            captured_from=captured_from,
            captured_until=to,
            limit=limit,
        )
        latest_captured_at = max(
            (item.event.captured_at for item in items), default=None
        )
        return EventPage(
            items=items,
            count=len(items),
            latest_captured_at=latest_captured_at,
            next_since=latest_captured_at,
        )

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
