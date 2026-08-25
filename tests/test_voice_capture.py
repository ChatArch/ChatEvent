import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from chatevent import CaptureMode
from chatevent.adapters import normalize_voice_talk
from chatevent.capture import capture_voice_backfill, capture_voice_once
from chatevent.store import EventStore
from chatevent.subscription import Subscription


class FakeHttpResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeHttpResponse":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def _talks() -> list[dict[str, object]]:
    return [
        {
            "id": "meeting_1",
            "title": "Planning",
            "tags": ["thought"],
            "created_at": "2026-08-20T01:00:00Z",
            "updated_at": "2026-08-20T01:10:00Z",
            "duration_seconds": 600,
            "preview": "private transcript preview must not be stored",
            "summary_content": "private summary must not be stored",
            "transcript_segments": [{"text": "private transcript segment"}],
        },
        {
            "id": "meeting_2",
            "title": "Follow-up",
            "created_at": "2026-08-21T01:00:00Z",
            "updated_at": "2026-08-21T01:00:00Z",
            "duration_seconds": 60,
        },
    ]


class VoiceCaptureTests(unittest.TestCase):
    def test_normalize_voice_talk_keeps_only_metadata_payload(self) -> None:
        event = normalize_voice_talk(_talks()[0], kind="talk.updated")
        retagged = normalize_voice_talk(
            {**_talks()[0], "tags": ["thought", "assignment"]},
            kind="talk.updated",
        )

        self.assertEqual(event.source, "voice")
        self.assertEqual(event.kind, "talk.updated")
        self.assertEqual(event.capture_mode, CaptureMode.POLL)
        self.assertEqual(event.subject_id, "talk:meeting_1")
        self.assertEqual(event.subject_type, "talk")
        self.assertEqual(event.target.type, "voice_talk")
        self.assertEqual(event.target.parent.type, "voice_account")
        self.assertEqual(event.payload["talk_id"], "meeting_1")
        self.assertEqual(event.payload["tags"], ["thought"])
        self.assertTrue(event.payload["summary_available"])
        self.assertTrue(event.payload["transcript_available"])
        self.assertIsNone(event.raw_payload)

        serialized = json.dumps(event.model_dump(mode="json"), ensure_ascii=False)
        self.assertNotIn("private transcript", serialized)
        self.assertNotIn("private summary", serialized)
        self.assertNotIn("preview", serialized)
        self.assertNotIn("summary_content", serialized)
        self.assertNotIn("transcript_segments", serialized)
        self.assertNotEqual(event.dedupe_key, retagged.dedupe_key)

    def test_voice_backfill_records_created_events_and_dedupes(self) -> None:
        def fake_urlopen(request, timeout: float = 0):  # type: ignore[no-untyped-def]
            self.assertEqual(request.get_method(), "GET")
            self.assertEqual(request.full_url, "https://voice.example.test/api/data/meetings")
            self.assertIn("Authorization", request.headers)
            return FakeHttpResponse({"meetings": _talks()})

        with TemporaryDirectory() as directory:
            db = Path(directory) / "events.db"
            env_file = Path(directory) / ".env"
            env_file.write_text(
                "CHATVOICE_BASE_URL=https://voice.example.test\nCHATVOICE_DATA_READ=secret\n",
                encoding="utf-8",
            )
            with patch("chatevent.capture.urlopen", fake_urlopen):
                first = capture_voice_backfill(db_path=db, env_file=env_file, all_talks=True)
                second = capture_voice_backfill(db_path=db, env_file=env_file, all_talks=True)
            events = EventStore(db).list_events(source="voice", limit=10)
            subscription = EventStore(db).get_subscription("voice-default")

        self.assertEqual(first.captured, 2)
        self.assertEqual(first.created, 2)
        self.assertEqual(second.captured, 2)
        self.assertEqual(second.created, 0)
        self.assertEqual(len(events), 2)
        self.assertEqual({event.event.kind for event in events}, {"talk.created"})
        self.assertTrue(all(event.seen_count == 2 for event in events))
        self.assertIsNotNone(subscription)
        assert subscription is not None
        self.assertEqual(subscription.source, "voice")
        self.assertEqual(subscription.target, "account:default")
        self.assertEqual(subscription.scope.type, "voice_account")
        self.assertEqual(
            [action.kind for action in subscription.actions],
            ["talk.created", "talk.updated"],
        )
        self.assertTrue(all(event.event.subscription_id == "voice-default" for event in events))

    def test_voice_once_filters_since_and_emits_updated_event(self) -> None:
        def fake_urlopen(_request, timeout: float = 0):  # type: ignore[no-untyped-def]
            return FakeHttpResponse({"meetings": _talks()})

        with TemporaryDirectory() as directory:
            db = Path(directory) / "events.db"
            env_file = Path(directory) / ".env"
            env_file.write_text(
                "CHATVOICE_BASE_URL=https://voice.example.test\nCHATVOICE_DATA_READ=secret\n",
                encoding="utf-8",
            )
            with patch("chatevent.capture.urlopen", fake_urlopen):
                summary = capture_voice_once(
                    db_path=db,
                    env_file=env_file,
                    since="2026-08-20T01:05:00Z",
                )
            events = EventStore(db).list_events(source="voice", limit=10)

        self.assertEqual(summary.captured, 2)
        self.assertEqual(summary.created, 2)
        self.assertEqual({event.event.kind for event in events}, {"talk.created", "talk.updated"})

    def test_voice_once_detects_tag_change_without_updated_at_change(self) -> None:
        responses = [
            {"meetings": [{**_talks()[0], "tags": ["reference"]}]},
            {"meetings": [{**_talks()[0], "tags": ["reference", "thought"]}]},
            {"meetings": [{**_talks()[0], "tags": ["reference", "thought"]}]},
        ]

        def fake_urlopen(_request, timeout: float = 0):  # type: ignore[no-untyped-def]
            return FakeHttpResponse(responses.pop(0))

        with TemporaryDirectory() as directory:
            db = Path(directory) / "events.db"
            env_file = Path(directory) / ".env"
            env_file.write_text(
                "CHATVOICE_BASE_URL=https://voice.example.test\nCHATVOICE_DATA_READ=secret\n",
                encoding="utf-8",
            )
            with patch("chatevent.capture.urlopen", fake_urlopen):
                baseline = capture_voice_backfill(db_path=db, env_file=env_file, all_talks=True)
                changed = capture_voice_once(
                    db_path=db,
                    env_file=env_file,
                    since="2026-08-20T01:10:00Z",
                )
                duplicate = capture_voice_once(
                    db_path=db,
                    env_file=env_file,
                    since="2026-08-20T01:10:00Z",
                )
            events = EventStore(db).list_events(source="voice", limit=10)

        updated = [event.event for event in events if event.event.kind == "talk.updated"]
        self.assertEqual(baseline.created, 1)
        self.assertEqual(changed.captured, 1)
        self.assertEqual(changed.created, 1)
        self.assertEqual(duplicate.captured, 0)
        self.assertEqual(len(updated), 1)
        self.assertEqual(updated[0].payload["tags"], ["reference", "thought"])

    def test_voice_capture_rejects_non_voice_subscription_id(self) -> None:
        def fake_urlopen(_request, timeout: float = 0):  # type: ignore[no-untyped-def]
            return FakeHttpResponse({"meetings": _talks()})

        with TemporaryDirectory() as directory:
            db = Path(directory) / "events.db"
            store = EventStore(db)
            store.save_subscription(
                Subscription(
                    id="shared-id",
                    source="x",
                    target="user:example",
                    event_kinds=["post.created"],
                    capture_modes=[CaptureMode.POLL],
                )
            )
            env_file = Path(directory) / ".env"
            env_file.write_text(
                "CHATVOICE_BASE_URL=https://voice.example.test\nCHATVOICE_DATA_READ=secret\n",
                encoding="utf-8",
            )
            with patch("chatevent.capture.urlopen", fake_urlopen):
                with self.assertRaisesRegex(RuntimeError, "not 'voice'"):
                    capture_voice_backfill(
                        db_path=db,
                        env_file=env_file,
                        all_talks=True,
                        subscription_id="shared-id",
                    )


if __name__ == "__main__":
    unittest.main()
