"""Official platform capture helpers used by the ChatEvent CLI."""

from __future__ import annotations

import base64
import html
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode, urljoin
from urllib.request import Request, urlopen

from .adapters import normalize_voice_talk, normalize_x_post, normalize_zulip_message_event
from .model import CaptureMode, ChatEvent
from .store import EventStore
from .subscription import Subscription, temporary_zulip_topic_watch


@dataclass(frozen=True)
class CaptureSummary:
    """Result returned by one bounded capture pass."""

    source: str
    captured: int
    created: int
    events: list[str]
    database: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "captured": self.captured,
            "created": self.created,
            "events": self.events,
            "database": self.database,
        }


def load_env_file(path: str | Path) -> dict[str, str]:
    """Load KEY=VALUE lines without printing or exporting secrets."""

    result: dict[str, str] = {}
    context = dict(os.environ)
    env_path = Path(path).expanduser()
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        value = re.sub(
            r"\$(?:\{(?P<braced>[A-Za-z_][A-Za-z0-9_]*)\}|(?P<bare>[A-Za-z_][A-Za-z0-9_]*))",
            lambda match: context.get(match.group("braced") or match.group("bare"), ""),
            value,
        )
        normalized_key = key.strip()
        result[normalized_key] = value
        context[normalized_key] = value
    return result


def load_proxy_env_file(path: str | Path) -> dict[str, str]:
    """Load only proxy-related variables from an env file."""

    allowed = {"all_proxy", "http_proxy", "https_proxy", "no_proxy"}
    env = load_env_file(path)
    return {key: value for key, value in env.items() if key.lower() in allowed}


def apply_proxy_env_file(path: str | Path | None) -> None:
    """Apply proxy env vars without printing or persisting their values."""

    if path is None:
        return
    for key, value in load_proxy_env_file(path).items():
        os.environ[key] = value


def _default_voice_env_file() -> Path | None:
    configured = os.environ.get("CHATEVENT_VOICE_ENV_FILE") or os.environ.get("CHATVOICE_ENV_FILE")
    if configured:
        return Path(configured).expanduser()
    for directory in (Path.cwd(), *Path.cwd().parents):
        env_path = directory / ".env"
        if env_path.exists():
            return env_path
    return None


def load_voice_env_file(path: str | Path | None = None) -> dict[str, str]:
    """Load ChatVoice connection settings from an env file plus process env."""

    loaded: dict[str, str] = {}
    env_path = Path(path).expanduser() if path is not None else _default_voice_env_file()
    if env_path is not None and env_path.exists():
        loaded.update(load_env_file(env_path))
    for key in ("CHATVOICE_BASE_URL", "CHATVOICE_DATA_READ"):
        if os.environ.get(key):
            loaded[key] = os.environ[key]
    return loaded


def _api_url(base_url: str, path: str, query: dict[str, Any] | None = None) -> str:
    url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    if query:
        url += "?" + urlencode({key: _form_value(value) for key, value in query.items()})
    return url


def _read_json_api(
    base_url: str,
    path: str,
    *,
    bearer_token: str,
    timeout: float = 10,
) -> dict[str, Any]:
    request = Request(
        _api_url(base_url, path),
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {bearer_token}",
            "User-Agent": "ChatEvent/0.2 voice metadata capture",
        },
        method="GET",
    )
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - user-configured service URL
        return json.loads(response.read().decode("utf-8"))


def fetch_voice_talks(
    *,
    env_file: str | Path | None = None,
    base_url: str | None = None,
    token_env: str = "CHATVOICE_DATA_READ",
    timeout_seconds: float = 10,
) -> list[dict[str, Any]]:
    """Fetch metadata-only ChatVoice talks from the authorized list endpoint."""

    env = load_voice_env_file(env_file)
    resolved_base_url = base_url or env.get("CHATVOICE_BASE_URL") or "http://127.0.0.1:18087"
    token = os.environ.get(token_env) or env.get(token_env)
    if not token:
        raise RuntimeError(f"missing ChatVoice API token env {token_env}")
    payload = _read_json_api(
        resolved_base_url,
        "/api/data/meetings",
        bearer_token=token,
        timeout=timeout_seconds,
    )
    meetings = payload.get("meetings")
    if not isinstance(meetings, list):
        raise RuntimeError("ChatVoice meetings response did not include a meetings list")
    return [meeting for meeting in meetings if isinstance(meeting, dict)]


