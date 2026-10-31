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
