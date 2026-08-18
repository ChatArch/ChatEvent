# ChatEvent

`chatevent` provides a small, typed event envelope and capture interface for
collaboration platforms such as Zulip, Discourse, Gitea, GitHub, and blogs.

It is intended to sit at the Event Capture boundary of an agent system:

```text
platform events -> ChatEvent -> gateway/router -> agent execution
```

## Install

```bash
pip install chatevent
```

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

The initial release deliberately contains no platform SDK or runtime
dependency. Platform adapters, persistence, filtering, and delivery guarantees
can evolve independently around this stable boundary.

