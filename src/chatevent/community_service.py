"""Opt-in service lifecycle for community capture and persistent dispatch."""
from __future__ import annotations

from collections import Counter
from functools import partial
import ipaddress
import json
import os
from pathlib import Path
import signal
import threading

from .community_capture import BoundedHTTPServer, CommunityCapture, private_path, reply_sender
from .community_dispatch import DispatchStore, DispatchWorker
from .community_hermes import HermesAdapter
from .community_remote import RemoteJobs
from .community_status import StatusDelivery, status_sender


def load(config_path: str | Path) -> tuple[dict, dict]:
    config = json.loads(private_path(config_path).read_text())
    registry = json.loads(private_path(config["registry_file"]).read_text())
    if registry.get("version") != 1 or not isinstance(registry.get("agents"), list):
        raise ValueError("trusted version-1 registry required")
    return config, registry


def status(config_path: str | Path) -> dict:
    config, registry = load(config_path)
    store = DispatchStore(config["dispatch_db"])
    # Counters only. Use the private ledger locally for detailed reconciliation.
    with store.connect() as db:
        rows = db.execute("SELECT execution_state,reply_state,COUNT(*) AS n FROM community_invocations GROUP BY execution_state,reply_state").fetchall()
        status_rows = db.execute("SELECT stage,delivery_state,COUNT(*) AS n FROM community_status GROUP BY stage,delivery_state").fetchall()
    return {"agents": [a["agent_id"] for a in registry["agents"] if a.get("enabled")],
            "states": [{"execution": r[0], "reply": r[1], "count": r[2]} for r in rows],
            "status_delivery": [{"stage": r[0], "delivery": r[1], "count": r[2]} for r in status_rows]}


def run(config_path: str | Path) -> None:
    os.umask(0o077)
    config, registry = load(config_path)
    address = ipaddress.ip_address(config.get("host", "127.0.0.1"))
    if address.is_unspecified or not (address.is_private or address.is_loopback):
        raise ValueError("companion must bind an explicit private address")
    store = DispatchStore(config["dispatch_db"])
    capture = CommunityCapture(config, registry, store)
    jobs = RemoteJobs(config["remote_jobs_db"], on_started=store.mark_started)
    with store.worker_lock() as owned:
        if not owned:
            raise ValueError("community worker already running")
        store._recover_interrupted()
        jobs.recover(store)
    capture.remote_jobs = jobs
    worker = DispatchWorker(store, adapters={"hermes": HermesAdapter(config["runs_dir"], on_started=store.mark_started), "hermes_remote": jobs.execute},
                            reply_sender=partial(reply_sender, registry=registry))
    notifier = StatusDelivery(store, status_sender)

    def notify() -> None:
        while not capture.stop.is_set():
            try:
                item = notifier.run_once()
                if item["status"] == "sent":
                    continue
            except Exception:
                pass  # Status delivery never changes/replays the execution.
            capture.stop.wait(.25)

    def work() -> None:
        while not capture.stop.is_set():
            try:
                item = worker.run_once()
                capture.errors.pop("worker", None)
                if item.get("status") not in {"idle", "busy"}:
                    continue
            except Exception as exc:
                capture.errors["worker"] = type(exc).__name__
            capture.stop.wait(1)

    server = BoundedHTTPServer((str(address), int(config["port"])), capture.handler())
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda signum, frame: capture.stop.set())
    capture.start()
    threading.Thread(target=notify, daemon=True, name="community-status").start()
    worker_thread = threading.Thread(target=work, daemon=True, name="community-executor")
    worker_thread.start()
    server_thread = threading.Thread(target=server.serve_forever, daemon=True, name="signed-webhooks")
    server_thread.start()
    try:
        capture.stop.wait()
    finally:
        server.shutdown()
        server.server_close()
        # The enclosing service's control group owns any bounded runtime child.
        worker_thread.join(timeout=5)
