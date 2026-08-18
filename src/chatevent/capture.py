"""Official platform capture helpers used by the ChatEvent CLI."""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

from .adapters import normalize_zulip_message_event
from .model import ChatEvent
from .store import EventStore


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
    env_path = Path(path).expanduser()
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        result[key.strip()] = value
    return result


def _api_url(base_url: str, path: str, query: dict[str, Any] | None = None) -> str:
    url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    if query:
        url += "?" + urlencode(query, doseq=True)
    return url


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
