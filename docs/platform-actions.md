# 平台与事件

ChatEvent 当前把四个平台作为明确支持范围。`push` / `pull` 不再承担产品语义；它们只可能作为旧数据里的粗粒度捕获方式。新的事件语义由 `source + action/kind + target` 表达；target 是承载链，不只是一个标签。

## 支持矩阵

| 平台 | 官方能力 | 首选捕获方式 | 常见 action kinds |
| --- | --- | --- | --- |
| Zulip | 官方 REST API、event queue | `event_queue`, `api_cursor` | `message.created`, `message.updated`, `reaction.added`, `reaction.removed`, `mention.created`, `topic.updated` |
| Discourse | 官方 REST API、webhook | `webhook`, `api_cursor` | `topic.created`, `post.created`, `reply.created`, `post.edited`, `post.deleted`, `mention.created`, `reaction.added` |
| Gitea | 官方 REST API、repository/org webhook | `webhook`, `api_cursor` | `push`, `commit.pushed`, `issue.opened`, `issue.closed`, `issue.commented`, `pull_request.opened`, `pull_request.updated`, `pull_request.merged`, `release.published` |
| GitHub | 官方 REST/GraphQL API、webhook | `webhook`, `api_cursor` | `push`, `commit.pushed`, `issue.opened`, `issue.closed`, `issue.commented`, `pull_request.opened`, `pull_request.synchronize`, `pull_request.closed`, `pull_request.merged`, `workflow_run.requested`, `workflow_run.in_progress`, `workflow_run.completed`, `release.published` |

## 字段含义

| 字段 | 含义 |
| --- | --- |
| `source` | 平台 ID，例如 `discourse`。 |
| `target` | 兼容和展示用订阅范围，例如 `category:agent-runs`、`stream:chatevent-practice/topic:real-loop`、`repo:ChatArch/ChatEvent`。 |
| `scope` | 结构化订阅承载目标，包含 `type`、`key`、`display`、`url`、`parent`、`metadata`，例如 repo、PR、topic。 |
| `actions` | 结构化动作选择器，由 `event_kinds` 自动派生，可保存 `kind`、`object_type`、`verb` 和扩展 metadata。 |
| `kind` | 平台动作，例如 `reply.created`。 |
| `capture_mode` | 捕获机制，例如 `webhook`、`event_queue`、`api_cursor`。 |
| `tags` / `labels` | 筛选、分组或路由提示，不定义平台动作本身。 |

## Discourse 首帖与回复

Discourse 官方 webhook 对 topic 首帖和回复都可能发送 `post_created`。ChatEvent 规范化时根据 `post.post_number` 区分：

- `post_number == 1` → `post.created`
- `post_number > 1` → `reply.created`

官方 webhook 的事件名来自 `X-Discourse-Event` header；ChatEvent endpoint 会读取该 header 并写入规范化流程。
## 动作与承载目标链

同一个平台动作可能挂在不同层级上。ChatEvent 不把 target type 或 actor role 写死成枚举，而是让各平台 action catalog 给出建议 target types，并在事件记录里保存实际 target chain 和可选发起人角色。

| 平台 | 订阅 scope 示例 | 事件 target chain 示例 |
| --- | --- | --- |
| Zulip | `stream:team/topic:release` | `zulip_stream:team → zulip_topic:team/release → message:123` |
| Discourse | `category:agent-runs` 或 `topic:22` | `discourse_topic:22 → discourse_post:35` |
| GitHub/Gitea | `repo:ChatArch/ChatEvent` | `repo:ChatArch/ChatEvent → pull_request:ChatArch/ChatEvent#4 → issue_comment:1234` |

Observatory 的 Platform actions 面板会显示 `action kind → target types`，Event Stream 点开详情会显示真实 `Action target` 和 `Target chain`。
