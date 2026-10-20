"""Behavioral contract for bounded queries and durable saved views."""

from datetime import datetime, timezone
import asyncio
import hmac
import hashlib
from unittest.mock import patch

import pytest

from chatevent import CaptureMode, ChatEvent, EventStore
from chatevent.query import FilterError, validate_filter
from chatevent.auth import UserRecord, token_digest
from chatevent.server import create_app
from chatevent.subscription import Subscription
from fastapi import HTTPException
from starlette.requests import Request
import json


def event(index: int, *, topic: str = "math", actor: str = "person") -> ChatEvent:
    return ChatEvent(
        id=str(index), source="zulip", kind="message.created",
        occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        captured_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        capture_mode=CaptureMode.EVENT_QUEUE, subscription_id="owned",
        actor_id=actor, subject_id=str(index), subject_type="message",
        payload={"topic": topic, "score": index}, tags=[topic],
    )


def test_filter_rejects_unknown_fields_bad_paths_and_cost_before_sql(tmp_path):
    store = EventStore(tmp_path / "events.db")
    for expression in (
        {"field": "payload.secret", "op": "eq", "value": "x"},
        {"field": "payload.topic\" OR 1=1", "op": "eq", "value": "x"},
        {"field": "source", "op": "regex", "value": ".*"},
        {"all": [{"field": "source", "op": "eq", "value": "zulip"}] * 65},
        {"not": {"not": {"not": {"not": {"not": {"not": {"not": {"field": "source", "op": "eq", "value": "x"}}}}}}}},
    ):
        with pytest.raises(FilterError):
            validate_filter(expression)
        with pytest.raises(FilterError):
            store.query_events(filter_expr=expression)


def test_nested_filter_runs_before_paging_and_cursor_survives_ties_and_duplicates(tmp_path):
    store = EventStore(tmp_path / "events.db")
    for index in range(12):
        store.record_event(event(index, topic="math" if index % 2 else "other"))
    store.record_event(event(1))
    expression = {"all": [
        {"field": "source", "op": "eq", "value": "zulip"},
        {"any": [
            {"field": "payload.topic", "op": "eq", "value": "math"},
            {"field": "tags", "op": "contains", "value": "math"},
        ]},
        {"not": {"field": "actor.id", "op": "eq", "value": "bot"}},
    ]}
    seen = []
    cursor = None
    while True:
        page = store.query_events(filter_expr=expression, sort="asc", limit=2, cursor=cursor)
        seen.extend(item.event.id for item in page.items)
        if not page.has_more:
            break
        cursor = page.next_cursor
    assert seen == [str(i) for i in range(1, 12, 2)]
    assert store.query_events(filter_expr=expression, sort="desc", limit=2).items[0].event.id == "11"
    with pytest.raises(FilterError, match="cursor"):
        store.query_events(filter_expr={"field": "source", "op": "eq", "value": "discourse"}, sort="asc", cursor=cursor)
    with pytest.raises(FilterError, match="cursor"):
        store.query_events(filter_expr=expression, sort="desc", cursor=cursor)


def test_missing_null_and_numeric_semantics(tmp_path):
    store = EventStore(tmp_path / "events.db")
    store.record_event(event(1))
    store.record_event(event(2).model_copy(update={"payload": {"topic": None, "score": "9"}}))
    assert [i.event.id for i in store.query_events(filter_expr={"field": "payload.topic", "op": "exists", "value": True}).items] == ["2", "1"]
    assert [i.event.id for i in store.query_events(filter_expr={"field": "payload.topic", "op": "eq", "value": None}).items] == ["2"]
    assert [i.event.id for i in store.query_events(filter_expr={"field": "payload.score", "op": "gt", "value": 1}).items] == []
    assert [i.event.id for i in store.query_events(filter_expr={"field": "captured_at", "op": "gte", "value": "2026-01-01T00:00:00Z"}).items] == ["2", "1"]
    assert [i.event.id for i in store.query_events(filter_expr={"field": "captured_at", "op": "eq", "value": "2026-01-01T00:00:00+00:00"}).items] == ["2", "1"]
    assert [i.event.id for i in store.query_events(filter_expr={"not": {"field": "payload.title", "op": "eq", "value": "x"}}).items] == ["2", "1"]
    assert [i.event.id for i in store.query_events(filter_expr={"field": "tags", "op": "any", "value": ["math", "proof"]}).items] == ["2", "1"]
    assert [i.event.id for i in store.query_events(filter_expr={"field": "tags", "op": "all", "value": ["math", "proof"]}).items] == []


