# ChatEvent

`chatevent` 是 ChatArch 的协作事件观察包：提供类型化事件 envelope、SQLite 事件账本、平台 normalizer 和 Web Observatory，用于观察 Discourse、Zulip、Gitea、GitHub、X 等协作平台的真实动作。

当前 `0.2.1` 范围把 ChatEvent 收敛为标准 Chat 系列包：依赖 ChatStyle 渲染完整/brief CLI 树，注册 ChatEnv 配置接口，并继续聚焦 **Discourse、Zulip、Gitea、GitHub、X** 的明确 action catalog。

```text
平台官方 webhook / event queue / API cursor / public web URL -> ChatEvent -> SQLite -> Observatory / API
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
uv run --extra serve chatevent --tree-brief
```

`0.2.1` 补齐标准 ChatStyle brief tree：保留 `0.2.0` 的 Event Hub / ChatEnv 对齐能力，并新增 `chatevent --tree-brief` 作为紧凑命令树入口。

## CLI

完整 CLI 树见 [docs/cli-tree.md](docs/cli-tree.md)，运行时可回读 detailed/brief 两种视图：

```bash
uv run chatevent --tree
uv run chatevent --tree-brief
```

核心命令族：

```text
chatevent
├── api        # REST API client for Event Hub operations
├── capture    # bounded official platform capture passes
├── paths      # ChatEnv/ChatArch-owned runtime paths
├── platforms  # platform action catalog
├── schema     # JSON Schema contracts
└── serve      # local Event Observatory and REST API
```

## 启动 Event Observatory

```bash
uv run --extra serve chatevent serve \
  --host 127.0.0.1 \
  --port 8765
```

打开：

```text
http://127.0.0.1:8765/
```

当前服务器 demo 入口：

- https://event.local.wzhecnu.cn/
- https://event.public.wzhecnu.cn/

## ChatArch 内部默认目录

ChatEvent 是 ChatArch 系列包，默认运行态必须留在 ChatArch home 内部。ChatArch home 优先由 ChatEnv `get_paths().home_dir` 提供；显式传入 `CHATARCH_HOME` 时保留兼容。

```text
<chatarch-home>/
└── chatevent/
    ├── events.db              # SQLite 事件账本和订阅配置
    ├── events.db-wal          # SQLite WAL，运行时可能出现
    ├── events.db-shm          # SQLite shared-memory，运行时可能出现
    └── secrets/
        └── admin-token        # 可选 Web/REST 订阅写操作管理员 token
```

默认数据库解析顺序：

1. CLI 显式 `--db <path>`；
2. `CHATEVENT_DB=<path>`；
3. ChatEnv `get_paths().home_dir / "chatevent/events.db"`；
4. `$CHATARCH_HOME/chatevent/events.db`；
5. `~/.chatarch/chatevent/events.db`。

首次使用默认路径时，如果发现旧版 `~/.chatevent/events.db` 且新数据库不存在，ChatEvent 会把旧库复制到 ChatArch 内部路径；旧文件保留不删除。显式 `--db` 或 `CHATEVENT_DB` 不触发自动迁移。

可用下面的命令回读当前路径，不会输出 token 值：

```bash
uv run chatevent paths --json
```

SQLite 内部主要有两张表：

- `subscriptions`：订阅配置和状态，`body` 保存完整 `Subscription` JSON；`last_cursor`、`last_event_at` 等更新也在这里。
- `events`：规范化后的 `ChatEvent`，`body` 保存完整事件 JSON，索引列保存 source、kind、subscription_id、captured_at 和 seen_count。

## ChatStyle 与 ChatEnv 对齐

`chatevent --tree` 与 `chatevent --tree-brief` 均由 ChatStyle 渲染；`chatevent.config:ChatEventConfig` 注册到 ChatEnv 的 `chatenv.configs` entry point。ChatEvent 自身只声明 Event Hub 相关 ENV：`CHATEVENT_API_URL`、`CHATEVENT_DB`、`CHATEVENT_ADMIN_TOKEN(_FILE)`、`CHATEVENT_API_USERNAME`、`CHATEVENT_API_PASSWORD_FILE`、`CHATEVENT_BOOTSTRAP_USERNAME`、`CHATEVENT_BOOTSTRAP_PASSWORD_FILE`。

