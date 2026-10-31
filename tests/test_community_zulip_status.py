"""Native reaction state changes with a deterministic in-memory API only."""

from copy import deepcopy

import pytest

from chatevent.community_capture import TransportError
from chatevent.community_zulip_status import STAGE_EMOJI, ZulipStatusSender


@pytest.fixture
def invocation():
    return {"agent_id": "hermes-recall", "community_scope": "stream:7",
            "binding": {"account_id": "user:18", "instance": "https://zulip.test", "profile": "/private/profile.env", "allowed_stream_ids": [7]},
            "event": {"source": "zulip", "kind": "message.created", "instance": "https://zulip.test", "subject_id": "message:21",
                      "actor_id": "user:1", "conversation_id": "stream:7/topic:Task", "metadata": {"community_scope": "stream:7"},
                      "raw_payload": {"message": {"id": 21, "stream_id": 7, "sender_id": 1, "subject": "Task"}}}}


def reaction(code, *, user_id=18, name=None, reaction_type="unicode_emoji"):
    return {"emoji_code": code, "emoji_name": name or next((v["emoji_name"] for v in STAGE_EMOJI.values() if v["emoji_code"] == code), "thumbs_up"),
            "reaction_type": reaction_type, "user_id": user_id}


class Platform:
    def __init__(self, reactions=None):
        self.message = {"id": 21, "stream_id": 7, "sender_id": 1, "type": "stream", "reactions": reactions or []}
        self.calls = []
        self.user_id = 18
        self.fail_write = False
        self.ignore_writes = False

    def __call__(self, url, **kwargs):
        self.calls.append((url, deepcopy(kwargs)))
        assert 0 < kwargs["timeout"] <= 10
        method = kwargs.get("method", "GET")
        if url.endswith("/users/me"):
            return {"result": "success", "user_id": self.user_id}
        if url.endswith("/messages/21"):
            return {"result": "success", "message": deepcopy(self.message)}
        assert url == "https://zulip.test/api/v1/messages/21/reactions"
        assert method in {"POST", "DELETE"}
        fields = kwargs["fields"]
        assert set(fields) == {"emoji_name", "emoji_code", "reaction_type"}
        if self.fail_write:
            raise TransportError("http_403")
        if not self.ignore_writes:
            if method == "POST":
                assert not any(r["user_id"] == self.user_id and r["emoji_code"] == fields["emoji_code"] and r["reaction_type"] == fields["reaction_type"] for r in self.message["reactions"])
                self.message["reactions"].append({**fields, "user_id": self.user_id})
            else:
                self.message["reactions"] = [r for r in self.message["reactions"] if not (r["user_id"] == self.user_id and r["emoji_code"] == fields["emoji_code"] and r["reaction_type"] == fields["reaction_type"])]
        return {"result": "success"}


def sender(platform):
    return ZulipStatusSender(request=platform, profile_loader=lambda binding, source: ("https://zulip.test", {"Authorization": "fixture-only"}))


@pytest.mark.parametrize("stage", list(STAGE_EMOJI))
def test_stage_add_and_native_readback(invocation, stage):
    api = Platform()
    receipt = sender(api)(invocation, stage)
    assert receipt["verified"] and receipt["changed"]
    assert receipt["identity_id"] == "user:18" and receipt["message_id"] == "21"
    assert receipt["emoji"] == STAGE_EMOJI[stage]
    assert [call[1].get("method") for call in api.calls] == [None, None, "POST", None]


def test_transition_preserves_other_users_custom_and_unrelated_own_reactions(invocation):
    keep = [reaction("1f440", user_id=99), reaction("2705", reaction_type="realm_emoji"), reaction("1f44d", name="thumbs_up")]
    api = Platform([reaction("1f440"), *deepcopy(keep)])
    receipt = sender(api)(invocation, "running")
    assert receipt["removed_emoji_codes"] == ["1f440"]
    assert all(item in api.message["reactions"] for item in keep)
    assert reaction("23f3") in api.message["reactions"]
    assert [c[1]["method"] for c in api.calls if "method" in c[1]] == ["POST", "DELETE"]


def test_repeated_status_is_observed_without_another_write(invocation):
    api = Platform([reaction("2705")])
    receipt = sender(api)(invocation, "succeeded")
    assert receipt["verified"] and not receipt["changed"]
    assert len(api.calls) == 2 and all("method" not in c[1] for c in api.calls)


def test_reconcile_partially_completed_transition_without_duplicate_add(invocation):
    api = Platform([reaction("1f440"), reaction("23f3")])
    receipt = sender(api)(invocation, "running")
    assert receipt["verified"]
    assert [c[1]["method"] for c in api.calls if "method" in c[1]] == ["DELETE"]


def test_identity_mismatch_never_mutates(invocation):
    api = Platform()
    api.user_id = 1
    with pytest.raises(ValueError, match="identity"):
        sender(api)(invocation, "queued")
    assert len(api.calls) == 1


@pytest.mark.parametrize("field,value", [("id", 99), ("stream_id", 99), ("sender_id", 99), ("type", "private")])
def test_live_message_mismatch_never_mutates(invocation, field, value):
    api = Platform()
    api.message[field] = value
    with pytest.raises(ValueError, match="live status"):
        sender(api)(invocation, "queued")
    assert len(api.calls) == 2


def test_snapshot_scope_and_site_guard_before_network(invocation):
    api = Platform()
    invocation["binding"]["allowed_stream_ids"] = [8]
    with pytest.raises(ValueError, match="outside"):
        sender(api)(invocation, "queued")
    assert not api.calls
    invocation["binding"]["allowed_stream_ids"] = [7]
    invocation["event"]["instance"] = "https://other.test"
    with pytest.raises(ValueError, match="instance"):
        sender(api)(invocation, "queued")
    assert not api.calls


def test_credential_transport_alias_must_be_explicit(invocation):
    api = Platform()
    invocation["binding"]["transport_site"] = "https://internal.test"
    with pytest.raises(ValueError, match="destination"):
        sender(api)(invocation, "queued")
    assert not api.calls


def test_failure_does_not_remove_previous_acknowledgement(invocation):
    api = Platform([reaction("1f440")])
    api.fail_write = True
    with pytest.raises(TransportError):
        sender(api)(invocation, "running")
    assert api.message["reactions"] == [reaction("1f440")]
    assert not any(c[1].get("method") == "DELETE" for c in api.calls)


def test_http_success_without_observed_reaction_is_not_delivery(invocation):
    api = Platform()
    api.ignore_writes = True
    with pytest.raises(TransportError, match="readback"):
        sender(api)(invocation, "succeeded")


def test_total_deadline_bounds_all_requests(invocation, monkeypatch):
    import chatevent.community_zulip_status as module

    api = Platform()
    ticks = iter([0, 0, 0, 11])
    monkeypatch.setattr(module.time, "monotonic", lambda: next(ticks))
    with pytest.raises(TransportError, match="deadline"):
        sender(api)(invocation, "queued")
    assert not any(c[1].get("method") for c in api.calls)


def test_unknown_stage_and_non_zulip_fail_without_network(invocation):
    api = Platform()
    with pytest.raises(ValueError, match="stage"):
        sender(api)(invocation, "accepted")
    invocation["event"]["source"] = "discourse"
    with pytest.raises(ValueError, match="Zulip"):
        sender(api)(invocation, "queued")
    assert not api.calls


def test_requested_cross_mark_is_not_zulip_x():
    assert STAGE_EMOJI["failed"]["emoji_code"] == "274c"
    assert STAGE_EMOJI["failed"]["emoji_name"] == "cross_mark"
