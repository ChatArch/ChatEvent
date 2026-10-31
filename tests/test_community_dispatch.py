"""Persistent side-effect and authorization boundaries, without any model/API."""

from copy import deepcopy
import json
import os
from pathlib import Path
import sys

import pytest

from chatevent.community_dispatch import DispatchStore, DispatchWorker
from chatevent.community_hermes import HermesAdapter


@pytest.fixture
def registry():
    return {"version": 1, "human_actor_ids": {"zulip": ["user:1"], "discourse": ["user:1"]},
            "ignored_actor_ids": {"zulip": ["user:18", "user:19"], "discourse": ["user:5"]},
            "agents": [{"agent_id": "hermes-recall", "enabled": True,
                        "bindings": {"zulip": {"account_id": "user:18", "instance": "https://zulip.test", "allowed_stream_ids": [7]},
                                     "discourse": {"account_id": "user:5", "instance": "https://discourse.test", "allowed_category_ids": [3]}},
                        "runtime": {"kind": "fake", "cwd": "/authorized/project"}}]}


@pytest.fixture
def event():
    return {"id": "message:21", "source": "zulip", "instance": "https://zulip.test", "kind": "message.created",
            "subject_id": "message:21", "actor_id": "user:1", "conversation_id": "stream:7/topic:Sandbox",
            "payload": {"content": "@Agent please summarize this"}, "metadata": {"community_scope": "stream:7"},
            "raw_payload": {"message": {"id": 21, "stream_id": 7, "subject": "Sandbox", "sender_id": 1}}}


@pytest.fixture
def store(tmp_path):
    return DispatchStore(tmp_path / "private" / "dispatch.db")


def complete(invocation):
    return {"status": "succeeded", "text": "Actual answer", "runtime_status": "completed", "evidence": {"completed": True}}


def sent(invocation, result):
    return {"id": "reply:35", "identity_id": invocation["binding"]["account_id"]}


def test_duplicate_collectors_execute_and_reply_once(store, event, registry):
    first = store.enqueue(event, ["user:18"], registry)
    replay = deepcopy(event)
    replay.update(id="queue:another-delivery", captured_at="later")
    second = store.enqueue(replay, ["user:18"], registry)
    assert first["dispatch_ids"] == second["dispatch_ids"] and second["duplicate"]
    calls = []
    def adapter(item):
        calls.append(item["id"])
        return complete(item)
    worker = DispatchWorker(store, adapters={"fake": adapter}, reply_sender=sent)
    result = worker.run_once()
    assert result["execution_state"] == "succeeded" and result["reply_state"] == "sent"
    assert worker.run_once() == {"status": "idle"} and len(calls) == 1
    assert result["receipt"]["identity_id"] == "user:18"


@pytest.mark.parametrize("change,reason", [
    ({"actor_id": "user:18"}, "agent_or_bot_author"),
    ({"actor_id": "user:19"}, "agent_or_bot_author"),
    ({"actor_id": "user:2"}, "human_not_authorized"),
    ({"actor_id": "user:display-name"}, "non_native_actor_id"),
    ({"kind": "message.updated"}, "unsupported_event"),
    ({"actor_role": "bot"}, "agent_or_bot_author"),
    ({"metadata": {"community_scope": "stream:8"}}, "unverified_scope"),
    ({"conversation_id": "stream:7/topic:Other"}, "unverified_scope"),
    ({"subject_id": "message:another"}, "unverified_scope"),
    ({"instance": "https://evil.test"}, "no_authorized_mention"),
])
def test_rule_rejections_never_enqueue(store, event, registry, change, reason):
    event.update(change)
    result = store.enqueue(event, ["user:18"], registry)
    assert result["ignored_reason"] == reason and not store.list()


def test_native_author_and_bot_crosscheck(store, event, registry):
    event["raw_payload"]["message"]["sender_id"] = 2
    assert store.enqueue(event, ["user:18"], registry)["ignored_reason"] == "unverified_scope"
    event["raw_payload"]["message"].update(sender_id=1, sender_is_bot=True)
    assert store.enqueue(event, ["user:18"], registry)["ignored_reason"] == "unverified_scope"


def test_mention_id_only_and_scope_authorized(store, event, registry):
    assert not store.enqueue(event, [], registry)["dispatch_ids"]
    with pytest.raises(ValueError):
        store.enqueue(event, ["@Agent"], registry)
    registry["agents"][0]["bindings"]["zulip"]["allowed_stream_ids"] = [8]
    assert store.enqueue(event, ["user:18"], registry)["ignored_reason"] == "no_authorized_mention"


def test_discourse_reply_numeric_author_and_category(store, registry):
    event = {"id": "post:51", "source": "discourse", "instance": "https://discourse.test", "kind": "reply.created",
             "subject_id": "post:51", "actor_id": "user:1", "conversation_id": "topic:9", "payload": {"content": "hello"},
             "metadata": {"community_scope": "category:3"}, "raw_payload": {"post": {"id": 51, "user_id": 1, "category_id": 3, "topic_id": 9}}}
    assert store.enqueue(event, ["user:5"], registry)["dispatch_ids"]


def test_conflicting_replay_cannot_replace_input(store, event, registry):
    first = store.enqueue(event, ["user:18"], registry)
    event["payload"]["content"] = "different side effect"
    with pytest.raises(ValueError, match="conflicting"):
        store.enqueue(event, ["user:18"], registry)
    assert store.get(first["dispatch_ids"][0])["event"]["payload"]["content"] != event["payload"]["content"]


