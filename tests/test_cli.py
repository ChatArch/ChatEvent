import contextlib
import io
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from chatevent.capture import _form_value, load_env_file
from chatevent.cli import main
from chatevent.store import EventStore


class FakeHttpResponse:
    def __init__(self, payload: object, status: int = 200) -> None:
        self.payload = payload
        self.status = status

    def __enter__(self) -> "FakeHttpResponse":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class CliTests(unittest.TestCase):
    def test_tree_lists_observatory_capture_and_schema_commands(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            main(["--tree"])

        tree = stdout.getvalue()
        self.assertIn("chatevent", tree)
        self.assertIn("--version", tree)
        self.assertIn("paths [--json]", tree)
        self.assertIn("serve", tree)
        self.assertIn("schema event", tree)
        self.assertIn("record-json", tree)
        self.assertIn("platforms", tree)
        self.assertIn("capture zulip-once", tree)
        self.assertIn("api events [filters]", tree)
        self.assertIn("api event DEDUPE_KEY", tree)
        self.assertIn("api save-subscription FILE", tree)
        self.assertIn("api delete-subscription ID", tree)
        self.assertIn("api session", tree)
        self.assertIn("api create-user USERNAME", tree)
        self.assertIn("api create-token [USER_ID]", tree)

    def test_version_outputs_package_version(self) -> None:
        stdout = io.StringIO()
        with self.assertRaises(SystemExit) as captured, contextlib.redirect_stdout(stdout):
            main(["--version"])

        self.assertEqual(captured.exception.code, 0)
        self.assertIn("chatevent 0.1.5", stdout.getvalue())

    def test_api_events_cli_queries_rest_endpoint_with_filters(self) -> None:
        requests = []

        def fake_urlopen(request, timeout: float = 0):  # type: ignore[no-untyped-def]
            requests.append((request, timeout))
            return FakeHttpResponse(
                {"items": [], "count": 0, "latest_captured_at": None, "next_since": None}
            )

        stdout = io.StringIO()
        with patch("urllib.request.urlopen", fake_urlopen), contextlib.redirect_stdout(stdout):
            main(
                [
                    "api",
                    "events",
                    "--base-url",
                    "https://event.example.test/root",
                    "--source",
                    "discourse",
                    "--kind",
                    "reply.created",
                    "--subscription-id",
                    "discourse-practice",
                    "--days",
                    "7",
                    "--limit",
                    "20",
                ]
            )

        result = json.loads(stdout.getvalue())
        self.assertEqual(result["count"], 0)
        request, timeout = requests[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(timeout, 20.0)
        parsed = urlparse(request.full_url)
        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "event.example.test")
        self.assertEqual(parsed.path, "/root/api/events")
        params = parse_qs(parsed.query)
        self.assertEqual(params["source"], ["discourse"])
        self.assertEqual(params["kind"], ["reply.created"])
        self.assertEqual(params["subscription_id"], ["discourse-practice"])
        self.assertEqual(params["days"], ["7"])
        self.assertEqual(params["limit"], ["20"])

    def test_api_event_cli_reads_one_rest_event(self) -> None:
        requests = []

        def fake_urlopen(request, timeout: float = 0):  # type: ignore[no-untyped-def]
            requests.append(request)
            return FakeHttpResponse(
                {
                    "event": {
                        "source": "github",
                        "id": "commit:ChatArch/ChatEvent:abc123",
                        "kind": "commit.pushed",
                    },
                    "seen_count": 1,
                }
            )

        stdout = io.StringIO()
        with patch("urllib.request.urlopen", fake_urlopen), contextlib.redirect_stdout(stdout):
            main(
                [
                    "api",
                    "event",
                    "github:commit:ChatArch/ChatEvent:abc123",
                    "--base-url",
                    "https://event.example.test",
                ]
            )

        result = json.loads(stdout.getvalue())
        self.assertEqual(result["event"]["kind"], "commit.pushed")
        request = requests[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(
            urlparse(request.full_url).path,
            "/api/events/github%3Acommit%3AChatArch%2FChatEvent%3Aabc123",
        )

    def test_api_delete_subscription_cli_sends_admin_token(self) -> None:
        requests = []

        def fake_urlopen(request, timeout: float = 0):  # type: ignore[no-untyped-def]
            requests.append(request)
            return FakeHttpResponse({"deleted": True, "id": "discourse-practice"})

        stdout = io.StringIO()
        with patch("urllib.request.urlopen", fake_urlopen), contextlib.redirect_stdout(stdout):
            main(
                [
                    "api",
                    "delete-subscription",
                    "discourse-practice",
                    "--base-url",
                    "https://event.example.test",
                    "--admin-token",
                    "secret-token",
                ]
            )

        result = json.loads(stdout.getvalue())
        self.assertTrue(result["deleted"])
        request = requests[0]
        self.assertEqual(request.get_method(), "DELETE")
        self.assertEqual(request.headers["X-chatevent-admin-token"], "secret-token")
        self.assertEqual(urlparse(request.full_url).path, "/api/subscriptions/discourse-practice")

    def test_api_create_user_cli_sends_initial_password(self) -> None:
        requests = []

        def fake_urlopen(request, timeout: float = 0):  # type: ignore[no-untyped-def]
            requests.append(request)
            return FakeHttpResponse(
                {"user": {"id": "u1", "username": "rexwzh@lookeng.cn", "role": "member", "enabled": True}}
            )

        with TemporaryDirectory() as directory:
            password_file = Path(directory) / "password.txt"
            password_file.write_text("initial-password\n", encoding="utf-8")
            stdout = io.StringIO()
            with patch("urllib.request.urlopen", fake_urlopen), contextlib.redirect_stdout(stdout):
                main(
                    [
                        "api",
                        "create-user",
                        "rexwzh@lookeng.cn",
                        "--new-password-file",
                        str(password_file),
                        "--display-name",
                        "Rex",
                        "--role",
                        "member",
                        "--base-url",
                        "https://event.example.test",
                        "--admin-token",
                        "arch_admin",
                    ]
                )

        result = json.loads(stdout.getvalue())
        self.assertNotIn("token", result)
        request = requests[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.headers["X-chatevent-admin-token"], "arch_admin")
        self.assertEqual(urlparse(request.full_url).path, "/api/users")
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["username"], "rexwzh@lookeng.cn")
        self.assertEqual(body["password"], "initial-password")
        self.assertEqual(body["display_name"], "Rex")

    def test_api_create_token_cli_prints_one_time_token(self) -> None:
        requests = []

        def fake_urlopen(request, timeout: float = 0):  # type: ignore[no-untyped-def]
            requests.append(request)
            return FakeHttpResponse(
                {"user": {"id": "u1", "username": "rexwzh@lookeng.cn", "role": "member", "enabled": True}, "token": "arch_generated"}
            )

        stdout = io.StringIO()
        with patch("urllib.request.urlopen", fake_urlopen), contextlib.redirect_stdout(stdout):
            main(
                [
                    "api",
                    "create-token",
                    "--base-url",
                    "https://event.example.test",
                    "--admin-token",
                    "arch_admin",
                ]
            )

        result = json.loads(stdout.getvalue())
        self.assertEqual(result["token"], "arch_generated")
        request = requests[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.headers["X-chatevent-admin-token"], "arch_admin")
        self.assertEqual(urlparse(request.full_url).path, "/api/me/token")

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
