# ChatEvent

`chatevent` provides a typed event envelope, SQLite event store, platform normalizers, and a Web Observatory for collaboration-event demos.

Current `0.1.0.dev0` scope is intentionally narrow and task-oriented: **Discourse, Zulip, Gitea, and GitHub**. Each platform registers an explicit action catalog so subscription/UI choices stay controllable instead of treating arbitrary `tag` values as event semantics.

```text
platform official webhook/event queue/API cursor -> ChatEvent -> SQLite -> Observatory/API
```

Gateway routing and agent execution are intentionally outside this package's current phase.

## Event semantics

Use these fields for product meaning:

- `source`: platform id, e.g. `zulip`, `discourse`, `gitea`, `github`.
- `kind`: platform-specific action kind, e.g. `message.created`, `post.created`, `issue.opened`, `commit.pushed`, `pull_request.merged`.
- `conversation_id` / `subject_id` / `subject_type`: where it happened and what object changed.
- `capture_mode`: acquisition mechanism, not product action. New integrations use `webhook`, `event_queue`, `api_cursor`, `poll`, `manual_backfill`, `gateway_forward`, `test_fixture`, or `synthetic`. Legacy `push`/`pull` remain readable for old data only.
- `tags`: optional labels/routing labels for filtering. They do **not** define the event source or action.

## Supported platforms and common actions

Inspect the canonical registry with:

```bash
uv run chatevent platforms
uv run chatevent platforms --json
```

| Platform | Primary acquisition | Common action kinds |
|---|---|---|
| Zulip | `event_queue`, `api_cursor` | `message.created`, `message.updated`, `reaction.added`, `reaction.removed`, `mention.created`, `topic.updated` |
| Discourse | `webhook`, `api_cursor` | `topic.created`, `post.created`, `reply.created`, `post.edited`, `post.deleted`, `mention.created`, `reaction.added` |
| Gitea | `webhook`, `api_cursor` | `push`, `commit.pushed`, `issue.opened`, `issue.closed`, `issue.commented`, `pull_request.opened`, `pull_request.updated`, `pull_request.merged`, `release.published` |
| GitHub | `webhook`, `api_cursor` | `push`, `commit.pushed`, `issue.opened`, `issue.closed`, `issue.commented`, `pull_request.opened`, `pull_request.synchronize`, `pull_request.closed`, `pull_request.merged`, `workflow_run.completed`, `release.published` |

GitHub's first demo target is `repo:ChatArch/ChatEvent`, so ChatEvent can observe its own commits, pull requests, workflow runs, and releases.

## Install from source

```bash
uv sync --extra serve --extra test
uv run --extra serve chatevent --tree
```

PyPI `0.0.1` contains the initial event envelope and monitor protocol only. The Observatory and action registry are development-stage `0.1.0.dev0` work.

## CLI

```text
chatevent
  --tree                         Print this command tree
  serve [--host HOST] [--port PORT] [--db DB]
                                 Run the local Event Observatory
  schema event|subscription      Print JSON Schema contracts
  platforms [--json]             List supported platforms and action kinds
  record-json FILE [--db DB]     Validate and write one ChatEvent JSON file
  capture zulip-once [options]   Official Zulip event-queue capture pass
```

## Run the Event Observatory

```bash
uv run --extra serve chatevent serve \
  --host 127.0.0.1 \
  --port 8765 \
  --db ./events.db
```

For the current server demo, Nginx exposes the service at:

- https://event.local.wzhecnu.cn/
- https://event.public.wzhecnu.cn/

## Define a normalized event

```python
from datetime import datetime, timezone

from chatevent import CaptureMode, ChatEvent

event = ChatEvent(
    id="issue:owner/repo:42",
    source="gitea",
    kind="issue.opened",
    occurred_at=datetime.now(timezone.utc),
    capture_mode=CaptureMode.WEBHOOK,
    conversation_id="repo:owner/repo",
    payload={"title": "Investigate event routing"},
)

assert event.dedupe_key == "gitea:issue:owner/repo:42"
```

## API surface

- `GET /api/health`
- `GET /api/schema/event`
- `GET /api/schema/subscription`
- `GET /api/platforms`
- `POST /api/subscriptions`
- `GET /api/subscriptions`
- `POST /api/events`
- `GET /api/events`
- `GET /api/events/{source:id}`
- `GET /api/stats`
- `POST /webhooks/zulip?subscription_id=...`
- `POST /webhooks/discourse?subscription_id=...`
- `POST /webhooks/gitea?subscription_id=...`
- `POST /webhooks/github?subscription_id=...` with `X-GitHub-Event`

Webhook endpoints accept official platform-shaped payloads, normalize them to `ChatEvent`, write SQLite with idempotent dedupe, and keep `raw_payload` for Observatory inspection.

## Capture examples

Zulip uses the official event queue. Existing secret files are referenced by path without copying or printing secrets:

```bash
uv run --extra serve chatevent capture zulip-once \
  --env-file /path/to/zulip.env \
  --db /path/to/events.db \
  --stream "Prompting, skills, and agent tools" \
  --topic "ChatEvent Observatory demo" \
  --content "ChatEvent real-loop" \
  --subscription-id zulip-practice
```

Discourse, Gitea, and GitHub can push official webhook-shaped payloads to their webhook endpoints. REST/API reads are used only for bounded object readback or cursor reconciliation; do not scan whole sites, all posts, or all repositories.

## Implement a monitor

An adapter exposes an asynchronous stream. It may receive webhooks, consume an official event queue, or read a bounded platform API cursor.

```python
from collections.abc import AsyncIterator

from chatevent import CaptureMode, ChatEvent, EventMonitor


class GiteaMonitor:
    source = "gitea"
    mode = CaptureMode.API_CURSOR

    async def events(self, *, cursor: str | None = None) -> AsyncIterator[ChatEvent]:
        if False:  # Replace with bounded incremental API reads.
            yield


monitor: EventMonitor = GiteaMonitor()
```
