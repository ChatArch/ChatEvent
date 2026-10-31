import threading
import time

import pytest

from chatevent.community_remote import RemoteJobs


def test_remote_job_once_claim_identity_and_result_replay(tmp_path):
    tmp_path.chmod(0o700)
    jobs = RemoteJobs(tmp_path / "remote.db")
    invocation = {"id": "one", "agent_id": "local", "runtime": {"executor_id": "local", "timeout_seconds": 5}}
    outputs = []
    thread = threading.Thread(target=lambda: outputs.append(jobs.execute(invocation)))
    thread.start()
    try:
        for _ in range(100):
            claimed = jobs.claim("local", 0)
            if claimed:
                break
            time.sleep(0.001)
        assert claimed["invocation"] == invocation
        assert jobs.claim("local", 0) is None
        assert jobs.claim("someone-else", 0) is None
        result = {"status": "succeeded", "text": "actual worker result"}
        with pytest.raises(ValueError):
            jobs.complete("someone-else", "one", result)
        assert jobs.complete("local", "one", result)
        assert not jobs.complete("local", "one", result)
        with pytest.raises(ValueError):
            jobs.complete("local", "one", {"text": "changed"})
    finally:
        thread.join(timeout=6)
    assert outputs == [result]


def test_remote_executor_cannot_impersonate_another_agent(tmp_path):
    tmp_path.chmod(0o700)
    jobs = RemoteJobs(tmp_path / "remote.db")
    with pytest.raises(ValueError):
        jobs.execute({"id": "one", "agent_id": "peer-agent", "runtime": {"executor_id": "local"}})


def test_claim_does_not_report_runtime_start_and_started_ack_is_idempotent(tmp_path):
    tmp_path.chmod(0o700)
    starts = []
    jobs = RemoteJobs(tmp_path / "remote.db", on_started=lambda item: starts.append(item["id"]))
    invocation = {"id": "one", "agent_id": "local", "runtime": {"executor_id": "local", "timeout_seconds": 3600}}
    outputs = []
    thread = threading.Thread(target=lambda: outputs.append(jobs.execute(invocation)))
    thread.start()
    try:
        claimed = jobs.claim("local", 1)
        assert claimed and starts == []
        with pytest.raises(ValueError):
            jobs.started("other", "one", time.time())
        now = time.time()
        assert jobs.started("local", "one", now)
        assert not jobs.started("local", "one", now)
        with jobs.connect() as db:
            assert db.execute("SELECT started_at FROM remote_jobs").fetchone()[0] == now
        jobs.complete("local", "one", {"status": "succeeded", "text": "work completed"})
    finally:
        thread.join(timeout=3)
    assert outputs[0]["status"] == "succeeded"


@pytest.mark.parametrize("completion", ["on_time", "late", "absent"])
def test_deadline_wakeup_reconciles_durable_result(tmp_path, monkeypatch, completion):
    """A delayed controller wake must not discard an already committed result."""
    from types import SimpleNamespace
    from chatevent import community_remote as module

    tmp_path.chmod(0o700)
    clock = SimpleNamespace(now=1000.0)
    monkeypatch.setattr(module, "time", SimpleNamespace(
        time=lambda: clock.now, monotonic=time.monotonic))
    jobs = RemoteJobs(tmp_path / "remote.db")
    invocation = {"id": "deadline-job", "agent_id": "own-agent",
                  "runtime": {"executor_id": "own-agent", "timeout_seconds": 5}}
    result = {"status": "succeeded", "text": "Durably completed",
              "runtime_status": "completed", "evidence": {"completed": True}}

    class DelayedWake:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def notify_all(self):
            pass

        def wait(self, timeout):
            claimed = jobs.claim("own-agent", 0)
            assert claimed is not None and claimed["id"] == invocation["id"]
            clock.now = 1004.0 if completion == "on_time" else 1006.0
            if completion != "absent":
                assert jobs.complete("own-agent", invocation["id"], result)
            clock.now = 1006.0  # Controller resumes after the original deadline.

    monkeypatch.setattr(jobs, "changed", DelayedWake())
    observed = jobs.execute(invocation)
    with jobs.connect() as db:
        row = db.execute("SELECT state,result FROM remote_jobs WHERE id=?",
                         (invocation["id"],)).fetchone()
    if completion == "on_time":
        assert row["state"] == "completed"
        assert observed == result
    else:
        assert observed["status"] == "unknown"
        assert observed["runtime_status"] == "remote_deadline"
        assert row["state"] == ("late_result" if completion == "late" else "unknown")
        if completion == "late":
            assert not jobs.complete("own-agent", invocation["id"], result)
            with pytest.raises(ValueError, match="replay conflict"):
                jobs.complete("own-agent", invocation["id"], {**result, "text": "changed"})
