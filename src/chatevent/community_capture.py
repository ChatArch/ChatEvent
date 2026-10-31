"""Community event transport. No model work happens in the capture threads.

Zulip uses its native blocking event queue; Discourse sends signed webhooks.
The private inbox is committed before acknowledging transport, then an outbox
persists ChatEvent and dispatch independently. Credentials never enter events.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import hmac
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .adapters import normalize_discourse_webhook, normalize_zulip_message_event
from .capture import load_env_file
from .model import ActorDescriptor, ChatEvent


class TransportError(Exception):
    """A sanitized transport failure, safe to put in service diagnostics."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def private_path(path: str | Path, *, directory: bool = False) -> Path:
    target = Path(path).expanduser()
    if target.is_symlink():
        raise ValueError("private state must not be a symlink")
    if directory:
        target.mkdir(parents=True, exist_ok=True, mode=0o700)
    if target.exists():
        if target.stat().st_uid != os.getuid() or target.stat().st_mode & 0o077:
            raise ValueError("private state permissions invalid")
    return target


def http_json(url: str, *, fields: dict | None = None,
              body: dict | None = None, headers: dict | None = None,
              timeout: float = 20, method: str | None = None) -> dict:
    hdr = {"Accept": "application/json", **(headers or {})}
    data = None
    if fields is not None:
        data = urlencode(fields).encode()
        hdr["Content-Type"] = "application/x-www-form-urlencoded"
    if body is not None:
        data = json.dumps(body).encode()
        hdr["Content-Type"] = "application/json"
    req = Request(url, data=data, headers=hdr, method=method)
    try:
        with build_opener(ProxyHandler({}), _NoRedirect()).open(req, timeout=timeout) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
            if len(raw) > 2 * 1024 * 1024:
                raise TransportError("response_too_large")
            item = json.loads(raw)
            if not isinstance(item, dict):
                raise TransportError("response_not_object")
            return item
    except HTTPError as exc:
        raise TransportError("http_" + str(exc.code)) from None
    except (OSError, ValueError):
        raise TransportError("transport_failed") from None


def profile_headers(binding: dict, source: str) -> tuple[str, dict]:
    profile = private_path(binding["profile"])
    values = load_env_file(profile)
    if source == "zulip":
        site = values["ZULIP_SITE"].rstrip("/")
        if site != binding.get("transport_site", binding["instance"]).rstrip("/"):
            raise ValueError("zulip credential destination changed")
        email, key = values["ZULIP_BOT_EMAIL"], values["ZULIP_BOT_API_KEY"]
        auth = base64.b64encode((email + ":" + key).encode()).decode()
        return site, {"Authorization": "Basic " + auth}
    site = values.get("DISCOURSE_SITE", values.get("DISCOURSE_BASE_URL", "")).rstrip("/")
    if site != binding.get("transport_site", binding["instance"]).rstrip("/"):
        raise ValueError("discourse credential destination changed")
    if values["DISCOURSE_USERNAME"] != binding["username"]:
        raise ValueError("discourse profile identity mismatch")
    return site, {"Api-Key": values["DISCOURSE_API_KEY"], "Api-Username": binding["username"]}


class Mentions(HTMLParser):
    """Accept rendered native mention elements; quoted text/code is ignored."""
    def __init__(self, source: str):
        super().__init__()
        self.source = source
        self.ids: set[str] = set()
        self.depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag in {"blockquote", "pre", "code"}:
            self.depth += 1
        if self.depth:
            return
        classes = (a.get("class") or "").split()
        if self.source == "zulip" and tag == "span" and "user-mention" in classes:
            uid = a.get("data-user-id") or ""
            if uid.isdecimal():
                self.ids.add("user:" + uid)
        if self.source == "discourse" and tag == "a" and "mention" in classes:
            href = a.get("href") or ""
            if href.startswith("/u/"):
                self.ids.add(href[3:].strip("/").lower())

    def handle_endtag(self, tag: str) -> None:
        if tag in {"blockquote", "pre", "code"} and self.depth:
            self.depth -= 1


