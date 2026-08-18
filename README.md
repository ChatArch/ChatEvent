# ChatEvent

`chatevent` 是 ChatArch 的协作事件观察包：提供类型化事件 envelope、SQLite 事件账本、平台 normalizer 和 Web Observatory，用于观察 Discourse、Zulip、Gitea、GitHub 等协作平台的真实动作。

当前 `0.1.0.dev0` 范围刻意收窄到 **Discourse、Zulip、Gitea、GitHub**。每个平台都有明确 action catalog，订阅和 UI 不再把任意 `tag` 当成事件语义。

```text
平台官方 webhook / event queue / API cursor -> ChatEvent -> SQLite -> Observatory / API
```

Gateway 路由和 Agent 执行不在当前包的阶段范围内。

英文版见 [README.en.md](README.en.md)。

## 文档

- MkDocs 源码：`docs/`
- 本地构建：

```bash
uv sync --extra docs
uv run mkdocs build --strict
uv run mkdocs serve
```

ChatArch 包文档目标地址：

https://arch.gh.wzhecnu.cn/ChatEvent/

## 从源码安装

```bash
uv sync --extra serve --extra test --extra docs
uv run --extra serve chatevent --tree
```

PyPI 上的 `0.0.1` 只包含初始事件 envelope 和 monitor protocol。Observatory、平台 action registry 和 webhook/event queue 接入属于开发中的 `0.1.0.dev0`。

## CLI

```text
chatevent
  --tree                         Print this command tree
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

## 启动 Event Observatory

```bash
uv run --extra serve chatevent serve \
  --host 127.0.0.1 \
  --port 8765 \
  --db ./events.db
```

打开：

```text
http://127.0.0.1:8765/
```

当前服务器 demo 入口：

- https://event.local.wzhecnu.cn/
- https://event.public.wzhecnu.cn/

## 配置和存储位置

ChatEvent 当前把运行时事件账本写在 SQLite 中，数据库路径由 `--db` 或 `CHATEVENT_DB` 决定；未设置时使用 `~/.chatevent/events.db`。当前线上 demo 的 DB 是：

```text
/home/zhihong/Playground/projects/08-18-chatevent/playground/real-loop/events.db
```

SQLite 内部主要有两张表：

- `subscriptions`：订阅配置和状态，`body` 保存完整 `Subscription` JSON；`last_cursor`、`last_event_at` 等更新也在这里。
- `events`：规范化后的 `ChatEvent`，`body` 保存完整事件 JSON，索引列保存 source、kind、subscription_id、captured_at 和 seen_count。

平台侧 webhook 注册、Zulip secret 文件、Nginx upstream、运行端口等不写入 SQLite；它们属于外部平台或运行时部署配置，凭据不写入项目文件。

## 刷新机制

Observatory 当前使用前端轮询，不是 WebSocket/SSE：

- 页面打开后立即加载一次；
- 每 **5 秒** 自动刷新；
- 点击 **刷新 / Refresh** 会立即手动刷新；
- 搜索输入约 **260ms debounce** 后刷新；
- 来源、事件类型和时间范围筛选变化后立即刷新。

每次刷新会请求 `/api/stats`、`/api/subscriptions`、`/api/events` 和 `/api/platforms`。事件流支持“全部时间 / 最近 24 小时 / 最近 3 天 / 最近 7 天 / 最近 30 天”，也支持自定义开始、结束时间。

## 事件语义

产品语义使用这些字段表达：

- `source`：平台来源，例如 `zulip`、`discourse`、`gitea`、`github`。
- `kind`：平台动作，例如 `message.created`、`post.created`、`reply.created`、`issue.opened`、`commit.pushed`、`pull_request.merged`。
- `conversation_id` / `subject_id` / `subject_type`：动作发生在哪里、对象是什么。
- `capture_mode`：捕获机制，不是业务动作。新接入使用 `webhook`、`event_queue`、`api_cursor`、`poll`、`manual_backfill`、`gateway_forward`、`test_fixture` 或 `synthetic`；旧数据里的 `push`/`pull` 仅兼容读取。
- `tags`：筛选或路由标签，不定义平台来源或动作。

## 支持平台与常见动作

查看 canonical registry：

```bash
uv run chatevent platforms
uv run chatevent platforms --json
```

| 平台 | 首选捕获方式 | 常见 action kinds |
|---|---|---|
| Zulip | `event_queue`, `api_cursor` | `message.created`, `message.updated`, `reaction.added`, `reaction.removed`, `mention.created`, `topic.updated` |
| Discourse | `webhook`, `api_cursor` | `topic.created`, `post.created`, `reply.created`, `post.edited`, `post.deleted`, `mention.created`, `reaction.added` |
| Gitea | `webhook`, `api_cursor` | `push`, `commit.pushed`, `issue.opened`, `issue.closed`, `issue.commented`, `pull_request.opened`, `pull_request.updated`, `pull_request.merged`, `release.published` |
| GitHub | `webhook`, `api_cursor` | `push`, `commit.pushed`, `issue.opened`, `issue.closed`, `issue.commented`, `pull_request.opened`, `pull_request.synchronize`, `pull_request.closed`, `pull_request.merged`, `workflow_run.completed`, `release.published` |

## 注册监控

1. 先在 ChatEvent 保存订阅：

```bash
curl -k -X POST https://event.public.wzhecnu.cn/api/subscriptions \
  -H 'Content-Type: application/json' \
  -d '{
    "id": "discourse-practice",
    "source": "discourse",
    "target": "category:agent-runs",
    "event_kinds": ["topic.created", "post.created", "reply.created"],
    "capture_modes": ["webhook", "api_cursor"]
  }'
