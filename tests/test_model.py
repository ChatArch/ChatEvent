import unittest
from datetime import datetime, timezone

from pydantic import ValidationError

from chatevent import (
    ActionDescriptor,
    ActorDescriptor,
    CaptureMode,
    CarrierTarget,
    ChatEvent,
    Subscription,
)


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
        self.assertIn("action", schema["properties"])
        self.assertIn("target", schema["properties"])
        self.assertIn("actor", schema["properties"])
        self.assertIn("actor_role", schema["properties"])
        self.assertEqual(schema["properties"]["schema_version"]["default"], "1.0")

    def test_event_records_flexible_action_target_chain(self) -> None:
        repo = CarrierTarget(
            type="repo",
            key="ChatArch/ChatEvent",
            display="ChatArch/ChatEvent",
            metadata={"provider": "github"},
        )
        pull_request = CarrierTarget(
            type="pull_request",
            key="ChatArch/ChatEvent#4",
            display="PR #4",
            parent=repo,
        )
        event = ChatEvent(
            id="pull_request:ChatArch/ChatEvent:4",
            source="github",
            kind="pull_request.merged",
            occurred_at=datetime(2026, 8, 18, tzinfo=timezone.utc),
            capture_mode=CaptureMode.WEBHOOK,
            actor=ActorDescriptor(id="user:RexWang", type="user", display="Rex Wang", role="maintainer"),
            action=ActionDescriptor(kind="pull_request.merged", object_type="pull_request", verb="merged"),
            target=pull_request,
        )

        data = event.to_dict()
        self.assertEqual(data["action"]["verb"], "merged")
        self.assertEqual(data["actor"]["role"], "maintainer")
        self.assertEqual(data["target"]["type"], "pull_request")
        self.assertEqual(data["target"]["parent"]["type"], "repo")
        self.assertEqual(data["target"]["parent"]["metadata"]["provider"], "github")

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

    def test_subscription_derives_scope_and_actions_from_legacy_fields(self) -> None:
        subscription = Subscription(
            source="github",
            target="pull_request:ChatArch/ChatEvent#4",
            event_kinds=["pull_request.opened", "issue.commented"],
            capture_modes=["webhook"],
        )

        self.assertEqual(subscription.scope.type, "pull_request")
        self.assertEqual(subscription.scope.key, "ChatArch/ChatEvent#4")
        self.assertEqual(subscription.scope.parent.type, "repo")
        self.assertEqual(subscription.scope.parent.key, "ChatArch/ChatEvent")
        self.assertEqual([action.kind for action in subscription.actions], ["pull_request.opened", "issue.commented"])
        self.assertEqual(subscription.actions[0].object_type, "pull_request")
        self.assertEqual(subscription.actions[0].verb, "opened")

    def test_subscription_accepts_platform_specific_scope_metadata(self) -> None:
        subscription = Subscription(
            source="future-platform",
            target="workspace:abc/card:123",
            scope=CarrierTarget(
                type="future_card",
                key="abc/123",
                metadata={"workspace": "abc", "custom": {"list": "triage"}},
            ),
            actions=[ActionDescriptor(kind="card.moved", object_type="card", verb="moved")],
        )

        self.assertEqual(subscription.event_kinds, ["card.moved"])
        self.assertEqual(subscription.scope.metadata["custom"]["list"], "triage")


if __name__ == "__main__":
    unittest.main()
