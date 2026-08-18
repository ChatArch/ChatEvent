import unittest
from datetime import datetime, timezone

from pydantic import ValidationError

from chatevent import CaptureMode, ChatEvent, Subscription


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
        self.assertEqual(event.to_dict()["occurred_at"], "2026-08-18T00:00:00Z")

    def test_event_rejects_naive_datetime(self) -> None:
        with self.assertRaises(ValidationError):
            ChatEvent(
                id="42",
                source="gitea",
                kind="issue.opened",
                occurred_at=datetime(2026, 8, 18),  # noqa: DTZ001 - invalid by design
                capture_mode=CaptureMode.PULL,
            )

    def test_event_rejects_empty_identity_fields(self) -> None:
        with self.assertRaisesRegex(ValidationError, "must not be empty"):
            ChatEvent(
                id="42",
                source=" ",
                kind="issue.opened",
                occurred_at=datetime(2026, 8, 18, tzinfo=timezone.utc),
                capture_mode=CaptureMode.PULL,
            )

    def test_event_schema_exposes_capture_contract(self) -> None:
        schema = ChatEvent.model_json_schema()

        self.assertIn("raw_payload", schema["properties"])
        self.assertIn("subscription_id", schema["properties"])
        self.assertEqual(schema["properties"]["schema_version"]["default"], "1.0")

    def test_subscription_normalizes_kinds_and_modes(self) -> None:
        subscription = Subscription(
            source=" gitea ",
            target="owner/repo",
            event_kinds=["issue.opened", "issue.opened", " "],
            capture_modes=[CaptureMode.PUSH, CaptureMode.PULL, CaptureMode.PUSH],
        )

        self.assertEqual(subscription.source, "gitea")
        self.assertEqual(subscription.event_kinds, ["issue.opened"])
        self.assertEqual(
            subscription.capture_modes, [CaptureMode.PUSH, CaptureMode.PULL]
        )


if __name__ == "__main__":
    unittest.main()
