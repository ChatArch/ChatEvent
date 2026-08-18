# 接口参考

## CLI 树

```text
chatevent
  --tree                         Print this command tree
  --version                      Print package version
  paths [--json]                 Show ChatArch-owned runtime paths
  serve [--host HOST] [--port PORT] [--db DB]
                                 Run the local Event Observatory
  schema event|subscription      Print JSON Schema contracts
  platforms [--json]             List supported platforms and action kinds
  record-json FILE [--db DB]     Validate and write one ChatEvent JSON file
  api health                     GET /api/health from a running Event Hub
  api stats                      GET /api/stats
  api platforms                  GET /api/platforms
  api schema event|subscription  GET /api/schema/{kind}
  api subscriptions [--enabled]  GET /api/subscriptions
  api subscription ID            GET /api/subscriptions/{id}
  api events [filters]           GET /api/events
  api event DEDUPE_KEY           GET /api/events/{dedupe_key}
  api record-json FILE           POST /api/events
  api save-subscription FILE     POST /api/subscriptions
  api delete-subscription ID     DELETE /api/subscriptions/{id}
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
| `DELETE` | `/api/subscriptions/{id}` | 删除订阅配置，不删除历史事件。 |
| `POST` | `/api/events` | 写入一条已规范化 `ChatEvent`。 |
| `GET` | `/api/events` | 查询事件流，可按 source、kind、subscription、关键词、`since` checkpoint、最近 N 天或日期区间筛选。 |
| `GET` | `/api/events/{dedupe_key}` | 查询单条事件详情。 |
| `GET` | `/api/stats` | 统计事件数、来源数、重复投递数等。 |
| `POST` | `/webhooks/zulip` | 接收 Zulip event queue/message payload。 |
| `POST` | `/webhooks/discourse` | 接收 Discourse webhook payload。 |
| `POST` | `/webhooks/gitea` | 接收 Gitea webhook payload。 |
| `POST` | `/webhooks/github` | 接收 GitHub webhook payload。 |

## CLI 与 REST API 对应

`chatevent api ...` 是 REST API 的命令行客户端，默认读取 `CHATEVENT_API_URL`，未设置时连接 `http://127.0.0.1:8765`。

| CLI | REST API |
| --- | --- |
| `chatevent api health` | `GET /api/health` |
| `chatevent api stats` | `GET /api/stats` |
| `chatevent api platforms` | `GET /api/platforms` |
| `chatevent api schema event` | `GET /api/schema/event` |
| `chatevent api subscriptions` | `GET /api/subscriptions` |
| `chatevent api subscription <id>` | `GET /api/subscriptions/{id}` |
| `chatevent api events --source discourse --days 7` | `GET /api/events?...` |
| `chatevent api event <dedupe_key>` | `GET /api/events/{dedupe_key}` |
| `chatevent api record-json event.json` | `POST /api/events` |
| `chatevent api save-subscription subscription.json` | `POST /api/subscriptions` |
| `chatevent api delete-subscription <id>` | `DELETE /api/subscriptions/{id}` |


## 查询事件

```bash
curl -k 'https://event.public.wzhecnu.cn/api/events?source=discourse&kind=reply.created&days=7&limit=20'
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
| `since` | consumer checkpoint：只返回 `captured_at > since` 的事件；必须带时区，例如 `2026-08-18T12:47:37Z`。 |
| `days` | 日期快捷筛选：只返回最近 N 天捕获的事件，例如 `days=7`。 |
| `from` | 日期区间开始：只返回 `captured_at >= from` 的事件；必须带时区。 |
| `to` | 日期区间结束：只返回 `captured_at <= to` 的事件；必须带时区。 |
| `q` | payload、actor、conversation 等关键词搜索。 |
| `limit` | 返回条数，1 到 500。 |

响应包含 `items`、`count`、`latest_captured_at` 和 `next_since`。consumer 处理成功后保存 `next_since`，下一轮作为 `since` 继续拉取。Observatory 的“最近 24 小时 / 最近 3 天 / 最近 7 天 / 最近 30 天”使用 `days`；自定义起止时间使用 `from`/`to`。

## 去重

默认 dedupe key 是：

```text
source:id
```

同一个事件重复投递时不会新增事件行，只会增加 `seen_count`，并在 `/api/stats` 的 `duplicate_count` 里体现。

## 存储与线上编辑

订阅配置和事件账本都在 SQLite 中。默认数据库位于 ChatArch 内部：

```text
$CHATARCH_HOME/chatevent/events.db
# 未设置 CHATARCH_HOME 时：~/.chatarch/chatevent/events.db
```

路径优先级是 `--db`、`CHATEVENT_DB`、`$CHATARCH_HOME/chatevent/events.db`、`~/.chatarch/chatevent/events.db`。第一次使用默认路径时，若旧版 `~/.chatevent/events.db` 存在且新数据库不存在，会复制旧库到 ChatArch 内部路径并保留旧文件。

`subscriptions.body` 保存完整 `Subscription` JSON，事件到达后 `last_cursor` / `last_event_at` 也会更新在订阅记录中；`events.body` 保存完整 `ChatEvent` JSON。

Web Observatory 的 `Subscriptions` 标签页可以新建、编辑、启停和删除订阅。生产或公网环境建议设置管理员 token：优先读取 `CHATEVENT_ADMIN_TOKEN`，其次读取 `CHATEVENT_ADMIN_TOKEN_FILE`，再读取默认文件 `$CHATARCH_HOME/chatevent/secrets/admin-token` 或 `~/.chatarch/chatevent/secrets/admin-token`。设置后，`POST /api/subscriptions` 和 `DELETE /api/subscriptions/{id}` 需要 `X-ChatEvent-Admin-Token` header。
