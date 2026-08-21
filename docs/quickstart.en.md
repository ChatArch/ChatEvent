# Quick Start

## Install the development environment

```bash
uv sync --extra serve --extra test --extra docs
uv run chatevent --tree
uv run chatevent --tree-brief
```

If you only need the API/UI, install at least the `serve` extra:

```bash
uv sync --extra serve
```

## Run the Observatory

```bash
uv run --extra serve chatevent serve \
  --host 127.0.0.1 \
  --port 8765
```

Open:

```text
http://127.0.0.1:8765/
```

The current server demo is exposed at:

```text
https://event.public.wzhecnu.cn/
https://event.local.wzhecnu.cn/
```


## Confirm default paths

You do not need to pass `--db` for normal use. ChatEvent resolves ChatArch home through ChatEnv and stores runtime state under its `chatevent/` directory:

```text
<chatarch-home>/chatevent/events.db
# usually ~/.chatarch/chatevent/events.db
```

Read the effective paths:

```bash
uv run chatevent paths --json
```

If legacy `~/.chatevent/events.db` exists and the new ChatArch-internal database does not, the first default startup copies the legacy database to `~/.chatarch/chatevent/events.db` without deleting the old file.

## Refresh behavior

The Observatory currently uses frontend polling, not WebSocket/SSE.

- It runs `loadAll()` immediately after the page loads.
- It automatically refreshes every **5 seconds**.
- The **Refresh** button triggers an immediate manual refresh.
- Search input refreshes after an approximately **260ms debounce**.
- Source and event-kind filter changes refresh immediately.

Each refresh requests these endpoints in parallel:

```text
GET /api/stats
GET /api/subscriptions
GET /api/events?...filters
GET /api/platforms
```

The delay from a platform action to the UI is therefore:

1. Platform delivery time: webhook delivery is normally seconds; Zulip event queues depend on the running capture pass; API cursors depend on the configured reconciliation interval.
2. The next 5-second frontend poll; click Refresh to check immediately.

## Record one event

```bash
uv run chatevent record-json event.json
```

Minimal event:

```json
{
  "id": "issue:owner/repo:42",
  "source": "gitea",
  "kind": "issue.opened",
  "occurred_at": "2026-08-18T12:00:00Z",
  "capture_mode": "webhook"
}
```

## Inspect the platform action catalog

```bash
uv run chatevent platforms
uv run chatevent platforms --json
```

The same action catalog appears in the Observatory's **Platform actions** panel.