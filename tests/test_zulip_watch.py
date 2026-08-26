import contextlib
import io
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from chatevent import CaptureMode, temporary_zulip_topic_watch
from chatevent.capture import (
    capture_subscription_once,
    capture_zulip_subscription_once,
    create_temporary_zulip_topic_watch,
)
from chatevent.cli import main
from chatevent.store import EventStore


class FakeHttpResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeHttpResponse":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def _env_file(directory: str) -> Path:
    env_file = Path(directory) / "zulip.env"
    env_file.write_text(
        "ZULIP_SITE=https://zulip.example.test\n"
        "ZULIP_BOT_EMAIL=bot@example.test\n"
        "ZULIP_BOT_API_KEY=secret\n",
        encoding="utf-8",
    )
    return env_file


def _message(message_id: int, sender_id: int = 7) -> dict[str, object]:
    return {
        "id": message_id,
        "timestamp": 1787047000 + message_id,
        "sender_id": sender_id,
        "sender_email": f"user{sender_id}@example.test",
        "sender_full_name": f"User {sender_id}",
        "sender_is_bot": False,
        "sender_realm_str": "example",
        "stream_id": 3,
        "display_recipient": "voice note",
        "topic": "assignment-123",
        "content": f"reply {message_id}",
        "content_type": "text/html",
    }


