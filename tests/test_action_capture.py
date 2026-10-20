"""Official queue/webhook action shapes, identity, and scope behavior."""

from chatevent.adapters import normalize_discourse_webhook, normalize_zulip_queue_event
from chatevent.model import CaptureMode
from chatevent.capture import capture_zulip_once
from chatevent.capture import capture_discourse_topic_backfill
from unittest.mock import patch


def test_zulip_bulk_move_and_delete_expand_without_object_identity_loss():
    moved = normalize_zulip_queue_event({
        "id": 7, "type": "update_message", "message_id": 11,
        "message_ids": [11, 12], "stream_id": 3, "orig_subject": "old",
        "new_stream_id": 4, "subject": "new", "edit_timestamp": 1787047000,
    }, instance="https://zulip.example.org", queue_lifetime="queue-a")
    assert len(moved) == 2
    assert {item.kind for item in moved} == {"message.moved"}
    assert {item.subject_id for item in moved} == {"message:11", "message:12"}
    assert moved[0].dedupe_key != normalize_zulip_queue_event({
        "id": 7, "type": "update_message", "message_id": 11,
        "message_ids": [11], "stream_id": 3, "orig_subject": "old",
        "new_stream_id": 4, "subject": "new", "edit_timestamp": 1787047000,
    }, instance="https://zulip.example.org", queue_lifetime="queue-b")[0].dedupe_key
    deleted = normalize_zulip_queue_event({
        "id": 8, "type": "delete_message", "message_ids": [11, 12],
        "stream_id": 4, "topic": "new",
    }, instance="https://zulip.example.org", queue_lifetime="queue-a")
    assert [item.subject_id for item in deleted] == ["message:11", "message:12"]
    assert all(item.kind == "message.deleted" for item in deleted)


def test_zulip_reaction_and_control_are_distinct():
    reaction = normalize_zulip_queue_event({
        "id": 9, "type": "reaction", "op": "add", "message_id": 11,
        "user_id": 5, "emoji_code": "1f389", "reaction_type": "unicode_emoji",
    }, instance="https://zulip.example.org", queue_lifetime="queue-a")
    assert reaction[0].kind == "reaction.added"
    assert reaction[0].actor_id == "user:5"
    assert reaction[0].subject_id == "message:11"
    assert normalize_zulip_queue_event({"id": 10, "type": "heartbeat"}, queue_lifetime="queue-a") == []


def test_discourse_wrapped_edit_retry_and_user_subject_actor():
    raw = {"post": {"id": 25, "topic_id": 18, "post_number": 2,
                    "username": "author", "updated_at": "2026-08-05T03:00:00Z", "raw": "edit"},
           "actor": {"id": 8, "username": "editor"}}
    edit = normalize_discourse_webhook(raw, event_name="post_edited", instance="https://forum.example.org")
    repeat = normalize_discourse_webhook(raw, event_name="post_edited", instance="https://forum.example.org")
    assert edit.kind == "post.edited"
    assert edit.subject_id == "post:25"
    assert edit.actor_id == "user:8"
    assert edit.dedupe_key == repeat.dedupe_key
    changed = normalize_discourse_webhook({**raw, "post": {**raw["post"], "raw": "second edit"}}, event_name="post_edited", instance="https://forum.example.org")
    assert changed.dedupe_key != edit.dedupe_key
    user = normalize_discourse_webhook({"user": {"id": 4, "username": "subject", "updated_at": "2026-08-05T03:00:00Z"}}, event_name="user_suspended")
    assert user.kind == "user.suspended"
    assert user.subject_id == "user:4"
    assert user.actor_id is None


def test_discourse_supported_registry_rejects_invented_like_removed():
    for name, wrapper, obj in (
        ("topic_revised", "topic", {"id": 9}),
        ("category_created", "category", {"id": 10}),
        ("tag_destroyed", "tag", {"id": 11}),
        ("group_user_added", "group_user", {"group_id": 12, "user_id": 3}),
        ("like_created", "like", {"id": 13}),
        ("notification_created", "notification", {"id": 14}),
    ):
        event = normalize_discourse_webhook({wrapper: obj}, event_name=name)
        assert event.subject_id is not None
        assert event.metadata["timestamp_source"] == "capture-time"
    try:
        normalize_discourse_webhook({"like": {"id": 1}}, event_name="like_removed")
    except ValueError:
        pass
    else:
        raise AssertionError("unsupported event was silently normalized")


def test_zulip_capture_requests_action_types_and_reports_unsupported(tmp_path):
    env_file = tmp_path / "zulip.env"
    env_file.write_text("ZULIP_SITE=https://zulip.example.org\nZULIP_BOT_EMAIL=bot@example.org\nZULIP_BOT_API_KEY=fake\n")
    calls = []
    polls = 0

    def fake_request(_env, method, path, *, data=None, query=None, timeout=None):
        nonlocal polls
        calls.append((method, path, data))
        if path == "/api/v1/register":
            return {"queue_id": "queue-a", "last_event_id": -1}
        if method == "DELETE":
            return {"result": "success"}
        polls += 1
        return {"events": [
            {"id": 1, "type": "reaction", "op": "add", "message_id": 11, "user_id": 5, "emoji_code": "1f389"},
            {"id": 2, "type": "unknown_plugin"}, {"id": 3, "type": "heartbeat"},
        ] if polls == 1 else []}

    with patch("chatevent.capture._zulip_request", fake_request):
        summary = capture_zulip_once(db_path=tmp_path / "events.db", env_file=env_file, timeout_seconds=0.03, subscription_id=None)
    requested = calls[0][2]["event_types"]
    assert set(requested) == {"message", "update_message", "delete_message", "reaction", "stream", "subscription", "realm_user"}
    assert summary.captured == 1
    assert summary.unsupported == 1
    assert summary.control == 1
    assert ("DELETE", "/api/v1/events", None) in calls


def test_discourse_topic_backfill_reads_bounded_current_snapshot(tmp_path):
    paths = []

    def fake_get(_base, path, **_kwargs):
        paths.append(path)
        if path == "/t/18.json":
            return {"id": 18, "slug": "discussion", "title": "Discussion",
                    "created_at": "2026-08-05T02:00:00Z",
                    "post_stream": {"stream": [25, 26, 27]}}
        return {"id": int(path.split("/")[2].split(".")[0]), "topic_id": 18,
                "post_number": int(path.split("/")[2].split(".")[0]) - 24,
                "username": "alice", "created_at": "2026-08-05T03:00:00Z",
                "raw": "snapshot"}

    with patch("chatevent.capture._discourse_get", fake_get):
        summary = capture_discourse_topic_backfill(
            db_path=tmp_path / "events.db", base_url="https://forum.example.org",
            topic_id=18, limit=2, subscription_id=None,
        )
    assert paths == ["/t/18.json", "/posts/25.json", "/posts/26.json"]
    assert summary.captured == 3  # topic snapshot + two current posts
    assert summary.created == 3
