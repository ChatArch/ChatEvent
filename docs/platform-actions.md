# 平台与事件

ChatEvent 当前把四个平台作为明确支持范围。`push` / `pull` 不再承担产品语义；它们只可能作为旧数据里的粗粒度捕获方式。新的事件语义由 `source + kind + target` 表达。

## 支持矩阵

| 平台 | 官方能力 | 首选捕获方式 | 常见 action kinds |
| --- | --- | --- | --- |
| Zulip | 官方 REST API、event queue | `event_queue`, `api_cursor` | `message.created`, `message.updated`, `reaction.added`, `reaction.removed`, `mention.created`, `topic.updated` |
| Discourse | 官方 REST API、webhook | `webhook`, `api_cursor` | `topic.created`, `post.created`, `reply.created`, `post.edited`, `post.deleted`, `mention.created`, `reaction.added` |
| Gitea | 官方 REST API、repository/org webhook | `webhook`, `api_cursor` | `push`, `commit.pushed`, `issue.opened`, `issue.closed`, `issue.commented`, `pull_request.opened`, `pull_request.updated`, `pull_request.merged`, `release.published` |
| GitHub | 官方 REST/GraphQL API、webhook | `webhook`, `api_cursor` | `push`, `commit.pushed`, `issue.opened`, `issue.closed`, `issue.commented`, `pull_request.opened`, `pull_request.synchronize`, `pull_request.closed`, `pull_request.merged`, `workflow_run.completed`, `release.published` |

## 字段含义

| 字段 | 含义 |
| --- | --- |
| `source` | 平台 ID，例如 `discourse`。 |
| `target` | 订阅范围，例如 `category:agent-runs`、`stream:chatevent-practice`、`repo:ChatArch/ChatEvent`。 |
| `kind` | 平台动作，例如 `reply.created`。 |
| `capture_mode` | 捕获机制，例如 `webhook`、`event_queue`、`api_cursor`。 |
| `tags` / `labels` | 筛选、分组或路由提示，不定义平台动作本身。 |

## Discourse 首帖与回复

Discourse 官方 webhook 对 topic 首帖和回复都可能发送 `post_created`。ChatEvent 规范化时根据 `post.post_number` 区分：

- `post_number == 1` → `post.created`
- `post_number > 1` → `reply.created`

官方 webhook 的事件名来自 `X-Discourse-Event` header；ChatEvent endpoint 会读取该 header 并写入规范化流程。