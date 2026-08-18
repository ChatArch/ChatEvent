# Reference

## CLI Tree

```text
chatevent
  --tree                         Print this command tree
  --version                      Print package version
  paths [--json]                 Show ChatArch-owned runtime paths
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

## HTTP API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Health check and current SQLite DB path. |
| `GET` | `/api/schema/event` | Return the `ChatEvent` JSON Schema. |
| `GET` | `/api/schema/subscription` | Return the `Subscription` JSON Schema. |
| `GET` | `/api/platforms` | Return the platform action catalog. |
| `POST` | `/api/subscriptions` | Create or update a subscription. |
| `GET` | `/api/subscriptions` | List subscriptions. |
| `DELETE` | `/api/subscriptions/{id}` | Delete a subscription without deleting captured events. |
| `POST` | `/api/events` | Record one normalized `ChatEvent`. |
| `GET` | `/api/events` | Query events with source, kind, subscription, keyword, `since` checkpoint, recent-day, and captured-at range filters. |
| `GET` | `/api/events/{dedupe_key}` | Read one stored event. |
| `GET` | `/api/stats` | Return event/source/duplicate statistics. |
| `POST` | `/webhooks/zulip` | Receive Zulip event-queue/message payloads. |
| `POST` | `/webhooks/discourse` | Receive Discourse webhook payloads. |
| `POST` | `/webhooks/gitea` | Receive Gitea webhook payloads. |
| `POST` | `/webhooks/github` | Receive GitHub webhook payloads. |

## CLI and REST API mapping

`chatevent api ...` is the command-line client for the REST API. It reads `CHATEVENT_API_URL` by default and falls back to `http://127.0.0.1:8765`.

| CLI | REST API |
| --- | --- |
| `chatevent api health` | `GET /api/health` |
| `chatevent api stats` | `GET /api/stats` |
| `chatevent api platforms` | `GET /api/platforms` |
| `chatevent api schema event` | `GET /api/schema/event` |
| `chatevent api subscriptions` | `GET /api/subscriptions` |
| `chatevent api subscription <id>` | `GET /api/subscriptions/{id}` |
| `chatevent api events --source discourse --days 7` | `GET /api/events?...` |
| `chatevent api event <dedupe_key>` | `GET /api/events/{dedupe_key}` |
| `chatevent api record-json event.json` | `POST /api/events` |
| `chatevent api save-subscription subscription.json` | `POST /api/subscriptions` |
| `chatevent api delete-subscription <id>` | `DELETE /api/subscriptions/{id}` |



## Action and carrier target fields

Both `ChatEvent` and `Subscription` support structured action targets while keeping old fields compatible:

- `Subscription.target`: canonical string for display and hand-written config.
- `Subscription.scope`: structured carrier target with `type`, `key`, `display`, `url`, `parent`, and `metadata`; `type` is open-ended.
- `Subscription.actions`: structured action selectors; if only `event_kinds` is provided, the service derives them automatically.
- `ChatEvent.action`: concrete action with `kind`, `object_type`, `verb`, and `metadata`.
- `ChatEvent.actor` / `actor_role`: initiator and platform-specific role; role stays an open string, e.g. maintainer, member, bot, or moderator.
- `ChatEvent.target`: concrete object acted on; `parent` links repo/PR/comment or stream/topic/message carrier chains.

Old clients that only send `kind`, `subject_id`, and `subject_type` remain valid. New adapters write full `action` and `target` whenever possible.

## Query events

```bash
curl -k 'https://event.public.wzhecnu.cn/api/events?source=discourse&kind=reply.created&days=7&limit=20'
```

Downstream systems consume by checkpoint:

```bash
curl -k 'https://event.public.wzhecnu.cn/api/events?source=discourse&subscription_id=discourse-practice&since=2026-08-18T12:47:37Z&limit=50'
```

Common parameters:

| Parameter | Meaning |
| --- | --- |
| `source` | Platform source such as `discourse`. |
| `kind` | Event kind such as `reply.created`. |
| `subscription_id` | Subscription id. |
| `since` | Consumer checkpoint: return only events with `captured_at > since`; timezone is required, e.g. `2026-08-18T12:47:37Z`. |
| `days` | Shortcut date filter: return events captured in the last N days, e.g. `days=7`. |
| `from` | Captured-at range start: return events with `captured_at >= from`; timezone is required. |
| `to` | Captured-at range end: return events with `captured_at <= to`; timezone is required. |
| `q` | Keyword search across payload, actor, and conversation fields. |
| `limit` | Number of events to return, from 1 to 500. |

Responses include `items`, `count`, `latest_captured_at`, and `next_since`. Consumers should save `next_since` after successful processing and send it as `since` on the next poll. The Observatory uses `days` for the last 24 hours / 3 days / 7 days / 30 days presets, and `from`/`to` for custom ranges.

## Deduplication

The default dedupe key is:

```text
source:id
```

Repeated delivery of the same event does not create a new row; it increments `seen_count` and contributes to `/api/stats` `duplicate_count`.

## Storage and online editing

Subscription configuration and the event ledger are stored in SQLite. The default database is ChatArch-internal:

```text
$CHATARCH_HOME/chatevent/events.db
# when CHATARCH_HOME is unset: ~/.chatarch/chatevent/events.db
```

Path precedence is `--db`, `CHATEVENT_DB`, `$CHATARCH_HOME/chatevent/events.db`, then `~/.chatarch/chatevent/events.db`. On first default-path use, if legacy `~/.chatevent/events.db` exists and the new database does not, ChatEvent copies it into the ChatArch-internal path and keeps the legacy file.

`subscriptions.body` stores the full `Subscription` JSON, including `last_cursor` and `last_event_at` updates after events arrive; `events.body` stores the full `ChatEvent` JSON.

The Web Observatory `Subscriptions` tab can create, edit, enable/disable, and delete subscriptions. For production or public deployments, configure an admin token: `CHATEVENT_ADMIN_TOKEN` first, then `CHATEVENT_ADMIN_TOKEN_FILE`, then the default file `$CHATARCH_HOME/chatevent/secrets/admin-token` or `~/.chatarch/chatevent/secrets/admin-token`. Once configured, `POST /api/subscriptions` and `DELETE /api/subscriptions/{id}` require the `X-ChatEvent-Admin-Token` header.

## Login, User Management, And Isolation

ChatEvent now includes a lightweight token login skeleton:

- `GET /api/session`: validate the current `X-ChatEvent-Admin-Token` and return `admin_required`, `authenticated`, `user`, and whether the caller is the bootstrap admin.
- `GET /api/users`: list users as an administrator.
- `POST /api/users`: create a user and return a one-time `arch_xxx` token; the server stores only the token hash.
- `DELETE /api/users/{id}`: delete a user as an administrator.

`CHATEVENT_ADMIN_TOKEN` / `secrets/admin-token` is the bootstrap administrator credential for creating the first users. `Subscription.owner_user_id` is the current isolation boundary: subscriptions created by member tokens are automatically owned by that user; members can only read, update, and delete their own subscriptions; bootstrap/admin tokens can manage all subscriptions. The event stream remains an Observatory debugging view for now and can be tightened by tenant/user owner later.