def _parse_since_cursor(value: str | None) -> datetime | None:
    if value is None or not value.strip():
        return None
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("--since must include timezone information")
    return parsed.astimezone(timezone.utc)


def _voice_timestamp(raw: dict[str, Any], key: str) -> datetime | None:
    value = raw.get(key)
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _voice_talk_id(raw: dict[str, Any]) -> str | None:
    value = raw.get("talk_id") or raw.get("meeting_id") or raw.get("id")
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _voice_tag_snapshot(value: Any) -> tuple[str, ...]:
    if isinstance(value, list):
        tags = [str(tag).strip() for tag in value]
    elif isinstance(value, str):
        tags = [tag.strip() for tag in value.split(",")]
    else:
        tags = []
    return tuple(sorted(dict.fromkeys(tag for tag in tags if tag)))


def _voice_tags_changed(store: EventStore, talk: dict[str, Any]) -> bool:
    talk_id = _voice_talk_id(talk)
    if talk_id is None:
        return False
    previous = store.latest_event_for_subject(
        source="voice",
        subject_id=f"talk:{talk_id}",
    )
    if previous is None:
        return False
    return _voice_tag_snapshot(talk.get("tags")) != _voice_tag_snapshot(
        previous.event.payload.get("tags")
    )


def _record_voice_talks(
    *,
    db_path: str | Path,
    talks: list[dict[str, Any]],
    subscription_id: str | None,
    capture_mode: CaptureMode,
    since: datetime | None = None,
    backfill: bool = False,
    limit: int | None = None,
) -> CaptureSummary:
    store = EventStore(db_path)
    if subscription_id:
        _ensure_voice_subscription(store, subscription_id)
    captured: list[ChatEvent] = []
    created = 0
    max_items = len(talks) if limit is None else max(0, limit)
    for talk in talks[:max_items]:
        created_at = _voice_timestamp(talk, "created_at")
        updated_at = _voice_timestamp(talk, "updated_at") or created_at
        if backfill:
            kind = "talk.created"
        else:
            tags_changed = _voice_tags_changed(store, talk)
            if since is not None and updated_at is not None and updated_at <= since and not tags_changed:
                continue
            kind = "talk.created" if since is not None and created_at is not None and created_at > since else "talk.updated"
        event = normalize_voice_talk(
            talk,
            kind=kind,
            subscription_id=subscription_id,
            capture_mode=capture_mode,
        )
        _, was_created = store.record_event(event)
        created += int(was_created)
        captured.append(event)
    return CaptureSummary(
        source="voice",
        captured=len(captured),
        created=created,
        events=[event.dedupe_key for event in captured],
        database=str(store.path),
    )


def _ensure_voice_subscription(store: EventStore, subscription_id: str) -> Subscription:
    """Ensure voice captures with a subscription id have a visible subscription row."""

    existing = store.get_subscription(subscription_id)
    if existing is not None:
        if existing.source != "voice":
            raise RuntimeError(
                f"subscription {subscription_id!r} exists for source {existing.source!r}, not 'voice'"
            )
        return existing
    subscription = Subscription(
        id=subscription_id,
        source="voice",
        target="account:default",
        label="Default ChatVoice talks",
        event_kinds=["talk.created", "talk.updated"],
        capture_modes=[
            CaptureMode.MANUAL_BACKFILL,
            CaptureMode.POLL,
            CaptureMode.API_CURSOR,
        ],
        filters={"account": "default"},
        labels=["voice", "chatvoice"],
        metadata={"integration": "chatvoice", "content_policy": "metadata-only"},
    )
    return store.save_subscription(subscription)


