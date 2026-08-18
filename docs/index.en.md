# ChatEvent

ChatEvent is ChatArch's collaboration-event observability layer. It captures official events from Zulip, Discourse, Gitea, and GitHub, normalizes them into a Pydantic `ChatEvent`, stores them in SQLite, and exposes a Web Observatory for inspection and debugging.

```text
official platform event / webhook / API cursor
  → ChatEvent normalizer
  → SQLite event store
  → Observatory / API
```

<div class="grid cards" markdown>

- **Run the Observatory**

  Start `chatevent serve`, open the browser UI, and inspect stats, subscriptions, event rows, and raw payloads.

  [Quick start](quickstart.md)

- **Register monitors**

  Create subscriptions for Discourse category/topic, Zulip stream/topic, and Gitea/GitHub repositories; connect platform webhooks or event queues to ChatEvent.

  [Register monitors](monitoring.md)

- **Review action catalog**

  ChatEvent treats supported platform actions as first-class entries instead of overloading arbitrary `tag` values.

  [Platforms and events](platform-actions.md)

- **Use API / CLI**

  Write and query events through HTTP; use `chatevent api ...` as the CLI counterpart to the REST API.

  [Reference](reference.md)

- **Confirm default paths**

  Runtime state defaults to `$CHATARCH_HOME/chatevent/` or `~/.chatarch/chatevent/`; verify with `chatevent paths --json`.

  [Quick start](quickstart.md)

</div>

## Current boundary

- ChatEvent only **captures, normalizes, deduplicates, stores, and observes** events.
- It does not execute agents, create tasks, or make routing decisions in the current scope.
- Platform REST APIs are used only for object completion after official events, bounded cursor reconciliation, and acceptance readback; ChatEvent itself exposes a standard REST API for downstream event write, query, and checkpoint consumption.
- Default install/runtime state, the SQLite ledger, and the optional admin-token file all live under `$CHATARCH_HOME/chatevent/`, falling back to `~/.chatarch/chatevent/`.
- It does not scan whole sites, all messages, complete forum history, or full repository history.

## Event semantics

- `source`: platform id such as `zulip`, `discourse`, `gitea`, or `github`.
- `target`: subscription scope such as stream/topic, category/topic, or repo/org.
- `kind`: business action such as `message.created`, `reply.created`, or `issue.opened`.
- `capture_mode`: acquisition mechanism such as `webhook`, `event_queue`, or `api_cursor`.
- `tags`: optional filtering/routing labels; they do not define the event action.

## Current demo endpoint

The current server demo is exposed at:

- https://event.public.wzhecnu.cn/
- https://event.local.wzhecnu.cn/

Add authentication, signature verification, and supervised service management before treating the demo as production. The service itself binds to loopback and is exposed through nginx.