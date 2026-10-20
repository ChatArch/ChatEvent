# Reference

## Event model and storage

The `ChatEvent` 1.0 envelope retains `id`, `source`, `kind`, `occurred_at`, `captured_at`, `capture_mode`, `subscription_id`, `actor`, `target`, `conversation_id`, `subject_id`, `payload`, `raw_payload`, and `metadata`; `instance` is an optional addition. Native object identity belongs in `subject_id`, separate from the event `id` for creation and later changes. Old keys without instance remain `source:id`; instance-aware keys include an instance hash. Duplicate deliveries increment `seen_count` without replacing the first body.

Existing rows stay in SQLite `events`. New `event_offsets` backfills immutable sequences for old rows in capture-time/key order and appends a sequence for new rows. `saved_views` holds account owner, name, filter, and sort. ChatEnv manages the default database, with compatible paths `$CHATARCH_HOME/chatevent/events.db` and `~/.chatarch/chatevent/events.db`; `chatevent paths --json` reports the actual path.

## HTTP and CLI

| HTTP | Real CLI | Purpose |
| --- | --- | --- |
| `GET /api/query` | `chatevent api query` | Structured filter, `sort=asc|desc`, `cursor`, `limit`; returns `next_cursor`/`has_more` |
| `GET /api/events` | `chatevent api events` | Legacy shorthand; `next_since` is not lossless |
| `GET /api/events/{dedupe_key}` | `chatevent api event` | Event detail |
| `POST /api/events` | `chatevent api record-json` | Authorized normalized event write |
| `GET /api/views` | `chatevent api views` | Current account's views |
| `GET /api/views/{id}` | `chatevent api view` | View detail |
| `POST /api/views` | `chatevent api save-view` | Create view |
| `PUT /api/views/{id}` | `chatevent api update-view` | Update view; body includes matching id |
| `DELETE /api/views/{id}` | `chatevent api delete-view` | Delete view |
| `GET /api/subscriptions` | `chatevent api subscriptions` | Acquisition configuration, not a view |
| `POST /api/subscriptions` | `chatevent api save-subscription` | Save acquisition configuration |
| `GET /api/stats` | `chatevent api stats` | Counters over authorized events |
| `GET /api/platforms` | `chatevent api platforms` | Capability catalog, not collector health |
| `POST /webhooks/discourse` | — | Wrapped payload; configurable raw-body HMAC |
| `POST /webhooks/zulip`, `/webhooks/gitea`, `/webhooks/github` | — | Ingest credentials required when authentication is configured |

`GET /api/query` accepts URL-encoded JSON `filter` or `view_id`, plus `source`, `kind`, `subscription_id` shorthand, `sort`, `cursor`, and `limit`. Unknown parameters, fields, or mismatched cursors return 422. `filter` and `view_id` cannot be combined. See [Filtering and Views](filtering.md) for the complete AST and curl/Python examples.

Legacy `GET /api/events` still takes `source`, `kind`, `subscription_id`, `q`, `since`, `days`, `from`, `to`, and `limit`. It returns a bounded newest-first captured-time page; its `next_since` is only the latest time in that page and **cannot guarantee** lossless incremental consumption. Migrate consumers to `/api/query?sort=asc`.

## Permissions and capture

With user or admin token authentication configured, member event lists, detail, structured query, and stats are restricted by immutable capture ownership; unowned legacy events are admin-only. Subscription IDs stay bound to their original owner, and deleting a subscription never transfers historical event access. Member views are owner-scoped; admins can inspect and manage all views. Submitted owner IDs do not set new view ownership. Member writes require an owned subscription. Cookie-authenticated writes require CSRF; API tokens do not. With no authentication configured, an unauthenticated local-development mode remains and must be used only on a trusted local interface. Raw payload is returned only to authorized readers.

The Discourse hook requires both `CHATEVENT_DISCOURSE_INSTANCE` and `CHATEVENT_DISCOURSE_SUBSCRIPTION_ID` when a signing secret is configured; missing bindings return 503 without ingestion. Set the secret through `CHATEVENT_DISCOURSE_WEBHOOK_SECRET_FILE` or `CHATEVENT_DISCOURSE_WEBHOOK_SECRET`. It verifies SHA-256 HMAC over raw bytes, and an instance header cannot assign ownership. Other webhooks require authorized ingest credentials. `capture zulip-once` is a bounded official queue reader; `capture subscription-once` is a message-creation-only topic cursor backfill; `capture discourse-topic-backfill` reads a current-object snapshot. See [Platform Actions](platform-actions.md) for coverage.

ChatEvent provides no Agent runner, wakeup dispatcher, task queue, assignment, or generic platform write gateway. ChatStyle renders `chatevent --tree` and `chatevent --tree-brief`; the executed [CLI tree](cli-tree.md) is included.