def test_api_query_and_views_enforce_owner_and_cursor(tmp_path):
    app = create_app(db_path=tmp_path / "events.db")
    store = app.state.store
    alice = store.save_user(UserRecord(username="alice", role="member"), token_hash=token_digest("alice-token"))
    bob = store.save_user(UserRecord(username="bob", role="member"), token_hash=token_digest("bob-token"))
    store.save_user(UserRecord(username="admin", role="admin"), token_hash=token_digest("admin-token"))
    for owner in (alice, bob):
        store.save_subscription(Subscription(id=owner.username, source="zulip", target="stream:test", owner_user_id=owner.id))
    for index in range(4):
        store.record_event(event(index).model_copy(update={"subscription_id": "alice" if index < 3 else "bob"}))
    def endpoint(path, method):
        return next(route.endpoint for route in app.routes if route.path == path and method in route.methods)
    query = endpoint("/api/query", "GET")
    save_view = endpoint("/api/views", "POST")
    list_views = endpoint("/api/views", "GET")
    get_view = endpoint("/api/views/{view_id}", "GET")
    delete_view = endpoint("/api/views/{view_id}", "DELETE")
    get_event = endpoint("/api/events/{dedupe_key:path}", "GET")
    stats = endpoint("/api/stats", "GET")
    record = endpoint("/api/events", "POST")
    expression = {"field": "source", "op": "eq", "value": "zulip"}
    request = Request({"type": "http", "method": "GET", "path": "/api/query", "query_string": b""})
    def page(token, **kwargs):
        return query(request=request, filter=kwargs.get("filter"), view_id=kwargs.get("view_id"),
                     source=None, kind=None, subscription_id=None, sort=kwargs.get("sort"),
                     limit=kwargs.get("limit", 100), cursor=kwargs.get("cursor"),
                     x_chatevent_admin_token=token, chatevent_session=None)
    first = page("alice-token", filter=json.dumps(expression), sort="asc", limit=2)
    assert [i.event.id for i in first.items] == ["0", "1"]
    second = page("alice-token", filter=json.dumps(expression), sort="asc", limit=2, cursor=first.next_cursor)
    assert [i.event.id for i in second.items] == ["2"]
    with pytest.raises(HTTPException) as denied:
        page("bob-token", cursor=first.next_cursor)
    assert denied.value.status_code == 422
    with pytest.raises(HTTPException) as denied:
        get_event("zulip:0", "bob-token", None)
    assert denied.value.status_code == 404
    assert stats("bob-token", None)["event_count"] == 1
    with pytest.raises(HTTPException) as denied:
        record(event(20).model_copy(update={"subscription_id": "bob"}), "alice-token", None, None)
    assert denied.value.status_code == 403
    with pytest.raises(HTTPException) as denied:
        record(event(21).model_copy(update={"subscription_id": "alice", "source": "discourse"}), "alice-token", None, None)
    assert denied.value.status_code == 403
    from chatevent.query import SavedView
    saved = save_view(SavedView(name="Mine", filter=expression, sort="asc", owner_user_id=bob.id), "alice-token", None, None)
    view_id = saved.id
    assert saved.owner_user_id == alice.id
    assert list_views("bob-token", None) == []
    assert get_view(view_id, "admin-token", None).owner_user_id == alice.id
    assert any(view.id == view_id for view in list_views("admin-token", None))
    with pytest.raises(HTTPException) as denied:
        get_view(view_id, "bob-token", None)
    assert denied.value.status_code == 404
    assert page("alice-token", view_id=view_id).count == 3
    with pytest.raises(HTTPException) as denied:
        delete_view(view_id, "bob-token", None, None)
    assert denied.value.status_code == 404
    assert delete_view(view_id, "alice-token", None, None).deleted


