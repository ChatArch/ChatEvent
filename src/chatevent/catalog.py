"""Supported platform/action catalog for ChatEvent v0.1.

The catalog is deliberately platform-specific. It tells the capture layer and UI
which actions are first-class today instead of treating arbitrary tags as event
semantics. New platforms/actions should be registered here with explicit
acquisition modes and scope examples.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .model import CaptureMode

PlatformId = Literal["discourse", "gitea", "github", "zulip"]


class PlatformAction(BaseModel):
    """A supported action kind for a concrete platform."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str = Field(min_length=1)
    object_type: str = Field(min_length=1)
    action: str = Field(min_length=1)
    description: str
    target_types: tuple[str, ...]
    acquisition_modes: tuple[CaptureMode, ...]
    webhook_events: tuple[str, ...] = ()


class PlatformSpec(BaseModel):
    """ChatEvent's explicit contract for one integration platform."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: PlatformId
    display_name: str
    description: str
    primary_acquisition_modes: tuple[CaptureMode, ...]
    scope_examples: tuple[str, ...]
    actions: tuple[PlatformAction, ...]


def action(
    kind: str,
    object_type: str,
    action_name: str,
    description: str,
    acquisition_modes: tuple[CaptureMode, ...],
    webhook_events: tuple[str, ...] = (),
    target_types: tuple[str, ...] = (),
) -> PlatformAction:
    return PlatformAction(
        kind=kind,
        object_type=object_type,
        action=action_name,
        description=description,
        target_types=target_types or (object_type,),
        acquisition_modes=acquisition_modes,
        webhook_events=webhook_events,
    )


PLATFORM_SPECS: tuple[PlatformSpec, ...] = (
    PlatformSpec(
        id="discourse",
        display_name="Discourse",
        description="Forum topics, posts, replies, edits, mentions, and reactions through official webhooks plus REST readback for object completion.",
        primary_acquisition_modes=(CaptureMode.WEBHOOK, CaptureMode.API_CURSOR),
        scope_examples=("category:<slug>", "topic:<id>", "tag:<slug>", "user:<username>"),
        actions=(
            action("topic.created", "topic", "created", "A new topic is created in a watched category/tag.", (CaptureMode.WEBHOOK, CaptureMode.API_CURSOR), ("topic",), ("discourse_category", "discourse_topic")),
            action("post.created", "post", "created", "A first post or standalone forum post is created.", (CaptureMode.WEBHOOK, CaptureMode.API_CURSOR), ("post",), ("discourse_topic", "discourse_post")),
            action("reply.created", "post", "created", "A reply is added to an existing topic.", (CaptureMode.WEBHOOK, CaptureMode.API_CURSOR), ("post",), ("discourse_topic", "discourse_post")),
            action("post.edited", "post", "edited", "A watched post is edited.", (CaptureMode.WEBHOOK, CaptureMode.API_CURSOR), ("post",), ("discourse_topic", "discourse_post")),
            action("post.deleted", "post", "deleted", "A watched post is deleted or hidden.", (CaptureMode.WEBHOOK,), ("post",), ("discourse_topic", "discourse_post")),
            action("mention.created", "mention", "created", "A watched bot/user is mentioned in a topic or reply.", (CaptureMode.WEBHOOK, CaptureMode.API_CURSOR), ("post",), ("discourse_topic", "discourse_post")),
            action("reaction.added", "reaction", "added", "A reaction/like is added to a watched post.", (CaptureMode.WEBHOOK, CaptureMode.API_CURSOR), ("like",), ("discourse_post", "reaction")),
        ),
    ),
    PlatformSpec(
        id="gitea",
        display_name="Gitea",
        description="Self-hosted forge repository events through repository webhooks and official REST API readback.",
        primary_acquisition_modes=(CaptureMode.WEBHOOK, CaptureMode.API_CURSOR),
        scope_examples=("repo:<owner>/<repo>", "org:<owner>", "issue:<owner>/<repo>#<number>"),
        actions=(
            action("push", "ref", "pushed", "One or more commits are pushed to a watched ref.", (CaptureMode.WEBHOOK,), ("push",), ("repo", "ref", "commit")),
            action("commit.pushed", "commit", "pushed", "A single commit from a push payload is normalized as an observable action.", (CaptureMode.WEBHOOK,), ("push",), ("repo", "commit")),
            action("issue.opened", "issue", "opened", "A watched repository issue is opened.", (CaptureMode.WEBHOOK, CaptureMode.API_CURSOR), ("issues",)),
            action("issue.closed", "issue", "closed", "A watched issue is closed.", (CaptureMode.WEBHOOK, CaptureMode.API_CURSOR), ("issues",)),
            action("issue.commented", "issue_comment", "commented", "A comment is added to a watched issue.", (CaptureMode.WEBHOOK,), ("issue_comment",), ("issue", "pull_request", "issue_comment")),
            action("pull_request.opened", "pull_request", "opened", "A pull request is opened.", (CaptureMode.WEBHOOK, CaptureMode.API_CURSOR), ("pull_request",)),
            action("pull_request.updated", "pull_request", "updated", "A pull request title/body/branch state changes.", (CaptureMode.WEBHOOK, CaptureMode.API_CURSOR), ("pull_request",)),
            action("pull_request.merged", "pull_request", "merged", "A pull request is merged.", (CaptureMode.WEBHOOK, CaptureMode.API_CURSOR), ("pull_request",)),
            action("release.published", "release", "published", "A release is published for a watched repository.", (CaptureMode.WEBHOOK,), ("release",)),
        ),
    ),
    PlatformSpec(
        id="github",
        display_name="GitHub",
        description="GitHub repository activity for ChatEvent itself and future ChatArch repos through repository webhooks, Events API cursors, and Actions API readback.",
        primary_acquisition_modes=(CaptureMode.WEBHOOK, CaptureMode.API_CURSOR),
        scope_examples=("repo:ChatArch/ChatEvent", "org:ChatArch", "pull_request:ChatArch/ChatEvent#<number>"),
        actions=(
            action("push", "ref", "pushed", "A push webhook is delivered for a watched branch or tag.", (CaptureMode.WEBHOOK,), ("push",), ("repo", "ref", "commit")),
            action("commit.pushed", "commit", "pushed", "The head commit in a push is recorded as a concrete action.", (CaptureMode.WEBHOOK,), ("push",), ("repo", "commit")),
            action("issue.opened", "issue", "opened", "A watched GitHub issue is opened.", (CaptureMode.WEBHOOK, CaptureMode.API_CURSOR), ("issues",)),
            action("issue.closed", "issue", "closed", "A watched issue is closed.", (CaptureMode.WEBHOOK, CaptureMode.API_CURSOR), ("issues",)),
            action("issue.commented", "issue_comment", "commented", "A comment is added to a watched issue.", (CaptureMode.WEBHOOK,), ("issue_comment",), ("issue", "pull_request", "issue_comment")),
            action("pull_request.opened", "pull_request", "opened", "A pull request is opened for a watched repository.", (CaptureMode.WEBHOOK, CaptureMode.API_CURSOR), ("pull_request",)),
            action("pull_request.synchronize", "pull_request", "synchronize", "New commits are pushed to a pull request branch.", (CaptureMode.WEBHOOK,), ("pull_request",)),
            action("pull_request.closed", "pull_request", "closed", "A pull request is closed without merge.", (CaptureMode.WEBHOOK, CaptureMode.API_CURSOR), ("pull_request",)),
            action("pull_request.merged", "pull_request", "merged", "A pull request is merged into the base branch.", (CaptureMode.WEBHOOK, CaptureMode.API_CURSOR), ("pull_request",)),
            action("workflow_run.completed", "workflow_run", "completed", "A GitHub Actions workflow run completes.", (CaptureMode.WEBHOOK, CaptureMode.API_CURSOR), ("workflow_run",)),
            action("release.published", "release", "published", "A GitHub release is published.", (CaptureMode.WEBHOOK,), ("release",)),
        ),
    ),
    PlatformSpec(
        id="zulip",
        display_name="Zulip",
        description="Stream/topic messages and interaction signals through Zulip event queues, bot events, and narrow API cursors.",
        primary_acquisition_modes=(CaptureMode.EVENT_QUEUE, CaptureMode.API_CURSOR),
        scope_examples=("stream:<name>", "topic:<name>", "narrow:stream=<name>,topic=<name>", "user:<email>"),
        actions=(
            action("message.created", "message", "created", "A new stream/topic/private message is sent.", (CaptureMode.EVENT_QUEUE, CaptureMode.API_CURSOR), ("message",), ("zulip_stream", "zulip_topic", "message")),
            action("message.updated", "message", "updated", "A message body/topic/status is edited.", (CaptureMode.EVENT_QUEUE, CaptureMode.API_CURSOR), ("update_message",), ("zulip_stream", "zulip_topic", "message")),
            action("reaction.added", "reaction", "added", "A reaction is added to a watched message.", (CaptureMode.EVENT_QUEUE,), ("reaction",), ("message", "reaction")),
            action("reaction.removed", "reaction", "removed", "A reaction is removed from a watched message.", (CaptureMode.EVENT_QUEUE,), ("reaction",), ("message", "reaction")),
            action("mention.created", "mention", "created", "A watched bot/user is mentioned in a message.", (CaptureMode.EVENT_QUEUE, CaptureMode.API_CURSOR), ("message",), ("zulip_topic", "message", "mention")),
            action("topic.updated", "topic", "updated", "A message topic is changed.", (CaptureMode.EVENT_QUEUE,), ("update_message",), ("zulip_stream", "zulip_topic")),
        ),
    ),
)

SUPPORTED_PLATFORM_IDS = tuple(sorted(spec.id for spec in PLATFORM_SPECS))
_SPEC_BY_ID = {spec.id: spec for spec in PLATFORM_SPECS}


def get_platform_spec(platform_id: str) -> PlatformSpec:
    """Return the registered platform spec, raising for unsupported sources."""

    try:
        return _SPEC_BY_ID[platform_id]
    except KeyError as error:
        supported = ", ".join(SUPPORTED_PLATFORM_IDS)
        raise ValueError(f"unsupported platform {platform_id!r}; supported: {supported}") from error


def list_platform_specs() -> tuple[PlatformSpec, ...]:
    """Return all platform specs sorted by stable platform id."""

    return tuple(_SPEC_BY_ID[platform_id] for platform_id in SUPPORTED_PLATFORM_IDS)


def action_kinds_for(platform_id: str) -> tuple[str, ...]:
    """Return all supported event kinds for a platform."""

    return tuple(action.kind for action in get_platform_spec(platform_id).actions)
