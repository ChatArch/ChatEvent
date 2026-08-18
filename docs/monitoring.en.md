# Register Monitors

Registering a monitor has two layers:

1. Save a ChatEvent `Subscription` describing the platform, scope, and action kinds to observe.
2. Configure the platform's official webhook, event queue, or bounded API cursor so real events reach ChatEvent.

## Create a ChatEvent subscription

```bash
curl -k -X POST https://event.public.wzhecnu.cn/api/subscriptions \
  -H 'Content-Type: application/json' \
  -d '{
    "id": "discourse-practice",
    "source": "discourse",
    "target": "category:agent-runs",
    "label": "Discourse practice",
    "event_kinds": ["topic.created", "post.created", "reply.created"],
    "capture_modes": ["webhook", "api_cursor"],
    "filters": {"category": "agent-runs"},
    "labels": ["practice", "forum"]
  }'
```

The `id` becomes the webhook URL's `subscription_id`, so each captured event can be filtered and can update subscription cursors.

## Discourse webhook

Discourse supports official webhooks. Configure the platform payload URL as:

```text
https://event.public.wzhecnu.cn/webhooks/discourse?subscription_id=discourse-practice
```

Recommended Discourse event types:

```text
topic_created
post_created
post_edited
post_destroyed
post_liked
notification_created
```

The ChatEvent endpoint reads the `X-Discourse-Event` header and normalizes:

- `post_created + post_number == 1` to `post.created`
- `post_created + post_number > 1` to `reply.created`

## Zulip event queue

Zulip should use the official event queue first:

```bash
uv run --extra serve chatevent capture zulip-once \
  --env-file /path/to/zulip.env \
  --stream "chatevent-practice" \
  --topic "real-loop" \
  --subscription-id zulip-practice
```

Secret files are referenced by path only. Do not copy or print secrets. A long-running capture should later be supervised by a proper service/cron/watchdog; the current CLI is a bounded capture pass.

## Gitea webhook

Gitea repository/org webhook payload URL:

```text
https://event.public.wzhecnu.cn/webhooks/gitea?subscription_id=gitea-practice
```

The current normalizer supports issue payloads and the first action catalog. Recommended events:

```text
push
issues
issue_comment
pull_request
release
```

## GitHub webhook

GitHub repository webhook payload URL:

```text
https://event.public.wzhecnu.cn/webhooks/github?subscription_id=github-chatevent
```

GitHub sends the event name through `X-GitHub-Event`. ChatEvent acknowledges `ping` without writing it to the event stream; `push` normalizes to `commit.pushed`.

## Acceptance checks

After registering a monitor, verify with:

```bash
curl -k https://event.public.wzhecnu.cn/api/stats
curl -k 'https://event.public.wzhecnu.cn/api/events?source=discourse&days=7&limit=20'
```

Or open the Observatory, wait up to 5 seconds for automatic refresh, or click **Refresh** manually. The top Event Stream filter keeps only source and time dropdowns; action kinds, subscriptions/channels, keyword search, and custom captured-at ranges live under **Advanced options**, with action-kind multi-select bound to the selected source.
