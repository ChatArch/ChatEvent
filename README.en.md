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
  api health                     GET /api/health from a running Event Hub
  api stats                      GET /api/stats
  api platforms                  GET /api/platforms
  api schema event|subscription  GET /api/schema/{kind}
  api subscriptions [--enabled]  GET /api/subscriptions
  api subscription ID            GET /api/subscriptions/{id}
  api events [filters]           GET /api/events
  api event DEDUPE_KEY           GET /api/events/{dedupe_key}
  api record-json FILE           POST /api/events
  api save-subscription FILE     POST /api/subscriptions
  api delete-subscription ID     DELETE /api/subscriptions/{id}
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

## Configuration and storage location

ChatEvent writes the runtime event ledger to SQLite. The database path comes from `--db` or `CHATEVENT_DB`; when neither is set, it uses `~/.chatevent/events.db`. The current online demo database is:

```text
/home/zhihong/Playground/projects/08-18-chatevent/playground/real-loop/events.db
```

The SQLite database mainly contains:

- `subscriptions`: subscription configuration and state. `body` stores the full `Subscription` JSON, including updates such as `last_cursor` and `last_event_at`.
- `events`: normalized `ChatEvent` records. `body` stores the full event JSON, while indexed columns keep source, kind, subscription_id, captured_at, and seen_count.

Platform-side webhook registration, Zulip secret files, nginx upstreams, and runtime ports are deployment/platform configuration, not SQLite records. Credentials are not written into project files.

## Refresh behavior

The Observatory is currently frontend polling, not WebSocket/SSE:

- loads immediately when the page opens;
- automatically refreshes every **5 seconds**;
- refreshes immediately when clicking **Refresh**;
- search input refreshes after about **260ms debounce**;
- source, kind, and time-range filter changes refresh immediately.

Each refresh calls `/api/stats`, `/api/subscriptions`, `/api/events`, and `/api/platforms`. The event stream can show all events, the last 24 hours, the last 3/7/30 days, or a custom captured-at start/end range.

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
- `DELETE /api/subscriptions/{id}`
- `POST /api/events`
- `GET /api/events`, with `source`, `kind`, `subscription_id`, `q`, `since`, `days`, `from`, `to`, and `limit` filters
- `GET /api/events/{dedupe_key}`
- `GET /api/stats`
- `POST /webhooks/zulip?subscription_id=...`
- `POST /webhooks/discourse?subscription_id=...` with `X-Discourse-Event`
- `POST /webhooks/gitea?subscription_id=...`
- `POST /webhooks/github?subscription_id=...` with `X-GitHub-Event`

Webhook endpoints accept official platform-shaped payloads, normalize them to `ChatEvent`, write SQLite with idempotent dedupe, and keep cleaned `raw_payload` for Observatory inspection.

## CLI and REST API mapping

ChatEvent acts as a lightweight Event Hub: platform official webhooks / event queues / API cursors bring raw actions in, ChatEvent normalizes, deduplicates, and stores them, and downstream systems read events through the REST API. The CLI `api` command group is the command-line counterpart to those REST endpoints.

The default base URL is `CHATEVENT_API_URL`, falling back to `http://127.0.0.1:8765`; every API command also accepts `--base-url`.

| CLI | REST API | Purpose |
| --- | --- | --- |
| `chatevent api health` | `GET /api/health` | Read service health and DB path. |
| `chatevent api stats` | `GET /api/stats` | Read event/source/duplicate statistics. |
| `chatevent api events --source discourse --days 7` | `GET /api/events?...` | Query the event stream with source/kind/subscription/q/since/days/from/to/limit filters. |
| `chatevent api event <dedupe_key>` | `GET /api/events/{dedupe_key}` | Read one concrete event. |
| `chatevent api record-json event.json` | `POST /api/events` | Write one normalized `ChatEvent` JSON document to the Event Hub. |
| `chatevent api subscriptions` | `GET /api/subscriptions` | List subscriptions. |
| `chatevent api save-subscription subscription.json` | `POST /api/subscriptions` | Save a subscription through REST. |
| `chatevent api delete-subscription <id>` | `DELETE /api/subscriptions/{id}` | Delete a subscription without deleting captured events. |

Examples:

```bash
uv run chatevent api events \
  --base-url https://event.public.wzhecnu.cn \
  --source discourse \
  --days 7 \
  --limit 20

uv run chatevent api event \
  --base-url https://event.public.wzhecnu.cn \
  'discourse:post:35'
```

## Online editing and safety settings

The Web Observatory `Subscriptions` tab supports creating, editing, enabling/disabling, and deleting subscriptions through the same REST API. If `CHATEVENT_ADMIN_TOKEN` is set, subscription mutation requests must include `X-ChatEvent-Admin-Token`; the web page prompts for the token after the first 401 response and stores it only in browser sessionStorage.

```bash
CHATEVENT_ADMIN_TOKEN=... uv run --extra serve chatevent serve --db ./events.db
uv run chatevent api save-subscription subscription.json --admin-token ...
uv run chatevent api delete-subscription discourse-practice --admin-token ...
```

Deleting a subscription only removes the `subscriptions` record. Already captured `events` remain in the ledger.

## Downstream consumption

The Observatory is only one debugging consumer. Other systems can poll the Event Hub with a checkpoint:

```bash
curl -k 'https://event.public.wzhecnu.cn/api/events?source=discourse&subscription_id=discourse-practice&since=2026-08-18T12:47:37Z&limit=50'
```

The response includes:

- `items`: normalized `ChatEvent` records;
- `count`: matched records in this page;
- `next_since`: the latest `captured_at` in the page. Save it after successful processing and send it as `since` on the next poll.

Recommended loop:

1. The consumer stores its own `last_since` checkpoint.
2. It calls `/api/events?since=<last_since>&source=...&kind=...&subscription_id=...`.
3. It processes each `event` idempotently by `source/kind/subject_id`.
4. After all events succeed, it stores response `next_since` as the next checkpoint.
5. If `count=0`, keep the old checkpoint and poll later.
