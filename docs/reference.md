# 接口参考

## CLI 树

```text
chatevent
  --tree                         Print this command tree
  serve [--host HOST] [--port PORT] [--db DB]
                                 Run the local Event Observatory
  schema event|subscription      Print JSON Schema contracts
  platforms [--json]             List supported platforms and action kinds
  record-json FILE [--db DB]     Validate and write one ChatEvent JSON file
  capture zulip-once [options]   Official Zulip event-queue capture pass
```

## HTTP API

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/api/health` | 健康检查，返回当前 SQLite DB 路径。 |
| `GET` | `/api/schema/event` | 返回 `ChatEvent` JSON Schema。 |
| `GET` | `/api/schema/subscription` | 返回 `Subscription` JSON Schema。 |
| `GET` | `/api/platforms` | 返回平台 action catalog。 |
| `POST` | `/api/subscriptions` | 创建或更新订阅。 |
| `GET` | `/api/subscriptions` | 列出订阅。 |
| `POST` | `/api/events` | 写入一条已规范化 `ChatEvent`。 |
| `GET` | `/api/events` | 查询事件流，可按 source、kind、subscription、关键词、`since` checkpoint 筛选。 |
| `GET` | `/api/events/{dedupe_key}` | 查询单条事件详情。 |
| `GET` | `/api/stats` | 统计事件数、来源数、重复投递数等。 |
| `POST` | `/webhooks/zulip` | 接收 Zulip event queue/message payload。 |
| `POST` | `/webhooks/discourse` | 接收 Discourse webhook payload。 |
| `POST` | `/webhooks/gitea` | 接收 Gitea webhook payload。 |
| `POST` | `/webhooks/github` | 接收 GitHub webhook payload。 |

## 查询事件

```bash
curl -k 'https://event.public.wzhecnu.cn/api/events?source=discourse&kind=reply.created&limit=20'
```

下游系统按 checkpoint 消费：

```bash
curl -k 'https://event.public.wzhecnu.cn/api/events?source=discourse&subscription_id=discourse-practice&since=2026-08-18T12:47:37Z&limit=50'
```

常用参数：

| 参数 | 含义 |
| --- | --- |
| `source` | 平台来源，例如 `discourse`。 |
| `kind` | 事件类型，例如 `reply.created`。 |
| `subscription_id` | 订阅 ID。 |
| `since` | 只返回 `captured_at > since` 的事件；必须带时区，例如 `2026-08-18T12:47:37Z`。 |
| `q` | payload、actor、conversation 等关键词搜索。 |
| `limit` | 返回条数，1 到 500。 |

响应包含 `items`、`count`、`latest_captured_at` 和 `next_since`。consumer 处理成功后保存 `next_since`，下一轮作为 `since` 继续拉取。

## 去重

默认 dedupe key 是：

```text
source:id
```

同一个事件重复投递时不会新增事件行，只会增加 `seen_count`，并在 `/api/stats` 的 `duplicate_count` 里体现。