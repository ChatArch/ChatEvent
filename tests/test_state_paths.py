import contextlib
import io
import json
import os
import stat
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from chatevent.cli import main
from chatevent.model import ChatEvent
from chatevent.server import create_app, default_database_path
from chatevent.state import load_admin_token, state_paths
from chatevent.store import EventStore
from fastapi.testclient import TestClient


class StatePathTests(unittest.TestCase):
    def test_default_database_path_lives_under_chatarch_home(self) -> None:
        with TemporaryDirectory() as directory:
            chatarch_home = Path(directory) / "chatarch-home"
            with patch.dict(
                os.environ,
                {"CHATARCH_HOME": str(chatarch_home)},
                clear=False,
            ):
                os.environ.pop("CHATEVENT_DB", None)
                paths = state_paths()
                db_path = default_database_path()

            self.assertEqual(paths.chatarch_home, chatarch_home)
            self.assertEqual(paths.state_dir, chatarch_home / "chatevent")
            self.assertEqual(paths.database, chatarch_home / "chatevent" / "events.db")
            self.assertEqual(db_path, chatarch_home / "chatevent" / "events.db")
            self.assertTrue(paths.state_dir.exists())
            if os.name == "posix":
                mode = stat.S_IMODE(paths.state_dir.stat().st_mode)
                self.assertEqual(mode, 0o700)

    def test_default_database_path_migrates_legacy_chatevent_database(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory) / "home"
            old_db = home / ".chatevent" / "events.db"
            event = ChatEvent(
                id="legacy-1",
                source="gitea",
                kind="issue.opened",
                occurred_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
                capture_mode="webhook",
                payload={"title": "legacy row"},
            )
            EventStore(old_db).record_event(event)

            with patch.dict(os.environ, {"HOME": str(home)}, clear=False):
                os.environ.pop("CHATARCH_HOME", None)
                os.environ.pop("CHATEVENT_DB", None)
                new_db = default_database_path()

            self.assertEqual(new_db, home / ".chatarch" / "chatevent" / "events.db")
            self.assertTrue(old_db.exists())
            self.assertEqual(EventStore(new_db).stats()["event_count"], 1)
            if os.name == "posix":
                mode = stat.S_IMODE(new_db.stat().st_mode)
                self.assertEqual(mode, 0o600)

    def test_admin_token_loads_from_chatarch_internal_file(self) -> None:
        with TemporaryDirectory() as directory:
            chatarch_home = Path(directory) / "chatarch-home"
            with patch.dict(
                os.environ,
                {"CHATARCH_HOME": str(chatarch_home)},
                clear=False,
            ):
                os.environ.pop("CHATEVENT_ADMIN_TOKEN", None)
                os.environ.pop("CHATEVENT_ADMIN_TOKEN_FILE", None)
                paths = state_paths(create=True)
                paths.admin_token_file.write_text("file-token\n", encoding="utf-8")

                self.assertEqual(load_admin_token(), "file-token")

                with patch.dict(os.environ, {"CHATEVENT_ADMIN_TOKEN": "env-token"}, clear=False):
                    self.assertEqual(load_admin_token(), "env-token")

    def test_server_uses_chatarch_admin_token_file(self) -> None:
        with TemporaryDirectory() as directory:
            chatarch_home = Path(directory) / "chatarch-home"
            with patch.dict(
                os.environ,
                {"CHATARCH_HOME": str(chatarch_home)},
                clear=False,
            ):
                os.environ.pop("CHATEVENT_ADMIN_TOKEN", None)
                os.environ.pop("CHATEVENT_ADMIN_TOKEN_FILE", None)
                paths = state_paths(create=True)
                paths.admin_token_file.write_text("file-token\n", encoding="utf-8")
                client = TestClient(create_app(db_path=Path(directory) / "events.db"))

                denied = client.post(
                    "/api/subscriptions",
                    json={
                        "id": "repo",
                        "source": "github",
                        "target": "repo:ChatArch/ChatEvent",
                        "capture_modes": ["webhook"],
                    },
                )
                allowed = client.post(
                    "/api/subscriptions",
                    headers={"X-ChatEvent-Admin-Token": "file-token"},
                    json={
                        "id": "repo",
                        "source": "github",
                        "target": "repo:ChatArch/ChatEvent",
                        "capture_modes": ["webhook"],
                    },
                )

            self.assertEqual(denied.status_code, 401)
            self.assertEqual(allowed.status_code, 201)

    def test_paths_cli_reports_chatarch_internal_paths_without_secret_values(self) -> None:
        with TemporaryDirectory() as directory:
            chatarch_home = Path(directory) / "chatarch-home"
            with patch.dict(
                os.environ,
                {"CHATARCH_HOME": str(chatarch_home)},
                clear=False,
            ):
                os.environ.pop("CHATEVENT_DB", None)
                os.environ.pop("CHATEVENT_ADMIN_TOKEN", None)
                os.environ.pop("CHATEVENT_ADMIN_TOKEN_FILE", None)
                paths = state_paths(create=True)
                paths.admin_token_file.write_text("secret-value\n", encoding="utf-8")
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    main(["paths", "--json"])

            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["chatarch_home"], str(chatarch_home))
            self.assertEqual(payload["database"], str(chatarch_home / "chatevent" / "events.db"))
            self.assertEqual(
                payload["admin_token_file"],
                str(chatarch_home / "chatevent" / "secrets" / "admin-token"),
            )
            self.assertTrue(payload["admin_token_configured"])
            self.assertNotIn("secret-value", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
