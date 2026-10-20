"""Bounded, typed event filters compiled to parameterized SQLite JSON queries.

Missing fields never match a leaf except ``exists: false``. Explicit JSON null
exists and matches ``eq: null``; comparisons require a matching JSON type.
Boolean ``not`` negates these two-valued leaf results, including missing fields.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FilterError(ValueError):
    """Malformed, excessive, or incompatible query expression/cursor."""


# Only normalized public envelope fields and explicitly declared extension fields.
# The SQL JSON path is always a bound value, never user-authored SQL.
FIELDS = {
    "source": "text", "instance": "text", "kind": "text",
    "action.kind": "text", "action.object_type": "text", "action.verb": "text",
    "subscription_id": "text", "actor.id": "text", "actor.type": "text",
    "actor.role": "text", "actor_id": "text", "actor_role": "text",
    "subject_id": "text", "subject_type": "text", "conversation_id": "text",
    "target.type": "text", "target.key": "text", "target.parent.type": "text",
    "target.parent.key": "text", "target.parent.parent.type": "text",
    "target.parent.parent.key": "text", "tags": "array",
    "occurred_at": "time", "captured_at": "time", "url": "text",
    "payload.title": "text", "payload.content": "text", "payload.text": "text",
    "payload.topic": "text", "payload.stream": "text", "payload.score": "number",
    "payload.post_number": "text", "payload.topic_id": "text",
    "payload.emoji_code": "text", "payload.from_topic": "text",
    "payload.from_stream": "text", "payload.sender_id": "text",
    "payload.name": "text",
    "metadata.timestamp_source": "text", "metadata.event_name": "text",
}
OPERATORS = {"eq", "ne", "in", "contains", "exists", "gt", "gte", "lt", "lte", "between", "any", "all"}
MAX_DEPTH = 6
MAX_NODES = 64
MAX_LIST = 50


class SavedView(BaseModel):
    """Named owner-scoped query definition. Capture configuration stays separate."""

    model_config = ConfigDict(extra="forbid")
    id: str = Field(default_factory=lambda: uuid4().hex, min_length=1)
    name: str = Field(min_length=1, max_length=100)
    owner_user_id: str | None = None
    filter: dict[str, Any] | None = None
    sort: str = "desc"

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value

    @field_validator("sort")
    @classmethod
    def valid_sort(cls, value: str) -> str:
        if value not in {"asc", "desc"}:
            raise ValueError("sort must be asc or desc")
        return value

    @field_validator("filter")
    @classmethod
    def valid_filter(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return validate_filter(value)


def _value(value: Any, field_type: str) -> Any:
    if value is None:
        return None
    if field_type == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise FilterError("numeric field requires a finite number")
        return value
    if field_type == "time":
        if not isinstance(value, str):
            raise FilterError("time field requires an ISO 8601 timestamp")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise FilterError("time field requires an ISO 8601 timestamp") from error
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise FilterError("time field requires a timezone")
        return parsed.astimezone(timezone.utc).isoformat()
    if not isinstance(value, str) or len(value) > 1024:
        raise FilterError("text field requires a string of at most 1024 characters")
    return value


def validate_filter(expression: Any) -> dict[str, Any] | None:
    """Validate and normalize a filter before any database access."""
    if expression is None:
        return None
    count = 0

    def visit(node: Any, depth: int) -> dict[str, Any]:
        nonlocal count
        count += 1
        if count > MAX_NODES or depth > MAX_DEPTH:
            raise FilterError("filter is too large or too deep")
        if not isinstance(node, dict):
            raise FilterError("filter node must be an object")
        if len(node) == 1 and "not" in node:
            return {"not": visit(node["not"], depth + 1)}
        if len(node) == 1 and ("all" in node or "any" in node):
            key = "all" if "all" in node else "any"
            children = node[key]
            if not isinstance(children, list) or not 1 <= len(children) <= MAX_NODES:
                raise FilterError(f"{key} must contain 1 to {MAX_NODES} conditions")
            return {key: [visit(child, depth + 1) for child in children]}
        if set(node) != {"field", "op", "value"}:
            raise FilterError("leaf requires exactly field, op, value")
        field, op, value = node["field"], node["op"], node["value"]
        if not isinstance(field, str) or field not in FIELDS:
            raise FilterError("unknown or undeclared filter field")
        if not isinstance(op, str) or op not in OPERATORS:
            raise FilterError("unknown filter operator")
        kind = FIELDS[field]
        if op == "exists":
            if not isinstance(value, bool):
                raise FilterError("exists requires a boolean")
        elif op == "contains":
            if kind not in {"text", "array"}:
                raise FilterError("contains requires text or tags")
            value = _value(value, "text")
        elif op in {"any", "all"}:
            if kind != "array" or not isinstance(value, list) or not 1 <= len(value) <= MAX_LIST:
                raise FilterError("any/all require a nonempty tags list of at most 50 values")
            value = list(dict.fromkeys(_value(item, "text") for item in value))
        elif op in {"gt", "gte", "lt", "lte", "between"}:
            if kind not in {"time", "number"}:
                raise FilterError("comparison requires a time or number field")
            if op == "between":
                if not isinstance(value, list) or len(value) != 2:
                    raise FilterError("between requires two values")
                value = [_value(item, kind) for item in value]
                if value[0] is None or value[1] is None or value[0] > value[1]:
                    raise FilterError("between requires ordered non-null values")
            else:
                value = _value(value, kind)
                if value is None:
                    raise FilterError("comparison requires a non-null value")
        elif op == "in":
            if not isinstance(value, list) or not 1 <= len(value) <= MAX_LIST:
                raise FilterError("in requires a nonempty scalar list of at most 50 values")
            value = [_value(item, "text" if kind == "array" else kind) for item in value]
            if any(item is None for item in value):
                raise FilterError("in does not accept null; use eq:null")
        else:
            if kind == "array":
                raise FilterError("tags support contains or exists")
            value = _value(value, kind)
        return {"field": field, "op": op, "value": value}

    return visit(expression, 0)


def compile_filter(expression: dict[str, Any] | None) -> tuple[str, list[Any]]:
    """Compile a previously validated expression; every path/value is bound."""
    if expression is None:
        return "1", []
    if "all" in expression or "any" in expression:
        key = "all" if "all" in expression else "any"
        parts = [compile_filter(item) for item in expression[key]]
        joiner = " AND " if key == "all" else " OR "
        return "(" + joiner.join(sql for sql, _ in parts) + ")", [param for _, params in parts for param in params]
    if "not" in expression:
        sql, params = compile_filter(expression["not"])
        return f"(NOT COALESCE(({sql}), 0))", params
    field, op, value = expression["field"], expression["op"], expression["value"]
    path = "$." + field
    kind = FIELDS[field]
    type_sql = "json_type(body, ?)"
    extract = "json_extract(body, ?)"
    valid_type = ("'integer','real'" if kind == "number" else "'text'" if kind in {"time", "text"} else "'array'")
    if op == "exists":
        return (f"({type_sql} IS {'NOT ' if value else ''}NULL)", [path])
    if value is None and op in {"eq", "ne"}:
        return (f"({type_sql} {'=' if op == 'eq' else 'IS NOT NULL AND '+type_sql+' <>'} 'null')",
                [path] if op == "eq" else [path, path])
    guard = f"({type_sql} IN ({valid_type})"
    if kind == "time" and op in {"gt", "gte", "lt", "lte", "between"}:
        operator = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<="}.get(op)
        if op == "between":
            return (f"{guard} AND julianday({extract}) BETWEEN julianday(?) AND julianday(?))",
                    [path, path, *value])
        return (f"{guard} AND julianday({extract}) {operator} julianday(?))",
                [path, path, value])
    if kind == "time" and op in {"eq", "ne", "in"}:
        if op == "in":
            choices = ",".join("julianday(?)" for _ in value)
            return (f"{guard} AND julianday({extract}) IN ({choices}))",
                    [path, path, *value])
        return (f"{guard} AND julianday({extract}) {'=' if op == 'eq' else '!='} julianday(?))",
                [path, path, value])
    if op == "contains" and kind == "array":
        return ("(json_type(body, ?) = 'array' AND EXISTS "
                "(SELECT 1 FROM json_each(body, ?) WHERE value = ?))", [path, path, value])
    if kind == "array" and op in {"any", "all", "in"}:
        placeholders = ",".join("?" for _ in value)
        if op == "all":
            return (f"(json_type(body, ?) = 'array' AND "
                    f"(SELECT COUNT(DISTINCT value) FROM json_each(body, ?) WHERE value IN ({placeholders})) = ?)",
                    [path, path, *value, len(value)])
        return (f"(json_type(body, ?) = 'array' AND EXISTS "
                f"(SELECT 1 FROM json_each(body, ?) WHERE value IN ({placeholders})))",
                [path, path, *value])
    if op == "contains":
        return (f"{guard} AND instr(lower({extract}), lower(?)) > 0)", [path, path, value])
    if op == "in":
        placeholders = ",".join("?" for _ in value)
        return (f"{guard} AND {extract} IN ({placeholders}))", [path, path, *value])
    if op == "between":
        return (f"{guard} AND {extract} BETWEEN ? AND ?)", [path, path, *value])
    operator = {"eq": "=", "ne": "!=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}[op]
    return (f"{guard} AND {extract} {operator} ?)", [path, path, value])


def query_fingerprint(expression: dict[str, Any] | None, sort: str, owner: str | None) -> str:
    raw = json.dumps([expression, sort, owner], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def encode_cursor(sequence: int, fingerprint: str) -> str:
    raw = json.dumps([1, sequence, fingerprint], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str, fingerprint: str) -> int:
    if not isinstance(cursor, str) or len(cursor) > 256:
        raise FilterError("invalid cursor")
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        version, sequence, received = json.loads(raw)
    except (ValueError, TypeError, UnicodeDecodeError) as error:
        raise FilterError("invalid cursor") from error
    if version != 1 or type(sequence) is not int or sequence < 0 or received != fingerprint:
        raise FilterError("cursor does not match filter, order, or owner")
    return sequence
