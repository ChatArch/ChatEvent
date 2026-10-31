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
        jobs.execute({"id": "one", "agent_id": "recall", "runtime": {"executor_id": "local"}})


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
