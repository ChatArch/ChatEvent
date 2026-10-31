"""Native, own-account status reactions on an invocation's source message.

No model, message posting, owner credentials, or other users' reactions are
involved. The caller owns the durable status ledger and catches delivery errors
independently of execution. Names/codes were checked against the current Zulip
renderer; notably Zulip ``x`` is 274e, while ``cross_mark`` is 274c.
"""

from __future__ import annotations

import re
import time
from typing import Callable

from .community_capture import TransportError, http_json, profile_headers


# Explicit Unicode namespace prevents custom realm emoji with matching names
# from changing the meaning of a status acknowledgement.
STAGE_EMOJI = {
    "queued": {"emoji_name": "eyes", "emoji_code": "1f440", "reaction_type": "unicode_emoji"},
    "running": {"emoji_name": "hourglass", "emoji_code": "23f3", "reaction_type": "unicode_emoji"},
    "succeeded": {"emoji_name": "check", "emoji_code": "2705", "reaction_type": "unicode_emoji"},
    "failed": {"emoji_name": "cross_mark", "emoji_code": "274c", "reaction_type": "unicode_emoji"},
    "unknown": {"emoji_name": "question", "emoji_code": "2753", "reaction_type": "unicode_emoji"},
    "waiting_for_user": {"emoji_name": "warning", "emoji_code": "26a0", "reaction_type": "unicode_emoji"},
    "cancelled": {"emoji_name": "no_entry", "emoji_code": "26d4", "reaction_type": "unicode_emoji"},
}
_MANAGED_CODES = {item["emoji_code"] for item in STAGE_EMOJI.values()}
_CANONICAL_NAMES = {item["emoji_code"]: item["emoji_name"] for item in STAGE_EMOJI.values()}


def _origin(invocation: dict) -> tuple[dict, dict, int, int, int]:
    event, binding = invocation["event"], invocation["binding"]
    if event.get("source") != "zulip" or event.get("kind") != "message.created":
        raise ValueError("Zulip source message required")
    if not re.fullmatch(r"user:[1-9][0-9]*", str(binding.get("account_id", ""))):
        raise ValueError("native bound identity required")
    if not event.get("instance") or str(event["instance"]).rstrip("/") != str(binding.get("instance", "")).rstrip("/"):
        raise ValueError("status source instance mismatch")
    raw = event.get("raw_payload") or {}
    message = raw.get("message", raw)
    values = [message.get(k) for k in ("id", "stream_id", "sender_id")]
    if any(not re.fullmatch(r"[1-9][0-9]*", str(value)) for value in values):
        raise ValueError("native source IDs required")
    message_id, stream_id, sender_id = map(int, values)
    scope = f"stream:{stream_id}"
    topic = message.get("subject") or message.get("topic")
    if (event.get("subject_id") != f"message:{message_id}"
            or event.get("actor_id") != f"user:{sender_id}"
            or event.get("conversation_id") != f"{scope}/topic:{topic}"
            or event.get("metadata", {}).get("community_scope") != scope
            or invocation.get("community_scope", scope) != scope):
        raise ValueError("status origin mismatch")
    if stream_id not in {int(v) for v in binding.get("allowed_stream_ids", [])}:
        raise ValueError("status stream outside binding")
    return event, binding, message_id, stream_id, sender_id


def _own_managed(message: dict, user_id: int) -> dict[str, dict]:
    reactions = message.get("reactions")
    if not isinstance(reactions, list):
        raise TransportError("reaction_snapshot_missing")
    own = {}
    for reaction in reactions:
        if not isinstance(reaction, dict):
            raise TransportError("invalid_reaction_snapshot")
        uid = reaction.get("user_id")
        if uid is None and isinstance(reaction.get("user"), dict):
            uid = reaction["user"].get("id")
        code = reaction.get("emoji_code")
        if str(uid) != str(user_id) or reaction.get("reaction_type") != "unicode_emoji" or code not in _MANAGED_CODES:
            continue
        name = reaction.get("emoji_name")
        if not isinstance(name, str) or not re.fullmatch(r"[a-zA-Z0-9_+\-]{1,100}", name):
            name = _CANONICAL_NAMES[code]
        own[code] = {"emoji_name": name, "emoji_code": code, "reaction_type": "unicode_emoji"}
    return own


class ZulipStatusSender:
    """Idempotent observed-state reconciliation; at most ten seconds per call.

    Add the desired status before removing this user's other managed statuses,
    so a failed transition leaves an acknowledgement visible. A subsequent
    status retry re-reads platform state and never retries the model turn.
    """

    def __init__(self, *, request: Callable | None = None, profile_loader: Callable | None = None, timeout: float = 10):
        if not 0 < timeout <= 10:
            raise ValueError("status budget must be within ten seconds")
        self.request = request or http_json
        self.profile_loader = profile_loader or profile_headers
        self.timeout = timeout

    def __call__(self, invocation: dict, stage: str) -> dict:
        if stage not in STAGE_EMOJI:
            raise ValueError("unsupported status stage")
        _, binding, message_id, stream_id, sender_id = _origin(invocation)
        deadline = time.monotonic() + self.timeout
        site, headers = self.profile_loader(binding, "zulip")
        # Recheck the trusted credential destination even for injected loaders.
        if site.rstrip("/") != binding.get("transport_site", binding["instance"]).rstrip("/"):
            raise ValueError("status credential destination mismatch")

        def call(path: str, **kwargs) -> dict:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TransportError("status_deadline")
            value = self.request(site.rstrip("/") + path, headers=headers, timeout=min(10, remaining), **kwargs)
            if not isinstance(value, dict) or value.get("result") != "success":
                raise TransportError("status_not_confirmed")
            if value.get("ignored_parameters_unsupported"):
                raise TransportError("status_parameters_unsupported")
            return value

        me = call("/api/v1/users/me")
        user_id = me.get("user_id")
        if f"user:{user_id}" != binding["account_id"]:
            raise ValueError("status credential identity mismatch")

        def snapshot() -> dict[str, dict]:
            message = call(f"/api/v1/messages/{message_id}").get("message")
            if (not isinstance(message, dict) or message.get("type") not in {"stream", "channel"}
                    or str(message.get("id")) != str(message_id)
                    or str(message.get("stream_id")) != str(stream_id)
                    or str(message.get("sender_id")) != str(sender_id)):
                raise ValueError("live status source mismatch")
            return _own_managed(message, int(user_id))

        current = snapshot()
        desired = STAGE_EMOJI[stage]
        changed = False
        removed = []
        if desired["emoji_code"] not in current:
            call(f"/api/v1/messages/{message_id}/reactions", method="POST", fields=dict(desired))
            changed = True
        # Only native own-user Unicode statuses in the snapshot are removed.
        # Never pass a target user ID, and never touch custom/unrelated emoji.
        for code, emoji in current.items():
            if code != desired["emoji_code"]:
                call(f"/api/v1/messages/{message_id}/reactions", method="DELETE", fields=emoji)
                removed.append(code)
                changed = True
        observed = snapshot() if changed else current
        if set(observed) != {desired["emoji_code"]}:
            raise TransportError("status_readback_mismatch")
        return {"source": "zulip", "message_id": str(message_id), "identity_id": binding["account_id"],
                "stage": stage, "emoji": dict(desired), "verified": True,
                "changed": changed, "removed_emoji_codes": removed}


def zulip_status_sender(invocation: dict, stage: str) -> dict:
    """Integration callback; callers isolate its failures from runtime execution."""
    return ZulipStatusSender()(invocation, stage)
