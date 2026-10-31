"""One own-author Discourse status post per durable community invocation.

The caller owns transition ordering, durable send intent and ambiguous-outcome
reconciliation. This transport never retries a create, starts an agent, changes
permissions, or uses the ordinary reply profile in place of a status profile.
"""

from __future__ import annotations

from hashlib import sha256
import re

from .community_capture import TransportError, http_json, profile_headers


STAGES = {
    "queued": "👀 已收到/排队",
    "running": "⏳ 开始处理",
    "succeeded": "✅ 完成",
    "failed": "❌ 失败",
    "unknown": "⚠ 需核对",
    "waiting_for_user": "⏸ 等待用户",
    "cancelled": "⏹ 已取消",
}

_INVOCATION = re.compile(r"[a-f0-9]{32}")
_ACCOUNT = re.compile(r"user:([1-9][0-9]*)")


class StatusCreateAmbiguous(TransportError):
    """A create may have committed; do not automatically send another POST.

    ``receipt`` is unverified when the server returned an own-author post ID but
    readback failed. It permits reconciliation by GET, never another create.
    """

    retry_safe = False

    def __init__(self, receipt: dict | None = None):
        super().__init__("status_create_ambiguous")
        self.receipt = receipt


def _positive(value: object) -> int:
    if isinstance(value, bool) or not re.fullmatch(r"[1-9][0-9]*", str(value)):
        raise ValueError("native positive identifier required")
    return int(str(value))


def _raw(invocation_id: str, stage: str) -> str:
    return STAGES[stage] + "\n\n`chat-event-status:" + invocation_id + "`"


def _digest(raw: str) -> str:
    return sha256(raw.encode()).hexdigest()


def _origin(invocation: dict) -> tuple[dict, int, int, int, int, str]:
    invocation_id = invocation.get("id", "")
    if not isinstance(invocation_id, str) or not _INVOCATION.fullmatch(invocation_id):
        raise ValueError("durable invocation identifier required")
    event, binding = invocation["event"], invocation["binding"]
    if event.get("source") != "discourse" or event.get("kind") not in {"post.created", "reply.created"}:
        raise ValueError("Discourse source message required")
    if not binding.get("status_profile"):
        raise ValueError("dedicated status profile required")
    account = _ACCOUNT.fullmatch(str(binding.get("account_id", "")))
    if not account or not binding.get("username"):
        raise ValueError("native bound identity required")
    instance = str(event.get("instance", "")).rstrip("/")
    if not instance or instance != str(binding.get("instance", "")).rstrip("/"):
        raise ValueError("status instance mismatch")
    post = event["raw_payload"]["post"]
    source_post_id = _positive(post["id"])
    topic_id, post_number = _positive(post["topic_id"]), _positive(post["post_number"])
    category_id, author_id = _positive(post["category_id"]), _positive(post["user_id"])
    if (event.get("subject_id") != "post:" + str(source_post_id)
            or event.get("conversation_id") != "topic:" + str(topic_id)
            or event.get("actor_id") != "user:" + str(author_id)
            or event.get("metadata", {}).get("community_scope") != "category:" + str(category_id)
            or category_id not in {_positive(v) for v in binding.get("allowed_category_ids", [])}):
        raise ValueError("status origin mismatch")
    return binding, int(account[1]), source_post_id, topic_id, post_number, invocation_id


def _check_receipt(receipt: dict, *, account_id: str, source_post_id: int,
                   topic_id: int, invocation_id: str) -> tuple[int, str]:
    if (not isinstance(receipt, dict) or receipt.get("source") != "discourse"
            or receipt.get("identity_id") != account_id
            or receipt.get("source_post_id") != str(source_post_id)
            or receipt.get("topic_id") != str(topic_id)
            or receipt.get("invocation_id") != invocation_id
            or receipt.get("stage") not in STAGES):
        raise ValueError("status receipt mismatch")
    expected = _digest(_raw(invocation_id, receipt["stage"]))
    if receipt.get("content_sha256") != expected:
        raise ValueError("status receipt content mismatch")
    return _positive(receipt.get("id")), expected


