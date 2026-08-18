# ChatEvent

`chatevent` provides a typed event specification, SQLite event store, platform
normalizers, and a Web Observatory for collaboration platforms such as Zulip,
Discourse, Gitea, GitHub, and blogs.

It sits at the Event Capture boundary of an agent system:

```text
platform official events/webhooks/API reads -> ChatEvent -> gateway/router -> agent execution
```

Gateway routing and agent execution are intentionally outside this package's
current phase.

## Install from source

The Event Observatory is currently the `0.1.0.dev0` development milestone.

```bash
uv sync --extra serve --extra test
uv run --extra serve chatevent --tree
```

PyPI `0.0.1` contains the initial event envelope and monitor protocol only.

## CLI

```text
chatevent
  --tree                         Print this command tree
  serve [--host HOST] [--port PORT] [--db DB]
                                 Run the local Event Observatory
  schema event|subscription      Print JSON Schema contracts
  record-json FILE [--db DB]     Validate and write one ChatEvent JSON file
  capture zulip-once [options]   Official Zulip event-queue capture pass
```

## Run the Event Observatory

```bash
uv run --extra serve chatevent serve \
  --host 127.0.0.1 \
  --port 18765 \
  --db /home/zhihong/Playground/projects/08-18-chatevent/playground/real-loop/events.db
```

On the server deployment used for validation, Nginx routes:

- `https://event.local.wzhecnu.cn/`
- `https://event.public.wzhecnu.cn/`

Both proxy to `127.0.0.1:18765`.

## Define a normalized event

```python
from datetime import datetime, timezone

from chatevent import CaptureMode, ChatEvent

event = ChatEvent(
    id="issue:owner/repo:42",
    source="gitea",
    kind="issue.opened",
    occurred_at=datetime.now(timezone.utc),
    capture_mode=CaptureMode.PUSH,
    conversation_id="repo:owner/repo",
    payload={"title": "Investigate event routing"},
)

assert event.dedupe_key == "gitea:issue:owner/repo:42"
```

## API surface

- `GET /api/health`
- `GET /api/schema/event`
- `GET /api/schema/subscription`
- `POST /api/subscriptions`
- `GET /api/subscriptions`
- `POST /api/events`
- `GET /api/events`
- `GET /api/events/{source:id}`
- `GET /api/stats`
- `POST /webhooks/zulip?subscription_id=...`
- `POST /webhooks/discourse?subscription_id=...`
- `POST /webhooks/gitea?subscription_id=...`

Webhook endpoints accept official platform-shaped payloads, normalize them to
`ChatEvent`, write SQLite with idempotent dedupe, and keep `raw_payload` for
Observatory inspection.

## Capture examples

Zulip uses the official event queue. Existing ChatRSS-style secret files are
supported without copying secrets:

```bash
uv run --extra serve chatevent capture zulip-once \
  --env-file /path/to/zulip.env \
  --db /path/to/events.db \
  --stream chatrss-quickstart \
  --topic chatevent-real-loop \
  --content "ChatEvent real-loop" \
  --subscription-id zulip-practice
```

Gitea and Discourse can push official webhook-shaped payloads to the webhook
endpoints. REST/API reads are used only for bounded object readback or cursor
reconciliation; do not scan whole sites, all posts, or all repositories.

## Implement a monitor

An adapter exposes an asynchronous stream. It may receive pushed events or poll
a platform with an incremental cursor.

```python
from collections.abc import AsyncIterator

from chatevent import CaptureMode, ChatEvent, EventMonitor


class GiteaMonitor:
    source = "gitea"
    mode = CaptureMode.PULL

    async def events(self, *, cursor: str | None = None) -> AsyncIterator[ChatEvent]:
        if False:  # Replace with incremental API reads.
            yield


monitor: EventMonitor = GiteaMonitor()
```
