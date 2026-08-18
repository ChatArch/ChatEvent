"""SQLite persistence for subscriptions and normalized events."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from .auth import UserRecord
from .model import ChatEvent, utc_now
from .state import set_private_file_mode
from .subscription import Subscription


class StoredEvent(BaseModel):
    """A normalized event plus capture history maintained by the store."""

    model_config = ConfigDict(extra="forbid")

    event: ChatEvent
    first_captured_at: str
    last_captured_at: str
    seen_count: int


class EventStore:
    """Small local event store optimized for observability and debugging."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
        set_private_file_mode(self.path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    target TEXT NOT NULL,
                    enabled INTEGER NOT NULL,
                    updated_at TEXT NOT NULL,
                    body TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    role TEXT NOT NULL,
                    enabled INTEGER NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    body TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS events (
                    dedupe_key TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    subscription_id TEXT,
                    conversation_id TEXT,
                    occurred_at TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    first_captured_at TEXT NOT NULL,
                    last_captured_at TEXT NOT NULL,
                    seen_count INTEGER NOT NULL DEFAULT 1,
                    body TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_events_source_captured
                    ON events(source, captured_at DESC);
                CREATE INDEX IF NOT EXISTS idx_events_kind_captured
                    ON events(kind, captured_at DESC);
                CREATE INDEX IF NOT EXISTS idx_events_subscription_captured
                    ON events(subscription_id, captured_at DESC);
                CREATE INDEX IF NOT EXISTS idx_users_token_hash
                    ON users(token_hash);
                CREATE INDEX IF NOT EXISTS idx_users_role_enabled
                    ON users(role, enabled);
                """
            )

    @staticmethod
    def _json(value: BaseModel) -> str:
        return json.dumps(
            value.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
        )

    def save_user(self, user: UserRecord, *, token_hash: str) -> UserRecord:
        now = utc_now()
        created = user.created_at or now
        updated = user.model_copy(update={"created_at": created, "updated_at": now})
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO users(id, username, role, enabled, token_hash, created_at, updated_at, body)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    username=excluded.username,
                    role=excluded.role,
                    enabled=excluded.enabled,
                    token_hash=excluded.token_hash,
                    updated_at=excluded.updated_at,
                    body=excluded.body
                """,
                (
                    updated.id,
                    updated.username,
                    updated.role,
                    int(updated.enabled),
                    token_hash,
                    updated.created_at.isoformat(),
                    updated.updated_at.isoformat(),
                    self._json(updated),
                ),
            )
        return updated

    def list_users(self) -> list[UserRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT body FROM users ORDER BY updated_at DESC"
            ).fetchall()
        return [UserRecord.model_validate_json(row["body"]) for row in rows]

    def get_user_by_token_hash(self, token_hash: str) -> UserRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT body FROM users WHERE token_hash = ? AND enabled = 1",
                (token_hash,),
            ).fetchone()
        if row is None:
            return None
        return UserRecord.model_validate_json(row["body"])

    def delete_user(self, user_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM users WHERE id = ?", (user_id,))
        return cursor.rowcount > 0

    def save_subscription(self, subscription: Subscription) -> Subscription:
        updated = subscription.model_copy(update={"updated_at": utc_now()})
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO subscriptions(id, source, target, enabled, updated_at, body)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    source=excluded.source,
                    target=excluded.target,
                    enabled=excluded.enabled,
                    updated_at=excluded.updated_at,
                    body=excluded.body
                """,
                (
                    updated.id,
                    updated.source,
                    updated.target,
                    int(updated.enabled),
                    updated.updated_at.isoformat(),
                    self._json(updated),
                ),
            )
        return updated

    def list_subscriptions(
        self, *, enabled: bool | None = None, owner_user_id: str | None = None
    ) -> list[Subscription]:
        sql = "SELECT body FROM subscriptions"
        parameters: list[Any] = []
        clauses: list[str] = []
        if enabled is not None:
            clauses.append("enabled = ?")
            parameters.append(int(enabled))
        if owner_user_id is not None:
            clauses.append("json_extract(body, '$.owner_user_id') = ?")
            parameters.append(owner_user_id)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY updated_at DESC"
        with self._connect() as connection:
            rows = connection.execute(sql, parameters).fetchall()
        return [Subscription.model_validate_json(row["body"]) for row in rows]

    def get_subscription(self, subscription_id: str) -> Subscription | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT body FROM subscriptions WHERE id = ?", (subscription_id,)
            ).fetchone()
        if row is None:
            return None
        return Subscription.model_validate_json(row["body"])

    def delete_subscription(self, subscription_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM subscriptions WHERE id = ?", (subscription_id,)
            )
        return cursor.rowcount > 0

    def record_event(self, event: ChatEvent) -> tuple[StoredEvent, bool]:
        captured_at = event.captured_at.isoformat()
        body = self._json(event)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO events(
                    dedupe_key, source, kind, subscription_id, conversation_id,
                    occurred_at, captured_at, first_captured_at,
                    last_captured_at, seen_count, body
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    event.dedupe_key,
                    event.source,
                    event.kind,
                    event.subscription_id,
                    event.conversation_id,
                    event.occurred_at.isoformat(),
                    captured_at,
                    captured_at,
                    captured_at,
                    body,
                ),
            )
            created = cursor.rowcount == 1
            if not created:
                connection.execute(
                    """
                    UPDATE events
                    SET last_captured_at = ?, seen_count = seen_count + 1
                    WHERE dedupe_key = ?
                    """,
                    (captured_at, event.dedupe_key),
                )
            if event.subscription_id:
                self._mark_subscription_event(connection, event)
            row = connection.execute(
                """
                SELECT body, first_captured_at, last_captured_at, seen_count
                FROM events WHERE dedupe_key = ?
                """,
                (event.dedupe_key,),
            ).fetchone()
        if row is None:
            raise RuntimeError("event disappeared after being recorded")
        return self._stored_event(row), created

    def _mark_subscription_event(
        self, connection: sqlite3.Connection, event: ChatEvent
    ) -> None:
        row = connection.execute(
            "SELECT body FROM subscriptions WHERE id = ?", (event.subscription_id,)
        ).fetchone()
        if row is None:
            return
        subscription = Subscription.model_validate_json(row["body"])
        updated = subscription.model_copy(
            update={
                "updated_at": utc_now(),
                "last_event_at": event.captured_at,
                "last_cursor": event.cursor or subscription.last_cursor,
                "last_error": None,
            }
        )
        connection.execute(
            """
            UPDATE subscriptions SET updated_at = ?, body = ? WHERE id = ?
            """,
            (updated.updated_at.isoformat(), self._json(updated), updated.id),
        )

    @staticmethod
    def _stored_event(row: sqlite3.Row) -> StoredEvent:
        return StoredEvent(
            event=ChatEvent.model_validate_json(row["body"]),
            first_captured_at=row["first_captured_at"],
            last_captured_at=row["last_captured_at"],
            seen_count=row["seen_count"],
        )

    def get_event(self, dedupe_key: str) -> StoredEvent | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT body, first_captured_at, last_captured_at, seen_count
                FROM events WHERE dedupe_key = ?
                """,
                (dedupe_key,),
            ).fetchone()
        return None if row is None else self._stored_event(row)

    def list_events(
        self,
        *,
        source: str | None = None,
        kind: str | None = None,
        subscription_id: str | None = None,
        query: str | None = None,
        captured_since: datetime | None = None,
        captured_from: datetime | None = None,
        captured_until: datetime | None = None,
        limit: int = 100,
    ) -> list[StoredEvent]:
        clauses: list[str] = []
        parameters: list[Any] = []
        for column, value in (
            ("source", source),
            ("kind", kind),
            ("subscription_id", subscription_id),
        ):
            if value:
                clauses.append(f"{column} = ?")
                parameters.append(value)
        if query:
            clauses.append("body LIKE ?")
            parameters.append(f"%{query}%")
        if captured_since is not None:
            if captured_since.tzinfo is None or captured_since.utcoffset() is None:
                raise ValueError("captured_since must include timezone information")
            clauses.append("captured_at > ?")
            parameters.append(captured_since.astimezone(timezone.utc).isoformat())
        if captured_from is not None:
            if captured_from.tzinfo is None or captured_from.utcoffset() is None:
                raise ValueError("captured_from must include timezone information")
            clauses.append("captured_at >= ?")
            parameters.append(captured_from.astimezone(timezone.utc).isoformat())
        if captured_until is not None:
            if captured_until.tzinfo is None or captured_until.utcoffset() is None:
                raise ValueError("captured_until must include timezone information")
            clauses.append("captured_at <= ?")
            parameters.append(captured_until.astimezone(timezone.utc).isoformat())
        sql = """
            SELECT body, first_captured_at, last_captured_at, seen_count
            FROM events
        """
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY captured_at DESC LIMIT ?"
        parameters.append(max(1, min(limit, 500)))
        with self._connect() as connection:
            rows = connection.execute(sql, parameters).fetchall()
        return [self._stored_event(row) for row in rows]

    def stats(self) -> dict[str, Any]:
        with self._connect() as connection:
            event_row = connection.execute(
                """
                SELECT COUNT(*) AS event_count,
                       COALESCE(SUM(seen_count - 1), 0) AS duplicate_count,
                       MAX(last_captured_at) AS latest_captured_at
                FROM events
                """
            ).fetchone()
            subscription_count = connection.execute(
                "SELECT COUNT(*) FROM subscriptions WHERE enabled = 1"
            ).fetchone()[0]
            sources = dict(
                connection.execute(
                    "SELECT source, COUNT(*) FROM events GROUP BY source ORDER BY COUNT(*) DESC"
                ).fetchall()
            )
            kinds = dict(
                connection.execute(
                    "SELECT kind, COUNT(*) FROM events GROUP BY kind ORDER BY COUNT(*) DESC"
                ).fetchall()
            )
        return {
            "event_count": event_row["event_count"],
            "duplicate_count": event_row["duplicate_count"],
            "latest_captured_at": event_row["latest_captured_at"],
            "subscription_count": subscription_count,
            "source_count": len(sources),
            "sources": sources,
            "kinds": kinds,
        }
