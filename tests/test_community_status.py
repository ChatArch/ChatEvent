import pytest

from chatevent.community_dispatch import DispatchStore, DispatchWorker
from chatevent.community_status import StatusDelivery


def fixture(tmp_path, source="zulip"):
    store = DispatchStore(tmp_path / "private" / "dispatch.db")
    event = {"id": "message:1", "source": source, "instance": "https://example.test", "kind": "message.created",
             "actor_id": "user:1", "conversation_id": "stream:7/topic:Task", "subject_id": "message:1", "payload": {"content": "work"},
             "metadata": {"community_scope": "stream:7"}, "raw_payload": {"message": {"id": 1, "stream_id": 7, "subject": "Task", "sender_id": 1}}}
    binding = {"account_id": "user:2", "instance": "https://example.test", "allowed_stream_ids": [7]}
    if source == "discourse":
        event.update(id="post:1", kind="post.created", conversation_id="topic:3", subject_id="post:1", metadata={"community_scope": "category:4"}, raw_payload={"post": {"id": 1, "topic_id": 3, "category_id": 4, "post_number": 1, "user_id": 1}})
        binding["allowed_category_ids"] = [4]
    registry = {"version": 1, "human_actor_ids": {source: ["user:1"]}, "agents": [{"agent_id": "agent", "enabled": True, "bindings": {source: binding}, "runtime": {"kind": "fake"}}]}
    ident = store.enqueue(event, ["user:2"], registry)["dispatch_ids"][0]
    return store, ident


def receipt(invocation, stage, previous):
    return {"id": "same-status", "identity_id": "user:2", "stage": stage, "verified": True}


def result():
    return {"status": "succeeded", "text": "completed", "runtime_status": "completed", "evidence": {"real": True}}


def test_received_then_real_start_then_terminal_and_receipt_reused(tmp_path):
    store, ident = fixture(tmp_path)
    calls = []
    def send(invocation, stage, previous):
        calls.append((stage, previous))
        return receipt(invocation, stage, previous)
    delivery = StatusDelivery(store, send)
    assert delivery.run_once()["stage"] == "queued"
    invocation = store._claim()
    assert delivery.run_once() == {"status": "idle"}  # Claim is not runtime start.
    assert store.mark_started(invocation)
    assert not store.mark_started(invocation)
    assert delivery.run_once()["stage"] == "running"
    store._finish(ident, result())
    assert not store.mark_started(invocation)
    assert delivery.run_once()["stage"] == "succeeded"
    assert [c[0] for c in calls] == ["queued", "running", "succeeded"]
    assert calls[1][1]["id"] == calls[2][1]["id"] == "same-status"
    assert delivery.run_once() == {"status": "idle"}


def test_status_failure_never_blocks_or_reexecutes_model(tmp_path):
    store, ident = fixture(tmp_path)
    def fail(*args):
        raise TimeoutError("private diagnostic must not be persisted")
    assert StatusDelivery(store, fail).run_once()["status"] == "delivery_failed"
    model = []
    worker = DispatchWorker(store, adapters={"fake": lambda job: model.append(job["id"]) or result()},
                            reply_sender=lambda *_: {"id": "reply", "identity_id": "user:2"})
    assert worker.run_once()["execution_state"] == "succeeded"
    assert worker.run_once() == {"status": "idle"}
    assert model == [ident]


def test_discourse_unknown_create_is_never_repeated_even_after_new_stage(tmp_path):
    store, ident = fixture(tmp_path, "discourse")
    calls = []
    def ambiguous(*args):
        calls.append(1)
        raise TimeoutError("possibly created")
    delivery = StatusDelivery(store, ambiguous)
    assert delivery.run_once()["status"] == "delivery_failed"
    assert delivery.run_once() == {"status": "idle"}
    invocation = store._claim()
    store.mark_started(invocation)
    assert delivery.run_once()["status"] == "delivery_unknown"
    assert calls == [1]


def test_stage_changes_while_sending_keep_receipt_and_deliver_latest(tmp_path):
    store, ident = fixture(tmp_path, "discourse")
    def while_sending(invocation, stage, previous):
        store._claim()
        store.mark_started(store.get(ident))
        return receipt(invocation, stage, previous)
    assert StatusDelivery(store, while_sending).run_once()["stage"] == "queued"
    seen = []
    def update(invocation, stage, previous):
        seen.append(previous)
        return receipt(invocation, stage, previous)
    assert StatusDelivery(store, update).run_once()["stage"] == "running"
    assert seen[0]["id"] == "same-status"
