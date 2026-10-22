# ChatEvent

ChatEvent captures actions from authorized communities, stores normalized events, and exposes them through the Web Observatory, CLI, and API. **Acquisition settings choose what to collect; saved views choose what to read. The Agent framework decides how to act.**

```text
Platform webhook / event queue / API snapshot → ChatEvent → SQLite → server query / Observatory
```

<div class="grid cards" markdown>

- **Connect a community**

    Configure Zulip's official event queue, signed Discourse webhooks, or read-only topic backfill.

    [Acquisition setup](monitoring.md) · [Action coverage](platform-actions.md)

- **Filter relevant facts**

    Combine source, action, actor, target, tags, and time; filter before pagination and save reusable views.

    [Filtering and views](filtering.md)

- **Read from tools and Agents**

    Python, REST, and CLI share query semantics. Resume new facts with stable sequence cursors.

    [Quick start](quickstart.md) · [API reference](reference.md)

- **Discover the interfaces**

    Inspect actual command and interface trees plus implementation status, rather than inferring capture support from a platform catalog.

    [CLI tree](cli-tree.md) · [Interface tree](interface-tree.md) · [Changelog](changelog.md)

</div>

## Runtime and boundaries

The default database is `<chatarch-home>/chatevent/events.db` under ChatEnv, compatible with `$CHATARCH_HOME/chatevent/events.db` and `~/.chatarch/chatevent/events.db`. Use `chatevent paths --json` for the effective paths and `chatevent --tree` for the actual commands.

ChatEvent does not run Agents, dispatch wakeups, assign tasks, or provide a generic posting gateway. Saving a subscription does not start a collector. Platform `capture_status` distinguishes implemented actions from catalog-only entries. Capture is bounded by the configured principal's platform permissions; query filters cannot widen access. Voice capture remains metadata-only.