def native_mentions(content: str, source: str) -> list[str]:
    parser = Mentions(source)
    parser.feed(content)
    return sorted(parser.ids)


def normalize_message(raw: dict, *, source: str, instance: str,
                      registry: dict) -> tuple[ChatEvent, list[str]]:
    if source == "zulip":
        message = raw.get("message", raw)
        if message.get("type") not in {"stream", "channel"}:
            raise ValueError("only configured channel mentions are enabled")
        event = normalize_zulip_message_event(raw, site_url=instance)
        scope = "stream:" + str(message["stream_id"])
        mentions = native_mentions(message.get("content", ""), source)
    else:
        post = raw.get("post")
        if not isinstance(post, dict) or not str(post.get("user_id", "")).isdecimal():
            raise ValueError("native discourse user ID required")
        if not str(post.get("category_id", "")).isdecimal():
            raise ValueError("native discourse category ID required")
        event = normalize_discourse_webhook(raw, event_name="post_created", instance=instance, base_url=instance)
        actor = "user:" + str(post["user_id"])
        event = event.model_copy(update={"actor_id": actor, "actor": ActorDescriptor(id=actor, type="user")})
        scope = "category:" + str(post["category_id"])
        by_name = {a["bindings"][source]["username"].lower(): a["bindings"][source]["account_id"]
                   for a in registry["agents"] if source in a.get("bindings", {})}
        mentions = [by_name[name] for name in native_mentions(post.get("cooked", ""), source) if name in by_name]
    return event.model_copy(update={"instance": instance,
                                   "metadata": {**event.metadata, "community_scope": scope}}), mentions


