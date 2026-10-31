from copy import deepcopy

import pytest

from chatevent import community_discourse_status as status


def invocation():
    return {"id": "a" * 32, "binding": {"instance": "https://forum.test", "account_id": "user:5",
            "username": "hermes-recall", "profile": "/private/reply.env",
            "status_profile": "/private/status.env", "allowed_category_ids": [5]},
            "event": {"source": "discourse", "kind": "reply.created", "instance": "https://forum.test",
            "subject_id": "post:45", "conversation_id": "topic:29", "actor_id": "user:3",
            "metadata": {"community_scope": "category:5"}, "raw_payload": {"post": {
                "id": 45, "topic_id": 29, "post_number": 1, "category_id": 5, "user_id": 3}}}}


def post(stage="queued", **updates):
    return {"id": 50, "user_id": 5, "username": "hermes-recall", "topic_id": 29,
            "reply_to_post_number": 1, "raw": status._raw("a" * 32, stage), **updates}


def receipt(stage="queued", **updates):
    return {"source": "discourse", "id": "50", "identity_id": "user:5", "source_post_id": "45",
            "topic_id": "29", "invocation_id": "a" * 32, "stage": stage,
            "content_sha256": status._digest(status._raw("a" * 32, stage)), **updates}


def mock_transport(monkeypatch, replies):
    calls, profiles = [], []

    def profile(binding, source):
        profiles.append((binding, source))
        return "https://forum.test", {"Api-Key": "fixture-fake-key"}

    def http(url, **kwargs):
        calls.append((url, kwargs))
        response = replies.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(status, "profile_headers", profile)
    monkeypatch.setattr(status, "http_json", http)
    return calls, profiles


ME = {"current_user": {"id": 5, "username": "hermes-recall", "admin": False, "moderator": False}}


def test_create_uses_dedicated_profile_and_reads_back_own_post(monkeypatch):
    calls, profiles = mock_transport(monkeypatch, [ME, post(), post()])
    result = status.status_sender(invocation(), "queued")
    assert result == {**receipt(), "created": True, "verified": True}
    assert profiles[0][0]["profile"] == "/private/status.env"
    assert profiles[0][1] == "discourse"
    assert calls[1][1]["fields"] == {"topic_id": 29, "reply_to_post_number": 1,
                                      "raw": status._raw("a" * 32, "queued")}
    assert [url.rsplit("/", 1)[-1] for url, _ in calls] == ["current.json", "posts.json", "50.json"]


def test_update_is_one_own_post_and_keeps_original_target(monkeypatch):
    calls, _ = mock_transport(monkeypatch, [ME, post(), {"post": post("running")}, post("running")])
    result = status.status_sender(invocation(), "running", receipt())
    assert result["id"] == "50" and result["stage"] == "running" and not result["created"]
    assert result["verified"] is True
    writes = [(url, kw) for url, kw in calls if kw.get("method") == "PUT"]
    assert len(writes) == 1 and writes[0][0].endswith("/posts/50.json")
    assert set(writes[0][1]["body"]["post"]) == {"raw", "edit_reason"}
    assert not any(url.endswith("/posts.json") for url, _ in calls)


def test_already_desired_update_reads_back_without_second_put(monkeypatch):
    calls, _ = mock_transport(monkeypatch, [ME, post("running")])
    result = status.status_sender(invocation(), "running", receipt())
    assert result["stage"] == "running" and result["verified"] is True
    assert len(calls) == 2 and all(not kw.get("method") for _, kw in calls)


@pytest.mark.parametrize("changes", [
    {"identity_id": "user:6"}, {"topic_id": "999"}, {"source_post_id": "99"},
    {"invocation_id": "b" * 32}, {"content_sha256": "changed"}, {"id": "../1"},
])
def test_cross_identity_or_forged_receipt_never_reads_credentials(monkeypatch, changes):
    calls, profiles = mock_transport(monkeypatch, [])
    with pytest.raises(ValueError):
        status.status_sender(invocation(), "running", receipt(**changes))
    assert not calls and not profiles


@pytest.mark.parametrize("changes", [
    {"user_id": 6}, {"username": "other"}, {"topic_id": 30},
    {"reply_to_post_number": 9}, {"raw": "human edit must be preserved"},
])
def test_foreign_or_manually_changed_post_is_preserved(monkeypatch, changes):
    calls, _ = mock_transport(monkeypatch, [ME, post(**changes)])
    with pytest.raises(ValueError):
        status.status_sender(invocation(), "running", receipt())
    assert len(calls) == 2 and not any(kw.get("method") == "PUT" for _, kw in calls)


