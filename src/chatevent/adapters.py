"""Platform adapters that normalize official API/webhook payloads.

The functions in this module deliberately keep acquisition and normalization
separate.  Platform-specific clients may use official event queues, webhooks, or
incremental REST APIs to obtain raw payloads; these helpers map those payloads
into the stable :class:`chatevent.model.ChatEvent` envelope.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote, urljoin

from .model import (
    ActionDescriptor,
    ActorDescriptor,
    CaptureMode,
    CarrierTarget,
    ChatEvent,
    action_from_kind,
    utc_now,
)


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            raise ValueError("timestamp must include timezone information")
        return parsed.astimezone(timezone.utc)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("timestamp must include timezone information")
        return value.astimezone(timezone.utc)
    raise TypeError(f"unsupported timestamp type: {type(value).__name__}")


def _string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _join_url(base_url: str | None, path: str | None) -> str | None:
    if not path:
        return None
    if path.startswith(("http://", "https://")):
        return path
    if not base_url:
        return None
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def _action(kind: str, object_type: str) -> ActionDescriptor:
    return action_from_kind(kind, object_type=object_type)


def _actor(actor_id: str | None, *, display: str | None = None, role: str | None = None) -> ActorDescriptor | None:
    if not (actor_id or display or role):
        return None
    return ActorDescriptor(
        id=f"user:{actor_id}" if actor_id and not actor_id.startswith("user:") else actor_id,
        type="user" if actor_id or display else None,
        display=display,
        role=role.lower() if role else None,
    )


def _repo_target(repo_name: str, url: str | None = None) -> CarrierTarget:
    return CarrierTarget(type="repo", key=repo_name, display=repo_name, url=url)


def _x_user_target(handle: str, *, display: str | None = None) -> CarrierTarget:
    return CarrierTarget(
        type="x_user",
        key=handle,
        display=display or f"@{handle}",
        url=f"https://x.com/{handle}",
    )


def _x_post_target(
    *,
    status_id: str,
    handle: str,
    url: str,
    author_name: str | None = None,
) -> CarrierTarget:
    return CarrierTarget(
        type="x_post",
        key=status_id,
        display=f"@{handle} status {status_id}",
        url=url,
        parent=_x_user_target(handle, display=author_name or f"@{handle}"),
    )


def _voice_talk_target(*, talk_id: str, title: str | None, url: str | None = None) -> CarrierTarget:
    return CarrierTarget(
        type="voice_talk",
        key=talk_id,
        display=title or f"talk:{talk_id}",
        url=url,
        parent=CarrierTarget(type="voice_account", key="default", display="default"),
    )


def _voice_tags(raw: dict[str, Any]) -> list[str]:
    value = raw.get("tags")
    if isinstance(value, list):
        return list(dict.fromkeys(tag.strip() for tag in map(str, value) if tag.strip()))
    if isinstance(value, str):
        return list(dict.fromkeys(tag.strip() for tag in value.split(",") if tag.strip()))
    return []


def _presence_flag(raw: dict[str, Any], field: str, *fallback_fields: str) -> bool:
    value = raw.get(field)
    if isinstance(value, bool):
        return value
    for fallback in fallback_fields:
        fallback_value = raw.get(fallback)
        if isinstance(fallback_value, list):
            if fallback_value:
                return True
        elif isinstance(fallback_value, str):
            if fallback_value.strip():
                return True
        elif fallback_value is not None:
            return True
    return False


def _voice_metadata_fingerprint(
    *,
    title: str,
    tags: list[str],
    duration_seconds: int | None,
    summary_available: bool,
    transcript_available: bool,
) -> str:
    payload = {
        "duration_seconds": duration_seconds,
        "summary_available": summary_available,
        "tags": tags,
        "title": title,
        "transcript_available": transcript_available,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:12]


def normalize_voice_talk(
    raw: dict[str, Any],
    *,
    kind: str = "talk.created",
    subscription_id: str | None = None,
    capture_mode: CaptureMode = CaptureMode.POLL,
) -> ChatEvent:
    """Normalize one ChatVoice/Speakr talk metadata record.

    This adapter intentionally keeps only metadata. It does not copy previews,
    transcript segments, summary content, summary-chat messages, cookies, tokens,
    or any other conversational text into the ChatEvent payload or raw payload.
    """

    talk_id = _string(raw.get("talk_id") or raw.get("meeting_id") or raw.get("id"))
    if not talk_id:
        raise ValueError("voice talk payload requires id, meeting_id, or talk_id")
    if kind not in {"talk.created", "talk.updated"}:
        raise ValueError("voice talk kind must be talk.created or talk.updated")

    title = _string(raw.get("title")) or "Untitled talk"
    created_at = _parse_datetime(raw.get("created_at") or raw.get("occurred_at"))
    updated_at = _parse_datetime(raw.get("updated_at") or raw.get("created_at") or raw.get("occurred_at"))
    occurred_at = created_at if kind == "talk.created" else updated_at
    duration = raw.get("duration_seconds")
    try:
        duration_seconds = int(duration) if duration is not None else None
    except (TypeError, ValueError):
        duration_seconds = None
    tags = _voice_tags(raw)
    summary_available = _presence_flag(raw, "summary_available", "summary_title", "summary_content")
    transcript_available = _presence_flag(raw, "transcript_available", "transcript_segments", "preview")
    if kind == "talk.created":
        event_suffix = "created"
    else:
        fingerprint = _voice_metadata_fingerprint(
            title=title,
            tags=tags,
            duration_seconds=duration_seconds,
            summary_available=summary_available,
            transcript_available=transcript_available,
        )
        event_suffix = f"updated:{updated_at.isoformat()}:{fingerprint}"

    payload: dict[str, Any] = {
        "talk_id": talk_id,
        "title": title,
        "tags": tags,
        "created_at": created_at.isoformat(),
        "updated_at": updated_at.isoformat(),
        "summary_available": summary_available,
        "transcript_available": transcript_available,
    }
    if duration_seconds is not None:
        payload["duration_seconds"] = duration_seconds

    return ChatEvent(
        id=f"talk:{talk_id}:{event_suffix}",
        source="voice",
        kind=kind,
        occurred_at=occurred_at,
        capture_mode=capture_mode,
        subscription_id=subscription_id,
        action=_action(kind, "talk"),
        target=_voice_talk_target(talk_id=talk_id, title=title, url=_string(raw.get("url"))),
        conversation_id="account:default",
        subject_id=f"talk:{talk_id}",
        subject_type="talk",
        url=_string(raw.get("url")),
        cursor=updated_at.isoformat(),
        payload=payload,
        raw_payload=None,
        metadata={"acquisition": "chatvoice-data-api", "content_policy": "metadata-only"},
        tags=["voice", "talk", *tags],
    )


def normalize_x_post(
    raw: dict[str, Any],
    *,
    subscription_id: str | None = None,
    capture_mode: CaptureMode = CaptureMode.POLL,
) -> ChatEvent:
    """Normalize one public X/Twitter post payload into ``ChatEvent``.

    The acquisition layer may build ``raw`` from public oEmbed, X web HTML,
    official API data, or a logged-in browser backend.  The normalized event
    semantics stay stable: an observed user post is ``source=x`` and
    ``kind=post.created`` with the acquisition route recorded in metadata.
    """

    status_id = _string(raw.get("status_id") or raw.get("id"))
    handle = _string(raw.get("author_handle") or raw.get("handle"))
    status_url = _string(raw.get("status_url") or raw.get("url"))
    if not (status_id and handle and status_url):
        raise ValueError("X post payload requires status_id, author_handle, and status_url")

    author_name = _string(raw.get("author_name"))
    text = _string(raw.get("text") or raw.get("content")) or ""
    created_at = raw.get("created_at") or raw.get("occurred_at")
    occurred_at = _parse_datetime(created_at) if created_at else utc_now()
    acquisition = _string(raw.get("acquisition")) or "x-web-url"
    timestamp_source = _string(raw.get("timestamp_source")) or (
        "source-payload" if created_at else "capture-time"
    )

    return ChatEvent(
        id=f"post:{status_id}",
        source="x",
        kind="post.created",
        occurred_at=occurred_at,
        capture_mode=capture_mode,
        subscription_id=subscription_id,
        action=_action("post.created", "post"),
        target=_x_post_target(
            status_id=status_id,
            handle=handle,
            url=status_url,
            author_name=author_name,
        ),
        actor=ActorDescriptor(
            id=f"user:{handle}",
            type="user",
            display=author_name or f"@{handle}",
            role="author",
            metadata={"handle": handle},
        ),
        conversation_id=f"user:{handle}",
        subject_id=f"post:{status_id}",
        subject_type="post",
        url=status_url,
        cursor=status_id,
        payload={
            "title": f"X post by {author_name or '@' + handle}",
            "content": text,
            "author_name": author_name or "",
            "author_handle": handle,
            "status_id": status_id,
            "status_url": status_url,
            "created_at": occurred_at.isoformat(),
            "timestamp_source": timestamp_source,
        },
        raw_payload=raw,
        metadata={
            "acquisition": acquisition,
            "timestamp_source": timestamp_source,
        },
        tags=["x", "post", acquisition],
    )


def _zulip_message_target(
    *,
    message_id: str,
    stream_id: str | None,
    stream_name: str | None,
    topic: str | None,
    url: str | None,
) -> CarrierTarget:
    parent: CarrierTarget | None = None
    stream_key = stream_name or stream_id
    if stream_key:
        parent = CarrierTarget(
            type="zulip_stream",
            key=stream_key,
            display=stream_name or stream_key,
            metadata={"stream_id": stream_id} if stream_id else {},
        )
    if topic:
        topic_key = f"{stream_key}/{topic}" if stream_key else topic
        parent = CarrierTarget(type="zulip_topic", key=topic_key, display=topic, parent=parent)
    return CarrierTarget(type="message", key=message_id, display=f"message:{message_id}", url=url, parent=parent)


def _discourse_post_target(
    *,
    post_id: str,
    post_number: str | None,
    topic_id: str | None,
    title: str,
    url: str | None,
    topic_url: str | None = None,
) -> CarrierTarget:
    parent = (
        CarrierTarget(type="discourse_topic", key=topic_id, display=title, url=topic_url)
        if topic_id
        else None
    )
    return CarrierTarget(
        type="discourse_post",
        key=post_id,
        display=f"post #{post_number}" if post_number else f"post:{post_id}",
        url=url,
        parent=parent,
    )


def _issue_target(
    *,
    repo_name: str,
    number: str,
    url: str | None,
    title: str | None = None,
    target_type: str = "issue",
) -> CarrierTarget:
    label = "PR" if target_type == "pull_request" else "Issue"
    return CarrierTarget(
        type=target_type,
        key=f"{repo_name}#{number}",
        display=title or f"{label} #{number}",
        url=url,
        parent=_repo_target(repo_name),
    )


def _zulip_stream_name(message: dict[str, Any]) -> str | None:
    recipient = message.get("display_recipient")
    if isinstance(recipient, str):
        return recipient
    if isinstance(recipient, list):
        return ",".join(
            str(item.get("full_name") or item.get("email") or item.get("id"))
            for item in recipient
            if isinstance(item, dict)
        )
    return _string(message.get("stream"))


def _zulip_message_url(site_url: str | None, message: dict[str, Any]) -> str | None:
    if not site_url:
        return None
    stream = _zulip_stream_name(message)
    topic = _string(message.get("topic") or message.get("subject"))
    message_id = _string(message.get("id"))
    if not (stream and topic and message_id):
        return None
    return (
        site_url.rstrip("/")
        + "/#narrow/channel/"
        + quote(stream, safe="-._~")
        + "/topic/"
        + quote(topic, safe="-._~")
        + "/near/"
        + quote(message_id, safe="")
    )


def normalize_zulip_message_event(
    raw: dict[str, Any],
    *,
    subscription_id: str | None = None,
    site_url: str | None = None,
    capture_mode: CaptureMode = CaptureMode.EVENT_QUEUE,
    acquisition: str = "zulip-event-queue",
) -> ChatEvent:
    """Normalize a Zulip ``message`` event-queue payload into ``ChatEvent``.

    Zulip's preferred low-latency capture surface is the official event queue:
    ``POST /api/v1/register`` followed by ``GET /api/v1/events``.  This function
    accepts either one event from that queue or a bare message object returned by
    Zulip's message APIs.
    """

    message = raw.get("message") if isinstance(raw.get("message"), dict) else raw
    message_id = _string(message.get("id"))
    if not message_id:
        raise ValueError("Zulip message payload is missing id")
    topic = _string(message.get("topic") or message.get("subject"))
    stream_id = _string(message.get("stream_id"))
    stream_name = _zulip_stream_name(message)
    conversation_id = None
    if stream_id and topic:
        conversation_id = f"stream:{stream_id}/topic:{topic}"
    elif stream_name and topic:
        conversation_id = f"stream:{stream_name}/topic:{topic}"

    raw_event_id = _string(raw.get("id")) if raw is not message else None
    sender_id = _string(message.get("sender_id") or message.get("sender_email"))
    sender_email = _string(message.get("sender_email"))
    sender_full_name = _string(message.get("sender_full_name"))
    sender_realm_str = _string(message.get("sender_realm_str"))
    sender_is_bot = message.get("sender_is_bot")
    if not isinstance(sender_is_bot, bool):
        sender_is_bot = None
    source_timestamp = message.get("timestamp") or message.get("date_sent")
    occurred_at = _parse_datetime(source_timestamp) if source_timestamp is not None else utc_now()
    url = _zulip_message_url(site_url, message)
    actor_metadata: dict[str, Any] = {}
    if sender_email:
        actor_metadata["email"] = sender_email
    if sender_realm_str:
        actor_metadata["realm"] = sender_realm_str
    if sender_is_bot is not None:
        actor_metadata["is_bot"] = sender_is_bot

    return ChatEvent(
        id=f"message:{message_id}",
        source="zulip",
        kind="message.created",
        occurred_at=occurred_at,
        capture_mode=capture_mode,
        subscription_id=subscription_id,
        action=_action("message.created", "message"),
        target=_zulip_message_target(
            message_id=message_id,
            stream_id=stream_id,
            stream_name=stream_name,
            topic=topic,
            url=url,
        ),
        actor=ActorDescriptor(
            id=f"user:{sender_id}" if sender_id else None,
            type="user" if sender_id or sender_email or sender_full_name else None,
            display=sender_full_name or sender_email,
            role="bot" if sender_is_bot is True else "sender",
            metadata=actor_metadata,
        )
        if sender_id or sender_email or sender_full_name or sender_is_bot is not None
        else None,
        actor_id=f"user:{sender_id}" if sender_id else None,
        conversation_id=conversation_id,
        subject_id=f"message:{message_id}",
        subject_type="message",
        url=url,
        cursor=raw_event_id or message_id,
        payload={
            "title": topic or stream_name or "Zulip message",
            "content": message.get("content") or "",
            "sender": sender_full_name or sender_email or "",
            "sender_id": sender_id or "",
            "sender_email": sender_email or "",
            "sender_full_name": sender_full_name or "",
            "sender_is_bot": sender_is_bot if sender_is_bot is not None else False,
            "stream": stream_name or "",
            "topic": topic or "",
        },
        raw_payload=raw,
        metadata={
            "acquisition": acquisition,
            "content_policy": "topic-scoped-message-content",
            "timestamp_source": "source-payload" if message.get("timestamp") or message.get("date_sent") else "capture-time",
        },
        tags=["zulip", "message"],
    )


# Names from the official /api/get-events and /api/register-queue snapshots.
ZULIP_QUEUE_ACTION_KINDS = {
    "message": ("message.created",),
    "update_message": ("message.edited", "message.moved", "message.rendered", "message.updated"),
    "delete_message": ("message.deleted",),
    "reaction": ("reaction.added", "reaction.removed"),
    "stream": ("stream.created", "stream.updated", "stream.deleted"),
    "subscription": ("subscription.added", "subscription.removed", "subscription.updated"),
    "realm_user": ("user.added", "user.updated", "user.removed"),
}
ZULIP_QUEUE_EVENT_TYPES = tuple(ZULIP_QUEUE_ACTION_KINDS)
ZULIP_CONTROL_EVENT_TYPES = {"heartbeat", "restart"}


def normalize_zulip_queue_event(
    raw: dict[str, Any], *, instance: str | None = None,
    queue_lifetime: str | None = None, subscription_id: str | None = None,
    site_url: str | None = None,
    context: ChatEvent | None = None,
) -> list[ChatEvent]:
    """Expand one official Zulip queue event into immutable facts.

    A queue event ID is only unique inside one queue. Creation uses the native
    message ID; changes use queue lifetime plus queue event ID (or a canonical
    payload fingerprint for direct fixture calls). Sparse events may inherit
    known message context supplied by the collector.
    """
    event_type = raw.get("type")
    if event_type in ZULIP_CONTROL_EVENT_TYPES:
        return []
    if event_type not in ZULIP_QUEUE_EVENT_TYPES:
        raise ValueError("unsupported Zulip queue event type")
    if event_type == "message":
        event = normalize_zulip_message_event(raw, subscription_id=subscription_id, site_url=site_url)
        return [event.model_copy(update={"instance": instance.rstrip("/") if instance else None})]

    queue_marker = hashlib.sha256((queue_lifetime or "unscoped").encode()).hexdigest()[:12]
    raw_fingerprint = hashlib.sha256(json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]
    event_marker = _string(raw.get("id")) or raw_fingerprint
    occurred_value = raw.get("edit_timestamp") or raw.get("timestamp") or raw.get("date")
    occurred_at = _parse_datetime(occurred_value) if occurred_value is not None else utc_now()
    timestamp_source = "source-payload" if occurred_value is not None else "capture-time"
    actor_value = (raw.get("user_id") or raw.get("sender_id")) if event_type in {"reaction", "update_message"} else None
    actor_id = f"user:{actor_value}" if actor_value is not None else None

    def fact(
        kind: str, object_type: str, object_id: str, *,
        payload: dict[str, Any] | None = None, conversation_id: str | None = None,
        target: CarrierTarget | None = None,
    ) -> ChatEvent:
        subject = f"{object_type}:{object_id}"
        return ChatEvent(
            id=f"queue:{queue_marker}:{event_marker}:{kind}:{subject}",
            source="zulip", instance=instance, kind=kind,
            occurred_at=occurred_at, capture_mode=CaptureMode.EVENT_QUEUE,
            subscription_id=subscription_id, actor_id=actor_id,
            subject_id=subject, subject_type=object_type,
            conversation_id=conversation_id or (context.conversation_id if context else None),
            target=target,
            url=context.url if context else None,
            cursor=event_marker, payload=payload or {}, raw_payload=raw,
            metadata={"acquisition": "zulip-event-queue", "timestamp_source": timestamp_source},
            tags=["zulip", object_type],
        )

    if event_type in {"update_message", "delete_message"}:
        message_ids = raw.get("message_ids")
        if not isinstance(message_ids, list) or not message_ids:
            single = raw.get("message_id")
            message_ids = [single] if single is not None else []
        if not message_ids:
            raise ValueError("Zulip message change lacks message IDs")
        stream_id = _string(raw.get("new_stream_id") or raw.get("stream_id"))
        topic = _string(raw.get("subject") or raw.get("topic") or raw.get("orig_subject"))
        conversation = f"stream:{stream_id}/topic:{topic}" if stream_id and topic else None
        if event_type == "delete_message":
            return [fact("message.deleted", "message", str(item), conversation_id=conversation,
                         payload={"topic": topic or "", "stream": stream_id or ""}) for item in message_ids]
        moved = any(key in raw for key in ("new_stream_id", "subject")) and (
            raw.get("new_stream_id") is not None or raw.get("subject") != raw.get("orig_subject")
        )
        result: list[ChatEvent] = []
        if moved:
            result.extend(fact("message.moved", "message", str(item), conversation_id=conversation,
                               payload={"topic": topic or "", "stream": stream_id or "",
                                        "from_topic": raw.get("orig_subject") or "",
                                        "from_stream": str(raw.get("stream_id") or "")}) for item in message_ids)
        if "content" in raw or "orig_content" in raw:
            result.append(fact("message.edited", "message", str(raw.get("message_id") or message_ids[0]),
                               conversation_id=conversation, payload={"content": raw.get("content") or "",
                                                                   "topic": topic or "", "stream": stream_id or ""}))
        if not result:
            result.append(fact("message.rendered" if raw.get("rendering_only") else "message.updated",
                               "message", str(raw.get("message_id") or message_ids[0]), conversation_id=conversation))
        return result
    if event_type == "reaction":
        if raw.get("op") not in {"add", "remove"} or raw.get("message_id") is None:
            raise ValueError("invalid Zulip reaction")
        return [fact("reaction.added" if raw["op"] == "add" else "reaction.removed",
                     "message", str(raw["message_id"]),
                     payload={"emoji_code": raw.get("emoji_code") or "",
                              "emoji_name": raw.get("emoji_name") or "",
                              "reaction_type": raw.get("reaction_type") or ""})]
    if event_type == "stream":
        op = raw.get("op")
        if op not in {"create", "update", "delete"}:
            raise ValueError("unsupported Zulip stream operation")
        objects = raw.get("streams") if op == "create" else (raw.get("stream_ids") or raw.get("streams")) if op == "delete" else [raw]
        if not isinstance(objects, list):
            objects = [raw]
        result = []
        for item in objects:
            item = item if isinstance(item, dict) else {"stream_id": item}
            stream_id = _string(item.get("stream_id"))
            if not stream_id:
                raise ValueError("Zulip stream event lacks stream ID")
            result.append(fact({"create": "stream.created", "update": "stream.updated", "delete": "stream.deleted"}[op],
                               "stream", stream_id, payload={"name": item.get("name") or raw.get("name") or "",
                                                             "property": raw.get("property"), "value": raw.get("value")}))
        return result
    if event_type == "subscription":
        op = raw.get("op")
        if op not in {"add", "remove", "update"}:
            raise ValueError("unsupported Zulip subscription operation")
        objects = raw.get("subscriptions") or [raw]
        if not isinstance(objects, list):
            raise ValueError("invalid Zulip subscriptions")
        result = []
        for item in objects:
            if not isinstance(item, dict):
                raise ValueError("invalid Zulip subscription object")
            stream_id = _string(item.get("stream_id") or item.get("id") or raw.get("stream_id"))
            if not stream_id:
                raise ValueError("Zulip subscription event lacks stream ID")
            result.append(fact({"add": "subscription.added", "remove": "subscription.removed", "update": "subscription.updated"}[op],
                               "stream", stream_id, payload={"name": item.get("name") or "",
                                                             "property": raw.get("property"), "value": raw.get("value")}))
        return result
    # realm_user: person is the affected subject, not necessarily the actor.
    op = raw.get("op")
    if op not in {"add", "update", "remove"}:
        raise ValueError("unsupported Zulip realm_user operation")
    person = raw.get("person") if isinstance(raw.get("person"), dict) else raw
    user_id = _string(person.get("user_id") or person.get("id"))
    if not user_id:
        raise ValueError("Zulip realm_user event lacks user ID")
    item = fact({"add": "user.added", "update": "user.updated", "remove": "user.removed"}[op],
                "user", user_id, payload={"name": person.get("full_name") or ""})
    return [item.model_copy(update={"actor_id": None, "actor": None})]


def _discourse_kind(event_name: str | None, post_number: str | None = None) -> str:
    if event_name == "post_created":
        try:
            if post_number is not None and int(post_number) > 1:
                return "reply.created"
        except ValueError:
            pass
    mapping = {
        "post_created": "post.created",
        "post_edited": "post.edited",
        "post_destroyed": "post.deleted",
        "topic_created": "topic.created",
        "topic_edited": "topic.edited",
    }
    if event_name:
        return mapping.get(event_name, event_name.replace("_", "."))
    return "post.created"


def normalize_discourse_post(
    raw: dict[str, Any],
    *,
    subscription_id: str | None = None,
    base_url: str | None = None,
    capture_mode: CaptureMode = CaptureMode.WEBHOOK,
) -> ChatEvent:
    """Normalize a Discourse post webhook or post API payload."""

    post = raw.get("post") if isinstance(raw.get("post"), dict) else raw
    post_id = _string(post.get("id"))
    if not post_id:
        raise ValueError("Discourse post payload is missing id")
    topic_id = _string(post.get("topic_id") or raw.get("topic_id"))
    post_number = _string(post.get("post_number"))
    username = _string(post.get("username") or post.get("user_username"))
    created_at = post.get("created_at") or post.get("updated_at")
    if created_at is None:
        raise ValueError("Discourse post payload is missing created_at")
    topic = raw.get("topic") if isinstance(raw.get("topic"), dict) else {}
    title = (
        _string(post.get("topic_title"))
        or _string(topic.get("title"))
        or _string(post.get("title"))
        or "Discourse post"
    )

    slug = _string(post.get("topic_slug") or topic.get("slug"))
    url = _join_url(base_url, post.get("post_url") or post.get("url"))
    if url is None and base_url and topic_id and slug:
        suffix = f"/{post_number}" if post_number else ""
        url = f"{base_url.rstrip('/')}/t/{quote(slug, safe='-._~')}/{topic_id}{suffix}"

    event_name = _string(raw.get("event_name") or raw.get("discourse_event"))
    kind = _discourse_kind(event_name, post_number)
    topic_url = None
    if base_url and topic_id and slug:
        topic_url = f"{base_url.rstrip('/')}/t/{quote(slug, safe='-._~')}/{topic_id}"
    acquisition = (
        "discourse-webhook"
        if capture_mode in {CaptureMode.WEBHOOK, CaptureMode.PUSH}
        else "discourse-posts-api"
    )
    return ChatEvent(
        id=f"post:{post_id}",
        source="discourse",
        kind=kind,
        occurred_at=_parse_datetime(created_at),
        capture_mode=capture_mode,
        subscription_id=subscription_id,
        action=_action(kind, "post"),
        target=_discourse_post_target(
            post_id=post_id,
            post_number=post_number,
            topic_id=topic_id,
            title=title,
            url=url,
            topic_url=topic_url,
        ),
        actor_id=f"user:{username}" if username else None,
        conversation_id=f"topic:{topic_id}" if topic_id else None,
        subject_id=f"post:{post_id}",
        subject_type="post",
        url=url,
        cursor=post_id,
        payload={
            "title": title,
            "content": post.get("raw") or post.get("cooked") or "",
            "post_number": post_number or "",
            "username": username or "",
        },
        raw_payload=raw,
        metadata={"acquisition": acquisition, "timestamp_source": "source-payload"},
        tags=["discourse", "post"],
    )


# Event names from upstream WebHookEventType::TYPES (core families only).
DISCOURSE_WEBHOOK_ACTIONS: dict[str, tuple[str, str]] = {
    "post_created": ("post.created", "post"),
    "post_edited": ("post.edited", "post"),
    "post_destroyed": ("post.deleted", "post"),
    "post_recovered": ("post.recovered", "post"),
    "topic_created": ("topic.created", "topic"),
    "topic_edited": ("topic.edited", "topic"),
    "topic_revised": ("topic.revised", "topic"),
    "topic_destroyed": ("topic.deleted", "topic"),
    "topic_recovered": ("topic.recovered", "topic"),
    "user_created": ("user.created", "user"),
    "user_updated": ("user.updated", "user"),
    "user_approved": ("user.approved", "user"),
    "user_suspended": ("user.suspended", "user"),
    "user_unsuspended": ("user.unsuspended", "user"),
    "user_destroyed": ("user.deleted", "user"),
    "category_created": ("category.created", "category"),
    "category_updated": ("category.updated", "category"),
    "category_destroyed": ("category.deleted", "category"),
    "tag_created": ("tag.created", "tag"),
    "tag_updated": ("tag.updated", "tag"),
    "tag_destroyed": ("tag.deleted", "tag"),
    "group_created": ("group.created", "group"),
    "group_updated": ("group.updated", "group"),
    "group_destroyed": ("group.deleted", "group"),
    "like_created": ("like.created", "like"),
    "notification_created": ("notification.created", "notification"),
    "group_user_added": ("group_user.added", "group_user"),
    "group_user_removed": ("group_user.removed", "group_user"),
}


def normalize_discourse_webhook(
    raw: dict[str, Any], *, event_name: str | None = None,
    event_type: str | None = None, instance: str | None = None,
    subscription_id: str | None = None, base_url: str | None = None,
    capture_mode: CaptureMode = CaptureMode.WEBHOOK,
) -> ChatEvent:
    """Normalize a wrapped Discourse webhook without trusting delivery-row IDs.

    Retries can create fresh X-Discourse-Event-Id values. Native object identity,
    action, source revision/time, and canonical payload fingerprint identify a
    fact; distinct edits and restoration remain separate immutable rows.
    """
    name = event_name or _string(raw.get("event_name") or raw.get("discourse_event"))
    if name is None and (event_type == "post" or "post" in raw):
        name = "post_created"  # Legacy local wrapper compatibility.
    if name not in DISCOURSE_WEBHOOK_ACTIONS:
        raise ValueError("unsupported Discourse webhook event")
    kind, object_type = DISCOURSE_WEBHOOK_ACTIONS[name]
    if event_type and event_type != object_type:
        raise ValueError("Discourse event type and wrapper disagree")
    obj = raw.get(object_type)
    if not isinstance(obj, dict):
        # Some group-user hooks wrap membership inside the group object.
        if object_type == "group_user" and isinstance(raw.get("group"), dict):
            obj = raw["group"]
        else:
            raise ValueError("Discourse webhook lacks expected object wrapper")
    native_id = _string(obj.get("id") or obj.get("post_id") or obj.get("topic_id") or obj.get("user_id"))
    if object_type == "like" and obj.get("id") is None:
        if obj.get("post_id") is None or obj.get("user_id") is None:
            raise ValueError("Discourse like lacks stable action or actor/post identity")
        native_id = f"{obj['post_id']}:{obj['user_id']}"
    if object_type == "group_user":
        group_id = _string(obj.get("group_id") or obj.get("id"))
        nested_user = obj.get("user") if isinstance(obj.get("user"), dict) else {}
        user_id = _string(obj.get("user_id") or nested_user.get("id"))
        if not group_id or not user_id:
            raise ValueError("Discourse group membership lacks identity")
        native_id = f"{group_id}:{user_id}"
    if not native_id:
        raise ValueError("Discourse webhook object lacks identity")
    if name == "post_created" and (obj.get("created_at") or obj.get("updated_at")):
        created = normalize_discourse_post(
            {**raw, "event_name": name}, subscription_id=subscription_id,
            base_url=base_url, capture_mode=capture_mode,
        )
        return created.model_copy(update={"instance": instance.rstrip("/") if instance else None})

    timestamp = (obj.get("updated_at") or obj.get("created_at") or obj.get("deleted_at")
                 or raw.get("updated_at") or raw.get("created_at"))
    occurred_at = _parse_datetime(timestamp) if timestamp is not None else utc_now()
    fingerprint = hashlib.sha256(json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:20]
    revision = _string(obj.get("version") or obj.get("revision") or timestamp) or "capture"
    identity = (f"{object_type}:{native_id}:created" if kind.endswith(".created") and not (object_type == "like" and obj.get("id") is None) else
                f"{object_type}:{native_id}:{kind}:{hashlib.sha256(revision.encode()).hexdigest()[:8]}:{fingerprint}")
    explicit_actor = raw.get("actor") or raw.get("acting_user")
    actor_id = None
    if isinstance(explicit_actor, dict):
        actor_value = _string(explicit_actor.get("id") or explicit_actor.get("user_id") or explicit_actor.get("username"))
        actor_id = f"user:{actor_value}" if actor_value else None
    elif object_type == "post" and name == "post_created":
        username = _string(obj.get("username"))
        actor_id = f"user:{username}" if username else None
    topic_id = _string(obj.get("topic_id") or raw.get("topic_id"))
    conversation = f"topic:{topic_id}" if topic_id and object_type != "topic" else None
    url = _join_url(base_url, obj.get("url") or obj.get("post_url"))
    if url is None and base_url and object_type in {"post", "topic"}:
        target_topic_id = topic_id if object_type == "post" else native_id
        slug = _string(obj.get("topic_slug") or obj.get("slug"))
        if target_topic_id and slug:
            suffix = f"/{obj['post_number']}" if object_type == "post" and obj.get("post_number") else ""
            url = f"{base_url.rstrip('/')}/t/{quote(slug, safe='-._~')}/{target_topic_id}{suffix}"
    target = CarrierTarget(type=f"discourse_{object_type}", key=native_id,
                           display=_string(obj.get("title") or obj.get("name") or obj.get("username")),
                           url=url,
                           parent=CarrierTarget(type="discourse_topic", key=topic_id) if conversation else None)
    payload = {
        "title": _string(obj.get("title") or obj.get("name") or obj.get("topic_title")) or "",
        "content": obj.get("raw") or obj.get("cooked") or "",
    }
    if topic_id:
        payload["topic_id"] = topic_id
    return ChatEvent(
        id=identity, source="discourse", instance=instance, kind=kind,
        occurred_at=occurred_at, capture_mode=capture_mode,
        subscription_id=subscription_id, actor_id=actor_id,
        subject_id=f"{object_type}:{native_id}", subject_type=object_type,
        conversation_id=conversation, target=target, url=url,
        payload=payload, raw_payload=raw,
        metadata={"acquisition": "discourse-topic-api" if capture_mode == CaptureMode.MANUAL_BACKFILL else "discourse-webhook", "event_name": name,
                  "timestamp_source": "source-payload" if timestamp is not None else "capture-time"},
        tags=["discourse", object_type],
    )


def normalize_gitea_issue(
    raw: dict[str, Any],
    *,
    repository: str | None = None,
    subscription_id: str | None = None,
    capture_mode: CaptureMode = CaptureMode.API_CURSOR,
) -> ChatEvent:
    """Normalize a Gitea issue webhook payload or issue API object."""

    issue = raw.get("issue") if isinstance(raw.get("issue"), dict) else raw
    repo = raw.get("repository") if isinstance(raw.get("repository"), dict) else {}
    repo_name = (
        repository
        or _string(repo.get("full_name"))
        or _string(repo.get("name"))
        or _string(issue.get("repository"))
    )
    if not repo_name:
        raise ValueError("Gitea issue payload is missing repository")
    number = _string(issue.get("number") or issue.get("index"))
    issue_id = _string(issue.get("id"))
    if not number:
        raise ValueError("Gitea issue payload is missing number")
    action = _string(raw.get("action"))
    if action:
        kind = f"issue.{action}"
    else:
        state = _string(issue.get("state")) or "open"
        kind = "issue.closed" if state == "closed" else "issue.opened"
    user = issue.get("user") if isinstance(issue.get("user"), dict) else {}
    sender = raw.get("sender") if isinstance(raw.get("sender"), dict) else {}
    login = _string(sender.get("login") or user.get("login") or issue.get("poster"))
    occurred_at = issue.get("created_at") or issue.get("updated_at")
    if occurred_at is None:
        raise ValueError("Gitea issue payload is missing created_at/updated_at")
    labels = issue.get("labels") if isinstance(issue.get("labels"), list) else []
    label_names = [item.get("name") for item in labels if isinstance(item, dict) and item.get("name")]
    issue_url = _string(issue.get("html_url") or issue.get("url"))

    return ChatEvent(
        id=f"issue:{repo_name}:{number}",
        source="gitea",
        kind=kind,
        occurred_at=_parse_datetime(occurred_at),
        capture_mode=capture_mode,
        subscription_id=subscription_id,
        action=_action(kind, "issue"),
        target=_issue_target(
            repo_name=repo_name,
            number=number,
            url=issue_url,
            title=_string(issue.get("title")),
        ),
        actor_id=f"user:{login}" if login else None,
        conversation_id=f"repo:{repo_name}",
        subject_id=f"issue:{number}",
        subject_type="issue",
        url=issue_url,
        cursor=issue_id or number,
        payload={
            "title": issue.get("title") or "",
            "content": issue.get("body") or "",
            "state": issue.get("state") or "",
            "repository": repo_name,
            "number": number,
            "labels": label_names,
        },
        raw_payload=raw,
        metadata={
            "acquisition": (
                "gitea-webhook"
                if capture_mode in {CaptureMode.WEBHOOK, CaptureMode.PUSH}
                else "gitea-issues-api"
            )
        },
        tags=["gitea", "issue"],
    )


def _github_repository_name(raw: dict[str, Any]) -> str | None:
    repository = raw.get("repository") if isinstance(raw.get("repository"), dict) else {}
    return _string(repository.get("full_name") or repository.get("name"))


def _github_repository_url(raw: dict[str, Any]) -> str | None:
    repository = raw.get("repository") if isinstance(raw.get("repository"), dict) else {}
    return _string(repository.get("html_url") or repository.get("url"))


def _github_sender_login(raw: dict[str, Any]) -> str | None:
    sender = raw.get("sender") if isinstance(raw.get("sender"), dict) else {}
    return _string(sender.get("login"))


def _github_pull_request_kind(action: str | None, pull_request: dict[str, Any]) -> str:
    if action == "closed" and pull_request.get("merged") is True:
        return "pull_request.merged"
    if action:
        return f"pull_request.{action}"
    return "pull_request.updated"


def normalize_github_event(
    github_event: str,
    raw: dict[str, Any],
    *,
    subscription_id: str | None = None,
    capture_mode: CaptureMode = CaptureMode.WEBHOOK,
) -> ChatEvent:
    """Normalize a GitHub repository webhook payload into ``ChatEvent``.

    The first GitHub demo target is expected to be ``repo:ChatArch/ChatEvent``.
    The normalizer accepts GitHub's official webhook event name from the
    ``X-GitHub-Event`` header and turns platform-specific actions into the
    controlled ``source + kind`` contract exposed by :mod:`chatevent.catalog`.
    """

    github_event = github_event.strip().lower().replace("-", "_")
    repo_name = _github_repository_name(raw)
    if not repo_name:
        raise ValueError("GitHub payload is missing repository.full_name")
    sender_login = _github_sender_login(raw)
    repo_target = _repo_target(repo_name, _github_repository_url(raw))

    if github_event == "push":
        commit = raw.get("head_commit") if isinstance(raw.get("head_commit"), dict) else {}
        commit_id = _string(commit.get("id") or raw.get("after"))
        if not commit_id:
            raise ValueError("GitHub push payload is missing head commit id")
        occurred_at = commit.get("timestamp") or raw.get("pushed_at")
        if occurred_at is None:
            raise ValueError("GitHub push payload is missing timestamp")
        author = commit.get("author") if isinstance(commit.get("author"), dict) else {}
        actor = _string(author.get("username") or author.get("name") or sender_login)
        return ChatEvent(
            id=f"commit:{repo_name}:{commit_id}",
            source="github",
            kind="commit.pushed",
            occurred_at=_parse_datetime(occurred_at),
            capture_mode=capture_mode,
            subscription_id=subscription_id,
            action=_action("commit.pushed", "commit"),
            target=CarrierTarget(
                type="commit",
                key=commit_id,
                display=commit_id[:12],
                url=_string(commit.get("url")),
                parent=repo_target,
            ),
            actor_id=f"user:{actor}" if actor else None,
            conversation_id=f"repo:{repo_name}",
            subject_id=f"commit:{commit_id}",
            subject_type="commit",
            url=_string(commit.get("url")),
            cursor=commit_id,
            payload={
                "title": commit.get("message") or "GitHub push",
                "content": commit.get("message") or "",
                "repository": repo_name,
                "ref": raw.get("ref") or "",
                "after": raw.get("after") or commit_id,
            },
            raw_payload=raw,
            metadata={"acquisition": "github-webhook", "github_event": "push"},
            tags=["github", "commit", "push"],
        )

    if github_event == "pull_request":
        pull_request = raw.get("pull_request") if isinstance(raw.get("pull_request"), dict) else {}
        number = _string(pull_request.get("number") or raw.get("number"))
        if not number:
            raise ValueError("GitHub pull_request payload is missing number")
        action_name = _string(raw.get("action"))
        kind = _github_pull_request_kind(action_name, pull_request)
        occurred_at = (
            pull_request.get("merged_at")
            if kind == "pull_request.merged"
            else pull_request.get("updated_at") or pull_request.get("created_at")
        )
        if occurred_at is None:
            raise ValueError("GitHub pull_request payload is missing timestamp")
        user = pull_request.get("user") if isinstance(pull_request.get("user"), dict) else {}
        login = _string(user.get("login") or sender_login)
        return ChatEvent(
            id=f"pull_request:{repo_name}:{number}",
            source="github",
            kind=kind,
            occurred_at=_parse_datetime(occurred_at),
            capture_mode=capture_mode,
            subscription_id=subscription_id,
            action=_action(kind, "pull_request"),
            target=CarrierTarget(
                type="pull_request",
                key=f"{repo_name}#{number}",
                display=pull_request.get("title") or f"PR #{number}",
                url=_string(pull_request.get("html_url")),
                parent=repo_target,
            ),
            actor_id=f"user:{login}" if login else None,
            conversation_id=f"repo:{repo_name}",
            subject_id=f"pull_request:{number}",
            subject_type="pull_request",
            url=_string(pull_request.get("html_url")),
            cursor=str(pull_request.get("id") or number),
            payload={
                "title": pull_request.get("title") or "",
                "content": pull_request.get("body") or "",
                "repository": repo_name,
                "number": number,
                "action": action_name or "",
                "state": pull_request.get("state") or "",
                "merged": bool(pull_request.get("merged")),
            },
            raw_payload=raw,
            metadata={"acquisition": "github-webhook", "github_event": "pull_request"},
            tags=["github", "pull_request"],
        )

    if github_event == "issues":
        issue = raw.get("issue") if isinstance(raw.get("issue"), dict) else {}
        number = _string(issue.get("number"))
        if not number:
            raise ValueError("GitHub issues payload is missing issue.number")
        action_name = _string(raw.get("action")) or "updated"
        occurred_at = issue.get("updated_at") or issue.get("created_at")
        if occurred_at is None:
            raise ValueError("GitHub issues payload is missing timestamp")
        user = issue.get("user") if isinstance(issue.get("user"), dict) else {}
        login = _string(user.get("login") or sender_login)
        return ChatEvent(
            id=f"issue:{repo_name}:{number}",
            source="github",
            kind=f"issue.{action_name}",
            occurred_at=_parse_datetime(occurred_at),
            capture_mode=capture_mode,
            subscription_id=subscription_id,
            action=_action(f"issue.{action_name}", "issue"),
            target=CarrierTarget(
                type="issue",
                key=f"{repo_name}#{number}",
                display=issue.get("title") or f"Issue #{number}",
                url=_string(issue.get("html_url")),
                parent=repo_target,
            ),
            actor_id=f"user:{login}" if login else None,
            conversation_id=f"repo:{repo_name}",
            subject_id=f"issue:{number}",
            subject_type="issue",
            url=_string(issue.get("html_url")),
            cursor=str(issue.get("id") or number),
            payload={
                "title": issue.get("title") or "",
                "content": issue.get("body") or "",
                "repository": repo_name,
                "number": number,
                "action": action_name,
                "state": issue.get("state") or "",
            },
            raw_payload=raw,
            metadata={"acquisition": "github-webhook", "github_event": "issues"},
            tags=["github", "issue"],
        )

    if github_event == "issue_comment":
        issue = raw.get("issue") if isinstance(raw.get("issue"), dict) else {}
        comment = raw.get("comment") if isinstance(raw.get("comment"), dict) else {}
        issue_number = _string(issue.get("number"))
        comment_id = _string(comment.get("id"))
        if not (issue_number and comment_id):
            raise ValueError("GitHub issue_comment payload is missing issue number/comment id")
        occurred_at = comment.get("updated_at") or comment.get("created_at")
        if occurred_at is None:
            raise ValueError("GitHub issue_comment payload is missing timestamp")
        user = comment.get("user") if isinstance(comment.get("user"), dict) else {}
        action_name = _string(raw.get("action")) or "created"
        kind = "issue.commented" if action_name == "created" else f"issue_comment.{action_name}"
        parent_target_type = "pull_request" if isinstance(issue.get("pull_request"), dict) else "issue"
        parent_label = "PR" if parent_target_type == "pull_request" else "Issue"
        parent_target = CarrierTarget(
            type=parent_target_type,
            key=f"{repo_name}#{issue_number}",
            display=issue.get("title") or f"{parent_label} #{issue_number}",
            url=_string(issue.get("html_url")),
            parent=repo_target,
        )
        login = _string(user.get("login") or sender_login)
        return ChatEvent(
            id=f"issue_comment:{repo_name}:{comment_id}",
            source="github",
            kind=kind,
            occurred_at=_parse_datetime(occurred_at),
            capture_mode=capture_mode,
            subscription_id=subscription_id,
            action=_action(kind, "issue_comment"),
            target=CarrierTarget(
                type="issue_comment",
                key=comment_id,
                display=f"comment:{comment_id}",
                url=_string(comment.get("html_url")),
                parent=parent_target,
            ),
            actor=_actor(login, role=_string(comment.get("author_association") or issue.get("author_association"))),
            actor_id=f"user:{login}" if login else None,
            conversation_id=f"issue:{repo_name}:{issue_number}",
            subject_id=f"comment:{comment_id}",
            subject_type="issue_comment",
            url=_string(comment.get("html_url")),
            cursor=comment_id,
            payload={
                "title": issue.get("title") or "GitHub issue comment",
                "content": comment.get("body") or "",
                "repository": repo_name,
                "number": issue_number,
                "action": action_name,
            },
            raw_payload=raw,
            metadata={"acquisition": "github-webhook", "github_event": "issue_comment"},
            tags=["github", "issue", "comment"],
        )

    if github_event == "workflow_run":
        workflow_run = raw.get("workflow_run") if isinstance(raw.get("workflow_run"), dict) else {}
        run_id = _string(workflow_run.get("id"))
        if not run_id:
            raise ValueError("GitHub workflow_run payload is missing id")
        occurred_at = workflow_run.get("updated_at") or workflow_run.get("created_at")
        if occurred_at is None:
            raise ValueError("GitHub workflow_run payload is missing timestamp")
        action_name = _string(raw.get("action")) or "completed"
        kind = f"workflow_run.{action_name}"
        return ChatEvent(
            id=f"workflow_run:{repo_name}:{run_id}",
            source="github",
            kind=kind,
            occurred_at=_parse_datetime(occurred_at),
            capture_mode=capture_mode,
            subscription_id=subscription_id,
            action=_action(kind, "workflow_run"),
            target=CarrierTarget(
                type="workflow_run",
                key=run_id,
                display=workflow_run.get("name") or f"workflow_run:{run_id}",
                url=_string(workflow_run.get("html_url")),
                parent=repo_target,
            ),
            actor_id=f"user:{sender_login}" if sender_login else None,
            conversation_id=f"repo:{repo_name}",
            subject_id=f"workflow_run:{run_id}",
            subject_type="workflow_run",
            url=_string(workflow_run.get("html_url")),
            cursor=run_id,
            payload={
                "title": workflow_run.get("name") or "GitHub workflow run",
                "content": workflow_run.get("display_title") or "",
                "repository": repo_name,
                "status": workflow_run.get("status") or "",
                "conclusion": workflow_run.get("conclusion") or "",
            },
            raw_payload=raw,
            metadata={"acquisition": "github-webhook", "github_event": "workflow_run"},
            tags=["github", "workflow_run"],
        )

    if github_event == "release":
        release = raw.get("release") if isinstance(raw.get("release"), dict) else {}
        release_id = _string(release.get("id") or release.get("tag_name"))
        if not release_id:
            raise ValueError("GitHub release payload is missing id/tag_name")
        occurred_at = release.get("published_at") or release.get("created_at")
        if occurred_at is None:
            raise ValueError("GitHub release payload is missing timestamp")
        action_name = _string(raw.get("action")) or "published"
        kind = f"release.{action_name}"
        return ChatEvent(
            id=f"release:{repo_name}:{release_id}",
            source="github",
            kind=kind,
            occurred_at=_parse_datetime(occurred_at),
            capture_mode=capture_mode,
            subscription_id=subscription_id,
            action=_action(kind, "release"),
            target=CarrierTarget(
                type="release",
                key=release_id,
                display=release.get("name") or release.get("tag_name") or f"release:{release_id}",
                url=_string(release.get("html_url")),
                parent=repo_target,
            ),
            actor_id=f"user:{sender_login}" if sender_login else None,
            conversation_id=f"repo:{repo_name}",
            subject_id=f"release:{release_id}",
            subject_type="release",
            url=_string(release.get("html_url")),
            cursor=release_id,
            payload={
                "title": release.get("name") or release.get("tag_name") or "GitHub release",
                "content": release.get("body") or "",
                "repository": repo_name,
                "tag": release.get("tag_name") or "",
                "action": action_name,
            },
            raw_payload=raw,
            metadata={"acquisition": "github-webhook", "github_event": "release"},
            tags=["github", "release"],
        )

    raise ValueError(f"unsupported GitHub webhook event: {github_event}")
