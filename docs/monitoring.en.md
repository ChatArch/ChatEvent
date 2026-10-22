# Register acquisition scope

A `Subscription` describes upstream platform, target, authorized scope, and requested actions. A `SavedView` queries facts already in the ledger. Saving or enabling a subscription does not start a background collector. Platform credentials remain in operator-managed ChatEnv profiles or service secret files.

## Create a subscription

Provide an account API token through `CHATEVENT_ADMIN_TOKEN`. The server binds a member's `owner_user_id` to that account.

```bash
curl -X POST 'https://events.example.org/api/subscriptions' \
  -H "X-ChatEvent-Admin-Token: $CHATEVENT_ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  --data '{"id":"zulip-community","source":"zulip","target":"stream:community/topic:news","event_kinds":["*"],"capture_modes":["event_queue"]}'
```

Members query only facts linked to subscriptions they own. Unowned historical events are admin-only. A query view cannot widen access.

## Zulip event queue

Configure `ZULIP_SITE`, `ZULIP_BOT_EMAIL`, and `ZULIP_BOT_API_KEY` (or compatible Actor names) in an operator-managed env file. Do not put values in docs, Git, or CLI arguments.

```bash
chatevent capture zulip-once --env-file ./zulip.env --subscription-id zulip-community --timeout 30
```

The command registers one official queue, requests message creation, edits/moves, single/bulk deletion, reactions, stream, subscription, and realm_user events, dispatches them, then deletes the queue. Its output includes `captured`, `created`, `unsupported`, `scope_unknown`, and `control`. With `--stream`/`--topic`, sparse events without verifiable context fail closed and increment `scope_unknown`. `--content` sends a real message and is only for an explicit write exercise. Fresh queues leave potential gaps between runs. For continuous collection, use an externally supervised bounded but sufficiently long capture window; repeated short polls do not provide complete queue history.

The existing `capture subscription-once --subscription-id zulip-community` is a topic message-ID cursor backfill for currently visible message creations. It cannot restore reaction or edit history during a queue outage or recover deleted messages.

## Discourse webhook and read-only backfill

In Discourse administration, set the hook URL to `https://events.example.org/webhooks/discourse`, select the core events in the [coverage table](platform-actions.md), and configure a webhook secret. Configure ChatEvent:

```text
CHATEVENT_DISCOURSE_WEBHOOK_SECRET_FILE=<operator-managed-secret-file>
CHATEVENT_DISCOURSE_INSTANCE=https://forum.example.org
CHATEVENT_DISCOURSE_SUBSCRIPTION_ID=discourse-community
```

The bound subscription must already exist with source=discourse. ChatEvent verifies `X-Discourse-Event-Signature: sha256=...` over the raw request body, reads `X-Discourse-Event` for the action name and `X-Discourse-Event-Type` for the wrapper type. It accepts `X-Discourse-Instance` for routing only when it matches the configured instance binding; an untrusted header or payload cannot set owner/instance. Without a configured signature secret, the webhook requires authorized ChatEvent API token or session credentials. Other platform webhooks also require authorized ingest credentials when authentication is configured.

Read a bounded current topic/posts snapshot:

```bash
chatevent capture discourse-topic-backfill --base-url https://forum.example.org --topic-id 18 --limit 50 --subscription-id discourse-community --api-key-env DISCOURSE_API_KEY --api-username api-user
```

The caller's environment supplies `DISCOURSE_API_KEY`. The command reads `/t/{id}.json` and up to 100 `/posts/{id}.json` objects and writes only the local ChatEvent database. A snapshot is the current visible state, not historical edits, deletions, or restorations. Discourse retries can create fresh delivery-row IDs; deduplication uses action, object, revision/time, and canonical payload fingerprint rather than `X-Discourse-Event-Id` alone.

Check captured facts:

```bash
chatevent api stats
chatevent api query --source discourse --sort desc --limit 50
```

Voice remains metadata-only. The platform action catalog is a capability directory, not proof that a collector is running. See [Filtering and Views](filtering.md) for query details.
