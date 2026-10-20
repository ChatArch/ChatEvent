# 接口参考

## 事件模型与存储

`ChatEvent` 1.0 envelope 保留 `id`、`source`、`kind`、`occurred_at`、`captured_at`、`capture_mode`、`subscription_id`、`actor`、`target`、`conversation_id`、`subject_id`、`payload`、`raw_payload` 和 `metadata`；新增可选 `instance`。原生对象 ID 属于 `subject_id`，创建与后续变更的 event `id` 分开。未设置 instance 的旧 key 保持 `source:id`；设置时 key 含实例 hash。重复投递增加 `seen_count`，原事件 body 不被替换。

SQLite 的 `events` 表保持原行；新 `event_offsets` 表为旧事件按捕获时间和 key 稳定回填不可变序号，新事件入库时追加序号。`saved_views` 存账号 owner、名字、过滤表达式与排序。默认库由 ChatEnv 管理，兼容 `$CHATARCH_HOME/chatevent/events.db` 与 `~/.chatarch/chatevent/events.db`；`chatevent paths --json` 可回读路径。

## HTTP 和 CLI

| HTTP | 真实 CLI | 用途 |
| --- | --- | --- |
| `GET /api/query` | `chatevent api query` | 结构化过滤、`sort=asc|desc`、`cursor`、`limit`，返回 `next_cursor`/`has_more` |
| `GET /api/events` | `chatevent api events` | 兼容旧简写参数；`next_since` 不能无损续读 |
| `GET /api/events/{dedupe_key}` | `chatevent api event` | 单条详情 |
| `POST /api/events` | `chatevent api record-json` | 写已规范化事件，需授权 |
| `GET /api/views` | `chatevent api views` | 当前账号视图列表 |
| `GET /api/views/{id}` | `chatevent api view` | 当前账号视图详情 |
| `POST /api/views` | `chatevent api save-view` | 新建视图 |
| `PUT /api/views/{id}` | `chatevent api update-view` | 更新视图；body 包含相同 id |
| `DELETE /api/views/{id}` | `chatevent api delete-view` | 删除视图 |
| `GET /api/subscriptions` | `chatevent api subscriptions` | 采集配置，不是视图 |
| `POST /api/subscriptions` | `chatevent api save-subscription` | 保存采集配置 |
| `GET /api/stats` | `chatevent api stats` | 当前账号可见事件统计 |
| `GET /api/platforms` | `chatevent api platforms` | 能力目录，不证明 collector 接通 |
| `POST /webhooks/discourse` | — | wrapped payload；可配置 raw-body HMAC |
| `POST /webhooks/zulip`, `/webhooks/gitea`, `/webhooks/github` | — | 配置认证后需要 ingest 凭据 |

`GET /api/query` 可传 URL 编码 JSON 的 `filter`，或 `view_id`，另有 `source`、`kind`、`subscription_id` 简写、`sort`、`cursor`、`limit`。未知参数、未知字段或不匹配的游标返回 422。`filter` 与 `view_id` 不能同时传。完整 AST 和 curl/Python 示例见[过滤与视图](filtering.md)。

`GET /api/events` 仍接收 `source`、`kind`、`subscription_id`、`q`、`since`、`days`、`from`、`to`、`limit`。它按 captured_at 倒序且限页，因此旧 `next_since` 是本页最新时间，**不保证**无损增量。客户端应迁移到 `/api/query?sort=asc`。

## 权限和采集

配置用户或管理员 token 后，member 的事件列表、详情、结构化查询、stats 仅含捕获时归属自己的行；无 owner 的旧事件仅 admin 可见。订阅 ID 的 owner 绑定不可转移，历史事件权限也不随订阅删除转移。member 视图按 owner 隔离，admin 可查看和管理全部；提交的 owner ID 不决定新视图归属；写入事件时 member 必须使用自有订阅。Cookie 写操作需要 CSRF；API token 不需要。无任何认证配置的本地开发模式保留匿名行为，必须只在可信本地使用。原始 payload 只向获授权读取者返回。

Discourse hook 配置签名密钥后，必须同时配置 `CHATEVENT_DISCOURSE_INSTANCE` 和 `CHATEVENT_DISCOURSE_SUBSCRIPTION_ID`；缺少绑定时返回 503，不入库。密钥由 `CHATEVENT_DISCOURSE_WEBHOOK_SECRET_FILE` 或 `CHATEVENT_DISCOURSE_WEBHOOK_SECRET` 提供；按原始请求体验证 SHA-256 HMAC，实例 header 不能自行指定归属。其他 webhook 使用授权 ingest 凭据。`capture zulip-once` 是有界官方队列读取，`capture subscription-once` 是仅消息创建的 topic 游标回填；`capture discourse-topic-backfill` 是当前对象只读快照。覆盖矩阵见[平台动作](platform-actions.md)。

ChatEvent 不提供 Agent runner、唤醒派发、任务队列、分配或通用写平台网关。`chatevent --tree` 与 `chatevent --tree-brief` 由 ChatStyle 渲染；完整实测树见[CLI 树](cli-tree.md)。
