"""FastAPI application for the local ChatEvent Observatory."""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from importlib import resources
from pathlib import Path
from typing import Annotated, Any, Callable, Literal

from chatlogin import (
    AccessDenied,
    CallbackBackend,
    MemorySessionStore,
    Principal,
    Role,
    SessionManager,
    StoreFull,
    require_csrf,
    safe_next,
)
from chatlogin.ui import LoginUI
from fastapi import Cookie, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from . import __version__
from .adapters import (
    normalize_discourse_post,
    normalize_github_event,
    normalize_gitea_issue,
    normalize_zulip_message_event,
)
from .auth import (
    UserRecord,
    UserRole,
    generate_arch_token,
    password_digest,
    token_digest,
    verify_password,
)
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
    csrf_token: str | None = None
    next: str | None = None


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    password: str = Field(min_length=1)
    display_name: str | None = None
    role: UserRole = "member"
    enabled: bool = True


class UserCreateResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user: UserRecord


class UserTokenResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user: UserRecord
    token: str


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    password: str
    next: str | None = None


SESSION_COOKIE = "chatevent_session"


def _positive_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be a positive integer") from error
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _secure_cookie() -> bool:
    configured = os.environ.get("CHATEVENT_COOKIE_SECURE", "").strip().lower()
    if configured in {"1", "true", "yes", "on"}:
        return True
    if configured in {"0", "false", "no", "off"}:
        return False
    origin = os.environ.get("CHATEVENT_PUBLIC_ORIGIN", "").strip().lower()
    return origin.startswith("https://")


def _mount_root(request: Request) -> str:
    root_path = str(request.scope.get("root_path", "") or "").rstrip("/")
    return f"{root_path}/" if root_path else "/"


def _safe_next_for_request(request: Request, value: str | None) -> str:
    return safe_next(value, _mount_root(request))