class CaptureInbox:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()
        private_path(self.path.parent, directory=True)
        private_path(self.path)
        with self.connect() as c:
            c.execute("CREATE TABLE IF NOT EXISTS inbox (event_key TEXT PRIMARY KEY, event TEXT NOT NULL, mentions TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending', error TEXT, created REAL NOT NULL)")
            c.execute("CREATE TABLE IF NOT EXISTS checkpoints (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        c = sqlite3.connect(self.path, timeout=10)
        c.execute("PRAGMA busy_timeout=10000")
        try:
            with c:
                yield c
        finally:
            c.close()

    def put(self, event: ChatEvent, mentions: list[str]) -> bool:
        with self.connect() as c:
            changed = c.execute("INSERT OR IGNORE INTO inbox(event_key,event,mentions,created) VALUES (?,?,?,?)",
                                (event.dedupe_key, event.model_dump_json(), json.dumps(mentions), time.time())).rowcount
        return bool(changed)

    def get_checkpoint(self, key: str, default: Any = None) -> Any:
        with self.connect() as c:
            row = c.execute("SELECT value FROM checkpoints WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def checkpoint(self, key: str, value: Any) -> None:
        with self.connect() as c:
            c.execute("INSERT OR REPLACE INTO checkpoints VALUES (?,?)", (key, json.dumps(value)))

    def relay_once(self, persist: Any, enqueue: Any, registry: dict) -> bool:
        with self.connect() as c:
            row = c.execute("SELECT event_key,event,mentions,state FROM inbox WHERE state IN ('pending','persisted') ORDER BY created LIMIT 1").fetchone()
        if not row:
            return False
        key, raw, mentions, state = row
        event = ChatEvent.model_validate_json(raw)
        try:
            if state == "pending":
                persist(event)
                with self.connect() as c:
                    c.execute("UPDATE inbox SET state='persisted',error=NULL WHERE event_key=?", (key,))
            enqueue(event, json.loads(mentions), registry)
            with self.connect() as c:
                c.execute("UPDATE inbox SET state='dispatched',error=NULL WHERE event_key=?", (key,))
        except ValueError as exc:
            # A deterministic invalid replay/config mismatch must not starve all
            # later valid events. Keep it for explicit operator reconciliation.
            with self.connect() as c:
                c.execute("UPDATE inbox SET state='quarantined',error=? WHERE event_key=?", (type(exc).__name__, key))
            return True
        except Exception as exc:
            with self.connect() as c:
                c.execute("UPDATE inbox SET error=? WHERE event_key=?", (type(exc).__name__, key))
            raise
        return True

    def status(self) -> dict:
        with self.connect() as c:
            return {"inbox": dict(c.execute("SELECT state,COUNT(*) FROM inbox GROUP BY state")),
                    "errors": c.execute("SELECT COUNT(*) FROM inbox WHERE error IS NOT NULL").fetchone()[0]}


def reply_sender(invocation: dict, result: dict, registry: dict) -> dict:
    """Send only to the stored source using the invoked account, never model routing."""
    event = ChatEvent.model_validate(invocation["event"])
    binding = invocation["binding"]  # Immutable binding snapshot, not today's registry.
    site, headers = profile_headers(binding, event.source)
    me = http_json(site + ("/api/v1/users/me" if event.source == "zulip" else "/session/current.json"), headers=headers)
    uid = me.get("user_id") if event.source == "zulip" else me.get("current_user", {}).get("id")
    if "user:" + str(uid) != binding["account_id"]:
        raise ValueError("reply credential identity mismatch")
    marker = "chat-event-run:" + invocation["id"]
    # The visible ID lets a human reconcile an ambiguous transport outcome.
    text = result["text"][:24000] + "\n\n`" + marker + "`"
    if event.source == "zulip":
        message = event.raw_payload.get("message", event.raw_payload)
        scope = "stream:" + str(message["stream_id"])
        if scope != event.metadata.get("community_scope"):
            raise ValueError("reply origin mismatch")
        response = http_json(site + "/api/v1/messages", fields={"type": "stream", "to": json.dumps([int(message["stream_id"])]),
                             "topic": message.get("subject", message.get("topic", "")), "content": text}, headers=headers)
        if response.get("result") != "success" or not response.get("id"):
            raise TransportError("reply_not_confirmed")
        return {"source": "zulip", "id": str(response["id"]), "identity_id": binding["account_id"]}
    post = event.raw_payload["post"]
    if "category:" + str(post["category_id"]) != event.metadata.get("community_scope"):
        raise ValueError("reply origin mismatch")
    response = http_json(site + "/posts.json", fields={"topic_id": int(post["topic_id"]), "reply_to_post_number": int(post["post_number"]), "raw": text}, headers=headers)
    if not response.get("id") or response.get("user_id") != int(binding["account_id"].split(":")[1]):
        raise TransportError("reply_not_confirmed")
    return {"source": "discourse", "id": str(response["id"]), "identity_id": binding["account_id"]}


class CommunityCapture:
    def __init__(self, config: dict, registry: dict, dispatch: Any):
        self.config, self.registry, self.dispatch = config, registry, dispatch
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.inbox = CaptureInbox(config["inbox_db"])
        self.errors: dict[str, str] = {}
        self.remote_jobs = None

    def accept(self, raw: dict, source: str, instance: str) -> bool:
        event, mentions = normalize_message(raw, source=source, instance=instance, registry=self.registry)
        if event.actor_id not in self.registry["human_actor_ids"].get(source, []):
            return False
        if event.actor_id in self.registry.get("ignored_actor_ids", {}).get(source, []):
            return False
        eligible = set()
        for agent in self.registry["agents"]:
            binding = agent.get("bindings", {}).get(source, {})
            prefix, ids = (("stream:", binding.get("allowed_stream_ids", [])) if source == "zulip"
                           else ("category:", binding.get("allowed_category_ids", [])))
            if (agent.get("enabled") and binding.get("instance", "").rstrip("/") == instance.rstrip("/")
                    and event.metadata["community_scope"] in {prefix + str(i) for i in ids}):
                eligible.add(binding["account_id"])
        mentions = sorted(set(mentions) & eligible)
        if not mentions:
            return False
        added = self.inbox.put(event, mentions)
        self.wake.set()
        return added

    def persist(self, event: ChatEvent) -> None:
        token = private_path(self.config["event_token_file"]).read_text().strip()
        http_json(self.config["event_base_url"].rstrip("/") + "/api/events", body=event.to_dict(),
                  headers={"X-ChatEvent-Admin-Token": token})

    def relay(self) -> None:
        while not self.stop.is_set():
            try:
                while self.inbox.relay_once(self.persist, self.dispatch.enqueue, self.registry):
                    self.wake.set()
                self.errors.pop("relay", None)
            except Exception as exc:
                self.errors["relay"] = type(exc).__name__
            self.wake.wait(2)
            self.wake.clear()

    def zulip_queue(self, agent: dict) -> None:
        binding = agent["bindings"]["zulip"]
        site, headers = profile_headers(binding, "zulip")
        key = "zulip:" + binding["account_id"]
        backoff = 2
        while not self.stop.is_set():
            try:
                saved = self.inbox.get_checkpoint(key)
                if not saved:
                    state = http_json(site + "/api/v1/register", fields={"event_types": '["message"]',
                                      "fetch_event_types": "[]", "apply_markdown": "true",
                                      "client_gravatar": "false"}, headers=headers)
                    if not state.get("queue_id"):
                        raise TransportError("queue_not_created")
                    saved = {"queue_id": state["queue_id"], "last_event_id": state["last_event_id"],
                             "timeout": state.get("event_queue_longpoll_timeout_seconds", 90)}
                    self.inbox.checkpoint(key, saved)
                    # Register before catch-up, closing the reconnect gap.
                    last = self.inbox.get_checkpoint(key + ":message")
                    saved["catchup"] = bool(last)
                    self.inbox.checkpoint(key, saved)
                if saved.get("catchup"):
                    last = self.inbox.get_checkpoint(key + ":message")
                    if last:
                        for _ in range(20):
                            page = http_json(site + "/api/v1/messages?" + urlencode({"anchor": last, "num_before": 0,
                                             "num_after": 100, "include_anchor": "false", "apply_markdown": "true"}), headers=headers)
                            messages = page.get("messages", [])
                            for message in messages:
                                self._zulip_one(message, binding["instance"], key)
                                last = max(last, int(message["id"]))
                            if page.get("found_newest") or not messages:
                                saved["catchup"] = False
                                self.inbox.checkpoint(key, saved)
                                break
                        else:
                            # The saved catch-up flag remains set: never skip to
                            # live delivery while a bounded page batch has more.
                            raise TransportError("catchup_limit_requires_operator")
                response = http_json(site + "/api/v1/events?" + urlencode({"queue_id": saved["queue_id"],
                                     "last_event_id": saved["last_event_id"], "dont_block": "false"}),
                                     headers=headers, timeout=min(float(saved["timeout"]) + 10, 150))
                for item in response.get("events", []):
                    if item.get("type") == "message":
                        self._zulip_one(item["message"], binding["instance"], key)
                    saved["last_event_id"] = max(saved["last_event_id"], item["id"])
                    self.inbox.checkpoint(key, saved)
                self.errors.pop(key, None)
                backoff = 2
            except Exception as exc:
                self.errors[key] = type(exc).__name__
                # A new queue catches up from the last durably observed message.
                if isinstance(exc, TransportError) and str(exc) == "http_400":
                    self.inbox.checkpoint(key, None)
                self.stop.wait(backoff)
                backoff = min(backoff * 2, 60)

    def _zulip_one(self, message: dict, site: str, key: str) -> None:
        if message.get("type") in {"stream", "channel"}:
            self.accept(message, "zulip", site)
        previous = self.inbox.get_checkpoint(key + ":message", 0)
        self.inbox.checkpoint(key + ":message", max(previous, int(message["id"])))

    def handler(self) -> type[BaseHTTPRequestHandler]:
        capture = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:
                pass

            def send_json(self, code: int, value: dict) -> None:
                body = json.dumps(value).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:
                if self.path.startswith("/workers/") and self.path.endswith("/next"):
                    from .community_remote import authorize_worker
                    parts = self.path.split("/")
                    if len(parts) != 4 or capture.remote_jobs is None or not authorize_worker(capture.config, parts[2], self.headers.get("Authorization", "")):
                        return self.send_json(401, {"error": "worker_auth"})
                    return self.send_json(200, {"job": capture.remote_jobs.claim(parts[2])})
                if self.path != "/health":
                    return self.send_json(404, {"error": "not_found"})
                # Health intentionally discloses no user text, account/profile or state path.
                self.send_json(200 if not capture.errors else 503, {"status": "ok" if not capture.errors else "degraded", "errors": capture.errors})

            def do_POST(self) -> None:
                if self.path.startswith("/workers/") and self.path.endswith(("/result", "/started")):
                    from .community_remote import authorize_worker
                    parts = self.path.split("/")
                    if len(parts) != 4 or capture.remote_jobs is None or not authorize_worker(capture.config, parts[2], self.headers.get("Authorization", "")):
                        return self.send_json(401, {"error": "worker_auth"})
                    try:
                        length = int(self.headers.get("Content-Length", "0"))
                        if not 0 < length <= 300000:
                            return self.send_json(413, {"error": "body_bound"})
                        payload = json.loads(self.rfile.read(length))
                        if self.path.endswith("/started"):
                            capture.remote_jobs.started(parts[2], payload["id"], payload["started_at"])
                        else:
                            capture.remote_jobs.complete(parts[2], payload["id"], payload["result"])
                        return self.send_json(200, {"accepted": True})
                    except (KeyError, ValueError, TypeError):
                        return self.send_json(409, {"error": "result_conflict"})
                if self.path != "/webhooks/discourse":
                    return self.send_json(404, {"error": "not_found"})
                self.connection.settimeout(10)
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 1024 * 1024:
                        return self.send_json(413, {"error": "body_bound"})
                    body = self.rfile.read(length)
                    secret = private_path(capture.config["discourse_secret_file"]).read_bytes().strip()
                    expected = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
                    if not secret or not hmac.compare_digest(expected, self.headers.get("X-Discourse-Event-Signature", "")):
                        return self.send_json(401, {"error": "signature"})
                    if self.headers.get("X-Discourse-Event") != "post_created":
                        return self.send_json(202, {"accepted": True, "ignored": "event_type"})
                    instance = capture.config["discourse_instance"]
                    if self.headers.get("X-Discourse-Instance", "").rstrip("/") != instance.rstrip("/"):
                        return self.send_json(403, {"error": "instance"})
                    added = capture.accept(json.loads(body), "discourse", instance)
                    self.send_json(202, {"accepted": True, "new": added})
                except (ValueError, KeyError, TypeError):
                    self.send_json(422, {"error": "invalid_event"})
                except Exception:
                    self.send_json(503, {"error": "capture_unavailable"})
        return Handler

    def start(self) -> list[threading.Thread]:
        threads = [threading.Thread(target=self.relay, daemon=True, name="capture-outbox")]
        for agent in self.registry["agents"]:
            if agent.get("enabled") and "zulip" in agent.get("bindings", {}):
                threads.append(threading.Thread(target=self.zulip_queue, args=(agent,), daemon=True,
                                                name="zulip-" + agent["agent_id"]))
        for thread in threads:
            thread.start()
        return threads


class BoundedHTTPServer(ThreadingHTTPServer):
    """Bound signed webhook connections on the existing private network."""
    daemon_threads = True
    request_queue_size = 8

    def __init__(self, *args: Any, **kwargs: Any):
        self.slots = threading.BoundedSemaphore(8)
        super().__init__(*args, **kwargs)

    def process_request(self, request: Any, address: Any) -> None:
        if not self.slots.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, address)
        except Exception:
            self.slots.release()
            raise

    def get_request(self):
        request, address = super().get_request()
        request.settimeout(10)
        return request, address

    def process_request_thread(self, request: Any, address: Any) -> None:
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()
