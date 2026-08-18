# ChatEvent

`chatevent` provides a typed event specification, local event store, and Web
Observatory for collaboration platforms such as Zulip, Discourse, Gitea,
GitHub, and blogs.

It is intended to sit at the Event Capture boundary of an agent system:

```text
platform events -> ChatEvent -> gateway/router -> agent execution
```

## Install

The Event Observatory is currently the `0.1.0.dev0` development milestone.
Install it from this source checkout:

```bash
pip install -e '.[serve]'
```

PyPI `0.0.1` contains the initial event envelope and monitor protocol only.

## Define a normalized event

```python
from datetime import datetime, timezone

from chatevent import CaptureMode, ChatEvent

event = ChatEvent(
    id="42",
    source="gitea",
    kind="issue.opened",
    occurred_at=datetime.now(timezone.utc),
    capture_mode=CaptureMode.PUSH,
    conversation_id="owner/repo#42",
    payload={"title": "Investigate event routing"},
)

assert event.dedupe_key == "gitea:42"
```

## Run the Event Observatory

```bash
chatevent serve
```

Open `http://127.0.0.1:8765`. By default, events and subscriptions are stored
in `~/.chatevent/events.db`.

Register a monitored target:

```bash
curl -X POST http://127.0.0.1:8765/api/subscriptions \
  -H 'content-type: application/json' \
  -d '{
    "label": "Core repository",
    "source": "gitea",
    "target": "owner/repo",
    "event_kinds": ["issue.*", "pull_request.*"],
    "capture_modes": ["push", "pull"]
  }'
```

Adapters write normalized events to `POST /api/events`. The Observatory keeps
the normalized payload and the original `raw_payload`, making it possible to
inspect what an adapter retained or lost.

## Implement a monitor

An adapter exposes an asynchronous stream. It may receive pushed events or
poll a platform with an incremental cursor.

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

Platform adapters, filtering, and delivery guarantees can evolve independently
around this stable capture boundary. Gateway routing and agent execution are
intentionally outside this phase.