@pytest.mark.parametrize("change", ["source", "scope", "conversation", "profile", "actor", "instance"])
def test_untrusted_origin_cannot_route_a_status(monkeypatch, change):
    item = deepcopy(invocation())
    if change == "source":
        item["event"]["source"] = "zulip"
    elif change == "scope":
        item["binding"]["allowed_category_ids"] = [9]
    elif change == "conversation":
        item["event"]["conversation_id"] = "topic:999"
    elif change == "profile":
        del item["binding"]["status_profile"]
    elif change == "actor":
        item["event"]["actor_id"] = "user:999"
    else:
        item["event"]["instance"] = "https://attacker.test"
    calls, profiles = mock_transport(monkeypatch, [])
    with pytest.raises(ValueError):
        status.status_sender(item, "queued")
    assert not calls and not profiles


def test_create_timeout_has_no_automatic_retry(monkeypatch):
    calls, _ = mock_transport(monkeypatch, [ME, status.TransportError("transport_failed")])
    with pytest.raises(status.StatusCreateAmbiguous, match="status_create_ambiguous") as captured:
        status.status_sender(invocation(), "queued")
    assert captured.value.retry_safe is False and captured.value.receipt is None
    assert len(calls) == 2


def test_known_created_id_survives_failed_readback_for_get_reconciliation(monkeypatch):
    calls, _ = mock_transport(monkeypatch, [ME, post(), status.TransportError("transport_failed")])
    with pytest.raises(status.StatusCreateAmbiguous) as captured:
        status.status_sender(invocation(), "queued")
    partial = captured.value.receipt
    assert partial == {**receipt(), "created": True, "verified": False}
    assert captured.value.retry_safe is False and len(calls) == 3
    calls, _ = mock_transport(monkeypatch, [ME, post()])
    result = status.status_sender(invocation(), "queued", partial)
    assert result["verified"] is True
    assert len(calls) == 2 and not any(url.endswith("/posts.json") for url, _ in calls)


@pytest.mark.parametrize("kind", ["post.created", "reply.created"])
def test_native_discourse_post_and_reply_kinds(monkeypatch, kind):
    item = invocation()
    item["event"]["kind"] = kind
    calls, _ = mock_transport(monkeypatch, [ME, post(), post()])
    assert status.status_sender(item, "queued")["verified"] is True
    assert len(calls) == 3


def test_non_native_message_kind_is_rejected(monkeypatch):
    item = invocation()
    item["event"]["kind"] = "message.created"
    calls, profiles = mock_transport(monkeypatch, [])
    with pytest.raises(ValueError, match="Discourse source"):
        status.status_sender(item, "queued")
    assert not calls and not profiles


def test_wrong_current_identity_stops_before_writing(monkeypatch):
    calls, _ = mock_transport(monkeypatch, [{"current_user": {"id": 6}}])
    with pytest.raises(ValueError, match="identity mismatch"):
        status.status_sender(invocation(), "queued")
    assert len(calls) == 1


def test_invalid_stage_has_no_side_effects(monkeypatch):
    calls, profiles = mock_transport(monkeypatch, [])
    with pytest.raises(ValueError, match="unsupported status"):
        status.status_sender(invocation(), "arbitrary-text")
    assert not calls and not profiles


def test_all_http_calls_share_one_ten_second_budget(monkeypatch):
    clock = iter([100, 100, 102, 107, 109.5])
    monkeypatch.setattr(status.time, "monotonic", lambda: next(clock))
    calls, _ = mock_transport(monkeypatch, [ME, post(), {"post": post("running")}, post("running")])
    assert status.status_sender(invocation(), "running", receipt())["verified"] is True
    assert [kwargs["timeout"] for _, kwargs in calls] == [10, 8, 3, 0.5]


def test_create_budget_expiry_keeps_known_id_without_another_http_call(monkeypatch):
    clock = iter([100, 100, 103, 111])
    monkeypatch.setattr(status.time, "monotonic", lambda: next(clock))
    calls, _ = mock_transport(monkeypatch, [ME, post()])
    with pytest.raises(status.StatusCreateAmbiguous) as captured:
        status.status_sender(invocation(), "queued")
    assert captured.value.retry_safe is False
    assert captured.value.receipt == {**receipt(), "created": True, "verified": False}
    assert len(calls) == 2
    assert [kwargs["timeout"] for _, kwargs in calls] == [10, 7]


def test_edit_budget_expiry_stops_before_put(monkeypatch):
    clock = iter([100, 100, 105, 111])
    monkeypatch.setattr(status.time, "monotonic", lambda: next(clock))
    calls, _ = mock_transport(monkeypatch, [ME, post()])
    with pytest.raises(status.TransportError, match="status_deadline_exceeded"):
        status.status_sender(invocation(), "running", receipt())
    assert len(calls) == 2 and not any(kwargs.get("method") == "PUT" for _, kwargs in calls)
