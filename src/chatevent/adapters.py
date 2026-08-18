"""Platform adapters that normalize official API/webhook payloads.

The functions in this module deliberately keep acquisition and normalization
separate.  Platform-specific clients may use official event queues, webhooks, or
incremental REST APIs to obtain raw payloads; these helpers map those payloads
into the stable :class:`chatevent.model.ChatEvent` envelope.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote, urljoin

from .model import CaptureMode, ChatEvent


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
    occurred_at = _parse_datetime(message.get("timestamp") or message.get("date_sent"))

    return ChatEvent(
        id=f"message:{message_id}",
        source="zulip",
        kind="message.created",
        occurred_at=occurred_at,
        capture_mode=capture_mode,
        subscription_id=subscription_id,
        actor_id=f"user:{sender_id}" if sender_id else None,
        conversation_id=conversation_id,
        subject_id=f"message:{message_id}",
        subject_type="message",
        url=_zulip_message_url(site_url, message),
        cursor=raw_event_id or message_id,
        payload={
            "title": topic or stream_name or "Zulip message",
            "content": message.get("content") or "",
            "sender": message.get("sender_full_name") or message.get("sender_email") or "",
            "stream": stream_name or "",
            "topic": topic or "",
        },
        raw_payload=raw,
        metadata={"acquisition": "zulip-event-queue"},
        tags=["zulip", "message"],
    )


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
    acquisition = (
        "discourse-webhook"
        if capture_mode in {CaptureMode.WEBHOOK, CaptureMode.PUSH}
        else "discourse-posts-api"
    )
    return ChatEvent(
        id=f"post:{post_id}",
        source="discourse",
        kind=_discourse_kind(event_name, post_number),
        occurred_at=_parse_datetime(created_at),
        capture_mode=capture_mode,
        subscription_id=subscription_id,
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
        metadata={"acquisition": acquisition},
        tags=["discourse", "post"],
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

    return ChatEvent(
        id=f"issue:{repo_name}:{number}",
        source="gitea",
        kind=kind,
        occurred_at=_parse_datetime(occurred_at),
        capture_mode=capture_mode,
        subscription_id=subscription_id,
        actor_id=f"user:{login}" if login else None,
        conversation_id=f"repo:{repo_name}",
        subject_id=f"issue:{number}",
        subject_type="issue",
        url=_string(issue.get("html_url") or issue.get("url")),
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
        return ChatEvent(
            id=f"issue_comment:{repo_name}:{comment_id}",
            source="github",
            kind="issue.commented" if action_name == "created" else f"issue_comment.{action_name}",
            occurred_at=_parse_datetime(occurred_at),
            capture_mode=capture_mode,
            subscription_id=subscription_id,
            actor_id=f"user:{_string(user.get('login') or sender_login)}" if _string(user.get("login") or sender_login) else None,
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
        return ChatEvent(
            id=f"workflow_run:{repo_name}:{run_id}",
            source="github",
            kind=f"workflow_run.{action_name}",
            occurred_at=_parse_datetime(occurred_at),
            capture_mode=capture_mode,
            subscription_id=subscription_id,
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
        return ChatEvent(
            id=f"release:{repo_name}:{release_id}",
            source="github",
            kind=f"release.{action_name}",
            occurred_at=_parse_datetime(occurred_at),
            capture_mode=capture_mode,
            subscription_id=subscription_id,
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
