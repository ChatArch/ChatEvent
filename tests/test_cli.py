import contextlib
import io
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from chatevent.capture import _form_value, load_env_file
from chatevent.cli import main
from chatevent.store import EventStore


class CliTests(unittest.TestCase):
    def test_tree_lists_observatory_capture_and_schema_commands(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            main(["--tree"])

        tree = stdout.getvalue()
        self.assertIn("chatevent", tree)
        self.assertIn("serve", tree)
        self.assertIn("schema event", tree)
        self.assertIn("record-json", tree)
        self.assertIn("platforms", tree)
        self.assertIn("capture zulip-once", tree)

    def test_platforms_outputs_action_catalog(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            main(["platforms", "--json"])

        result = json.loads(stdout.getvalue())
        self.assertEqual(result["count"], 4)
        github = next(item for item in result["items"] if item["id"] == "github")
        self.assertIn("repo:ChatArch/ChatEvent", github["scope_examples"])
        self.assertIn("commit.pushed", {action["kind"] for action in github["actions"]})

    def test_schema_event_outputs_json_schema(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            main(["schema", "event"])

        schema = json.loads(stdout.getvalue())
        self.assertIn("raw_payload", schema["properties"])
        self.assertEqual(schema["properties"]["schema_version"]["default"], "1.0")

    def test_record_json_writes_event_to_store(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            event_path = root / "event.json"
            db_path = root / "events.db"
            event_path.write_text(
                json.dumps(
                    {
                        "id": "issue-42",
                        "source": "gitea",
                        "kind": "issue.opened",
                        "occurred_at": datetime(2026, 8, 18, tzinfo=timezone.utc).isoformat(),
                        "capture_mode": "push",
                        "payload": {"title": "CLI record"},
                    }
                ),
                encoding="utf-8",
            )
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                main(["record-json", str(event_path), "--db", str(db_path)])

            result = json.loads(stdout.getvalue())
            self.assertTrue(result["created"])
            self.assertEqual(result["dedupe_key"], "gitea:issue-42")
            self.assertEqual(EventStore(db_path).stats()["event_count"], 1)


    def test_zulip_form_encoding_uses_json_booleans(self) -> None:
        self.assertEqual(_form_value(False), "false")
        self.assertEqual(_form_value(True), "true")
        self.assertEqual(_form_value(["message"]), '["message"]')
        self.assertEqual(_form_value("stream"), "stream")

    def test_load_env_file_preserves_space_containing_values(self) -> None:
        with TemporaryDirectory() as directory:
            env_file = Path(directory) / "zulip.env"
            env_file.write_text(
                "ZULIP_BASE_URL=https://zulip.public.lookeng.cn\n"
                "ZULIP_ACTOR_EMAIL=actor@example.invalid\n"
                "ZULIP_ACTOR_FULL_NAME=ChatRSS Actor\n"
                "ZULIP_ACTOR_API_KEY=secret-value\n",
                encoding="utf-8",
            )

            values = load_env_file(env_file)

            self.assertEqual(values["ZULIP_BASE_URL"], "https://zulip.public.lookeng.cn")
            self.assertEqual(values["ZULIP_ACTOR_FULL_NAME"], "ChatRSS Actor")
            self.assertEqual(values["ZULIP_ACTOR_API_KEY"], "secret-value")


if __name__ == "__main__":
    unittest.main()
