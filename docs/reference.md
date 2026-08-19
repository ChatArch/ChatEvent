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



## 动作与承载目标字段

`ChatEvent` 与 `Subscription` 都支持结构化 action target，且保留旧字段兼容：

- `Subscription.target`：canonical string，适合快速展示和手写配置。
- `Subscription.scope`：结构化承载目标，字段为 `type`、`key`、`display`、`url`、`parent`、`metadata`；`type` 是开放字符串。
- `Subscription.actions`：结构化 action selectors；如果只传 `event_kinds`，服务会自动派生。
- `ChatEvent.action`：真实动作，字段为 `kind`、`object_type`、`verb`、`metadata`。
- `ChatEvent.actor` / `actor_role`：发起人和平台角色，角色保持开放字符串，例如 maintainer、member、bot、moderator。
- `ChatEvent.target`：本次动作作用对象；`parent` 串起 repo/PR/comment 或 stream/topic/message 等承载链。

旧客户端只传 `kind`、`subject_id`、`subject_type` 仍然可写入；新 adapter 会尽量写入完整 `action` 和 `target`。

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

Web Observatory 的 `Subscriptions` 标签页可以新建、编辑、启停和删除订阅。生产或公网环境应配置用户登录，并可以保留 bootstrap API token：优先读取 `CHATEVENT_ADMIN_TOKEN`，其次读取 `CHATEVENT_ADMIN_TOKEN_FILE`，再读取默认文件 `$CHATARCH_HOME/chatevent/secrets/admin-token` 或 `~/.chatarch/chatevent/secrets/admin-token`。bootstrap token 只用于 API/CLI 初始化或恢复管理权限，不是 Web 登录凭据。

## 登录、用户管理与隔离

ChatEvent 的最小登录模型是账号密码 + API token：

- `GET /`：配置用户或 bootstrap 凭据后，未登录只返回账号密码登录页；登录后才返回 Observatory。
- `POST /api/login`：校验 `username` / `password` 并设置浏览器 cookie。
- `POST /api/logout`：清除浏览器 cookie。
- `GET /api/session`：校验当前 `X-ChatEvent-Admin-Token` 或 cookie，返回 `admin_required`、`authenticated`、`user` 与是否为 bootstrap admin。
- `GET /api/users`：管理员列出用户。
- `POST /api/users`：管理员创建账号密码用户；服务端只保存 password hash。
- `POST /api/me/token`：当前登录用户为自己的账号生成一次性 `arch_xxx` API token。
- `POST /api/users/{id}/token`：管理员为指定用户生成一次性 API token。
- `DELETE /api/users/{id}`：管理员删除用户。

配置管理员 token 或用户后，`/api/stats`、`/api/events`、`/api/events/{dedupe_key}`、schema、platforms、subscriptions 等读取 API 都需要登录。事件写入接口和 webhook 接口保持可达，用于接收平台事件。

`CHATEVENT_BOOTSTRAP_USERNAME` 与 `CHATEVENT_BOOTSTRAP_PASSWORD_FILE` 可初始化第一个管理员账号。`CHATEVENT_ADMIN_TOKEN` / `secrets/admin-token` 是 bootstrap 管理员 API 凭据，用于 CLI/模型/API 创建用户或恢复管理权限。`Subscription.owner_user_id` 是当前数据隔离边界：member 账号创建的订阅自动归属该用户；member 只能读取、修改、删除自己的订阅；admin 可管理全部订阅。事件流仍保留 Observatory 调试视图，后续可进一步按 tenant/user owner 收敛事件读取范围。