```

2. 再把平台官方捕获面指向 ChatEvent：

```text
Discourse: https://event.public.wzhecnu.cn/webhooks/discourse?subscription_id=discourse-practice
Gitea:     https://event.public.wzhecnu.cn/webhooks/gitea?subscription_id=gitea-practice
GitHub:    https://event.public.wzhecnu.cn/webhooks/github?subscription_id=github-chatevent
Zulip:     用 `chatevent capture zulip-once` 做官方 event queue bounded capture pass
```

详细步骤见 `docs/monitoring.md`。

## API 表面

- `GET /api/health`
- `GET /api/schema/event`
- `GET /api/schema/subscription`
- `GET /api/platforms`
- `POST /api/subscriptions`
- `GET /api/subscriptions`
- `DELETE /api/subscriptions/{id}`
- `POST /api/events`
- `GET /api/events`，支持 `source`、`kind`、`subscription_id`、`q`、`since`、`days`、`from`、`to` 和 `limit`
- `GET /api/events/{dedupe_key}`
- `GET /api/stats`
- `POST /webhooks/zulip?subscription_id=...`
- `POST /webhooks/discourse?subscription_id=...`，读取 `X-Discourse-Event`
- `POST /webhooks/gitea?subscription_id=...`
- `POST /webhooks/github?subscription_id=...`，读取 `X-GitHub-Event`

Webhook endpoint 接收官方平台形状 payload，规范化为 `ChatEvent`，幂等写入 SQLite，并保留清洗后的 `raw_payload` 供 Observatory 调试。

## CLI 与 REST API 对应

ChatEvent 可以当作一个轻量 Event Hub：平台官方 webhook / event queue / API cursor 负责把原始动作送进来，ChatEvent 负责规范化、去重、保存；下游系统通过 REST API 读取事件，CLI 的 `api` 命令组就是这些 REST endpoint 的命令行对应。

默认 base URL 是 `CHATEVENT_API_URL`，未设置时使用 `http://127.0.0.1:8765`；也可以对每个命令传 `--base-url`。

| CLI | REST API | 用途 |
| --- | --- | --- |
| `chatevent api health` | `GET /api/health` | 读服务健康状态和 DB 路径。 |
| `chatevent api stats` | `GET /api/stats` | 读事件数、来源数、重复投递数。 |
| `chatevent api events --source discourse --days 7` | `GET /api/events?...` | 按 source/kind/subscription/q/since/days/from/to/limit 查询事件流。 |
| `chatevent api event <dedupe_key>` | `GET /api/events/{dedupe_key}` | 直接读取某一条具体 event。 |
| `chatevent api record-json event.json` | `POST /api/events` | 把已规范化的 `ChatEvent` JSON 写入 Event Hub。 |
| `chatevent api subscriptions` | `GET /api/subscriptions` | 列出订阅。 |
| `chatevent api save-subscription subscription.json` | `POST /api/subscriptions` | 通过 REST 保存订阅。 |
| `chatevent api delete-subscription <id>` | `DELETE /api/subscriptions/{id}` | 删除订阅，不删除已捕获事件。 |

示例：

```bash
uv run chatevent api events \
  --base-url https://event.public.wzhecnu.cn \
  --source discourse \
  --days 7 \
  --limit 20

uv run chatevent api event \
  --base-url https://event.public.wzhecnu.cn \
  'discourse:post:35'
```

## 线上编辑与安全设定

Web Observatory 的 `Subscriptions` 标签页支持新建、编辑、启停和删除订阅；这些操作调用同一套 REST API。若设置 `CHATEVENT_ADMIN_TOKEN`，订阅写操作必须带 `X-ChatEvent-Admin-Token` header；Web 页面会在首次写操作收到 401 时提示输入 token，并只保存在当前浏览器 sessionStorage。

```bash
CHATEVENT_ADMIN_TOKEN=... uv run --extra serve chatevent serve --db ./events.db
uv run chatevent api save-subscription subscription.json --admin-token ...
uv run chatevent api delete-subscription discourse-practice --admin-token ...
```

删除订阅只删除 `subscriptions` 里的配置，不会删除 `events` 表中已经捕获的历史事件。

## 下游消费

Observatory 只是一个调试 consumer。其他系统可以按 checkpoint 轮询 Event Hub：

```bash
curl -k 'https://event.public.wzhecnu.cn/api/events?source=discourse&subscription_id=discourse-practice&since=2026-08-18T12:47:37Z&limit=50'
```

日期筛选示例：

```bash
curl -k 'https://event.public.wzhecnu.cn/api/events?days=7&source=discourse&limit=50'
curl -k 'https://event.public.wzhecnu.cn/api/events?from=2026-08-16T00:00:00Z&to=2026-08-18T00:00:00Z&limit=50'
```

其中 `days` 表示按服务器当前时间回看最近 N 天，`from`/`to` 表示按 `captured_at` 做日期区间筛选；`since` 仍保留给 consumer checkpoint，语义是严格返回 `captured_at > since`。

返回体包含：

- `items`：规范化 `ChatEvent` 列表；
- `count`：本次命中的条数；
- `next_since`：本批最新 `captured_at`。consumer 处理成功后保存它，下次作为 `since` 继续拉取。

推荐循环：

1. consumer 保存自己的 `last_since`。
2. 请求 `/api/events?since=<last_since>&source=...&kind=...&subscription_id=...`。
3. 对每条 `event` 按 `source/kind/subject_id` 做幂等处理。
4. 全部处理成功后，把响应里的 `next_since` 存回 checkpoint。
5. 如果 `count=0`，保持原 checkpoint，稍后再拉。