def test_ingestion_auth_local_mode_and_signed_discourse_binding(tmp_path):
    local = create_app(db_path=tmp_path / "local.db")
    record_local = next(route.endpoint for route in local.routes if route.path == "/api/events" and "POST" in route.methods)
    assert record_local(event(1), None, None, None).created

    with patch.dict("os.environ", {
        "CHATEVENT_ADMIN_TOKEN": "test-admin-token",
        "CHATEVENT_DISCOURSE_WEBHOOK_SECRET": "test-webhook-secret",
        "CHATEVENT_DISCOURSE_INSTANCE": "https://forum.example.org",
        "CHATEVENT_DISCOURSE_SUBSCRIPTION_ID": "signed-hook",
    }):
        app = create_app(db_path=tmp_path / "secured.db")
        app.state.store.save_subscription(Subscription(id="signed-hook", source="discourse", target="category:test"))
        record = next(route.endpoint for route in app.routes if route.path == "/api/events" and "POST" in route.methods)
        with pytest.raises(HTTPException) as denied:
            record(event(1), None, None, None)
        assert denied.value.status_code == 401
        assert record(event(1), "test-admin-token", None, None).created

        hook = next(route.endpoint for route in app.routes if route.path == "/webhooks/discourse")
        body = {"post": {"id": 2, "topic_id": 3, "post_number": 1,
                         "created_at": "2026-08-05T03:00:00Z", "raw": "example"}}
        raw = json.dumps(body).encode()
        async def receive():
            return {"type": "http.request", "body": raw, "more_body": False}
        request = Request({"type": "http", "method": "POST", "path": "/webhooks/discourse"}, receive)
        def call(signature, instance):
            return asyncio.run(hook(request, body, None, "post_created", "post", signature,
                                    instance, None, None, None))
        with pytest.raises(HTTPException) as denied:
            call(None, "https://forum.example.org")
        assert denied.value.status_code == 401
        signature = "sha256=" + hmac.new(b"test-webhook-secret", raw, hashlib.sha256).hexdigest()
        with pytest.raises(HTTPException) as denied:
            call(signature, "https://attacker.example.org")
        assert denied.value.status_code == 403
        assert call(signature, "https://forum.example.org").created
        key = "discourse:instance:" + hashlib.sha256(b"https://forum.example.org").hexdigest()[:16] + ":post:2"
        assert app.state.store.get_event(key).event.subscription_id == "signed-hook"


def test_dashboard_uses_server_query_and_view_controls():
    from chatevent.dashboard import DASHBOARD_HTML
    assert 'id="advancedFilterJson"' in DASHBOARD_HTML
    assert 'id="savedViews"' in DASHBOARD_HTML
    assert 'id="nextPage"' in DASHBOARD_HTML
    assert 'api(`/api/query?${params}`)' in DASHBOARD_HTML
    assert 'renderEvents(events.items)' in DASHBOARD_HTML
    assert 'applyAdvancedEventFilters' not in DASHBOARD_HTML


def test_zulip_webhook_dispatches_bulk_actions_and_rejects_unknown(tmp_path):
    app = create_app(db_path=tmp_path / "events.db")
    hook = next(route.endpoint for route in app.routes if route.path == "/webhooks/zulip")
    def ingest(raw):
        return hook(raw, None, None, None, None)
    result = ingest({"id": 8, "queue_id": "queue-a", "type": "delete_message",
                     "message_ids": [11, 12], "stream_id": 4, "topic": "new"})
    assert result.count == 2
    assert result.created == 2
    assert ingest({"id": 9, "type": "heartbeat"}).count == 0
    with pytest.raises(HTTPException) as denied:
        ingest({"id": 10, "type": "unknown_plugin"})
    assert denied.value.status_code == 422
