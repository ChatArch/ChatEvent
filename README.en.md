# ChatEvent

ChatEvent captures community actions, normalizes them as `ChatEvent`, stores them in SQLite, and exposes them through an API, CLI, and Observatory. A `Subscription` sets upstream acquisition scope; a `SavedView` defines a query over captured facts. The Agent framework decides when to read, schedule, and act. **0.3.0** adds multi-action capture, structured filters, and saved views; see the [changelog](CHANGELOG.md).

[中文](README.md) · [Documentation](https://arch.gh.wzhecnu.cn/ChatEvent/) · [Filtering and views](docs/filtering.en.md)

## Install and start

From this source checkout:

```bash
python -m pip install -e '.[serve]'
chatevent --tree
chatevent --tree-brief
chatevent paths --json
chatevent serve --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765/`. For authenticated deployments, initialize an administrator with `CHATEVENT_BOOTSTRAP_USERNAME` and `CHATEVENT_BOOTSTRAP_PASSWORD_FILE`. After login, create an API token; the CLI reads `CHATEVENT_ADMIN_TOKEN` from the environment. Supply values through an operator-managed ChatEnv profile or secret file, never in the repository. With no user or admin token configured, the service retains an explicit unauthenticated local-development mode; bind it only to a trusted local interface.

The database normally lives at `<chatarch-home>/chatevent/events.db` under ChatEnv. `CHATEVENT_DB` overrides it. Compatible paths include `$CHATARCH_HOME/chatevent/events.db` and `~/.chatarch/chatevent/events.db`. `chatevent paths --json` reports the actual path without credentials.

## Capture

The Zulip queue command requests `message`, `update_message`, `delete_message`, `reaction`, `stream`, `subscription`, and `realm_user`, reads for a bounded duration, then deletes the queue:

```bash
chatevent capture zulip-once --env-file ./zulip.env --timeout 30 --subscription-id zulip-community
```

`zulip.env` needs `ZULIP_SITE`, `ZULIP_BOT_EMAIL`, and `ZULIP_BOT_API_KEY` (or their ChatEnv compatible names). `--content` sends a real message and is only for an explicit write exercise. Actions between fresh queue lifetimes can be missed. The topic message-ID path in `capture subscription-once` recovers currently visible message creations only; it cannot recover edit or reaction history.

Configure a Discourse hook to `https://events.example.org/webhooks/discourse`. On ChatEvent, set `CHATEVENT_DISCOURSE_WEBHOOK_SECRET_FILE`, `CHATEVENT_DISCOURSE_INSTANCE`, and optionally `CHATEVENT_DISCOURSE_SUBSCRIPTION_ID` to bind the hook to one instance and subscription. The server verifies `X-Discourse-Event-Signature` over raw request bytes. Other webhooks and normalized `POST /api/events` require authorized token/session credentials when authentication is configured. A bounded, read-only snapshot of a current Discourse topic and its posts is available:

```bash
chatevent capture discourse-topic-backfill --base-url https://forum.example.org --topic-id 18 --limit 50 --api-key-env DISCOURSE_API_KEY --api-username api-user
```

The snapshot does not reconstruct historical edits or deletions. Saving/enabling a `Subscription` configures acquisition; it does not start a collector. The platform catalog is broader than the implemented capture adapters; see the [action coverage table](docs/platform-actions.en.md).

## Query and views

`GET /api/query` filters on the server before paging by immutable insertion sequence. Use `sort=desc` to browse and `sort=asc` with `next_cursor` for lossless page traversal. Legacy `GET /api/events` remains available, but its `next_since` is the newest timestamp in one page and **is not** a reliable backlog checkpoint.

```bash
cat > filter.json <<'JSON'
{"all":[{"field":"source","op":"eq","value":"zulip"},{"field":"kind","op":"in","value":["message.created","reaction.added"]},{"not":{"field":"actor.role","op":"eq","value":"bot"}}]}
JSON
chatevent api query --filter-file filter.json --sort asc --limit 50
chatevent api save-view view.json
chatevent api views
```

Example `view.json`: `{"name":"Community facts","filter":{"field":"source","op":"eq","value":"zulip"},"sort":"asc"}`. Views belong to the authenticated account. Members can read only events linked to their own subscriptions; unowned legacy events are admin-only. The dashboard supports multi-select conditions, JSON condition groups, paging, and saving/loading/deleting views. The [filtering guide](docs/filtering.en.md) has curl and Python examples and exact missing/null semantics.

ChatEvent does not run Agents, wakeup dispatch, task queues, assignment, or a generic posting gateway. Voice capture remains metadata-only.
