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
                    "event_kinds": ["issue.*"],
                    "capture_modes": ["push", "pull"],
                },
            )
            self.assertEqual(subscription.status_code, 201)

            event = {
                "id": "issue-42",
                "source": "gitea",
                "kind": "issue.opened",
                "occurred_at": datetime(2026, 8, 18, tzinfo=timezone.utc).isoformat(),
                "capture_mode": "push",
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