def _check_post(post: dict, *, post_id: int, user_id: int, username: str,
                topic_id: int, post_number: int) -> str:
    if (post.get("id") != post_id or post.get("user_id") != user_id
            or post.get("username") != username or post.get("topic_id") != topic_id
            or str(post.get("reply_to_post_number")) != str(post_number)
            or not isinstance(post.get("raw"), str)):
        raise ValueError("status post ownership or origin mismatch")
    return _digest(post["raw"])


def status_sender(invocation: dict, stage: str, previous_receipt: dict | None = None) -> dict:
    """Create/update only this invocation's own status post; no retry on timeout.

    Persist the returned receipt before the next transition. A create with an
    unknown transport result must be reconciled by the caller instead of calling
    this function again with ``previous_receipt=None``. An update can safely read
    back the desired content using its prior receipt, without sending another PUT.
    """
    if stage not in STAGES:
        raise ValueError("unsupported status stage")
    binding, user_id, source_post_id, topic_id, post_number, invocation_id = _origin(invocation)
    previous_id, previous_hash = None, None
    if previous_receipt is not None:
        previous_id, previous_hash = _check_receipt(
            previous_receipt, account_id=binding["account_id"], source_post_id=source_post_id,
            topic_id=topic_id, invocation_id=invocation_id)
    status_binding = {**binding, "profile": binding["status_profile"]}
    site, headers = profile_headers(status_binding, "discourse")
    me = http_json(site + "/session/current.json", headers=headers).get("current_user", {})
    if (me.get("id") != user_id or me.get("username") != binding["username"]
            or me.get("admin") is not False or me.get("moderator") is not False):
        raise ValueError("status credential identity mismatch")
    raw, created = _raw(invocation_id, stage), previous_id is None
    expected = _digest(raw)
    def receipt(post_id: int, *, verified: bool) -> dict:
        return {"source": "discourse", "id": str(post_id), "identity_id": binding["account_id"],
                "source_post_id": str(source_post_id), "topic_id": str(topic_id),
                "invocation_id": invocation_id, "stage": stage, "content_sha256": expected,
                "created": created, "verified": verified}

    if created:
        partial = None
        try:
            response = http_json(site + "/posts.json", fields={"topic_id": topic_id,
                                 "reply_to_post_number": post_number, "raw": raw}, headers=headers)
            if response.get("user_id") != user_id or response.get("username") != binding["username"]:
                raise TransportError("status_create_not_confirmed")
            post_id = _positive(response.get("id"))
            partial = receipt(post_id, verified=False)
            post = http_json(site + "/posts/" + str(post_id) + ".json", headers=headers)
            if _check_post(post, post_id=post_id, user_id=user_id, username=binding["username"],
                           topic_id=topic_id, post_number=post_number) != expected:
                raise TransportError("status_readback_not_confirmed")
        except Exception:
            # Never conceal a possibly committed create behind a generic soft
            # transport error that an outbox might safely retry.
            raise StatusCreateAmbiguous(partial) from None
        return receipt(post_id, verified=True)
    else:
        post_id = previous_id
        post = http_json(site + "/posts/" + str(post_id) + ".json", headers=headers)
        actual = _check_post(post, post_id=post_id, user_id=user_id, username=binding["username"],
                             topic_id=topic_id, post_number=post_number)
        if actual != expected:
            if actual != previous_hash:
                raise ValueError("status post changed outside receipt")
            response = http_json(site + "/posts/" + str(post_id) + ".json", method="PUT",
                                 body={"post": {"raw": raw, "edit_reason": "Agent status: " + stage}},
                                 headers=headers)
            if not isinstance(response.get("post"), dict) or response["post"].get("id") != post_id:
                raise TransportError("status_update_not_confirmed")
        else:
            return {**previous_receipt, "stage": stage, "content_sha256": expected,
                    "created": False, "verified": True}
    post = http_json(site + "/posts/" + str(post_id) + ".json", headers=headers)
    if _check_post(post, post_id=post_id, user_id=user_id, username=binding["username"],
                   topic_id=topic_id, post_number=post_number) != expected:
        raise TransportError("status_readback_not_confirmed")
    return receipt(post_id, verified=True)
