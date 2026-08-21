# ChatEvent

`chatevent` provides a typed event envelope, SQLite event store, platform normalizers, and a Web Observatory for collaboration-event demos.

Current `0.2.0` scope aligns ChatEvent as a standard Chat-series package: ChatStyle renders the CLI tree, ChatEnv owns the configuration contract, and the package keeps focusing on explicit action catalogs for **Discourse, Zulip, Gitea, and GitHub**.

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

`0.2.0` is the standard Chat-series alignment release: it keeps the Event Hub behavior while adding a ChatStyle-rendered CLI tree, ChatEnv config registration, and standard MkDocs command/interface navigation.

## CLI

See [docs/cli-tree.en.md](docs/cli-tree.en.md) for the full CLI tree. You can also read it from the installed command:

```bash
uv run chatevent --tree
```

Core command families:

```text
chatevent
├── api        # REST API client for Event Hub operations
├── capture    # bounded official platform capture passes
├── paths      # ChatEnv/ChatArch-owned runtime paths
├── platforms  # platform action catalog
├── schema     # JSON Schema contracts
└── serve      # local Event Observatory and REST API
```

## Run the Event Observatory

```bash
uv run --extra serve chatevent serve \
  --host 127.0.0.1 \
  --port 8765
```

Open:

```text
http://127.0.0.1:8765/
```

For the current server demo, nginx exposes the service at:

- https://event.local.wzhecnu.cn/
- https://event.public.wzhecnu.cn/

## ChatArch-internal default paths

ChatEvent is a ChatArch-series package, so its default runtime state stays under ChatArch home. ChatArch home is provided by ChatEnv `get_paths().home_dir` first; explicit `CHATARCH_HOME` remains supported for compatibility.

```text
<chatarch-home>/
└── chatevent/
    ├── events.db              # SQLite event ledger and subscription config
    ├── events.db-wal          # SQLite WAL, may exist while running
    ├── events.db-shm          # SQLite shared-memory file, may exist while running
    └── secrets/
        └── admin-token        # optional admin token for subscription mutations
```

Database path precedence:

1. Explicit CLI `--db <path>`;
2. `CHATEVENT_DB=<path>`;
3. ChatEnv `get_paths().home_dir / "chatevent/events.db"`;
4. `$CHATARCH_HOME/chatevent/events.db`;
5. `~/.chatarch/chatevent/events.db`.

On first use of the default path, if legacy `~/.chatevent/events.db` exists and the new database does not, ChatEvent copies it into the ChatArch-internal path and keeps the legacy file in place. Explicit `--db` or `CHATEVENT_DB` does not trigger automatic migration.

Read the effective paths without printing token values:

```bash
uv run chatevent paths --json
```

The SQLite database mainly contains:

- `subscriptions`: subscription configuration and state. `body` stores the full `Subscription` JSON, including updates such as `last_cursor` and `last_event_at`.
- `events`: normalized `ChatEvent` records. `body` stores the full event JSON, while indexed columns keep source, kind, subscription_id, captured_at, and seen_count.

## ChatStyle And ChatEnv Alignment

`chatevent --tree` is rendered by ChatStyle. `chatevent.config:ChatEventConfig` is registered under the ChatEnv `chatenv.configs` entry point. ChatEvent only declares Event Hub env keys: `CHATEVENT_API_URL`, `CHATEVENT_DB`, `CHATEVENT_ADMIN_TOKEN(_FILE)`, `CHATEVENT_API_USERNAME`, `CHATEVENT_API_PASSWORD_FILE`, `CHATEVENT_BOOTSTRAP_USERNAME`, and `CHATEVENT_BOOTSTRAP_PASSWORD_FILE`.

Platform credentials belong to platform-specific ChatEnv profiles or service secret files. For example, `capture zulip-once` defaults to ChatEnv `envs_dir/Zulip/.env`; that file contains `ZULIP_SITE`, `BOT_EMAIL`, and `BOT_API_KEY`, and ChatEvent never prints those values.

Platform-side webhook registration, Zulip secret files, nginx upstreams, and runtime ports are deployment/platform configuration, not SQLite records. Credentials are not written into project files.

## Refresh behavior

The Observatory is currently frontend polling, not WebSocket/SSE:

- loads immediately when the page opens;
- automatically refreshes every **5 seconds**;
- refreshes immediately when clicking **Refresh**;
- search input refreshes after about **260ms debounce**;
- source, kind, and time-range filter changes refresh immediately.

Each refresh calls `/api/stats`, `/api/subscriptions`, `/api/events`, and `/api/platforms`. The top Event Stream filter keeps only source and time dropdowns; action kinds, subscription/channel filters, keyword search, and custom start/end ranges live under Advanced options. Action-kind checkboxes are bound to the selected source so platform-specific actions are not mixed into one flat dropdown.

## Event semantics

Use these fields for product meaning:

- `source`: platform id, e.g. `zulip`, `discourse`, `gitea`, `github`.
- `kind`: platform-specific action kind, e.g. `message.created`, `post.created`, `reply.created`, `issue.opened`, `commit.pushed`, `pull_request.merged`.
- `conversation_id` / `subject_id` / `subject_type`: where it happened and what object changed.
- `capture_mode`: acquisition mechanism, not product action. New integrations use `webhook`, `event_queue`, `api_cursor`, `poll`, `manual_backfill`, `gateway_forward`, `test_fixture`, or `synthetic`. Legacy `push`/`pull` remain readable for old data only.
- `tags`: optional labels/routing labels for filtering. They do **not** define the event source or action.


