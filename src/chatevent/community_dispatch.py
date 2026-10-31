"""Opt-in persistent dispatch; ingestion alone never authorizes execution.

The trusted capture layer supplies platform-native mention IDs and scope metadata.
The worker serializes side effects and quarantines interrupted work instead of
blindly retrying a model turn or a possibly delivered community reply.
"""

from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import time
from typing import Any, Callable
from uuid import uuid4


_ACTOR = re.compile(r"user:[0-9]+\Z")
_KINDS = {"zulip": {"message.created"}, "discourse": {"post.created", "reply.created"}}
_RUNTIME_FIELDS = {"kind", "python", "source", "home", "cwd", "timeout_seconds", "max_iterations", "source_sha", "executor_id"}
_BINDING_FIELDS = {"account_id", "username", "profile", "instance", "transport_site", "allowed_stream_ids", "allowed_category_ids"}
_RESULT_STATES = {"succeeded", "failed", "waiting_for_user", "cancelled", "unknown"}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def private_directory(path: Path) -> Path:
    """Create a private owned state directory; never follow a final symlink."""
    path = path.expanduser().absolute()
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("state directory must be owned, private and not a symlink")
    return path


def private_file(path: Path) -> None:
    """Precreate a regular private file before opening it with a library."""
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    except FileExistsError:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("state file must be owned, private and not a symlink")
    else:
        os.close(fd)


def _native_scope(event: dict) -> str | None:
    source = event["source"]
    scope = event.get("metadata", {}).get("community_scope")
    raw = event.get("raw_payload") or {}
    if not isinstance(raw, dict):
        return None
    obj = raw.get("message" if source == "zulip" else "post", raw)
    if not isinstance(obj, dict):
        return None
    field = "stream_id" if source == "zulip" else "category_id"
    prefix = "stream" if source == "zulip" else "category"
    native_id = obj.get(field)
    if native_id is None:
        return None  # Metadata alone is not proof of a native scope.
    expected = f"{prefix}:{native_id}"
    actor = obj.get("sender_id" if source == "zulip" else "user_id")
    if actor is None or event.get("actor_id") != f"user:{actor}":
        return None
    native_subject = f"{'message' if source == 'zulip' else 'post'}:{obj.get('id')}"
    if event.get("subject_id") != native_subject:
        return None
    if source == "zulip":
        topic = obj.get("subject") or obj.get("topic")
        conversation = f"stream:{native_id}/topic:{topic}"
    else:
        conversation = f"topic:{obj.get('topic_id')}"
    if event.get("conversation_id") != conversation:
        return None
    if obj.get("sender_is_bot") is True:
        return None
    return scope if scope == expected and str(native_id).isdigit() else None


def _selection(event: dict, mentions: list[str], registry: dict) -> tuple[list[dict], str | None]:
    if registry.get("version") != 1:
        raise ValueError("unsupported registry version")
    source = event.get("source")
    if source not in _KINDS or event.get("kind") not in _KINDS[source]:
        return [], "unsupported_event"
    actor = event.get("actor_id")
    if not isinstance(actor, str) or not _ACTOR.fullmatch(actor):
        return [], "non_native_actor_id"
    agents = registry.get("agents", [])
    ignored = set(registry.get("ignored_actor_ids", {}).get(source, []))
    ignored.update(a.get("bindings", {}).get(source, {}).get("account_id") for a in agents)
    actor_info = event.get("actor") or {}
    if actor in ignored or event.get("actor_role") in {"bot", "system", "agent"} or actor_info.get("role") in {"bot", "system", "agent"}:
        return [], "agent_or_bot_author"
    if actor_info.get("metadata", {}).get("is_bot") is True or event.get("payload", {}).get("sender_is_bot") is True:
        return [], "agent_or_bot_author"
    if actor not in registry.get("human_actor_ids", {}).get(source, []):
        return [], "human_not_authorized"
    if not event.get("conversation_id") or not event.get("instance"):
        return [], "missing_source_context"
    scope = _native_scope(event)
    if scope is None:
        return [], "unverified_scope"
    selected = []
    for agent in agents:
        binding = agent.get("bindings", {}).get(source, {})
        if not agent.get("enabled") or binding.get("account_id") not in mentions:
            continue
        if not _ACTOR.fullmatch(str(binding.get("account_id", ""))):
            raise ValueError("binding requires a native numeric account ID")
        if str(binding.get("instance", "")).rstrip("/") != str(event["instance"]).rstrip("/"):
            continue
        allowed = binding.get("allowed_stream_ids" if source == "zulip" else "allowed_category_ids", [])
        if scope.split(":", 1)[1] not in {str(v) for v in allowed}:
            continue
        runtime = agent.get("runtime", {})
        if not agent.get("agent_id") or not runtime.get("kind"):
            raise ValueError("enabled agent needs stable identity and runtime")
        selected.append({
            "agent_id": agent["agent_id"],
            "binding": {k: v for k, v in binding.items() if k in _BINDING_FIELDS},
            "runtime": {k: v for k, v in runtime.items() if k in _RUNTIME_FIELDS},
            "community_scope": scope,
        })
    return selected, None if selected else "no_authorized_mention"


