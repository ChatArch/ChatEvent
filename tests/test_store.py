import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from chatevent import CaptureMode, ChatEvent, EventStore, Subscription


class EventStoreTests(unittest.TestCase):
    def test_subscriptions_events_and_duplicates_survive_reopen(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "events.db"
            store = EventStore(path)
            subscription = store.save_subscription(
                Subscription(
                    id="core-repo",
                    source="gitea",
                    target="owner/repo",
                    event_kinds=["issue.*"],
                    capture_modes=[CaptureMode.PUSH, CaptureMode.PULL],
                )
            )
            event = ChatEvent(
                id="issue-42",
                source="gitea",
                kind="issue.opened",
                occurred_at=datetime(2026, 8, 18, tzinfo=timezone.utc),
                captured_at=datetime(2026, 8, 18, 1, tzinfo=timezone.utc),
                capture_mode=CaptureMode.PUSH,
                subscription_id=subscription.id,
                cursor="43",
                payload={"title": "Investigate event routing"},
                raw_payload={"action": "opened", "issue": {"number": 42}},
            )

            first, created = store.record_event(event)
            duplicate, duplicate_created = store.record_event(event)

            self.assertTrue(created)
            self.assertFalse(duplicate_created)
            self.assertEqual(first.seen_count, 1)
            self.assertEqual(duplicate.seen_count, 2)

            reopened = EventStore(path)
            self.assertEqual(len(reopened.list_events(source="gitea")), 1)
            reopened_event = reopened.get_event("gitea:issue-42")
            self.assertIsNotNone(reopened_event)
            self.assertEqual(reopened_event.seen_count, 2)
            reopened_subscription = reopened.get_subscription("core-repo")
            self.assertIsNotNone(reopened_subscription)
            self.assertEqual(reopened_subscription.last_cursor, "43")
            self.assertEqual(reopened.stats()["duplicate_count"], 1)

    def test_event_query_searches_serialized_payload(self) -> None:
        with TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "events.db")
            store.record_event(
                ChatEvent(
                    id="1",
                    source="discourse",
                    kind="post.created",
                    occurred_at=datetime(2026, 8, 18, tzinfo=timezone.utc),
                    capture_mode=CaptureMode.PULL,
                    payload={"title": "Watchdog design"},
                )
            )

            self.assertEqual(len(store.list_events(query="Watchdog")), 1)
            self.assertEqual(len(store.list_events(query="missing")), 0)


if __name__ == "__main__":
    unittest.main()