def test_inflight_binding_is_immutable(store, event, registry):
    dispatch_id = store.enqueue(event, ["user:18"], registry)["dispatch_ids"][0]
    registry["agents"][0]["runtime"]["cwd"] = "/elsewhere"
    assert store.get(dispatch_id)["runtime"]["cwd"] == "/authorized/project"


def test_interrupted_execution_is_unknown_and_never_replayed(store, event, registry):
    dispatch_id = store.enqueue(event, ["user:18"], registry)["dispatch_ids"][0]
    with store.worker_lock() as owned:
        assert owned and store._claim()["id"] == dispatch_id
    worker = DispatchWorker(store, adapters={"fake": lambda _: pytest.fail("replayed")}, reply_sender=sent)
    assert worker.run_once() == {"status": "idle"}
    assert store.get(dispatch_id)["execution_state"] == "unknown"


def test_singleton_worker_cannot_claim_while_owner_active(store, event, registry):
    dispatch_id = store.enqueue(event, ["user:18"], registry)["dispatch_ids"][0]
    other = DispatchWorker(DispatchStore(store.path), adapters={"fake": complete}, reply_sender=sent)
    with store.worker_lock():
        assert other.run_once() == {"status": "busy"}
        assert store.get(dispatch_id)["execution_state"] == "queued"


def test_accepted_or_partial_text_is_not_success(store, event, registry):
    store.enqueue(event, ["user:18"], registry)
    worker = DispatchWorker(store, adapters={"fake": lambda _: {"status": "succeeded", "text": "HTTP 202", "runtime_status": "accepted"}}, reply_sender=sent)
    result = worker.run_once()
    assert result["execution_state"] == "unknown" and result["reply_state"] == "not_ready"


def test_ambiguous_reply_never_resends_or_reexecutes(store, event, registry):
    store.enqueue(event, ["user:18"], registry)
    calls = []
    def ambiguous(item, result):
        calls.append(item["id"])
        raise TimeoutError("possibly delivered")
    worker = DispatchWorker(store, adapters={"fake": complete}, reply_sender=ambiguous)
    result = worker.run_once()
    assert result["execution_state"] == "succeeded" and result["reply_state"] == "unknown"
    assert worker.run_once() == {"status": "idle"} and len(calls) == 1


def test_sender_cannot_claim_another_identity(store, event, registry):
    store.enqueue(event, ["user:18"], registry)
    worker = DispatchWorker(store, adapters={"fake": complete}, reply_sender=lambda *_: {"id": "42", "identity_id": "user:1"})
    assert worker.run_once()["reply_state"] == "unknown"


def test_computed_result_survives_restart_before_reply(store, event, registry):
    dispatch_id = store.enqueue(event, ["user:18"], registry)["dispatch_ids"][0]
    with store.worker_lock():
        store._claim()
        store._finish(dispatch_id, complete({}))
    worker = DispatchWorker(DispatchStore(store.path), adapters={"fake": lambda _: pytest.fail("recomputed")}, reply_sender=sent)
    assert worker.run_once()["reply_state"] == "sent"


def test_interrupted_send_is_quarantined(store, event, registry):
    dispatch_id = store.enqueue(event, ["user:18"], registry)["dispatch_ids"][0]
    with store.worker_lock():
        store._claim()
        store._finish(dispatch_id, complete({}))
        store._claim(reply=True)
    worker = DispatchWorker(store, adapters={"fake": complete}, reply_sender=lambda *_: pytest.fail("resent"))
    assert worker.run_once() == {"status": "idle"}
    assert store.get(dispatch_id)["reply_state"] == "unknown"


def test_private_database_and_symlink_refusal(store, tmp_path):
    assert store.path.stat().st_mode & 0o777 == 0o600
    path = tmp_path / "bad.db"
    path.symlink_to(store.path)
    with pytest.raises(ValueError):
        DispatchStore(path)


def test_adapter_transport_is_shell_free_and_records_actual_child(tmp_path, monkeypatch, event):
    # Replace only the child program with a tiny deterministic fixture. No Hermes,
    # provider, network or model is involved in this transport/lifecycle test.
    import chatevent.community_hermes as module

    child = tmp_path / "fixture.py"
    child.write_text("import sys,json\np=json.load(sys.stdin)\nassert '$(touch' in p['prompt']\njson.dump({'status':'succeeded','text':'fixture answer','runtime_status':'completed','evidence':{'fixture':True}},open(p['output'],'w'))\n")
    monkeypatch.setattr(module, "__file__", str(child))
    source, home, cwd = [tmp_path / name for name in ("source", "home", "project")]
    for path in (source, home, cwd):
        path.mkdir()
    event["payload"]["content"] = "$(touch NEVER_EXECUTE) `echo unsafe`"
    invocation = {"event": event, "agent_id": "agent", "runtime": {"kind": "hermes", "python": sys.executable, "source": str(source), "home": str(home), "cwd": str(cwd), "timeout_seconds": 5}}
    result = HermesAdapter(tmp_path / "state")(invocation)
    assert result["status"] == "succeeded" and result["evidence"]["exit_code"] == 0
    assert not (cwd / "NEVER_EXECUTE").exists()