def create_app(
    *,
    db_path: str | Path | None = None,
    clock: Callable[[], float] | None = None,
    login_ui: LoginUI | None = None,
) -> FastAPI:
    store = EventStore(db_path or default_database_path())
    app = FastAPI(
        title="ChatEvent Observatory",
        version=__version__,
        description="Capture, normalize, inspect, and debug collaboration events.",
    )
    app.state.store = store
    admin_token = load_admin_token()
    session_ttl = _positive_int_env("CHATEVENT_SESSION_TTL_SECONDS", 60 * 60 * 24)
    max_sessions = _positive_int_env("CHATEVENT_MAX_SESSIONS", 1024)
    session_manager = SessionManager(
        MemorySessionStore(max_sessions=max_sessions),
        instance="chatevent",
        ttl=session_ttl,
        clock=clock or __import__("time").time,
    )
    login_ui = login_ui or LoginUI(
        title="ChatEvent",
        subtitle="登录后查看事件流、订阅和用户管理。API token 只用于 CLI、模型或程序调用。",
        palette="forest",
        appearance="dark",
    )

    def load_secret(name: str, file_name: str) -> str | None:
        value = os.environ.get(name)
        if value:
            return value.strip()
        path = os.environ.get(file_name)
        if path:
            secret_path = Path(path).expanduser()
            if secret_path.exists():
                return secret_path.read_text(encoding="utf-8").strip()
        return None

    def bootstrap_password_user() -> None:
        username = os.environ.get("CHATEVENT_BOOTSTRAP_USERNAME", "").strip()
        password = load_secret(
            "CHATEVENT_BOOTSTRAP_PASSWORD", "CHATEVENT_BOOTSTRAP_PASSWORD_FILE"
        )
        if not username or not password:
            return
        existing = store.get_user_by_username(username, enabled_only=False)
        user = existing or UserRecord(username=username, role="admin")
        if user.role != "admin":
            user = user.model_copy(update={"role": "admin"})
        store.save_user(user, password_hash=password_digest(password))

    bootstrap_password_user()

    def admin_required() -> bool:
        return bool(admin_token or store.list_users())

    def bootstrap_admin(legacy: bool) -> UserRecord:
        return UserRecord(
            id="bootstrap-admin" if legacy else "local-admin",
            username="bootstrap-admin" if legacy else "local-admin",
            display_name="Bootstrap administrator" if legacy else "Local administrator",
            role="admin",
        )

    def to_principal(user: UserRecord) -> Principal:
        return Principal(
            user_id=user.id,
            display_name=user.display_name or user.username,
            role=Role.ADMIN if user.role == "admin" else Role.USER,
        )

    def authenticate_password(username: str, password: str) -> Principal | None:
        user = store.get_user_by_username(username)
        password_hash = store.get_user_password_hash(user.id) if user is not None else None
        if user is None or not verify_password(password, password_hash):
            return None
        return to_principal(user)

    backend = CallbackBackend(authenticate_password)

    def session_user(cookie_value: str | None) -> tuple[UserRecord | None, Any | None]:
        session = session_manager.resolve(cookie_value)
        if session is None or session.principal.user_id is None:
            return None, None
        return store.get_user(session.principal.user_id), session

    def resolve_api_identity(header_value: str | None) -> tuple[UserRecord | None, bool]:
        if not header_value:
            return None, False
        if admin_token and secrets.compare_digest(header_value, admin_token):
            return bootstrap_admin(True), True
        user = store.get_user_by_token_hash(token_digest(header_value))
        if user is not None:
            return user, False
        return None, False

    def resolve_identity(
        header_value: str | None, cookie_value: str | None = None
    ) -> tuple[UserRecord | None, bool, Literal["api", "legacy", "session", "local", "none"]]:
        api_identity, legacy = resolve_api_identity(header_value)
        if api_identity is not None:
            return api_identity, legacy, "legacy" if legacy else "api"
        session_identity, _session = session_user(cookie_value)
        if session_identity is not None:
            return session_identity, False, "session"
        if not admin_required():
            return bootstrap_admin(False), False, "local"
        return None, False, "none"

    def require_authenticated(
        header_value: str | None, cookie_value: str | None = None
    ) -> tuple[UserRecord, Literal["api", "legacy", "session", "local"]]:
        identity, _legacy, source = resolve_identity(header_value, cookie_value)
        if identity is None:
            raise HTTPException(status_code=401, detail="login required")
        return identity, source  # type: ignore[return-value]

    def require_admin_token(
        header_value: str | None, cookie_value: str | None = None
    ) -> tuple[UserRecord, Literal["api", "legacy", "session", "local"]]:
        identity, source = require_authenticated(header_value, cookie_value)
        if identity.role != "admin":
            raise HTTPException(status_code=403, detail="admin role required")
        return identity, source

    def require_write_csrf(
        source: Literal["api", "legacy", "session", "local"],
        cookie_value: str | None,
        csrf_header: str | None,
    ) -> None:
        if source != "session":
            return
        _user, session = session_user(cookie_value)
        if session is None:
            raise HTTPException(status_code=401, detail="login required")
        try:
            require_csrf(session, csrf_header)
        except AccessDenied as error:
            raise HTTPException(status_code=403, detail="CSRF validation failed") from error

    def current_csrf(cookie_value: str | None) -> str | None:
        _user, session = session_user(cookie_value)
        return session.csrf_token if session is not None else None

    def can_read_subscription(subscription: Subscription, identity: UserRecord | None) -> bool:
        if identity is None:
            return subscription.owner_user_id is None
        if identity.role == "admin":
            return True
        return subscription.owner_user_id == identity.id

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def dashboard(
        request: Request,
        chatevent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    ) -> str:
        if admin_required() and resolve_identity(None, chatevent_session)[0] is None:
            return render_login_page(request)
        return DASHBOARD_HTML

    @app.post("/api/login", response_model=SessionStatus)
    def login(
        payload: LoginRequest,
        request: Request,
        response: Response,
        x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
        chatevent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    ) -> SessionStatus:
        previous_user, previous_session = session_user(chatevent_session)
        if previous_session is not None:
            try:
                require_csrf(previous_session, x_csrf_token)
            except AccessDenied as error:
                raise HTTPException(status_code=403, detail="CSRF validation failed") from error
        principal = backend.authenticate(payload.username, payload.password)
        if principal is None or principal.user_id is None:
            raise HTTPException(status_code=401, detail="invalid username or password")
        user = store.get_user(principal.user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="invalid username or password")
        try:
            issued = session_manager.issue(
                principal,
                previous_token=chatevent_session if previous_user is not None else None,
            )
        except StoreFull as error:
            raise HTTPException(status_code=503, detail="session capacity exhausted") from error
        response.set_cookie(
            SESSION_COOKIE,
            issued.token,
            httponly=True,
            samesite="lax",
            max_age=session_ttl,
            secure=_secure_cookie(),
        )
        return SessionStatus(
            admin_required=admin_required(),
            authenticated=True,
            user=user,
            legacy_admin=False,
            csrf_token=issued.session.csrf_token,
            next=_safe_next_for_request(request, payload.next),
        )

    @app.post("/api/logout", response_model=SessionStatus)
    def logout(
        response: Response,
        x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
        chatevent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    ) -> SessionStatus:
        if chatevent_session:
            _user, session = session_user(chatevent_session)
            if session is not None:
                try:
                    require_csrf(session, x_csrf_token)
                except AccessDenied as error:
                    raise HTTPException(status_code=403, detail="CSRF validation failed") from error
            session_manager.revoke(chatevent_session)
        response.delete_cookie(SESSION_COOKIE)
        return SessionStatus(admin_required=admin_required(), authenticated=False)

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
        chatevent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    ) -> SessionStatus:
        identity, legacy, _source = resolve_identity(x_chatevent_admin_token, chatevent_session)
        csrf = current_csrf(chatevent_session) if identity is not None and not legacy else None
        return SessionStatus(
            admin_required=admin_required(),
            authenticated=identity is not None,
            user=identity,
            legacy_admin=legacy,
            csrf_token=csrf,
        )

    @app.get("/login", response_class=HTMLResponse, include_in_schema=False)
    def login_page(request: Request, next: str | None = None) -> str:
        return render_login_page(request, next=next)

    @app.get("/login/assets/{name}", include_in_schema=False)
    def login_asset(name: str) -> Response:
        content_types = {
            "login.css": "text/css; charset=utf-8",
            "login.js": "application/javascript; charset=utf-8",
        }
        content_type = content_types.get(name)
        if content_type is None:
            raise HTTPException(status_code=404, detail="asset not found")
        data = (resources.files("chatlogin.web") / "assets" / name).read_bytes()
        return Response(data, media_type=content_type, headers={"Cache-Control": "public, max-age=3600"})

    def render_login_page(request: Request, next: str | None = None) -> str:
        prefix = str(request.scope.get("root_path", "") or "").rstrip("/")
        return login_ui.render(
            {
                "login_url": f"{prefix}/api/login",
                "session_url": f"{prefix}/api/session",
                "logout_url": f"{prefix}/api/logout",
                "assets_path": f"{prefix}/login/assets",
                "next": _safe_next_for_request(request, next),
            }
        )

    @app.get("/api/users", response_model=list[UserRecord])
    def list_users(
        x_chatevent_admin_token: str | None = Header(
            default=None, alias="X-ChatEvent-Admin-Token"
        ),
        chatevent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    ) -> list[UserRecord]:
        require_admin_token(x_chatevent_admin_token, chatevent_session)
        return store.list_users()

    @app.post("/api/users", response_model=UserCreateResult, status_code=201)
    def create_user(
        payload: UserCreate,
        x_chatevent_admin_token: str | None = Header(
            default=None, alias="X-ChatEvent-Admin-Token"
        ),
        x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
        chatevent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    ) -> UserCreateResult:
        _admin, source = require_admin_token(x_chatevent_admin_token, chatevent_session)
        require_write_csrf(source, chatevent_session, x_csrf_token)
        user = store.save_user(
            UserRecord(
                username=payload.username,
                display_name=payload.display_name,
                role=payload.role,
                enabled=payload.enabled,
            ),
            password_hash=password_digest(payload.password),
        )
        return UserCreateResult(user=user)

    @app.post("/api/me/token", response_model=UserTokenResult)
    def create_my_token(
        x_chatevent_admin_token: str | None = Header(
            default=None, alias="X-ChatEvent-Admin-Token"
        ),
        x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
        chatevent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    ) -> UserTokenResult:
        identity, source = require_authenticated(x_chatevent_admin_token, chatevent_session)
        require_write_csrf(source, chatevent_session, x_csrf_token)
        if identity.id in {"bootstrap-admin", "local-admin"}:
            raise HTTPException(status_code=409, detail="create a real user before issuing API tokens")
        token = generate_arch_token()
        user = store.save_user(identity, token_hash=token_digest(token))
        return UserTokenResult(user=user, token=token)

    @app.post("/api/users/{user_id}/token", response_model=UserTokenResult)
    def create_user_token(
        user_id: str,
        x_chatevent_admin_token: str | None = Header(
            default=None, alias="X-ChatEvent-Admin-Token"
        ),
        x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
        chatevent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    ) -> UserTokenResult:
        admin, source = require_admin_token(x_chatevent_admin_token, chatevent_session)
        require_write_csrf(source, chatevent_session, x_csrf_token)
        target = store.get_user(user_id)
        if target is None:
            raise HTTPException(status_code=404, detail="user not found")
        if admin.role != "admin" and admin.id != target.id:
            raise HTTPException(status_code=403, detail="cannot issue token for another user")
        token = generate_arch_token()
        user = store.save_user(target, token_hash=token_digest(token))
        return UserTokenResult(user=user, token=token)

    @app.delete("/api/users/{user_id}", response_model=DeleteResult)
    def delete_user(
        user_id: str,
        x_chatevent_admin_token: str | None = Header(
            default=None, alias="X-ChatEvent-Admin-Token"
        ),
        x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
        chatevent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    ) -> DeleteResult:
        _admin, source = require_admin_token(x_chatevent_admin_token, chatevent_session)
        require_write_csrf(source, chatevent_session, x_csrf_token)
        deleted = store.delete_user(user_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="user not found")
        return DeleteResult(deleted=True, id=user_id)

    @app.get("/api/schema/event")
    def event_schema(
        x_chatevent_admin_token: str | None = Header(
            default=None, alias="X-ChatEvent-Admin-Token"
        ),
        chatevent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    ) -> dict[str, Any]:
        require_authenticated(x_chatevent_admin_token, chatevent_session)
        return ChatEvent.model_json_schema()

    @app.get("/api/schema/subscription")
    def subscription_schema(
        x_chatevent_admin_token: str | None = Header(
            default=None, alias="X-ChatEvent-Admin-Token"
        ),
        chatevent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    ) -> dict[str, Any]:
        require_authenticated(x_chatevent_admin_token, chatevent_session)
        return Subscription.model_json_schema()

    @app.get("/api/platforms", response_model=PlatformPage)
    def list_platforms(
        x_chatevent_admin_token: str | None = Header(
            default=None, alias="X-ChatEvent-Admin-Token"
        ),
        chatevent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    ) -> PlatformPage:
        require_authenticated(x_chatevent_admin_token, chatevent_session)
        items = list(list_platform_specs())
        return PlatformPage(items=items, count=len(items))

    @app.post("/api/subscriptions", response_model=Subscription, status_code=201)
    def save_subscription(
        subscription: Subscription,
        x_chatevent_admin_token: str | None = Header(
            default=None, alias="X-ChatEvent-Admin-Token"
        ),
        x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
        chatevent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    ) -> Subscription:
        identity, source = require_authenticated(x_chatevent_admin_token, chatevent_session)
        require_write_csrf(source, chatevent_session, x_csrf_token)
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
        chatevent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    ) -> list[Subscription]:
        identity, _source = require_authenticated(x_chatevent_admin_token, chatevent_session)
        items = store.list_subscriptions(enabled=enabled)
        return [item for item in items if can_read_subscription(item, identity)]

    @app.get("/api/subscriptions/{subscription_id}", response_model=Subscription)
    def get_subscription(
        subscription_id: str,
        x_chatevent_admin_token: str | None = Header(
            default=None, alias="X-ChatEvent-Admin-Token"
        ),
        chatevent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    ) -> Subscription:
        identity, _source = require_authenticated(x_chatevent_admin_token, chatevent_session)
        subscription = store.get_subscription(subscription_id)
        if subscription is None or not can_read_subscription(subscription, identity):
            raise HTTPException(status_code=404, detail="subscription not found")
        return subscription

    @app.delete("/api/subscriptions/{subscription_id}", response_model=DeleteResult)
    def delete_subscription(
        subscription_id: str,
        x_chatevent_admin_token: str | None = Header(
            default=None, alias="X-ChatEvent-Admin-Token"
        ),
        x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
        chatevent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    ) -> DeleteResult:
        identity, source = require_authenticated(x_chatevent_admin_token, chatevent_session)
        require_write_csrf(source, chatevent_session, x_csrf_token)
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
        x_chatevent_admin_token: str | None = Header(
            default=None, alias="X-ChatEvent-Admin-Token"
        ),
        chatevent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    ) -> EventPage:
        require_authenticated(x_chatevent_admin_token, chatevent_session)
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
    def get_event(
        dedupe_key: str,
        x_chatevent_admin_token: str | None = Header(
            default=None, alias="X-ChatEvent-Admin-Token"
        ),
        chatevent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    ) -> StoredEvent:
        require_authenticated(x_chatevent_admin_token, chatevent_session)
        event = store.get_event(dedupe_key)
        if event is None:
            raise HTTPException(status_code=404, detail="event not found")
        return event

    @app.get("/api/stats")
    def stats(
        x_chatevent_admin_token: str | None = Header(
            default=None, alias="X-ChatEvent-Admin-Token"
        ),
        chatevent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    ) -> dict[str, Any]:
        require_authenticated(x_chatevent_admin_token, chatevent_session)
        return store.stats()

    return app
