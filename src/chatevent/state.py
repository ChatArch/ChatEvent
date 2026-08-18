"""ChatArch-owned runtime path helpers for ChatEvent."""

from __future__ import annotations

import os
import shutil
import sqlite3
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ChatEventPaths:
    """Resolved ChatEvent runtime paths under one ChatArch state root."""

    chatarch_home: Path
    state_dir: Path
    database: Path
    secrets_dir: Path
    admin_token_file: Path
    legacy_database: Path

    def as_dict(self) -> dict[str, Any]:
        return {
            "chatarch_home": str(self.chatarch_home),
            "state_dir": str(self.state_dir),
            "database": str(self.database),
            "secrets_dir": str(self.secrets_dir),
            "admin_token_file": str(self.admin_token_file),
            "legacy_database": str(self.legacy_database),
            "legacy_database_exists": self.legacy_database.exists(),
            "admin_token_configured": bool(load_admin_token()),
            "admin_token_source": admin_token_source(),
        }


def state_paths(*, chatarch_home: str | Path | None = None, create: bool = False) -> ChatEventPaths:
    """Return all default ChatEvent state paths under ChatArch home.

    Precedence for the ChatArch root is explicit ``chatarch_home`` >
    ``CHATARCH_HOME`` > ``~/.chatarch``. Individual DB overrides still use
    ``CHATEVENT_DB`` at the command boundary, but the default always stays here.
    """

    root = Path(
        chatarch_home or os.environ.get("CHATARCH_HOME") or Path.home() / ".chatarch"
    ).expanduser()
    state_dir = root / "chatevent"
    paths = ChatEventPaths(
        chatarch_home=root,
        state_dir=state_dir,
        database=state_dir / "events.db",
        secrets_dir=state_dir / "secrets",
        admin_token_file=state_dir / "secrets" / "admin-token",
        legacy_database=Path.home() / ".chatevent" / "events.db",
    )
    if create:
        _ensure_private_dir(paths.chatarch_home)
        _ensure_private_dir(paths.state_dir)
        _ensure_private_dir(paths.secrets_dir)
    return paths


def default_database_path() -> Path:
    """Resolve the default SQLite database path.

    Explicit ``CHATEVENT_DB`` remains an override for tests and controlled
    deployments. Without it, ChatEvent uses ChatArch-owned state and copies a
    legacy ``~/.chatevent/events.db`` into the new location once, without
    deleting or overwriting the legacy file.
    """

    configured = os.environ.get("CHATEVENT_DB")
    if configured:
        return Path(configured).expanduser()
    paths = state_paths(create=True)
    migrate_legacy_database(paths)
    return paths.database


def migrate_legacy_database(paths: ChatEventPaths | None = None) -> bool:
    """Copy a legacy ``~/.chatevent/events.db`` to ChatArch state if needed."""

    paths = paths or state_paths(create=True)
    if not paths.legacy_database.exists() or paths.database.exists():
        return False
    _ensure_private_dir(paths.database.parent)
    try:
        _sqlite_backup(paths.legacy_database, paths.database)
    except sqlite3.DatabaseError:
        shutil.copy2(paths.legacy_database, paths.database)
    _ensure_private_file(paths.database)
    return True


def load_admin_token() -> str | None:
    """Load the optional admin token without exposing its value."""

    configured = os.environ.get("CHATEVENT_ADMIN_TOKEN")
    if configured:
        return configured
    token_file = Path(
        os.environ.get("CHATEVENT_ADMIN_TOKEN_FILE") or state_paths(create=False).admin_token_file
    ).expanduser()
    if not token_file.exists():
        return None
    value = token_file.read_text(encoding="utf-8").strip()
    return value or None


def admin_token_source() -> str | None:
    if os.environ.get("CHATEVENT_ADMIN_TOKEN"):
        return "env"
    token_file = Path(
        os.environ.get("CHATEVENT_ADMIN_TOKEN_FILE") or state_paths(create=False).admin_token_file
    ).expanduser()
    if token_file.exists() and token_file.read_text(encoding="utf-8").strip():
        return "file"
    return None


def _sqlite_backup(source: Path, destination: Path) -> None:
    source_connection = sqlite3.connect(source)
    try:
        destination_connection = sqlite3.connect(destination)
        try:
            source_connection.backup(destination_connection)
        finally:
            destination_connection.close()
    finally:
        source_connection.close()


def _ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        path.chmod(0o700)


def _ensure_private_file(path: Path) -> None:
    if os.name == "posix" and path.exists():
        path.chmod(0o600)


def set_private_file_mode(path: Path) -> None:
    """Best-effort POSIX file permission tightening for runtime state files."""

    _ensure_private_file(path)
    for suffix in ("-wal", "-shm"):
        sibling = Path(str(path) + suffix)
        if sibling.exists():
            if os.name == "posix":
                mode = stat.S_IMODE(sibling.stat().st_mode)
                if mode & 0o077:
                    sibling.chmod(0o600)
