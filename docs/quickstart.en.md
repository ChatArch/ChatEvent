# Quick start

ChatEvent captures, normalizes, stores, and queries community facts. The Agent framework decides wakeup, runtime scheduling, and assignments.

## Install

From the source checkout:

```bash
python -m pip install -e '.[serve]'
chatevent --tree
chatevent --tree-brief
chatevent paths --json
chatevent serve --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765/`. ChatEnv manages the default database; compatible paths are `$CHATARCH_HOME/chatevent/events.db` and `~/.chatarch/chatevent/events.db`. `CHATEVENT_DB` overrides the path. The existing legacy database migration remains additive, and the new sequence table is populated for old events without rewriting their bodies.

## Accounts and credentials

Set `CHATEVENT_BOOTSTRAP_USERNAME` and `CHATEVENT_BOOTSTRAP_PASSWORD_FILE` to initialize an administrator. Log in with that account and create an API token. The CLI reads `CHATEVENT_ADMIN_TOKEN` or uses `--username` with `--password-file`. Supply values through an operator-managed ChatEnv profile or service secret file. With no account or admin token, an unauthenticated local-development mode remains; bind it only to a trusted local interface.

## First query

Connect a platform through [monitor registration](monitoring.md), or write an authorized normalized event. Saving a subscription alone does not start capture. Query authorized facts:

```bash
chatevent api query --sort desc --limit 50
chatevent api query --source zulip --kind message.created --sort asc --limit 50
```

Use `next_cursor` for another page or incremental resume. Legacy `GET /api/events` remains for clients, but its `next_since` is not a lossless checkpoint. Observatory multi-select and JSON condition groups run on the server before pagination. See [Filtering and Views](filtering.md) for curl, Python, and saved-view examples, and [Reference](reference.md) for endpoints.

Voice capture retains metadata only, never summary or transcript content.

## Upgrading

Pause collectors and make a consistent SQLite backup first. Version 0.3.0 additively migrates sequences, views, subscription identities, and capture ownership without rewriting existing event bodies or keys. Legacy ownership is snapshotted once from existing subscriptions; records with no known owner are admin-only. Upgrade the server and all collector processes together before resuming capture. Do not keep older writers that bypass the new ownership constraints.