平台凭据交给各平台 ChatEnv profile 或服务 secret 文件管理。比如 `capture zulip-once` 默认读取 ChatEnv `envs_dir/Zulip/.env`，文件内容需要包含 `ZULIP_SITE`、`BOT_EMAIL`、`BOT_API_KEY`，ChatEvent 不在 CLI 输出里打印这些值。

X 公开网页捕获首版不需要账号或 API token；若目标环境需要代理，可对单次捕获传入 `--proxy-env-file /path/to/.env`，ChatEvent 只加载 proxy 相关变量，不打印或保存代理值。

平台侧 webhook 注册、Zulip secret 文件、Nginx upstream、运行端口等不写入 SQLite；它们属于外部平台或运行时部署配置，凭据不写入项目文件。

## 刷新机制

Observatory 当前使用前端轮询，不是 WebSocket/SSE：

- 页面打开后立即加载一次；
- 每 **5 秒** 自动刷新；
- 点击 **刷新 / Refresh** 会立即手动刷新；
- 搜索输入约 **260ms debounce** 后刷新；
- 来源、事件类型和时间范围筛选变化后立即刷新。

每次刷新会请求 `/api/stats`、`/api/subscriptions`、`/api/events` 和 `/api/platforms`。事件流顶层只保留“来源”和“时间”两个下拉框；事件类型、订阅/渠道、关键词和自定义开始/结束时间在“高级选项”里组合筛选。事件类型 checkbox 会随来源联动，避免把不同平台 action 混在同一个下拉框里。

## 事件语义

产品语义使用这些字段表达：

- `source`：平台来源，例如 `zulip`、`discourse`、`gitea`、`github`、`x`。
- `kind`：平台动作，例如 `message.created`、`post.created`、`reply.created`、`issue.opened`、`commit.pushed`、`pull_request.merged`。
- `conversation_id` / `subject_id` / `subject_type`：动作发生在哪里、对象是什么。
- `capture_mode`：捕获机制，不是业务动作。新接入使用 `webhook`、`event_queue`、`api_cursor`、`poll`、`manual_backfill`、`gateway_forward`、`test_fixture` 或 `synthetic`；旧数据里的 `push`/`pull` 仅兼容读取。
- `tags`：筛选或路由标签，不定义平台来源或动作。


### 动作 + 承载目标

ChatEvent 现在把订阅和事件都表达成“动作 + 承载目标”：

```text
Subscription = source + actions/event_kinds + scope/target + capture_modes + filters
ChatEvent    = source + action/kind + actor/role + target + subject + payload
```

- `Subscription.target`：兼容和快速展示用的 canonical string，例如 `repo:ChatArch/ChatEvent`、`pull_request:ChatArch/ChatEvent#4`、`stream:demo/topic:loop`。
- `Subscription.scope`：结构化承载目标，包含开放字符串 `type`、`key`、`display`、`url`、`parent` 和 `metadata`，不把平台类型写死。
- `Subscription.actions`：结构化动作选择器，由 `event_kinds` 自动派生，也可以显式保存 `kind`、`object_type`、`verb` 和扩展 metadata。
- `ChatEvent.action`：本次真实发生的动作，例如 `pull_request.merged` / `reply.created`。
- `ChatEvent.actor` / `actor_role`：发起人及其平台角色，例如 maintainer、member、bot、moderator；角色是开放字符串，可继续细分。
- `ChatEvent.target`：本次动作作用到的具体对象，并通过 `parent` 串起承载链，例如 `repo -> pull_request -> issue_comment` 或 `zulip_stream -> zulip_topic -> message`。

示例：

```json
{
  "source": "github",
  "target": "pull_request:ChatArch/ChatEvent#4",
  "scope": {
    "type": "pull_request",
    "key": "ChatArch/ChatEvent#4",
    "parent": {"type": "repo", "key": "ChatArch/ChatEvent"}
  },
  "event_kinds": ["pull_request.opened", "pull_request.merged", "issue.commented"],
  "capture_modes": ["webhook", "api_cursor"]
}
```

