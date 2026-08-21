import unittest
from datetime import timezone

from chatevent import CaptureMode
from chatevent.adapters import (
    normalize_discourse_post,
    normalize_gitea_issue,
    normalize_x_post,
    normalize_zulip_message_event,
)


class AdapterNormalizationTests(unittest.TestCase):
    def test_x_post_normalizes_public_web_payload(self) -> None:
        event = normalize_x_post(
            {
                "status_id": "2087423996115681767",
                "status_url": "https://x.com/thsottiaux/status/2087423996115681767",
                "author_handle": "thsottiaux",
                "author_name": "Tibo",
                "text": "Little surprise for you tomorrow.",
                "created_at": "2026-08-12T06:20:37.000Z",
                "timestamp_source": "x-web-html",
                "acquisition": "x-web-url",
            },
            subscription_id="x-user-thsottiaux",
        )

        self.assertEqual(event.source, "x")
        self.assertEqual(event.kind, "post.created")
        self.assertEqual(event.id, "post:2087423996115681767")
        self.assertEqual(event.dedupe_key, "x:post:2087423996115681767")
        self.assertEqual(event.subscription_id, "x-user-thsottiaux")
        self.assertEqual(event.actor_id, "user:thsottiaux")
        self.assertEqual(event.actor.display, "Tibo")
        self.assertEqual(event.actor.role, "author")
        self.assertEqual(event.conversation_id, "user:thsottiaux")
        self.assertEqual(event.subject_id, "post:2087423996115681767")
        self.assertEqual(event.subject_type, "post")
        self.assertEqual(event.target.type, "x_post")
        self.assertEqual(event.target.parent.type, "x_user")
        self.assertEqual(event.url, "https://x.com/thsottiaux/status/2087423996115681767")
        self.assertEqual(event.payload["content"], "Little surprise for you tomorrow.")
        self.assertEqual(event.payload["created_at"], "2026-08-12T06:20:37+00:00")
        self.assertEqual(event.metadata["acquisition"], "x-web-url")
        self.assertIn("x-web-url", event.tags)

    def test_zulip_message_event_normalizes_official_event_queue_payload(self) -> None:
        event = normalize_zulip_message_event(
            {
                "id": 101,
                "type": "message",
                "message": {
                    "id": 24,
                    "timestamp": 1787047000,
                    "sender_id": 7,
                    "sender_email": "watcher@example.invalid",
                    "sender_full_name": "Watcher Bot",
                    "stream_id": 3,
                    "display_recipient": "chatevent-practice",
                    "topic": "zulip-event-queue",
                    "subject": "zulip-event-queue",
                    "content": "hello from Zulip",
                    "content_type": "text/html",
                },
            },
            subscription_id="zulip-practice",
            site_url="https://zulip.public.lookeng.cn",
        )

        self.assertEqual(event.source, "zulip")
        self.assertEqual(event.kind, "message.created")
        self.assertEqual(event.id, "message:24")
        self.assertEqual(event.capture_mode, CaptureMode.EVENT_QUEUE)
        self.assertEqual(event.subscription_id, "zulip-practice")
        self.assertEqual(event.actor_id, "user:7")
        self.assertEqual(event.conversation_id, "stream:3/topic:zulip-event-queue")
        self.assertEqual(event.subject_id, "message:24")
        self.assertEqual(event.action.kind, "message.created")
        self.assertEqual(event.action.object_type, "message")
        self.assertEqual(event.action.verb, "created")
        self.assertEqual(event.target.type, "message")
        self.assertEqual(event.target.key, "24")
        self.assertEqual(event.target.parent.type, "zulip_topic")
        self.assertEqual(event.target.parent.key, "chatevent-practice/zulip-event-queue")
        self.assertEqual(event.target.parent.parent.type, "zulip_stream")
        self.assertEqual(event.target.parent.parent.key, "chatevent-practice")
        self.assertEqual(event.cursor, "101")
        self.assertEqual(event.url, "https://zulip.public.lookeng.cn/#narrow/channel/chatevent-practice/topic/zulip-event-queue/near/24")
        self.assertEqual(event.payload["content"], "hello from Zulip")
        self.assertEqual(event.metadata["acquisition"], "zulip-event-queue")
        self.assertIn("zulip", event.tags)
        self.assertEqual(event.occurred_at.tzinfo, timezone.utc)

    def test_discourse_topic_post_normalizes_webhook_payload(self) -> None:
        event = normalize_discourse_post(
            {
                "event_name": "post_created",
                "post": {
                    "id": 25,
                    "topic_id": 18,
                    "post_number": 1,
                    "username": "RexWang",
                    "created_at": "2026-08-05T02:59:00Z",
                    "topic_slug": "chatevent-discourse-practice",
                    "topic_title": "ChatEvent Discourse practice",
                    "raw": "hello from Discourse",
                },
            },
            subscription_id="discourse-practice",
            base_url="https://discourse.public.lookeng.cn",
        )

        self.assertEqual(event.source, "discourse")
        self.assertEqual(event.kind, "post.created")
        self.assertEqual(event.id, "post:25")
        self.assertEqual(event.capture_mode, CaptureMode.WEBHOOK)
        self.assertEqual(event.actor_id, "user:RexWang")
        self.assertEqual(event.conversation_id, "topic:18")
        self.assertEqual(event.subject_id, "post:25")
        self.assertEqual(event.subject_type, "post")
        self.assertEqual(event.action.kind, "post.created")
        self.assertEqual(event.action.object_type, "post")
        self.assertEqual(event.target.type, "discourse_post")
        self.assertEqual(event.target.key, "25")
        self.assertEqual(event.target.parent.type, "discourse_topic")
        self.assertEqual(event.target.parent.key, "18")
        self.assertEqual(event.target.parent.display, "ChatEvent Discourse practice")
        self.assertEqual(event.cursor, "25")
        self.assertEqual(event.url, "https://discourse.public.lookeng.cn/t/chatevent-discourse-practice/18/1")
        self.assertEqual(event.payload["title"], "ChatEvent Discourse practice")
        self.assertEqual(event.payload["content"], "hello from Discourse")
        self.assertEqual(event.metadata["acquisition"], "discourse-webhook")

    def test_discourse_reply_created_is_distinct_from_topic_post(self) -> None:
        event = normalize_discourse_post(
            {
                "event_name": "post_created",
                "post": {
                    "id": 26,
                    "topic_id": 18,
                    "post_number": 2,
                    "username": "RexWang",
                    "created_at": "2026-08-05T03:00:00Z",
                    "topic_slug": "chatevent-discourse-practice",
                    "topic_title": "ChatEvent Discourse practice",
                    "raw": "reply from Discourse",
                },
            },
            subscription_id="discourse-practice",
            base_url="https://discourse.public.lookeng.cn",
        )

        self.assertEqual(event.kind, "reply.created")
        self.assertEqual(event.subject_id, "post:26")
        self.assertEqual(event.conversation_id, "topic:18")
        self.assertEqual(event.url, "https://discourse.public.lookeng.cn/t/chatevent-discourse-practice/18/2")
        self.assertEqual(event.action.verb, "created")
        self.assertEqual(event.target.type, "discourse_post")
        self.assertEqual(event.target.parent.type, "discourse_topic")

    def test_gitea_issue_normalizes_issue_api_payload(self) -> None:
        event = normalize_gitea_issue(
            {
                "id": 9001,
                "number": 42,
                "title": "ChatEvent practice issue",
                "body": "hello from Gitea",
                "state": "open",
                "created_at": "2026-08-18T09:00:00Z",
                "updated_at": "2026-08-18T09:02:00Z",
                "html_url": "https://gitea.lookeng.cn/ChatEvent/practice/issues/42",
                "user": {"login": "RexWang"},
            },
            repository="ChatEvent/practice",
            subscription_id="gitea-practice",
        )

        self.assertEqual(event.source, "gitea")
        self.assertEqual(event.kind, "issue.opened")
        self.assertEqual(event.id, "issue:ChatEvent/practice:42")
        self.assertEqual(event.capture_mode, CaptureMode.API_CURSOR)
        self.assertEqual(event.actor_id, "user:RexWang")
        self.assertEqual(event.conversation_id, "repo:ChatEvent/practice")
        self.assertEqual(event.subject_id, "issue:42")
        self.assertEqual(event.subject_type, "issue")
        self.assertEqual(event.action.kind, "issue.opened")
        self.assertEqual(event.action.object_type, "issue")
        self.assertEqual(event.target.type, "issue")
        self.assertEqual(event.target.key, "ChatEvent/practice#42")
        self.assertEqual(event.target.parent.type, "repo")
        self.assertEqual(event.target.parent.key, "ChatEvent/practice")
        self.assertEqual(event.cursor, "9001")
        self.assertEqual(event.payload["title"], "ChatEvent practice issue")
        self.assertEqual(event.metadata["acquisition"], "gitea-issues-api")


if __name__ == "__main__":
    unittest.main()
