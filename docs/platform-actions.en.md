# Platform action coverage

This table describes implemented adapter and collector behavior covered by synthetic payload and HTTP tests. Validate production integration against the actual credentials, permissions, and server version. `/api/platforms` marks implemented actions with `capture_status=implemented`; `catalog_only` entries are platform concepts, not capture promises. Saving a `Subscription` does not start a collector.

| Platform path | Upstream events | Normalized kind | Boundary |
| --- | --- | --- | --- |
| Zulip official queue | `message` | `message.created` | Retains bot/Agent activity; dedupes by instance and native message ID |
| Zulip queue | `update_message` | `message.edited`, `message.moved`, `message.rendered` / `message.updated` | One move can expand across messages; content edit belongs to its message |
| Zulip queue | `delete_message` | `message.deleted` | Single `message_id` and bulk `message_ids` |
| Zulip queue | `reaction` add/remove | `reaction.added`, `reaction.removed` | Sparse events need known message context for topic scope |
| Zulip queue | `stream` create/update/delete | `stream.created/updated/deleted` | Create lists can expand |
| Zulip queue | `subscription` add/remove/update | `subscription.added/removed/updated` | Lists can expand; peer events are not relabeled as subscriptions |
| Zulip queue | `realm_user` add/update/remove | `user.added/updated/removed` | Affected user is the subject, not assumed actor |
| Discourse webhook | `post_created` | `post.created` or `reply.created` | `post_number > 1` is a reply; old `normalize_discourse_post()` remains |
| Discourse webhook | `post_edited`, `post_destroyed`, `post_recovered` | `post.edited/deleted/recovered` | Distinct changes to one post remain distinct facts |
| Discourse webhook | `topic_created`, `topic_edited`, `topic_revised`, `topic_destroyed`, `topic_recovered` | `topic.created/edited/revised/deleted/recovered` | Upstream wrapped `topic` object |
| Discourse webhook | `user_created`, `user_updated`, `user_approved`, `user_suspended`, `user_unsuspended`, `user_destroyed` | `user.created/updated/approved/suspended/unsuspended/deleted` | Affected user is the subject; unknown actor remains unknown |
| Discourse webhook | category/tag/group create/update/destroy | `category.*`, `tag.*`, `group.*` | Three families with three upstream names each |
| Discourse webhook | `like_created`, `notification_created`, `group_user_added/removed` | `like.created`, `notification.created`, `group_user.added/removed` | Requires stable object/membership identity in payload |
| Discourse topic API | Current topic and posts | `topic.created`, `post.created` / `reply.created` snapshots | Bounded read-only backfill; no historical changes reconstructed |

The Zulip collector requests **7 queue event types** and the Discourse adapter maps **28 upstream event names**. These are implementation counts, not all upstream events or production acceptance. See the official [Zulip events API](https://zulip.com/api/get-events), [queue registration](https://zulip.com/api/register-queue), [Discourse event catalog](https://github.com/discourse/discourse/blob/main/app/models/web_hook_event_type.rb), and [delivery/signature implementation](https://github.com/discourse/discourse/blob/main/app/jobs/regular/emit_web_hook_event.rb).

Zulip heartbeat/restart are control events, not messages. Unknown types increment `unsupported`; unverifiable topic/stream scope increments `scope_unknown` and fails closed. `realm_user_groups`, other Zulip types, and Discourse plugin events are outside the current adapter; `like_removed` is not advertised. Queue outages do not preserve edit/reaction history, and snapshots do not reconstruct missed webhooks. Bot activity remains captured; use [filters](filtering.md) to control visibility. Actor roles are available only when known from source data.

Zulip deletion/removal events are observer-relative and may mean lost access or channel archival, not permanent global deletion. Channel and subscription updates preserve `payload.property` / `payload.value`; `raw_payload` retains the complete source payload.

The native object ID is `subject_id`; each change has its own event `id`. `instance` distinguishes platform instances. Repeated deliveries dedupe deterministically while edits, deletion, and restoration remain separate facts. `occurred_at` uses source time when available; otherwise `metadata.timestamp_source=capture-time` marks a capture-time fallback.
