# Platforms and Events

ChatEvent currently treats six platforms as the explicit support scope. `push` / `pull` no longer carry product semantics; they may only appear as legacy coarse acquisition modes. Event meaning is expressed by `source + action/kind + target`; target is a carrier chain, not just a label.

## Support matrix

| Platform | Official capability | Primary acquisition | Common action kinds |
| --- | --- | --- | --- |
| Zulip | Official REST API and event queue | `event_queue`, `api_cursor` | `message.created`, `message.updated`, `reaction.added`, `reaction.removed`, `mention.created`, `topic.updated` |
| Discourse | Official REST API and webhooks | `webhook`, `api_cursor` | `topic.created`, `post.created`, `reply.created`, `post.edited`, `post.deleted`, `mention.created`, `reaction.added` |
| Gitea | Official REST API and repository/org webhooks | `webhook`, `api_cursor` | `push`, `commit.pushed`, `issue.opened`, `issue.closed`, `issue.commented`, `pull_request.opened`, `pull_request.updated`, `pull_request.merged`, `release.published` |
| GitHub | Official REST/GraphQL API and webhooks | `webhook`, `api_cursor` | `push`, `commit.pushed`, `issue.opened`, `issue.closed`, `issue.commented`, `pull_request.opened`, `pull_request.synchronize`, `pull_request.closed`, `pull_request.merged`, `workflow_run.requested`, `workflow_run.in_progress`, `workflow_run.completed`, `release.published` |
| Voice | ChatVoice/Speakr read-only data API | `manual_backfill`, `poll`, `api_cursor` | `talk.created`, `talk.updated` |
| X | Public user pages/status URLs/oEmbed; future official API or browser profile backends can be added | `poll`, `manual_backfill` | `post.created` |

## Field semantics

| Field | Meaning |
| --- | --- |
| `source` | Platform id such as `discourse`. |
| `target` | Compatibility/display subscription scope such as `category:agent-runs`, `stream:chatevent-practice/topic:real-loop`, or `repo:ChatArch/ChatEvent`. |
| `scope` | Structured subscription carrier target with `type`, `key`, `display`, `url`, `parent`, and `metadata`, e.g. repo, PR, or topic. |
| `actions` | Structured action selectors derived from `event_kinds` by default; can store `kind`, `object_type`, `verb`, and metadata. |
| `kind` | Platform action such as `reply.created`. |
| `capture_mode` | Acquisition mechanism such as `webhook`, `event_queue`, or `api_cursor`. |
| `tags` / `labels` | Filtering, grouping, or routing hints; they do not define the platform action. |

## Discourse first posts and replies

Discourse official webhooks may send `post_created` for both the first topic post and later replies. ChatEvent normalizes them with `post.post_number`:

- `post_number == 1` → `post.created`
- `post_number > 1` → `reply.created`

The official webhook event name comes from the `X-Discourse-Event` header; the ChatEvent endpoint reads that header before normalization.
## Actions and carrier target chains

A platform action can attach to different hierarchy levels. ChatEvent keeps target types and actor roles open-ended: each platform action catalog declares suggested target types, and each stored event records the actual target chain plus an optional initiator role.

| Platform | Subscription scope example | Event target chain example |
| --- | --- | --- |
| Zulip | `stream:team/topic:release` | `zulip_stream:team → zulip_topic:team/release → message:123` |
| Discourse | `category:agent-runs` or `topic:22` | `discourse_topic:22 → discourse_post:35` |
| GitHub/Gitea | `repo:ChatArch/ChatEvent` | `repo:ChatArch/ChatEvent → pull_request:ChatArch/ChatEvent#4 → issue_comment:1234` |
| Voice | `account:default` or `talk:<uuid>` | `voice_account:default → voice_talk:<uuid>` |

The Observatory Platform actions panel shows `action kind → target types`; opening an Event Stream detail shows the concrete `Action target` and `Target chain`.

## Voice metadata actions

Voice events use `source=voice` and capture talk metadata through the ChatVoice/Speakr read-only data API. `capture voice-backfill --all` writes `talk.created` for existing talks on the current account; `capture voice-once --since <timestamp>` uses the `updated_at` cursor to write `talk.created` for new talks or `talk.updated` for existing talks. Payloads keep only talk ID, title, tags, timestamps, duration, and summary/transcript availability booleans; they do not store full summary text, transcript text, preview text, or token values.