def capture_voice_backfill(
    *,
    db_path: str | Path,
    env_file: str | Path | None = None,
    base_url: str | None = None,
    token_env: str = "CHATVOICE_DATA_READ",
    all_talks: bool = False,
    limit: int | None = None,
    timeout_seconds: float = 10,
    subscription_id: str | None = "voice-default",
) -> CaptureSummary:
    """Backfill current/default ChatVoice talks as metadata-only created events."""

    if not all_talks and limit is None:
        raise RuntimeError("voice-backfill requires --all or --limit")
    talks = fetch_voice_talks(
        env_file=env_file,
        base_url=base_url,
        token_env=token_env,
        timeout_seconds=timeout_seconds,
    )
    return _record_voice_talks(
        db_path=db_path,
        talks=talks,
        subscription_id=subscription_id,
        capture_mode=CaptureMode.MANUAL_BACKFILL,
        backfill=True,
        limit=None if all_talks else limit,
    )


def capture_voice_once(
    *,
    db_path: str | Path,
    env_file: str | Path | None = None,
    base_url: str | None = None,
    token_env: str = "CHATVOICE_DATA_READ",
    since: str | None = None,
    limit: int | None = None,
    timeout_seconds: float = 10,
    subscription_id: str | None = "voice-default",
) -> CaptureSummary:
    """Capture one incremental ChatVoice metadata poll using an optional cursor."""

    talks = fetch_voice_talks(
        env_file=env_file,
        base_url=base_url,
        token_env=token_env,
        timeout_seconds=timeout_seconds,
    )
    return _record_voice_talks(
        db_path=db_path,
        talks=talks,
        subscription_id=subscription_id,
        capture_mode=CaptureMode.POLL if since is None else CaptureMode.API_CURSOR,
        since=_parse_since_cursor(since),
        backfill=False,
        limit=limit,
    )


_X_HANDLE = re.compile(r"^[A-Za-z0-9_]{1,15}$")
_X_STATUS_URL = re.compile(
    r"https?://(?:www\.)?(?:x|twitter)\.com/(?P<handle>[A-Za-z0-9_]{1,15})/status/(?P<status_id>\d+)"
)
_X_ISO_TIMESTAMP = re.compile(r"\b20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z\b")


def _read_text_url(url: str, *, timeout: float = 15) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": "ChatEvent/0.2 public web capture (+https://github.com/ChatArch/ChatEvent)",
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
        },
        method="GET",
    )
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - user-supplied public URL
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def normalize_x_handle(handle: str) -> str:
    """Validate and normalize an X handle without the leading ``@``."""

    normalized = handle.strip().removeprefix("@").strip()
    if not _X_HANDLE.fullmatch(normalized):
        raise ValueError("X handle must contain 1-15 letters, numbers, or underscores")
    return normalized


def parse_x_status_url(url: str) -> tuple[str, str]:
    """Return ``(handle, status_id)`` from a public X/Twitter status URL."""

    match = _X_STATUS_URL.search(url.strip())
    if match is None:
        raise ValueError("expected X status URL like https://x.com/<handle>/status/<id>")
    return normalize_x_handle(match.group("handle")), match.group("status_id")


def canonical_x_status_url(handle: str, status_id: str) -> str:
    return f"https://x.com/{normalize_x_handle(handle)}/status/{status_id}"