### Action + carrier target

ChatEvent now models both subscriptions and events as “action + carrier target”:

```text
Subscription = source + actions/event_kinds + scope/target + capture_modes + filters
ChatEvent    = source + action/kind + actor/role + target + subject + payload
```

- `Subscription.target`: a compatibility/display canonical string such as `repo:ChatArch/ChatEvent`, `pull_request:ChatArch/ChatEvent#4`, or `stream:demo/topic:loop`.
- `Subscription.scope`: the structured carrier target, with open `type`, `key`, `display`, `url`, `parent`, and `metadata` fields so platform-specific shapes remain extensible.
- `Subscription.actions`: structured action selectors derived from `event_kinds` by default, or explicitly stored with `kind`, `object_type`, `verb`, and metadata.
- `ChatEvent.action`: the concrete action that happened, such as `pull_request.merged` or `reply.created`.
- `ChatEvent.actor` / `actor_role`: the initiator and platform-specific role, e.g. maintainer, member, bot, or moderator; role is an open string for future refinement.
- `ChatEvent.target`: the concrete object acted on, chained through `parent`, e.g. `repo -> pull_request -> issue_comment` or `zulip_stream -> zulip_topic -> message`.

Example:

```json
{
  "source": "github",
  "target": "pull_request:ChatArch/ChatEvent#4",
  "scope": {
    "type": "pull_request",
    "key": "ChatArch/ChatEvent#4",
    "parent": {"type": "repo", "key": "ChatArch/ChatEvent"}
  },
  "event_kinds": ["pull_request.opened", "pull_request.merged", "issue.commented"],
  "capture_modes": ["webhook", "api_cursor"]
}
```

The Observatory Event Stream now includes a Target column. Opening an event detail shows `Action`, `Action target`, and `Target chain`. The Platform actions panel also shows the target types each action usually attaches to.

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
| GitHub | `webhook`, `api_cursor` | `push`, `commit.pushed`, `issue.opened`, `issue.closed`, `issue.commented`, `pull_request.opened`, `pull_request.synchronize`, `pull_request.closed`, `pull_request.merged`, `workflow_run.requested`, `workflow_run.in_progress`, `workflow_run.completed`, `release.published` |

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
| `chatevent api session` | `GET /api/session` | Validate the current API token or login cookie and return user/role. |
| `chatevent api users` | `GET /api/users` | List users as an administrator. |
| `chatevent api create-user <username> --new-password-file pass.txt` | `POST /api/users` | Create a username/password user; no token is returned. |
| `chatevent api create-token [user_id]` | `POST /api/me/token` or `POST /api/users/{id}/token` | Issue a one-time `arch_xxx` API token for the current account or a target user. |
| `chatevent api delete-user <id>` | `DELETE /api/users/{id}` | Delete a user as an administrator. |
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

The Web Observatory `Subscriptions` tab supports creating, editing, enabling/disabling, and deleting subscriptions through the same REST API. If users or bootstrap credentials are configured, visits to `/` first show a username/password login page and the Observatory is shown only after login; event-stream, stats, platform catalog, schema, and subscription read APIs also require login. The logged-in browser session can edit directly. CLI, model, or programmatic clients can use `X-ChatEvent-Admin-Token` with the account's `arch_xxx` API token, or use the CLI username/password options to login before calling an endpoint.

`CHATEVENT_ADMIN_TOKEN` is only a bootstrap administrator API credential, not a Web login mechanism. Production deployments should configure `CHATEVENT_BOOTSTRAP_USERNAME` and `CHATEVENT_BOOTSTRAP_PASSWORD_FILE` to initialize the administrator account. After logging in, an administrator can create username/password users through `POST /api/users` or `chatevent api create-user <username> --new-password-file pass.txt`. Users generate their own `arch_xxx` API tokens from Account / API Token after login; the server stores only token hashes. `Subscription.owner_user_id` is the first isolation boundary: member accounts create/read/delete only their own subscriptions, while admins can manage all subscriptions. Passwords and tokens must not be written to source, docs, or Git history.

```bash
mkdir -p ~/.chatarch/chatevent/secrets
chmod 700 ~/.chatarch/chatevent ~/.chatarch/chatevent/secrets
printf '<admin-token>\n' > ~/.chatarch/chatevent/secrets/admin-token
printf '<admin-password>\n' > ~/.chatarch/chatevent/secrets/admin-password
chmod 600 ~/.chatarch/chatevent/secrets/admin-token ~/.chatarch/chatevent/secrets/admin-password

CHATEVENT_BOOTSTRAP_USERNAME='admin@example.com' \
CHATEVENT_BOOTSTRAP_PASSWORD_FILE=~/.chatarch/chatevent/secrets/admin-password \
uv run --extra serve chatevent serve
uv run chatevent api create-token --username admin@example.com --password-file ~/.chatarch/chatevent/secrets/admin-password
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
