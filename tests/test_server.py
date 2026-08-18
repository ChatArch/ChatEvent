import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from chatevent.server import create_app


class ServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._admin_env = patch.dict(
            "os.environ",
            {"CHATEVENT_ADMIN_TOKEN_FILE": "/tmp/chatevent-test-admin-token-missing"},
        )
        self._admin_env.start()

    def tearDown(self) -> None:
        self._admin_env.stop()

    def test_observatory_flow(self) -> None:
        with TemporaryDirectory() as directory:
            client = TestClient(create_app(db_path=Path(directory) / "events.db"))

            dashboard = client.get("/")
            self.assertEqual(dashboard.status_code, 200)
            self.assertIn("ChatEvent Observatory", dashboard.text)
            self.assertIn('role="tablist"', dashboard.text)
            self.assertIn('data-tab-target="eventsPanel"', dashboard.text)
            self.assertIn('data-tab-target="subscriptionsPanel"', dashboard.text)
            self.assertIn('data-tab-target="platformsPanel"', dashboard.text)
            self.assertIn('id="sourceFilter"', dashboard.text)
            self.assertIn('id="timeFilter"', dashboard.text)
            self.assertIn('id="advancedFiltersToggle"', dashboard.text)
            self.assertIn('id="advancedFilters"', dashboard.text)
            self.assertIn('id="kindCheckboxes"', dashboard.text)
            self.assertIn('id="subscriptionCheckboxes"', dashboard.text)
            self.assertIn("selectedKinds", dashboard.text)
            self.assertIn("renderAdvancedFilters", dashboard.text)
            self.assertNotIn('id="kindFilter"', dashboard.text)
            self.assertNotIn("全部事件类型", dashboard.text)
            self.assertIn("editSubscription", dashboard.text)
            self.assertIn("deleteSubscription", dashboard.text)
            self.assertIn("adminToken", dashboard.text)
            self.assertIn("subscriptionScopeType", dashboard.text)
            self.assertIn("Action target", dashboard.text)
            self.assertIn("Actor role", dashboard.text)
            self.assertIn("targetChain", dashboard.text)
            self.assertIn("actionTargetLabel", dashboard.text)
            self.assertIn('id="githubLink"', dashboard.text)
            self.assertIn('href="https://github.com/ChatArch/ChatEvent"', dashboard.text)
            self.assertIn('id="docsLink"', dashboard.text)
            self.assertIn('href="https://arch.gh.wzhecnu.cn/ChatEvent/"', dashboard.text)
            self.assertIn('id="themeToggle"', dashboard.text)
            self.assertIn("data-theme", dashboard.text)
            self.assertIn("platformActionDialog", dashboard.text)
            self.assertIn("openPlatformAction", dashboard.text)
            self.assertIn("API 大致含义", dashboard.text)

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
            self.assertEqual(subscription.json()["scope"]["type"], "repo")
            self.assertEqual(subscription.json()["scope"]["key"], "owner/repo")
            self.assertEqual(subscription.json()["actions"][0]["kind"], "issue.opened")

            event = {
                "id": "issue-42",
                "source": "gitea",
                "kind": "issue.opened",
                "occurred_at": datetime(2026, 8, 18, tzinfo=timezone.utc).isoformat(),
                "capture_mode": "webhook",
                "subscription_id": "core-repo",
                "action": {"kind": "issue.opened", "object_type": "issue", "verb": "opened"},
                "target": {
                    "type": "issue",
                    "key": "owner/repo#42",
                    "parent": {"type": "repo", "key": "owner/repo"},
                },
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
            self.assertEqual(events["items"][0]["event"]["action"]["verb"], "opened")
            self.assertEqual(events["items"][0]["event"]["target"]["parent"]["key"], "owner/repo")

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

    def test_subscription_mutations_can_require_admin_token(self) -> None:
        with TemporaryDirectory() as directory, patch.dict(
            "os.environ", {"CHATEVENT_ADMIN_TOKEN": "secret-token"}
        ):
            client = TestClient(create_app(db_path=Path(directory) / "events.db"))
            body = {
                "id": "discourse-practice",
                "source": "discourse",
                "target": "category:agent-runs",
                "event_kinds": ["post.created", "reply.created"],
                "capture_modes": ["webhook", "api_cursor"],
            }

            no_token = client.post("/api/subscriptions", json=body)
            wrong_token = client.post(
                "/api/subscriptions",
                headers={"X-ChatEvent-Admin-Token": "wrong"},
                json=body,
            )
            ok = client.post(
                "/api/subscriptions",
                headers={"X-ChatEvent-Admin-Token": "secret-token"},
                json=body,
            )
            delete_without_token = client.delete("/api/subscriptions/discourse-practice")
            delete_ok = client.delete(
                "/api/subscriptions/discourse-practice",
                headers={"X-ChatEvent-Admin-Token": "secret-token"},
            )

            self.assertEqual(no_token.status_code, 401)
            self.assertEqual(wrong_token.status_code, 401)
            self.assertEqual(ok.status_code, 201)
            self.assertEqual(delete_without_token.status_code, 401)
            self.assertEqual(delete_ok.status_code, 200)
            self.assertTrue(delete_ok.json()["deleted"])
            self.assertEqual(client.get("/api/subscriptions/discourse-practice").status_code, 404)

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
            discourse_header_event = client.post(
                "/webhooks/discourse",
                headers={"X-Discourse-Event": "post_created"},
                json={
                    "post": {
                        "id": 26,
                        "topic_id": 18,
                        "post_number": 2,
                        "username": "RexWang",
                        "created_at": "2026-08-05T03:00:00Z",
                        "raw": "official header reply from Discourse",
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
            ping = client.post(
                "/webhooks/github",
                headers={"X-GitHub-Event": "ping"},
                json={
                    "zen": "Responsive is better than fast.",
                    "hook_id": 123,
                    "repository": {"full_name": "ChatArch/ChatEvent"},
                },
            )

            self.assertEqual(zulip.status_code, 202)
            self.assertEqual(discourse.status_code, 202)
            self.assertEqual(discourse_header_event.status_code, 202)
            self.assertEqual(gitea.status_code, 202)
            self.assertEqual(github.status_code, 202)
            self.assertEqual(ping.status_code, 202)
            self.assertFalse(ping.json()["created"])
            discourse_events = client.get("/api/events", params={"source": "discourse"}).json()
            discourse_kinds = {item["event"]["id"]: item["event"]["kind"] for item in discourse_events["items"]}
            self.assertEqual(discourse_kinds["post:26"], "reply.created")
            stats = client.get("/api/stats").json()
            self.assertEqual(stats["event_count"], 5)
            self.assertEqual(
                stats["sources"],
                {"discourse": 2, "gitea": 1, "github": 1, "zulip": 1},
            )

    def test_api_events_since_returns_captured_after_checkpoint(self) -> None:
        with TemporaryDirectory() as directory:
            client = TestClient(create_app(db_path=Path(directory) / "events.db"))

            old_event = {
                "id": "post-1",
                "source": "discourse",
                "kind": "post.created",
                "occurred_at": "2026-08-18T10:00:00+00:00",
                "captured_at": "2026-08-18T10:00:01+00:00",
                "capture_mode": "webhook",
                "subscription_id": "discourse-practice",
                "payload": {"title": "old topic"},
            }
            new_event = {
                "id": "post-2",
                "source": "discourse",
                "kind": "reply.created",
                "occurred_at": "2026-08-18T10:00:04+00:00",
                "captured_at": "2026-08-18T10:00:05+00:00",
                "capture_mode": "webhook",
                "subscription_id": "discourse-practice",
                "payload": {"title": "new reply"},
            }
            client.post("/api/events", json=old_event)
            client.post("/api/events", json=new_event)

            response = client.get(
                "/api/events",
                params={
                    "source": "discourse",
                    "subscription_id": "discourse-practice",
                    "since": "2026-08-18T10:00:02+00:00",
                },
            )

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["count"], 1)
            self.assertEqual(payload["next_since"], "2026-08-18T10:00:05Z")
            self.assertEqual(payload["items"][0]["event"]["id"], "post-2")
            self.assertEqual(payload["items"][0]["event"]["kind"], "reply.created")

    def test_api_events_days_filters_recent_captures(self) -> None:
        with TemporaryDirectory() as directory:
            client = TestClient(create_app(db_path=Path(directory) / "events.db"))

            client.post(
                "/api/events",
                json={
                    "id": "old-post",
                    "source": "discourse",
                    "kind": "post.created",
                    "occurred_at": "2000-01-01T00:00:00+00:00",
                    "captured_at": "2000-01-01T00:00:00+00:00",
                    "capture_mode": "webhook",
                    "payload": {"title": "old"},
                },
            )
            client.post(
                "/api/events",
                json={
                    "id": "recent-post",
                    "source": "discourse",
                    "kind": "reply.created",
                    "occurred_at": datetime.now(timezone.utc).isoformat(),
                    "captured_at": datetime.now(timezone.utc).isoformat(),
                    "capture_mode": "webhook",
                    "payload": {"title": "recent"},
                },
            )

            response = client.get("/api/events", params={"days": "1"})

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["count"], 1)
            self.assertEqual(payload["items"][0]["event"]["id"], "recent-post")

    def test_api_events_from_to_filter_captured_range(self) -> None:
        with TemporaryDirectory() as directory:
            client = TestClient(create_app(db_path=Path(directory) / "events.db"))

            for event_id, captured_at in [
                ("before", "2026-08-15T23:59:59+00:00"),
                ("inside", "2026-08-16T12:00:00+00:00"),
                ("after", "2026-08-18T00:00:01+00:00"),
            ]:
                client.post(
                    "/api/events",
                    json={
                        "id": event_id,
                        "source": "gitea",
                        "kind": "issue.opened",
                        "occurred_at": captured_at,
                        "captured_at": captured_at,
                        "capture_mode": "webhook",
                        "payload": {"title": event_id},
                    },
                )

            response = client.get(
                "/api/events",
                params={
                    "from": "2026-08-16T00:00:00+00:00",
                    "to": "2026-08-18T00:00:00+00:00",
                },
            )

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["count"], 1)
            self.assertEqual(payload["items"][0]["event"]["id"], "inside")

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