def _plain_oembed_html(value: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", value))
    return re.sub(r"\s+", " ", text).strip()


def _strip_oembed_attribution(text: str, *, author_name: str | None, handle: str) -> str:
    if not text:
        return text
    escaped_handle = re.escape(handle)
    if author_name:
        escaped_author = re.escape(author_name)
        text = re.sub(
            rf"\s+—\s+{escaped_author}\s+\(@{escaped_handle}\)\s+.+$",
            "",
            text,
        )
    return text.strip()


def extract_x_status_ids_from_user_html(html_text: str, handle: str) -> list[str]:
    """Extract visible status IDs for ``handle`` from public X profile HTML."""

    handle = normalize_x_handle(handle)
    patterns = [
        rf"https://(?:www\.)?(?:x|twitter)\.com/{re.escape(handle)}/status/(\d+)",
        rf"/{re.escape(handle)}/status/(\d+)",
        rf"%2F{re.escape(handle)}%2Fstatus%2F(\d+)",
    ]
    matches: list[tuple[int, str]] = []
    for pattern in patterns:
        for match in re.finditer(pattern, html_text, flags=re.IGNORECASE):
            matches.append((match.start(), match.group(1)))
    ids: list[str] = []
    for _position, status_id in sorted(matches):
        if status_id not in ids:
            ids.append(status_id)
    return ids


def extract_x_status_created_at(html_text: str, status_id: str) -> str | None:
    """Extract the most likely exact UTC creation timestamp from a status page."""

    positions = [match.start() for match in re.finditer(re.escape(status_id), html_text)]
    windows = [html_text[max(0, pos - 8000) : pos + 8000] for pos in positions[:5]]
    windows.append(html_text)
    for window in windows:
        match = _X_ISO_TIMESTAMP.search(window)
        if match:
            return match.group(0)
    return None


def fetch_x_status_payload(status_url: str, *, timeout: float = 15) -> dict[str, Any]:
    """Fetch one public X status via oEmbed plus best-effort web enrichment."""

    handle, status_id = parse_x_status_url(status_url)
    canonical_url = canonical_x_status_url(handle, status_id)
    oembed_url = "https://publish.twitter.com/oembed?omit_script=1&url=" + quote(
        canonical_url,
        safe=":/",
    )
    oembed_text = _read_text_url(oembed_url, timeout=timeout)
    oembed = json.loads(oembed_text)
    author_name = oembed.get("author_name") if isinstance(oembed, dict) else None
    author_url = oembed.get("author_url") if isinstance(oembed, dict) else None
    if isinstance(author_url, str):
        try:
            handle = normalize_x_handle(author_url.rstrip("/").rsplit("/", 1)[-1])
        except ValueError:
            pass
    rendered_text = _plain_oembed_html(str(oembed.get("html") or "")) if isinstance(oembed, dict) else ""
    content = _strip_oembed_attribution(rendered_text, author_name=author_name, handle=handle)

    web_error: str | None = None
    created_at = None
    try:
        page_html = _read_text_url(canonical_url, timeout=timeout)
        created_at = extract_x_status_created_at(page_html, status_id)
    except Exception as error:  # best-effort timestamp enrichment
        web_error = type(error).__name__

    return {
        "status_id": status_id,
        "status_url": canonical_url,
        "author_handle": handle,
        "author_name": author_name or "",
        "author_url": author_url or f"https://x.com/{handle}",
        "text": content,
        "created_at": created_at,
        "timestamp_source": "x-web-html" if created_at else "capture-time",
        "acquisition": "x-web-url",
        "oembed": oembed,
        "web_error": web_error,
    }


def fetch_x_user_status_urls(
    handle: str,
    *,
    limit: int = 5,
    timeout: float = 15,
) -> list[str]:
    """Fetch one public X user page and return latest status URLs found in HTML."""

    handle = normalize_x_handle(handle)
    html_text = _read_text_url(f"https://x.com/{handle}", timeout=timeout)
    status_ids = extract_x_status_ids_from_user_html(html_text, handle)
    return [canonical_x_status_url(handle, status_id) for status_id in status_ids[: max(1, limit)]]


def _record_x_statuses(
    *,
    db_path: str | Path,
    status_urls: list[str],
    subscription_id: str | None,
    capture_mode: CaptureMode,
    timeout_seconds: float,
    occurred_since: datetime | None = None,
) -> CaptureSummary:
    store = EventStore(db_path)
    captured: list[ChatEvent] = []
    created = 0
    for status_url in status_urls:
        payload = fetch_x_status_payload(status_url, timeout=timeout_seconds)
        event = normalize_x_post(
            payload,
            subscription_id=subscription_id,
            capture_mode=capture_mode,
        )
        if occurred_since is not None and event.occurred_at < occurred_since:
            continue
        _, was_created = store.record_event(event)
        created += int(was_created)
        captured.append(event)
    return CaptureSummary(
        source="x",
        captured=len(captured),
        created=created,
        events=[event.dedupe_key for event in captured],
        database=str(store.path),
    )


def capture_x_status_once(
    *,
    db_path: str | Path,
    url: str,
    subscription_id: str | None = None,
    timeout_seconds: float = 15,
    proxy_env_file: str | Path | None = None,
) -> CaptureSummary:
    """Capture one known public X status URL and store it as ``post.created``."""

    apply_proxy_env_file(proxy_env_file)
    return _record_x_statuses(
        db_path=db_path,
        status_urls=[url],
        subscription_id=subscription_id,
        capture_mode=CaptureMode.MANUAL_BACKFILL,
        timeout_seconds=timeout_seconds,
    )


def capture_x_user_once(
    *,
    db_path: str | Path,
    handle: str,
    limit: int = 5,
    days: int | None = None,
    subscription_id: str | None = None,
    timeout_seconds: float = 15,
    proxy_env_file: str | Path | None = None,
) -> CaptureSummary:
    """Capture recent public posts found on one X user's web profile page."""

    apply_proxy_env_file(proxy_env_file)
    status_urls = fetch_x_user_status_urls(handle, limit=limit, timeout=timeout_seconds)
    occurred_since = None
    if days is not None:
        occurred_since = datetime.now(timezone.utc) - timedelta(days=max(0, days))
    return _record_x_statuses(
        db_path=db_path,
        status_urls=status_urls,
        subscription_id=subscription_id or f"x-user-{normalize_x_handle(handle)}",
        capture_mode=CaptureMode.POLL,
        timeout_seconds=timeout_seconds,
        occurred_since=occurred_since,
    )


def _form_value(value: Any) -> str:
    """Encode Zulip form values with JSON-compatible booleans/lists/dicts."""

    if isinstance(value, bool | list | dict):
        return json.dumps(value)
    return str(value)


def _zulip_request(
    env: dict[str, str],
    method: str,
    path: str,
    *,
    data: dict[str, Any] | None = None,
    query: dict[str, Any] | None = None,
    timeout: float = 15,
) -> dict[str, Any]:
    site = env.get("ZULIP_SITE") or env.get("ZULIP_BASE_URL")
    email = env.get("ZULIP_BOT_EMAIL") or env.get("ZULIP_ACTOR_EMAIL")
    api_key = env.get("ZULIP_BOT_API_KEY") or env.get("ZULIP_ACTOR_API_KEY")
    if not (site and email and api_key):
        raise RuntimeError(
            "Zulip env file must contain ZULIP_SITE/ZULIP_BOT_EMAIL/ZULIP_BOT_API_KEY "
            "or ChatRSS-compatible ZULIP_BASE_URL/ZULIP_ACTOR_EMAIL/ZULIP_ACTOR_API_KEY"
        )
    encoded = base64.b64encode(f"{email}:{api_key}".encode()).decode()
    body = None
    headers = {"Authorization": f"Basic {encoded}"}
    if data is not None:
        body = urlencode({key: _form_value(value) for key, value in data.items()}).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = Request(
        _api_url(site, path, query),
        data=body,
        headers=headers,
        method=method,
    )
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - user-configured platform URL
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("result") not in {None, "success"}:
        raise RuntimeError(payload.get("msg") or payload)
    return payload


def _matches_zulip_message(
    event: dict[str, Any], *, stream: str | None, topic: str | None, message_id: int | None
) -> bool:
    message = event.get("message")
    if not isinstance(message, dict):
        return False
    if message_id is not None and message.get("id") != message_id:
        return False
    if stream and message.get("display_recipient") != stream:
        return False
    if topic and (message.get("topic") or message.get("subject")) != topic:
        return False
    return True


def _zulip_topic_scope(subscription: Subscription) -> tuple[str, str]:
    if subscription.source != "zulip":
        raise RuntimeError(
            f"subscription {subscription.id!r} exists for source {subscription.source!r}, not 'zulip'"
        )
    stream = subscription.filters.get("stream")
    topic = subscription.filters.get("topic")
    if isinstance(stream, str) and isinstance(topic, str) and stream.strip() and topic.strip():
        return stream.strip(), topic.strip()
    scope = subscription.scope
    if scope is not None and scope.type == "zulip_topic":
        parent = scope.parent
        if parent is not None and parent.type == "zulip_stream":
            return parent.key, scope.display or scope.key.rsplit("/", 1)[-1]
    raise RuntimeError(
        f"subscription {subscription.id!r} must define Zulip stream/topic platform filters"
    )


def create_temporary_zulip_topic_watch(
    *,
    db_path: str | Path,
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
    """Create or update a temporary Zulip topic watch in the event store."""

    store = EventStore(db_path)
    return store.save_subscription(
        temporary_zulip_topic_watch(
            stream=stream,
            topic=topic,
            assignment_id=assignment_id,
            interval_seconds=interval_seconds,
            expires_at=expires_at,
            ttl_seconds=ttl_seconds,
            hot_until=hot_until,
            reason=reason,
            subscription_id=subscription_id,
            owner_user_id=owner_user_id,
        )
    )


def _fetch_zulip_topic_messages(
    env: dict[str, str],
    *,
    stream: str,
    topic: str,
    last_cursor: str | None,
    limit: int,
    timeout: float,
) -> list[dict[str, Any]]:
    narrow = [
        {"operator": "stream", "operand": stream},
        {"operator": "topic", "operand": topic},
    ]
    query: dict[str, Any] = {
        "anchor": last_cursor or "oldest",
        "num_before": 0,
        "num_after": max(1, limit),
        "narrow": narrow,
        "apply_markdown": False,
    }
    payload = _zulip_request(
        env,
        "GET",
        "/api/v1/messages",
        query=query,
        timeout=timeout,
    )
    messages = payload.get("messages")
    if not isinstance(messages, list):
        raise RuntimeError("Zulip messages response did not include a messages list")
    result: list[dict[str, Any]] = []
    cursor_id = int(last_cursor) if last_cursor and last_cursor.isdigit() else None
    for message in messages:
        if not isinstance(message, dict):
            continue
        message_id = message.get("id")
        if cursor_id is not None:
            try:
                if int(message_id) <= cursor_id:
                    continue
            except (TypeError, ValueError):
                pass
        result.append(message)
    return result


def capture_zulip_once(
    *,
    db_path: str | Path,
    env_file: str | Path,
    stream: str | None = None,
    topic: str | None = None,
    content: str | None = None,
    timeout_seconds: float = 10,
    subscription_id: str | None = "zulip-practice",
) -> CaptureSummary:
    """Capture one bounded Zulip event-queue pass and store matching messages.

    This uses Zulip's official event queue.  If ``content`` is provided, the
    helper first sends a stream message through the official ``/messages`` API,
    then waits for that exact message id to arrive via ``/events``.
    """

    env = load_env_file(env_file)
    if stream is None:
        stream = (env.get("ZULIP_NEWS_STREAMS") or "").split(",")[0].strip() or None
    if topic is None:
        topic = (env.get("ZULIP_NEWS_TOPICS") or "").split(",")[0].strip() or None
    if content and not (stream and topic):
        raise RuntimeError("--stream and --topic are required when emitting a Zulip test message")

    register = _zulip_request(
        env,
        "POST",
        "/api/v1/register",
        data={"event_types": ["message"], "apply_markdown": False},
        timeout=timeout_seconds,
    )
    queue_id = register.get("queue_id")
    last_event_id = register.get("last_event_id", -1)
    if not queue_id:
        raise RuntimeError("Zulip register response did not include queue_id")

    emitted_message_id: int | None = None
    if content:
        sent = _zulip_request(
            env,
            "POST",
            "/api/v1/messages",
            data={"type": "stream", "to": stream, "topic": topic, "content": content},
            timeout=timeout_seconds,
        )
        emitted_message_id = int(sent["id"])

    store = EventStore(db_path)
    captured: list[ChatEvent] = []
    created = 0
    deadline = time.time() + timeout_seconds
    try:
        while time.time() < deadline:
            poll = _zulip_request(
                env,
                "GET",
                "/api/v1/events",
                query={
                    "queue_id": queue_id,
                    "last_event_id": last_event_id,
                    "dont_block": "false",
                },
                timeout=min(8, max(1, deadline - time.time())),
            )
            events = poll.get("events") or []
            for raw_event in events:
                if isinstance(raw_event, dict) and "id" in raw_event:
                    last_event_id = raw_event["id"]
                if not isinstance(raw_event, dict) or raw_event.get("type") != "message":
                    continue
                if not _matches_zulip_message(
                    raw_event,
                    stream=stream,
                    topic=topic,
                    message_id=emitted_message_id,
                ):
                    continue
                event = normalize_zulip_message_event(
                    raw_event,
                    subscription_id=subscription_id,
                    site_url=env.get("ZULIP_SITE") or env.get("ZULIP_BASE_URL"),
                )
                _, was_created = store.record_event(event)
                created += int(was_created)
                captured.append(event)
            if emitted_message_id is not None and captured:
                break
            if not events:
                time.sleep(0.25)
    finally:
        try:
            _zulip_request(env, "DELETE", "/api/v1/events", query={"queue_id": queue_id}, timeout=3)
        except Exception:
            pass

    return CaptureSummary(
        source="zulip",
        captured=len(captured),
        created=created,
        events=[event.dedupe_key for event in captured],
        database=str(EventStore(db_path).path),
    )


def capture_zulip_subscription_once(
    *,
    db_path: str | Path,
    env_file: str | Path,
    subscription_id: str,
    limit: int = 50,
    timeout_seconds: float = 10,
) -> CaptureSummary:
    """Poll one Zulip topic subscription with a durable message-id cursor."""

    store = EventStore(db_path)
    subscription = store.get_subscription(subscription_id)
    if subscription is None:
        raise RuntimeError(f"subscription {subscription_id!r} not found")
    if not subscription.enabled:
        return CaptureSummary(
            source=subscription.source,
            captured=0,
            created=0,
            events=[],
            database=str(store.path),
        )
    if subscription.is_expired():
        store.save_subscription(subscription.model_copy(update={"enabled": False}))
        return CaptureSummary(
            source=subscription.source,
            captured=0,
            created=0,
            events=[],
            database=str(store.path),
        )
    stream, topic = _zulip_topic_scope(subscription)
    env = load_env_file(env_file)
    messages = _fetch_zulip_topic_messages(
        env,
        stream=stream,
        topic=topic,
        last_cursor=subscription.last_cursor,
        limit=limit,
        timeout=timeout_seconds,
    )
    captured: list[ChatEvent] = []
    created = 0
    for message in messages:
        event = normalize_zulip_message_event(
            message,
            subscription_id=subscription.id,
            site_url=env.get("ZULIP_SITE") or env.get("ZULIP_BASE_URL"),
            capture_mode=CaptureMode.API_CURSOR,
            acquisition="zulip-messages-api",
        )
        _, was_created = store.record_event(event)
        created += int(was_created)
        captured.append(event)
    if not captured:
        store.save_subscription(subscription.model_copy(update={"last_error": None}))
    return CaptureSummary(
        source="zulip",
        captured=len(captured),
        created=created,
        events=[event.dedupe_key for event in captured],
        database=str(store.path),
    )


def capture_subscription_once(
    *,
    db_path: str | Path,
    env_file: str | Path,
    subscription_id: str,
    limit: int = 50,
    timeout_seconds: float = 10,
) -> CaptureSummary:
    """Run one bounded capture pass for a saved subscription."""

    store = EventStore(db_path)
    subscription = store.get_subscription(subscription_id)
    if subscription is None:
        raise RuntimeError(f"subscription {subscription_id!r} not found")
    if subscription.source == "zulip":
        return capture_zulip_subscription_once(
            db_path=db_path,
            env_file=env_file,
            subscription_id=subscription_id,
            limit=limit,
            timeout_seconds=timeout_seconds,
        )
    raise RuntimeError(f"subscription source {subscription.source!r} is not supported by this runner")