Observatory 的 Event Stream 增加了 Target 列；点开事件详情后会显示 `Action`、`Action target` 和 `Target chain`。Platform actions 面板也会显示每个 action 通常挂载的 target types。

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
| GitHub | `webhook`, `api_cursor` | `push`, `commit.pushed`, `issue.opened`, `issue.closed`, `issue.commented`, `pull_request.opened`, `pull_request.synchronize`, `pull_request.closed`, `pull_request.merged`, `workflow_run.requested`, `workflow_run.in_progress`, `workflow_run.completed`, `release.published` |
| X | `poll`, `manual_backfill` | `post.created` |


### X 公开网页捕获

首版 X 支持分为两个 bounded capture 动作：

```bash
uv run chatevent capture x-user \
  --handle thsottiaux \
  --limit 20 \
  --days 7 \
  --proxy-env-file /home/zhihong/Playground/.env

uv run chatevent capture x-status \
  --url https://x.com/thsottiaux/status/2087423996115681767 \
  --proxy-env-file /home/zhihong/Playground/.env
```

`x-user` 用公开用户页发现最近 status URL，再逐条通过 oEmbed 和 status 网页补充作者、内容、发布时间和来源 URL，写入 `source=x` / `kind=post.created` 事件。重复运行会复用 `x:post:<status-id>` 去重，新帖子会新增 Event，适合先做一次性最近 N 条/最近 N 天回填，再由后续 trigger 定时执行。

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
X:         用 `chatevent capture x-user --handle <handle> --limit <N> --days <N>` 从公开用户页回填/轮询最近 post
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
| `chatevent api session` | `GET /api/session` | 校验当前 API token 或登录 cookie 并返回用户/角色。 |
| `chatevent api users` | `GET /api/users` | 管理员列出用户。 |
| `chatevent api create-user <username> --new-password-file pass.txt` | `POST /api/users` | 管理员创建账号密码用户，不返回 token。 |
| `chatevent api create-token [user_id]` | `POST /api/me/token` 或 `POST /api/users/{id}/token` | 为当前账号或指定用户生成一次性 `arch_xxx` API token。 |
| `chatevent api delete-user <id>` | `DELETE /api/users/{id}` | 管理员删除用户。 |
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

Web Observatory 的 `Subscriptions` 标签页支持新建、编辑、启停和删除订阅；这些操作调用同一套 REST API。若配置了用户或 bootstrap 管理凭据，访问 `/` 会先进入账号密码登录页，登录后才显示 Observatory；事件流、统计、平台目录、schema、订阅等读取 API 也需要登录。网页端登录后可以直接编辑；CLI、模型或其他程序可以使用 `X-ChatEvent-Admin-Token` 携带账号的 `arch_xxx` API token，也可以通过 CLI 的账号密码参数先登录后操作。

`CHATEVENT_ADMIN_TOKEN` 仅是 bootstrap 管理员 API 凭据，不是 Web 登录方式；生产部署应配置 `CHATEVENT_BOOTSTRAP_USERNAME` 与 `CHATEVENT_BOOTSTRAP_PASSWORD_FILE` 来初始化管理员账号密码。管理员登录后可以通过 `POST /api/users` 或 `chatevent api create-user <username> --new-password-file pass.txt` 创建账号密码用户；用户登录后在“账号 / API Token”里主动生成自己的 `arch_xxx` token，服务端只保存 token hash。`Subscription.owner_user_id` 是数据隔离基础：member 创建/读取/删除订阅时只作用于自己的 owner；admin 可管理全部订阅。密码和 token 都不应写入源码、文档或 Git 历史。

```bash
mkdir -p ~/.chatarch/chatevent/secrets
chmod 700 ~/.chatarch/chatevent ~/.chatarch/chatevent/secrets
printf '<admin-token>\n' > ~/.chatarch/chatevent/secrets/admin-token
printf '<admin-password>\n' > ~/.chatarch/chatevent/secrets/admin-password
chmod 600 ~/.chatarch/chatevent/secrets/admin-token ~/.chatarch/chatevent/secrets/admin-password

CHATEVENT_BOOTSTRAP_USERNAME='admin@example.com' \
CHATEVENT_BOOTSTRAP_PASSWORD_FILE=~/.chatarch/chatevent/secrets/admin-password \
uv run --extra serve chatevent serve
uv run chatevent api create-token --username admin@example.com --password-file ~/.chatarch/chatevent/secrets/admin-password
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
