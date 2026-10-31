"""Outbound workers for agents whose model credentials remain on another host.

The central adapter stays in its claimed execution until a worker result exists.
A job is claimed once; a lost worker is ambiguous, never automatically replayed.
Use the existing SSH transport for encrypted access to the private companion.
"""
from __future__ import annotations

from contextlib import contextmanager
import hmac
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import threading
import time

from .community_capture import TransportError, http_json, private_path
from .community_dispatch import private_file, private_directory


class RemoteJobs:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().absolute()
        private_directory(self.path.parent)
        private_file(self.path)
        self.changed = threading.Condition()
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS remote_jobs (id TEXT PRIMARY KEY, executor_id TEXT NOT NULL, invocation TEXT NOT NULL, state TEXT NOT NULL, result TEXT, deadline REAL NOT NULL)")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def execute(self, invocation: dict) -> dict:
        executor = invocation["runtime"]["executor_id"]
        if executor != invocation["agent_id"]:
            raise ValueError("executor identity mismatch")
        timeout = int(invocation["runtime"].get("timeout_seconds", 240))
        if not 5 <= timeout <= 300:
            raise ValueError("remote deadline outside bounds")
        deadline = time.time() + timeout
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO remote_jobs VALUES (?,?,?,'queued',NULL,?)",
                       (invocation["id"], executor, json.dumps(invocation), deadline))
        with self.changed:
            self.changed.notify_all()
        while time.time() < deadline:
            with self.connect() as db:
                row = db.execute("SELECT state,result FROM remote_jobs WHERE id=?", (invocation["id"],)).fetchone()
            if row["state"] == "completed":
                return json.loads(row["result"])
            with self.changed:
                self.changed.wait(min(1, max(0, deadline - time.time())))
        with self.connect() as db:
            db.execute("UPDATE remote_jobs SET state='unknown' WHERE id=? AND state!='completed'", (invocation["id"],))
        return {"status": "unknown", "text": "", "runtime_status": "remote_deadline", "evidence": {"executor_id": executor, "automatic_retry": False}}

    def claim(self, executor: str, wait_seconds: float = 35) -> dict | None:
        until = time.monotonic() + min(max(wait_seconds, 0), 40)
        while True:
            with self.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute("SELECT * FROM remote_jobs WHERE executor_id=? AND state='queued' AND deadline>? ORDER BY deadline LIMIT 1", (executor, time.time())).fetchone()
                if row:
                    db.execute("UPDATE remote_jobs SET state='running' WHERE id=? AND state='queued'", (row["id"],))
                    return {"id": row["id"], "deadline": row["deadline"], "invocation": json.loads(row["invocation"])}
            remaining = until - time.monotonic()
            if remaining <= 0:
                return None
            with self.changed:
                self.changed.wait(min(remaining, 1))

    def complete(self, executor: str, job_id: str, result: dict) -> bool:
        if not isinstance(result, dict) or len(json.dumps(result).encode()) > 262144:
            raise ValueError("bounded structured result required")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM remote_jobs WHERE id=? AND executor_id=?", (job_id, executor)).fetchone()
            if not row:
                raise ValueError("job identity mismatch")
            if row["state"] in {"completed", "late_result"}:
                if json.loads(row["result"]) != result:
                    raise ValueError("result replay conflict")
                return False
            if row["state"] not in {"running", "unknown"}:
                raise ValueError("job not claimed")
            # Late results are retained for reconciliation but do not rewrite a
            # central execution that has already timed out.
            state = "completed" if row["deadline"] >= time.time() else "late_result"
            db.execute("UPDATE remote_jobs SET state=?,result=? WHERE id=?", (state, json.dumps(result), job_id))
        with self.changed:
            self.changed.notify_all()
        return True

    def recover(self, dispatch: object) -> None:
        """Quarantine uncompleted jobs whose owning central run is interrupted."""
        with self.connect() as db:
            for row in db.execute("SELECT id FROM remote_jobs WHERE state IN ('queued','running')").fetchall():
                invocation = dispatch.get(row["id"])
                if not invocation or invocation["execution_state"] != "running":
                    db.execute("UPDATE remote_jobs SET state='unknown' WHERE id=?", (row["id"],))


