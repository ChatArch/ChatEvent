# ChatEvent

`chatevent` provides a typed event envelope, SQLite event store, platform normalizers, and a Web Observatory for collaboration-event demos.

Current `0.1.0.dev0` scope is intentionally narrow and task-oriented: **Discourse, Zulip, Gitea, and GitHub**. Each platform registers an explicit action catalog so subscription/UI choices stay controllable instead of treating arbitrary `tag` values as event semantics.

```text
platform official webhook/event queue/API cursor -> ChatEvent -> SQLite -> Observatory/API
```

Gateway routing and agent execution are intentionally outside this package's current phase.

Chinese README: [README.md](README.md).

## Documentation

- MkDocs source: `docs/`
- Local docs build:

```bash
uv sync --extra docs
uv run mkdocs build --strict
uv run mkdocs serve
```

The ChatArch package-docs target is:

https://arch.gh.wzhecnu.cn/ChatEvent/

## Install from source

```bash
uv sync --extra serve --extra test --extra docs
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

Open:

```text
http://127.0.0.1:8765/
```

For the current server demo, nginx exposes the service at:

- https://event.local.wzhecnu.cn/
- https://event.public.wzhecnu.cn/

## Refresh behavior

The Observatory is currently frontend polling, not WebSocket/SSE:

- loads immediately when the page opens;
- automatically refreshes every **5 seconds**;
- refreshes immediately when clicking **刷新 / Refresh**;
- search input refreshes after about **260ms debounce**;
- source/kind filter changes refresh immediately.

Each refresh calls `/api/stats`, `/api/subscriptions`, `/api/events`, and `/api/platforms`.

## Event semantics

Use these fields for product meaning:

- `source`: platform id, e.g. `zulip`, `discourse`, `gitea`, `github`.
- `kind`: platform-specific action kind, e.g. `message.created`, `post.created`, `reply.created`, `issue.opened`, `commit.pushed`, `pull_request.merged`.
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

## Register monitors

1. Save a ChatEvent subscription:

```bash
curl -k -X POST https://event.public.wzhecnu.cn/api/subscriptions \
  -H 'Content-Type: application/json' \
  -d '{
    "id": "discourse-practice",
    "source": "discourse",
    "target": "category:agent-runs",
    "event_kinds": ["topic.created", "post.created", "reply.created"],
    "capture_modes": ["webhook", "api_cursor"]
  }'
```

2. Configure the platform official capture surface to call ChatEvent:

```text
Discourse: https://event.public.wzhecnu.cn/webhooks/discourse?subscription_id=discourse-practice
Gitea:     https://event.public.wzhecnu.cn/webhooks/gitea?subscription_id=gitea-practice
GitHub:    https://event.public.wzhecnu.cn/webhooks/github?subscription_id=github-chatevent
Zulip:     use `chatevent capture zulip-once` for the official event queue pass
```

See `docs/monitoring.md` for detailed registration steps.

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
- `POST /webhooks/discourse?subscription_id=...` with `X-Discourse-Event`
- `POST /webhooks/gitea?subscription_id=...`
- `POST /webhooks/github?subscription_id=...` with `X-GitHub-Event`

Webhook endpoints accept official platform-shaped payloads, normalize them to `ChatEvent`, write SQLite with idempotent dedupe, and keep cleaned `raw_payload` for Observatory inspection.