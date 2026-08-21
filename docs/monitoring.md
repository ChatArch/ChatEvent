# 注册监控

注册监控分两层：

1. 在 ChatEvent 里保存一个 `Subscription`，说明要观察哪个平台、哪个范围、哪些 action。
2. 在对应平台上配置官方 webhook、event queue 或 bounded API cursor，让事件真正送到 ChatEvent。

## 创建 ChatEvent subscription

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

`id` 会作为 webhook URL 的 `subscription_id`，写入每条事件，方便筛选和 cursor 更新。

## Discourse webhook

Discourse 支持官方 webhook。平台侧 payload URL 配置为：

```text
https://event.public.wzhecnu.cn/webhooks/discourse?subscription_id=discourse-practice
```

建议选择这些 Discourse event type：

```text
topic_created
post_created
post_edited
post_destroyed
post_liked
notification_created
```

ChatEvent endpoint 会读取 `X-Discourse-Event` header，并把：

- `post_created + post_number == 1` 规范化为 `post.created`
- `post_created + post_number > 1` 规范化为 `reply.created`

## Zulip event queue

Zulip 优先用官方 event queue：

```bash
uv run --extra serve chatevent capture zulip-once \
  --env-file ~/.chatarch/envs/Zulip/.env \
  --stream "chatevent-practice" \
  --topic "real-loop" \
  --subscription-id zulip-practice
```

平台 secret 由 ChatEnv profile 或服务 secret 文件管理；ChatEvent 只通过路径引用，不复制、不打印。长时间运行时应由后续 supervisor/cron/watchdog 管理，当前 CLI 是 bounded capture pass。

## Gitea webhook

Gitea repo/org webhook 的 payload URL：

```text
https://event.public.wzhecnu.cn/webhooks/gitea?subscription_id=gitea-practice
```

当前 normalizer 已支持 issue payload 和部分 repo action 目录。推荐事件：

```text
push
issues
issue_comment
pull_request
release
```

## GitHub webhook

GitHub repo webhook 的 payload URL：

```text
https://event.public.wzhecnu.cn/webhooks/github?subscription_id=github-chatevent
```

GitHub 事件名来自 `X-GitHub-Event` header。ChatEvent 会 ACK `ping`，但不把 ping 写入事件流；`push` 会规范化为 `commit.pushed`。

## 验收

注册后用以下接口验收：

```bash
curl -k https://event.public.wzhecnu.cn/api/stats
curl -k 'https://event.public.wzhecnu.cn/api/events?source=discourse&days=7&limit=20'
```

或者打开 Observatory，等待最多 5 秒自动刷新，也可以手动点击 **刷新**；事件流顶层只保留来源和时间两个下拉框，事件类型、订阅/渠道、关键词和自定义日期区间放在 **高级选项** 里，事件类型多选会随来源联动。
