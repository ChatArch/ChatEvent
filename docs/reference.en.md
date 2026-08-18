# Reference

## CLI Tree

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

## HTTP API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Health check and current SQLite DB path. |
| `GET` | `/api/schema/event` | Return the `ChatEvent` JSON Schema. |
| `GET` | `/api/schema/subscription` | Return the `Subscription` JSON Schema. |
| `GET` | `/api/platforms` | Return the platform action catalog. |
| `POST` | `/api/subscriptions` | Create or update a subscription. |
| `GET` | `/api/subscriptions` | List subscriptions. |
| `POST` | `/api/events` | Record one normalized `ChatEvent`. |
| `GET` | `/api/events` | Query events with source, kind, subscription, keyword, `since` checkpoint, recent-day, and captured-at range filters. |
| `GET` | `/api/events/{dedupe_key}` | Read one stored event. |
| `GET` | `/api/stats` | Return event/source/duplicate statistics. |
| `POST` | `/webhooks/zulip` | Receive Zulip event-queue/message payloads. |
| `POST` | `/webhooks/discourse` | Receive Discourse webhook payloads. |
| `POST` | `/webhooks/gitea` | Receive Gitea webhook payloads. |
| `POST` | `/webhooks/github` | Receive GitHub webhook payloads. |

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
