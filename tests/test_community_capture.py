from datetime import datetime, timezone
import json

import pytest

from chatevent.community_capture import CaptureInbox, CommunityCapture, native_mentions, normalize_message


def registry():
    return {"version": 1, "human_actor_ids": {"zulip": ["user:2"], "discourse": ["user:1"]},
            "ignored_actor_ids": {"zulip": ["user:18"]},
            "agents": [{"agent_id": "recall", "enabled": True, "bindings": {
                "zulip": {"account_id": "user:18", "instance": "https://chat.example", "allowed_stream_ids": [12]},
                "discourse": {"account_id": "user:5", "username": "hermes-recall", "instance": "https://forum.example", "allowed_category_ids": [9]}}}]}


def message(sender=2, stream=12, text=None):
    return {"id": 40, "type": "stream", "stream_id": stream, "subject": "one task", "sender_id": sender,
            "timestamp": 1800000000, "display_recipient": "tasks", "content": text or '<p><span class="user-mention" data-user-id="18">@Recall</span> help</p>'}


def test_native_mentions_ignore_plain_text_code_and_quotes():
    rendered = ('@Recall <code><span class="user-mention" data-user-id="18">@Recall</span></code>'
                '<blockquote><span class="user-mention" data-user-id="19">x</span></blockquote>'
                '<span class="user-mention" data-user-id="20">real</span>')
    assert native_mentions(rendered, "zulip") == ["user:20"]
    assert native_mentions('<a class="mention" href="/u/hermes-recall">@x</a>', "discourse") == ["hermes-recall"]


def test_disclosure_guard_and_inbox_durability(tmp_path):
    tmp_path.chmod(0o700)
    capture = CommunityCapture({"inbox_db": str(tmp_path / "inbox.db")}, registry(), None)
    assert not capture.accept(message(sender=18), "zulip", "https://chat.example")
    assert not capture.accept(message(sender=99), "zulip", "https://chat.example")
    assert not capture.accept(message(stream=999), "zulip", "https://chat.example")
    assert capture.accept(message(), "zulip", "https://chat.example")
    assert not capture.accept(message(), "zulip", "https://chat.example")
    assert capture.inbox.status() == {"inbox": {"pending": 1}, "errors": 0}
    assert capture.inbox.path.stat().st_mode & 0o777 == 0o600


def test_relay_commits_store_before_dispatch_and_recovers_without_second_ingest(tmp_path):
    tmp_path.chmod(0o700)
    inbox = CaptureInbox(tmp_path / "inbox.db")
    event, mentions = normalize_message(message(), source="zulip", instance="https://chat.example", registry=registry())
    inbox.put(event, mentions)
    calls = []
    def persist(event):
        calls.append("persist")
    def fail(event, mentions, registry):
        calls.append("enqueue-failed")
        raise RuntimeError("sensitive text must not be stored as error")
    with pytest.raises(RuntimeError):
        inbox.relay_once(persist, fail, registry())
    assert inbox.status() == {"inbox": {"persisted": 1}, "errors": 1}
    def enqueue(*args):
        calls.append("enqueue")
    assert inbox.relay_once(persist, enqueue, registry())
    assert calls == ["persist", "enqueue-failed", "enqueue"]
    assert not inbox.relay_once(persist, enqueue, registry())


def test_discourse_canonical_numeric_actor_and_category():
    raw = {"post": {"id": 99, "post_number": 2, "topic_id": 42, "user_id": 1, "username": "owner",
                    "category_id": 9, "created_at": "2026-10-30T17:00:00Z", "raw": "@hermes-recall hi",
                    "cooked": '<p><a class="mention" href="/u/hermes-recall">@hermes-recall</a> hi</p>'}}
    event, mentions = normalize_message(raw, source="discourse", instance="https://forum.example", registry=registry())
    assert event.actor_id == event.actor.id == "user:1"
    assert event.kind == "reply.created"
    assert event.metadata["community_scope"] == "category:9"
    assert mentions == ["user:5"]


def test_bad_dispatch_does_not_starve_later_valid_events(tmp_path):
    tmp_path.chmod(0o700)
    inbox = CaptureInbox(tmp_path / "inbox.db")
    event, mentions = normalize_message(message(), source="zulip", instance="https://chat.example", registry=registry())
    inbox.put(event, mentions)
    inbox.put(event.model_copy(update={"id": "message:41", "subject_id": "message:41"}), mentions)
    def enqueue(event, *args):
        if event.id == "message:40":
            raise ValueError("invalid source")
    assert inbox.relay_once(lambda event: None, enqueue, registry())
    assert inbox.relay_once(lambda event: None, enqueue, registry())
    assert inbox.status() == {"inbox": {"dispatched": 1, "quarantined": 1}, "errors": 1}