class DispatchStore:
    """SQLite execution ledger and reply outbox, independent of EventStore."""

    def __init__(self, db_path: str | Path):
        self.path = Path(db_path).expanduser().absolute()
        private_directory(self.path.parent)
        private_file(self.path)
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS community_invocations (
                id TEXT PRIMARY KEY, event_key TEXT NOT NULL, agent_id TEXT NOT NULL,
                input_digest TEXT NOT NULL, event_json TEXT NOT NULL, snapshot_json TEXT NOT NULL,
                execution_state TEXT NOT NULL, reply_state TEXT NOT NULL,
                result_json TEXT, receipt_json TEXT, error_code TEXT,
                created_at REAL NOT NULL, updated_at REAL NOT NULL,
                UNIQUE(event_key, agent_id))""")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @contextmanager
    def worker_lock(self):
        import fcntl

        path = self.path.with_suffix(self.path.suffix + ".worker.lock")
        private_file(path)
        fd = os.open(path, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0))
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                yield False
                return
            yield True
        finally:
            os.close(fd)

    def enqueue(self, event: Any, mentions: list[str], registry: dict) -> dict:
        """Persist eligible work only; never invoke an adapter here."""
        if hasattr(event, "to_dict"):
            event = event.to_dict()
        if not isinstance(event, dict) or not isinstance(mentions, list):
            raise ValueError("event object and native mention list required")
        if any(not isinstance(v, str) or not _ACTOR.fullmatch(v) for v in mentions):
            raise ValueError("mentions must be canonical native numeric IDs")
        encoded = _json(event)
        if len(encoded.encode()) > 262144:
            raise ValueError("event exceeds dispatch limit")
        selected, ignored = _selection(event, mentions, registry)
        receipt = {"dispatch_ids": [], "duplicate": False, "ignored_reason": ignored}
        if not selected:
            return receipt
        subject = event.get("subject_id") or event.get("id")
        if not isinstance(subject, str) or not subject:
            raise ValueError("stable source object ID required")
        key = sha256(_json([event["source"], event["instance"].rstrip("/"), subject]).encode()).hexdigest()
        # Capture IDs/timestamps/raw delivery wrappers may differ across collectors.
        semantic = {k: event.get(k) for k in ("source", "instance", "actor_id", "conversation_id", "subject_id", "payload")}
        semantic["scope"] = selected[0]["community_scope"]
        semantic["mentions"] = sorted(set(mentions))
        digest = sha256(_json(semantic).encode()).hexdigest()
        now = time.time()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for snapshot in selected:
                existing = db.execute("SELECT id,input_digest FROM community_invocations WHERE event_key=? AND agent_id=?", (key, snapshot["agent_id"])).fetchone()
                if existing:
                    if existing["input_digest"] != digest:
                        raise ValueError("conflicting source message replay")
                    receipt["dispatch_ids"].append(existing["id"])
                    receipt["duplicate"] = True
                    continue
                dispatch_id = uuid4().hex
                db.execute("INSERT INTO community_invocations VALUES (?,?,?,?,?,?,?,'not_ready',NULL,NULL,NULL,?,?)",
                           (dispatch_id, key, snapshot["agent_id"], digest, encoded, _json(snapshot), "queued", now, now))
                receipt["dispatch_ids"].append(dispatch_id)
        return receipt

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict:
        item = dict(row)
        for key in ("event", "snapshot", "result", "receipt"):
            value = item.pop(key + "_json")
            item[key] = json.loads(value) if value else None
        item.update(item["snapshot"])
        return item

    def get(self, dispatch_id: str) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM community_invocations WHERE id=?", (dispatch_id,)).fetchone()
        return self._decode(row) if row else None

    def list(self, limit: int = 100) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM community_invocations ORDER BY created_at DESC LIMIT ?", (min(max(limit, 1), 500),)).fetchall()
        return [self._decode(row) for row in rows]

    def _recover_interrupted(self) -> None:
        # Call only after taking the singleton worker lock.
        with self.connect() as db:
            db.execute("UPDATE community_invocations SET execution_state='unknown',error_code='worker_interrupted',updated_at=? WHERE execution_state='running'", (time.time(),))
            db.execute("UPDATE community_invocations SET reply_state='unknown',error_code='reply_interrupted',updated_at=? WHERE reply_state='sending'", (time.time(),))

    def _claim(self, *, reply: bool = False) -> dict | None:
        condition = "reply_state='pending'" if reply else "execution_state='queued'"
        field, state = ("reply_state", "sending") if reply else ("execution_state", "running")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(f"SELECT * FROM community_invocations WHERE {condition} ORDER BY created_at LIMIT 1").fetchone()
            if not row:
                return None
            db.execute(f"UPDATE community_invocations SET {field}=?,updated_at=? WHERE id=?", (state, time.time(), row["id"]))
        return self.get(row["id"])

    def _finish(self, dispatch_id: str, result: dict) -> None:
        state = result.get("status")
        if state not in _RESULT_STATES:
            raise ValueError("runtime returned unsupported state")
        if state == "succeeded" and (not str(result.get("text", "")).strip() or result.get("runtime_status") != "completed" or not result.get("evidence")):
            raise ValueError("runtime success requires final text and completion evidence")
        if len(_json(result).encode()) > 262144:
            raise ValueError("runtime result exceeds limit")
        reply = "pending" if state in {"succeeded", "failed", "waiting_for_user", "cancelled"} else "not_ready"
        with self.connect() as db:
            db.execute("UPDATE community_invocations SET execution_state=?,reply_state=?,result_json=?,updated_at=? WHERE id=? AND execution_state='running'", (state, reply, _json(result), time.time(), dispatch_id))

    def _reply_finished(self, dispatch_id: str, receipt: dict | None, error: str | None) -> None:
        with self.connect() as db:
            db.execute("UPDATE community_invocations SET reply_state=?,receipt_json=?,error_code=?,updated_at=? WHERE id=? AND reply_state='sending'", ("sent" if receipt else "unknown", _json(receipt) if receipt else None, error, time.time(), dispatch_id))


class DispatchWorker:
    """One bounded invocation per tick; caller owns scheduling and credentials."""

    def __init__(self, store: DispatchStore, *, adapters: dict[str, Callable], reply_sender: Callable):
        self.store, self.adapters, self.reply_sender = store, adapters, reply_sender

    def _send(self, invocation: dict) -> None:
        try:
            receipt = self.reply_sender(invocation, invocation["result"])
            if not isinstance(receipt, dict) or not receipt.get("id") or receipt.get("identity_id") != invocation["binding"]["account_id"]:
                raise ValueError("reply identity/acceptance receipt missing")
        except Exception as exc:
            self.store._reply_finished(invocation["id"], None, "reply_" + type(exc).__name__)
        else:
            self.store._reply_finished(invocation["id"], receipt, None)

    def run_once(self) -> dict:
        with self.store.worker_lock() as owned:
            if not owned:
                return {"status": "busy"}
            self.store._recover_interrupted()
            invocation = self.store._claim(reply=True)
            if invocation:
                self._send(invocation)
                return self.store.get(invocation["id"])
            invocation = self.store._claim()
            if not invocation:
                return {"status": "idle"}
            try:
                adapter = self.adapters[invocation["runtime"]["kind"]]
                result = adapter(invocation)
                self.store._finish(invocation["id"], result)
            except Exception as exc:
                self.store._finish(invocation["id"], {"status": "unknown", "text": "", "runtime_status": "adapter_error", "evidence": {"error_type": type(exc).__name__}})
            item = self.store.get(invocation["id"])
            if item["reply_state"] == "pending":
                with self.store.connect() as db:
                    db.execute("UPDATE community_invocations SET reply_state='sending',updated_at=? WHERE id=? AND reply_state='pending'", (time.time(), item["id"]))
                self._send(self.store.get(item["id"]))
            return self.store.get(item["id"])
