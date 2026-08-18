from datetime import datetime, timezone
import unittest

from chatevent import CaptureMode, ChatEvent


class ChatEventTests(unittest.TestCase):
    def test_event_has_stable_dedupe_key_and_serializes(self) -> None:
        event = ChatEvent(
            id="42",
            source="gitea",
            kind="issue.opened",
            occurred_at=datetime(2026, 8, 18, tzinfo=timezone.utc),
            capture_mode=CaptureMode.PUSH,
            payload={"title": "Investigate event routing"},
        )

        self.assertEqual(event.dedupe_key, "gitea:42")
        self.assertEqual(event.to_dict()["capture_mode"], "push")
        self.assertEqual(event.to_dict()["occurred_at"], "2026-08-18T00:00:00+00:00")

    def test_event_rejects_naive_datetime(self) -> None:
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            ChatEvent(
                id="42",
                source="gitea",
                kind="issue.opened",
                occurred_at=datetime(2026, 8, 18),
                capture_mode=CaptureMode.PULL,
            )

    def test_event_rejects_empty_identity_fields(self) -> None:
        with self.assertRaisesRegex(ValueError, "source must not be empty"):
            ChatEvent(
                id="42",
                source=" ",
                kind="issue.opened",
                occurred_at=datetime(2026, 8, 18, tzinfo=timezone.utc),
                capture_mode=CaptureMode.PULL,
            )


if __name__ == "__main__":
    unittest.main()