class ZulipTemporaryWatchTests(unittest.TestCase):
    def test_temporary_watch_contract_saves_metadata(self) -> None:
        with TemporaryDirectory() as directory:
            db = Path(directory) / "events.db"
            subscription = create_temporary_zulip_topic_watch(
                db_path=db,
                stream="voice note",
                topic="assignment-123",
                assignment_id="assign-123",
                interval_seconds=5,
                expires_at=datetime(2026, 8, 26, 12, 30, tzinfo=timezone.utc),
                hot_until=datetime(2026, 8, 26, 12, 15, tzinfo=timezone.utc),
                reason="active assignment clarification",
                subscription_id="watch-assign-123",
            )
            stored = EventStore(db).get_subscription("watch-assign-123")

        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual(subscription.target, "stream:voice note/topic:assignment-123")
        self.assertEqual(stored.source, "zulip")
        self.assertEqual(stored.scope.type, "zulip_topic")
        self.assertEqual(stored.scope.parent.type, "zulip_stream")
        self.assertEqual(stored.filters, {"stream": "voice note", "topic": "assignment-123"})
        self.assertEqual(stored.metadata["assignment_id"], "assign-123")
        self.assertEqual(stored.metadata["interval_seconds"], 5)
        self.assertEqual(stored.metadata["expires_at"], "2026-08-26T12:30:00+00:00")
        self.assertEqual(stored.metadata["hot_until"], "2026-08-26T12:15:00+00:00")
        self.assertEqual(stored.metadata["content_policy"], "topic-scoped-message-content")
        self.assertIn("consumer filters sender", stored.metadata["policy_boundary"])
        self.assertNotIn("rex", json.dumps(stored.model_dump(mode="json")).lower())
        self.assertNotIn("thought", json.dumps(stored.model_dump(mode="json")).lower())

    def test_topic_scoped_zulip_capture_updates_cursor_and_sender_fields(self) -> None:
        requests = []

        def fake_urlopen(request, timeout: float = 0):  # type: ignore[no-untyped-def]
            requests.append(request)
            return FakeHttpResponse({"result": "success", "messages": [_message(24), _message(25)]})

        with TemporaryDirectory() as directory:
            db = Path(directory) / "events.db"
            env_file = _env_file(directory)
            create_temporary_zulip_topic_watch(
                db_path=db,
                stream="voice note",
                topic="assignment-123",
                assignment_id="assign-123",
                interval_seconds=5,
                ttl_seconds=3600,
                reason="active assignment clarification",
                subscription_id="watch-assign-123",
            )
            with patch("chatevent.capture.urlopen", fake_urlopen):
                summary = capture_zulip_subscription_once(
                    db_path=db,
                    env_file=env_file,
                    subscription_id="watch-assign-123",
                )
            store = EventStore(db)
            events = store.list_events(source="zulip", subscription_id="watch-assign-123")
            subscription = store.get_subscription("watch-assign-123")

        self.assertEqual(summary.captured, 2)
        self.assertEqual(summary.created, 2)
        self.assertEqual(len(events), 2)
        self.assertEqual(subscription.last_cursor, "25")
        event = events[0].event
        self.assertEqual(event.capture_mode, CaptureMode.API_CURSOR)
        self.assertEqual(event.metadata["acquisition"], "zulip-messages-api")
        self.assertEqual(event.payload["content"], "reply 25")
        self.assertEqual(event.payload["sender_id"], "7")
        self.assertEqual(event.payload["sender_email"], "user7@example.test")
        self.assertEqual(event.payload["sender_full_name"], "User 7")
        self.assertFalse(event.payload["sender_is_bot"])
        self.assertEqual(event.actor.id, "user:7")
        self.assertEqual(event.actor.metadata["email"], "user7@example.test")
        parsed = urlparse(requests[0].full_url)
        params = parse_qs(parsed.query)
        narrow = json.loads(params["narrow"][0])
        self.assertEqual(narrow, [{"operator": "stream", "operand": "voice note"}, {"operator": "topic", "operand": "assignment-123"}])

    def test_subscription_capture_uses_cursor_without_sender_policy(self) -> None:
        requests = []

        def fake_urlopen(request, timeout: float = 0):  # type: ignore[no-untyped-def]
            requests.append(request)
            return FakeHttpResponse({"result": "success", "messages": [_message(25), _message(26, sender_id=9)]})

        with TemporaryDirectory() as directory:
            db = Path(directory) / "events.db"
            env_file = _env_file(directory)
            watch = temporary_zulip_topic_watch(
                stream="voice note",
                topic="assignment-123",
                assignment_id="assign-123",
                interval_seconds=5,
                ttl_seconds=3600,
                reason="active assignment clarification",
                subscription_id="watch-assign-123",
            ).model_copy(update={"last_cursor": "25"})
            EventStore(db).save_subscription(watch)
            with patch("chatevent.capture.urlopen", fake_urlopen):
                summary = capture_subscription_once(
                    db_path=db,
                    env_file=env_file,
                    subscription_id="watch-assign-123",
                )
            store = EventStore(db)
            events = store.list_events(source="zulip", subscription_id="watch-assign-123")
            subscription = store.get_subscription("watch-assign-123")

        self.assertEqual(summary.captured, 1)
        self.assertEqual(events[0].event.payload["sender_id"], "9")
        self.assertNotIn("sender_id", subscription.filters)
        params = parse_qs(urlparse(requests[0].full_url).query)
        self.assertEqual(params["anchor"], ["25"])

    def test_cli_creates_temporary_watch(self) -> None:
        with TemporaryDirectory() as directory:
            db = Path(directory) / "events.db"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                main(
                    [
                        "capture",
                        "watch-zulip-topic",
                        "--db",
                        str(db),
                        "--stream",
                        "voice note",
                        "--topic",
                        "assignment-123",
                        "--assignment-id",
                        "assign-123",
                        "--interval-seconds",
                        "5",
                        "--expires-at",
                        "2026-08-26T12:30:00Z",
                        "--reason",
                        "active assignment clarification",
                        "--subscription-id",
                        "watch-assign-123",
                    ]
                )

        result = json.loads(stdout.getvalue())
        self.assertEqual(result["id"], "watch-assign-123")
        self.assertEqual(result["metadata"]["assignment_id"], "assign-123")
        self.assertEqual(result["filters"], {"stream": "voice note", "topic": "assignment-123"})


if __name__ == "__main__":
    unittest.main()
