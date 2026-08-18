import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from chatevent.server import create_app


class ServerTests(unittest.TestCase):
    def test_observatory_flow(self) -> None:
        with TemporaryDirectory() as directory:
            client = TestClient(create_app(db_path=Path(directory) / "events.db"))

            dashboard = client.get("/")
            self.assertEqual(dashboard.status_code, 200)
            self.assertIn("ChatEvent Observatory", dashboard.text)
            self.assertIn("Subscriptions", dashboard.text)

            subscription = client.post(
                "/api/subscriptions",
                json={
                    "id": "core-repo",
                    "label": "Core repository",
                    "source": "gitea",
                    "target": "owner/repo",
                    "event_kinds": ["issue.opened"],
                    "capture_modes": ["webhook", "api_cursor"],
                    "filters": {"repository": "owner/repo"},
                    "labels": ["practice", "repo:owner/repo"],
                },
            )
            self.assertEqual(subscription.status_code, 201)

            event = {
                "id": "issue-42",
                "source": "gitea",
                "kind": "issue.opened",
                "occurred_at": datetime(2026, 8, 18, tzinfo=timezone.utc).isoformat(),
                "capture_mode": "webhook",
                "subscription_id": "core-repo",
                "payload": {"title": "Investigate event routing"},
                "raw_payload": {"action": "opened", "issue": {"number": 42}},
            }
            first = client.post("/api/events", json=event)
            second = client.post("/api/events", json=event)

            self.assertEqual(first.status_code, 202)
            self.assertTrue(first.json()["created"])
            self.assertFalse(second.json()["created"])
            self.assertEqual(second.json()["seen_count"], 2)

            events = client.get("/api/events", params={"source": "gitea"}).json()
            self.assertEqual(events["count"], 1)
            self.assertEqual(
                events["items"][0]["event"]["raw_payload"]["action"], "opened"
            )

            detail = client.get("/api/events/gitea:issue-42")
            self.assertEqual(detail.status_code, 200)
            self.assertEqual(detail.json()["seen_count"], 2)

            stats = client.get("/api/stats").json()
            self.assertEqual(stats["event_count"], 1)
            self.assertEqual(stats["subscription_count"], 1)
            self.assertEqual(stats["duplicate_count"], 1)

            event_schema = client.get("/api/schema/event").json()
            self.assertIn("raw_payload", event_schema["properties"])

            platforms = client.get("/api/platforms")
            self.assertEqual(platforms.status_code, 200)
            platform_ids = [item["id"] for item in platforms.json()["items"]]
            self.assertEqual(platform_ids, ["discourse", "gitea", "github", "zulip"])

    def test_webhook_endpoints_normalize_platform_payloads(self) -> None:
        with TemporaryDirectory() as directory:
            client = TestClient(create_app(db_path=Path(directory) / "events.db"))

            zulip = client.post(
                "/webhooks/zulip",
                json={
                    "id": 101,
                    "type": "message",
                    "message": {
                        "id": 24,
                        "timestamp": 1787047000,
                        "sender_id": 7,
                        "stream_id": 3,
                        "display_recipient": "chatevent-practice",
                        "topic": "zulip-event-queue",
                        "content": "hello from Zulip",
                    },
                },
            )
            discourse = client.post(
                "/webhooks/discourse",
                json={
                    "event_name": "post_created",
                    "post": {
                        "id": 25,
                        "topic_id": 18,
                        "post_number": 2,
                        "username": "RexWang",
                        "created_at": "2026-08-05T02:59:00Z",
                        "raw": "hello from Discourse",
                    },
                },
            )
            gitea = client.post(
                "/webhooks/gitea",
                json={
                    "action": "opened",
                    "repository": {"full_name": "ChatEvent/practice"},
                    "issue": {
                        "id": 9001,
                        "number": 42,
                        "title": "ChatEvent practice issue",
                        "created_at": "2026-08-18T09:00:00Z",
                    },
                },
            )
            github = client.post(
                "/webhooks/github",
                headers={"X-GitHub-Event": "push"},
                json={
                    "ref": "refs/heads/main",
                    "after": "abc123456789",
                    "head_commit": {
                        "id": "abc123456789",
                        "message": "feat: record ChatEvent demo loop",
                        "timestamp": "2026-08-18T10:30:00Z",
                    },
                    "repository": {"full_name": "ChatArch/ChatEvent"},
                    "sender": {"login": "RexWang"},
                },
            )

            self.assertEqual(zulip.status_code, 202)
            self.assertEqual(discourse.status_code, 202)
            self.assertEqual(gitea.status_code, 202)
            self.assertEqual(github.status_code, 202)
            stats = client.get("/api/stats").json()
            self.assertEqual(stats["event_count"], 4)
            self.assertEqual(
                stats["sources"],
                {"discourse": 1, "gitea": 1, "github": 1, "zulip": 1},
            )

    def test_webhook_subscription_id_updates_subscription_cursor(self) -> None:
        with TemporaryDirectory() as directory:
            client = TestClient(create_app(db_path=Path(directory) / "events.db"))
            client.post(
                "/api/subscriptions",
                json={
                    "id": "zulip-practice",
                    "source": "zulip",
                    "target": "stream:chatevent-practice/topic:real-loop",
                    "capture_modes": ["push"],
                },
            )

            response = client.post(
                "/webhooks/zulip?subscription_id=zulip-practice",
                json={
                    "id": 101,
                    "type": "message",
                    "message": {
                        "id": 24,
                        "timestamp": 1787047000,
                        "sender_id": 7,
                        "stream_id": 3,
                        "display_recipient": "chatevent-practice",
                        "topic": "real-loop",
                        "content": "hello from Zulip",
                    },
                },
            )
            self.assertEqual(response.status_code, 202)

            subscriptions = client.get("/api/subscriptions").json()
            self.assertEqual(len(subscriptions), 1)
            item = subscriptions[0]
            self.assertEqual(item["id"], "zulip-practice")
            self.assertEqual(item["last_cursor"], "101")
            self.assertIsNotNone(item["last_event_at"])

    def test_api_rejects_naive_time_and_unknown_fields(self) -> None:
        with TemporaryDirectory() as directory:
            client = TestClient(create_app(db_path=Path(directory) / "events.db"))
            response = client.post(
                "/api/events",
                json={
                    "id": "1",
                    "source": "gitea",
                    "kind": "issue.opened",
                    "occurred_at": "2026-08-18T00:00:00",
                    "capture_mode": "push",
                    "unknown": True,
                },
            )

            self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
