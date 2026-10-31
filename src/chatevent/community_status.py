"""Model-free, durable community status delivery, independent of execution."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from .community_dispatch import private_file


class StatusDelivery:
    def __init__(self, store, sender):
        self.store, self.sender = store, sender

    def run_once(self) -> dict:
        import fcntl
        path = self.store.path.with_suffix(".status.lock")
        private_file(path)
        with open(path, "rb") as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return {"status": "busy"}
            with self.store.connect() as db:
                row = db.execute("SELECT * FROM community_status WHERE revision>delivered_revision AND next_attempt<=? AND delivery_state IN ('pending','sending','failed') ORDER BY updated_at LIMIT 1", (time.time(),)).fetchone()
                if not row:
                    return {"status": "idle"}
                row = dict(row)
                db.execute("UPDATE community_status SET delivery_state='sending' WHERE invocation_id=? AND revision=?", (row["invocation_id"], row["revision"]))
            invocation = self.store.get(row["invocation_id"])
            previous = json.loads(row["receipt_json"]) if row["receipt_json"] else None
            creating_post = invocation["event"]["source"] == "discourse" and previous is None
            if creating_post:
                with self.store.connect() as db:
                    if row["creation_attempted"]:
                        db.execute("UPDATE community_status SET delivery_state='unknown',error_type='status_create_requires_reconciliation' WHERE invocation_id=?", (row["invocation_id"],))
                        return {"status": "delivery_unknown", "invocation_id": row["invocation_id"]}
                    db.execute("UPDATE community_status SET creation_attempted=1 WHERE invocation_id=?", (row["invocation_id"],))
            try:
                receipt = self.sender(invocation, row["stage"], previous)
                if not isinstance(receipt, dict) or receipt.get("identity_id") != invocation["binding"]["account_id"] or receipt.get("verified") is not True:
                    raise ValueError("native status identity/readback required")
            except Exception as exc:
                partial = getattr(exc, "receipt", None)
                usable = (isinstance(partial, dict) and partial.get("id") and
                          partial.get("identity_id") == invocation["binding"]["account_id"] and
                          partial.get("invocation_id") == invocation["id"])
                with self.store.connect() as db:
                    if usable:
                        db.execute("UPDATE community_status SET receipt_json=? WHERE invocation_id=?", (json.dumps(partial), row["invocation_id"]))
                    state = "unknown" if creating_post and not usable else "failed"
                    db.execute("UPDATE community_status SET delivery_state=?,error_type=?,attempts=attempts+1,next_attempt=? WHERE invocation_id=? AND revision=?", (state, type(exc).__name__, time.time()+min(2**min(row["attempts"]+1, 6), 60), row["invocation_id"], row["revision"]))
                return {"status": "delivery_failed", "invocation_id": row["invocation_id"], "stage": row["stage"]}
            with self.store.connect() as db:
                # Save the native receipt even if a newer stage arrived in-flight.
                # A Discourse post can then be edited rather than created again.
                db.execute("UPDATE community_status SET receipt_json=?,delivered_revision=?,delivery_state=CASE WHEN revision=? THEN 'sent' ELSE 'pending' END,error_type=NULL,next_attempt=0 WHERE invocation_id=?", (json.dumps(receipt), row["revision"], row["revision"], row["invocation_id"]))
                db.execute("INSERT OR IGNORE INTO community_status_deliveries VALUES (?,?,?,?,?)", (row["invocation_id"], row["revision"], row["stage"], time.time(), json.dumps(receipt)))
            return {"status": "sent", "invocation_id": row["invocation_id"], "stage": row["stage"]}


def status_sender(invocation: dict, stage: str, previous_receipt: dict | None = None) -> dict:
    source = invocation["event"]["source"]
    if source == "zulip":
        from .community_zulip_status import zulip_status_sender
        return zulip_status_sender(invocation, stage)
    if source == "discourse":
        from .community_discourse_status import status_sender as discourse_status_sender
        return discourse_status_sender(invocation, stage, previous_receipt)
    raise ValueError("unsupported community status platform")
