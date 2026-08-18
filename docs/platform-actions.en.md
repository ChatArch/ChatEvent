# Platforms and Events

ChatEvent currently treats four platforms as the explicit support scope. `push` / `pull` no longer carry product semantics; they may only appear as legacy coarse acquisition modes. Event meaning is expressed by `source + kind + target`.

## Support matrix

| Platform | Official capability | Primary acquisition | Common action kinds |
| --- | --- | --- | --- |
| Zulip | Official REST API and event queue | `event_queue`, `api_cursor` | `message.created`, `message.updated`, `reaction.added`, `reaction.removed`, `mention.created`, `topic.updated` |
| Discourse | Official REST API and webhooks | `webhook`, `api_cursor` | `topic.created`, `post.created`, `reply.created`, `post.edited`, `post.deleted`, `mention.created`, `reaction.added` |
| Gitea | Official REST API and repository/org webhooks | `webhook`, `api_cursor` | `push`, `commit.pushed`, `issue.opened`, `issue.closed`, `issue.commented`, `pull_request.opened`, `pull_request.updated`, `pull_request.merged`, `release.published` |
| GitHub | Official REST/GraphQL API and webhooks | `webhook`, `api_cursor` | `push`, `commit.pushed`, `issue.opened`, `issue.closed`, `issue.commented`, `pull_request.opened`, `pull_request.synchronize`, `pull_request.closed`, `pull_request.merged`, `workflow_run.completed`, `release.published` |

## Field semantics

| Field | Meaning |
| --- | --- |
| `source` | Platform id such as `discourse`. |
| `target` | Subscription scope such as `category:agent-runs`, `stream:chatevent-practice`, or `repo:ChatArch/ChatEvent`. |
| `kind` | Platform action such as `reply.created`. |
| `capture_mode` | Acquisition mechanism such as `webhook`, `event_queue`, or `api_cursor`. |
| `tags` / `labels` | Filtering, grouping, or routing hints; they do not define the platform action. |

## Discourse first posts and replies

Discourse official webhooks may send `post_created` for both the first topic post and later replies. ChatEvent normalizes them with `post.post_number`:

- `post_number == 1` → `post.created`
- `post_number > 1` → `reply.created`

The official webhook event name comes from the `X-Discourse-Event` header; the ChatEvent endpoint reads that header before normalization.