def authorize_worker(config: dict, executor: str, authorization: str) -> bool:
    worker = next((w for w in config.get("workers", []) if w["agent_id"] == executor), None)
    if not worker or not authorization.startswith("Bearer "):
        return False
    token = private_path(worker["token_file"]).read_text().strip()
    return bool(token) and hmac.compare_digest("Bearer " + token, authorization)


def run_worker(config_path: str | Path) -> None:
    from .community_hermes import HermesAdapter
    from .community_capture import CaptureInbox

    os.umask(0o077)
    config = json.loads(private_path(config_path).read_text())
    agent_id = config["agent_id"]
    private_directory(Path(config["runs_dir"]))
    journal = CaptureInbox(config["worker_db"])
    adapter = HermesAdapter(config["runs_dir"])
    stop = threading.Event()
    import fcntl
    lock_path = Path(config["worker_db"]).expanduser().with_suffix(".worker.lock")
    private_file(lock_path)
    lock = open(lock_path, "rb")
    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    def stopping(signum, frame):
        stop.set()
        raise SystemExit(0)  # Adapter finally cleans only its own process group.
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, stopping)
    tunnel = None
    try:
        if config.get("ssh_alias"):
            # Fixed trusted configuration only, never data from a forum message.
            tunnel = subprocess.Popen(["/usr/bin/ssh", "-N", "-T", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
                "-o", "ExitOnForwardFailure=yes", "-o", "ServerAliveInterval=20", "-o", "ServerAliveCountMax=3",
                "-L", config["ssh_forward"], config["ssh_alias"]], stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        base = config["base_url"].rstrip("/") + "/workers/" + agent_id
        token = private_path(config["token_file"]).read_text().strip()
        headers = {"Authorization": "Bearer " + token}
        backoff = 2
        while not stop.is_set():
            if tunnel and tunnel.poll() is not None:
                raise TransportError("worker_ssh_tunnel_closed")
            try:
                pending = journal.get_checkpoint("pending_result")
                if pending:
                    http_json(base + "/result", body=pending, headers=headers)
                    journal.checkpoint("pending_result", None)
                claimed = http_json(base + "/next", headers=headers, timeout=50)
                job = claimed.get("job")
                if not job:
                    backoff = 2
                    continue
                invocation = job["invocation"]
                if invocation["agent_id"] != agent_id or invocation["runtime"].get("executor_id") != agent_id:
                    raise ValueError("remote invocation agent mismatch")
                # Server selects source/identity; only local trusted config selects
                # the interpreter, model home, project directory and tools.
                invocation["runtime"] = config["runtime"]
                state_key = "executed:" + job["id"]
                if journal.get_checkpoint(state_key):
                    raise ValueError("job already claimed locally; reconcile instead of rerunning")
                journal.checkpoint(state_key, {"state": "running"})
                remaining = int(job["deadline"] - time.time() - 3)
                if remaining < 5:
                    result = {"status": "unknown", "text": "", "runtime_status": "expired_before_start", "evidence": {"model_started": False}}
                else:
                    invocation["runtime"] = {**config["runtime"], "timeout_seconds": min(remaining, int(config["runtime"].get("timeout_seconds", 180)))}
                    result = adapter(invocation)
                result.setdefault("evidence", {})["executor_id"] = agent_id
                pending = {"id": job["id"], "result": result}
                journal.checkpoint("pending_result", pending)
                journal.checkpoint(state_key, {"state": "completed"})
                http_json(base + "/result", body=pending, headers=headers)
                journal.checkpoint("pending_result", None)
                backoff = 2
            except (TransportError, OSError):
                stop.wait(backoff)
                backoff = min(backoff * 2, 60)
    finally:
        if tunnel and tunnel.poll() is None:
            os.killpg(tunnel.pid, signal.SIGTERM)
            try:
                tunnel.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(tunnel.pid, signal.SIGKILL)
                tunnel.wait(timeout=5)
        lock.close()
