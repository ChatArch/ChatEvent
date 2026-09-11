import json
import http.client
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import urlparse

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 test dependency
    import tomli as tomllib

from chatlogin.ui import LoginUI
from fastapi.testclient import TestClient

from chatevent.server import create_app
from chatevent.store import EventStore


class ServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._admin_env = patch.dict(
            "os.environ",
            {"CHATEVENT_ADMIN_TOKEN_FILE": "/tmp/chatevent-test-admin-token-missing"},
        )
        self._admin_env.start()

    def tearDown(self) -> None:
        self._admin_env.stop()

    def test_observatory_flow(self) -> None:
        with TemporaryDirectory() as directory:
            client = TestClient(create_app(db_path=Path(directory) / "events.db"))

            dashboard = client.get("/")
            self.assertEqual(dashboard.status_code, 200)
            self.assertIn("ChatEvent Observatory", dashboard.text)
            self.assertIn('role="tablist"', dashboard.text)
            self.assertIn('data-tab-target="eventsPanel"', dashboard.text)
            self.assertIn('data-tab-target="subscriptionsPanel"', dashboard.text)
            self.assertIn('data-tab-target="platformsPanel"', dashboard.text)
            self.assertIn('id="sourceFilter"', dashboard.text)
            self.assertIn('id="timeFilter"', dashboard.text)
            self.assertIn('id="advancedFiltersToggle"', dashboard.text)
            self.assertIn('id="advancedFilters"', dashboard.text)
            self.assertIn('id="kindCheckboxes"', dashboard.text)
            self.assertIn('id="subscriptionCheckboxes"', dashboard.text)
            self.assertIn("selectedKinds", dashboard.text)
            self.assertIn("renderAdvancedFilters", dashboard.text)
            self.assertNotIn('id="kindFilter"', dashboard.text)
            self.assertNotIn("全部事件类型", dashboard.text)
            self.assertIn("editSubscription", dashboard.text)
            self.assertIn("deleteSubscription", dashboard.text)
            self.assertIn("adminToken", dashboard.text)
            self.assertIn('id="sessionStatus"', dashboard.text)
            self.assertIn("账号 / API Token", dashboard.text)
            self.assertIn('id="adminTokenDialog"', dashboard.text)
            self.assertIn('id="generatedAdminToken"', dashboard.text)
            self.assertIn('id="generateAdminToken"', dashboard.text)
            self.assertIn('id="copyAdminToken"', dashboard.text)
            self.assertIn("arch_", dashboard.text)
            self.assertIn("复制 Token", dashboard.text)
            self.assertIn("它不是主页登录凭据", dashboard.text)
            self.assertIn('id="userAdminPanel"', dashboard.text)
            self.assertIn('id="newUserName"', dashboard.text)
            self.assertIn('id="newUserPassword"', dashboard.text)
            self.assertIn('id="createUser"', dashboard.text)
            self.assertIn('id="userList"', dashboard.text)
            self.assertIn("API Token 用于 CLI", dashboard.text)
            self.assertIn('sessionStorage.getItem("chateventApiToken")', dashboard.text)
            self.assertIn('X-ChatEvent-Admin-Token', dashboard.text)
            self.assertIn("subscriptionScopeType", dashboard.text)
            self.assertIn("Action target", dashboard.text)
            self.assertIn("Actor role", dashboard.text)
            self.assertIn("targetChain", dashboard.text)
            self.assertIn("actionTargetLabel", dashboard.text)
            self.assertIn('id="githubLink"', dashboard.text)
            self.assertIn('href="https://github.com/ChatArch/ChatEvent"', dashboard.text)
            self.assertIn('id="docsLink"', dashboard.text)
            self.assertIn('href="https://arch.gh.wzhecnu.cn/ChatEvent/"', dashboard.text)
            self.assertIn('id="themeToggle"', dashboard.text)
            self.assertIn("☾ 夜间", dashboard.text)
            self.assertIn("☀ 日间", dashboard.text)
            self.assertNotIn("黑底", dashboard.text)
            self.assertNotIn("白底", dashboard.text)
            self.assertIn("data-theme", dashboard.text)
            self.assertIn("platformActionDialog", dashboard.text)
            self.assertIn("openPlatformAction", dashboard.text)
            self.assertIn("API 大致含义", dashboard.text)

            subscription = client.post(
                "/api/subscriptions",
                json={
                    "id": "core-repo",
                    "label": "Core repository",
                    "source": "gitea",
                    "target": "owner/repo",
                    "event_kinds": ["issue.opened"],
                    "capture_modes": ["webhook", "api_cursor"],
                    "filters": {"repository": "owner/repo"},
                    "labels": ["practice", "repo:owner/repo"],
                },
            )
            self.assertEqual(subscription.status_code, 201)
            self.assertEqual(subscription.json()["scope"]["type"], "repo")
            self.assertEqual(subscription.json()["scope"]["key"], "owner/repo")
            self.assertEqual(subscription.json()["actions"][0]["kind"], "issue.opened")

            event = {
                "id": "issue-42",
                "source": "gitea",
                "kind": "issue.opened",
                "occurred_at": datetime(2026, 8, 18, tzinfo=timezone.utc).isoformat(),
                "capture_mode": "webhook",
                "subscription_id": "core-repo",
                "action": {"kind": "issue.opened", "object_type": "issue", "verb": "opened"},
                "target": {
                    "type": "issue",
                    "key": "owner/repo#42",
                    "parent": {"type": "repo", "key": "owner/repo"},
                },
                "payload": {"title": "Investigate event routing"},
                "raw_payload": {"action": "opened", "issue": {"number": 42}},
            }
            first = client.post("/api/events", json=event)
            second = client.post("/api/events", json=event)

            self.assertEqual(first.status_code, 202)
            self.assertTrue(first.json()["created"])
            self.assertFalse(second.json()["created"])
            self.assertEqual(second.json()["seen_count"], 2)

            events = client.get("/api/events", params={"source": "gitea"}).json()
            self.assertEqual(events["count"], 1)
            self.assertEqual(
                events["items"][0]["event"]["raw_payload"]["action"], "opened"
            )
            self.assertEqual(events["items"][0]["event"]["action"]["verb"], "opened")
            self.assertEqual(events["items"][0]["event"]["target"]["parent"]["key"], "owner/repo")

            detail = client.get("/api/events/gitea:issue-42")
            self.assertEqual(detail.status_code, 200)
            self.assertEqual(detail.json()["seen_count"], 2)

            stats = client.get("/api/stats").json()
            self.assertEqual(stats["event_count"], 1)
            self.assertEqual(stats["subscription_count"], 1)
            self.assertEqual(stats["duplicate_count"], 1)

            event_schema = client.get("/api/schema/event").json()
            self.assertIn("raw_payload", event_schema["properties"])

            platforms = client.get("/api/platforms")
            self.assertEqual(platforms.status_code, 200)
            platform_ids = [item["id"] for item in platforms.json()["items"]]
            self.assertEqual(platform_ids, ["discourse", "gitea", "github", "voice", "x", "zulip"])
            voice = next(item for item in platforms.json()["items"] if item["id"] == "voice")
            self.assertEqual(
                [action["kind"] for action in voice["actions"]],
                ["talk.created", "talk.updated"],
            )

            voice_subscription = client.post(
                "/api/subscriptions",
                json={
                    "id": "voice-default",
                    "label": "Default ChatVoice talks",
                    "source": "voice",
                    "target": "account:default",
                    "event_kinds": ["talk.created", "talk.updated"],
                    "capture_modes": ["manual_backfill", "poll", "api_cursor"],
                },
            )
            self.assertEqual(voice_subscription.status_code, 201)
            self.assertEqual(voice_subscription.json()["scope"]["type"], "voice_account")
            self.assertEqual(
                [action["kind"] for action in voice_subscription.json()["actions"]],
                ["talk.created", "talk.updated"],
            )
            subscriptions = client.get("/api/subscriptions").json()
            voice_items = [item for item in subscriptions if item["source"] == "voice"]
            self.assertEqual(len(voice_items), 1)
            self.assertEqual(voice_items[0]["id"], "voice-default")
            self.assertEqual(
                [action["kind"] for action in voice_items[0]["actions"]],
                ["talk.created", "talk.updated"],
            )

    def test_subscription_mutations_can_require_admin_token(self) -> None:
        with TemporaryDirectory() as directory, patch.dict(
            "os.environ", {"CHATEVENT_ADMIN_TOKEN": "secret-token"}
        ):
            client = TestClient(create_app(db_path=Path(directory) / "events.db"))
            body = {
                "id": "discourse-practice",
                "source": "discourse",
                "target": "category:agent-runs",
                "event_kinds": ["post.created", "reply.created"],
                "capture_modes": ["webhook", "api_cursor"],
            }

            no_token = client.post("/api/subscriptions", json=body)
            wrong_token = client.post(
                "/api/subscriptions",
                headers={"X-ChatEvent-Admin-Token": "wrong"},
                json=body,
            )
            ok = client.post(
                "/api/subscriptions",
                headers={"X-ChatEvent-Admin-Token": "secret-token"},
                json=body,
            )
            delete_without_token = client.delete("/api/subscriptions/discourse-practice")
            delete_ok = client.delete(
                "/api/subscriptions/discourse-practice",
                headers={"X-ChatEvent-Admin-Token": "secret-token"},
            )

            self.assertEqual(no_token.status_code, 401)
            self.assertEqual(wrong_token.status_code, 401)
            self.assertEqual(ok.status_code, 201)
            self.assertEqual(delete_without_token.status_code, 401)
            self.assertEqual(delete_ok.status_code, 200)
            self.assertTrue(delete_ok.json()["deleted"])
            self.assertEqual(
                client.get("/api/subscriptions/discourse-practice").status_code, 401
            )

    def test_login_page_gates_observatory_and_read_apis(self) -> None:
        with TemporaryDirectory() as directory, patch.dict(
            "os.environ",
            {
                "CHATEVENT_BOOTSTRAP_USERNAME": "rexwzh@lookeng.cn",
                "CHATEVENT_BOOTSTRAP_PASSWORD": "test-password",
            },
        ):
            client = TestClient(create_app(db_path=Path(directory) / "events.db"))

            login_page = client.get("/")
            self.assertEqual(login_page.status_code, 200)
            self.assertIn("<h1>ChatEvent</h1>", login_page.text)
            self.assertIn("chatlogin", login_page.text)
            self.assertIn('name="username"', login_page.text)
            self.assertIn('name="password"', login_page.text)
            self.assertIn("/login/assets/login.js", login_page.text)
            self.assertNotIn('id="tokenInput"', login_page.text)
            self.assertNotIn('role="tablist"', login_page.text)
            self.assertEqual(client.get("/api/stats").status_code, 401)
            self.assertEqual(client.get("/api/events").status_code, 401)

            bad_login = client.post(
                "/api/login",
                json={"username": "rexwzh@lookeng.cn", "password": "wrong"},
            )
            self.assertEqual(bad_login.status_code, 401)

            good_login = client.post(
                "/api/login",
                json={"username": "rexwzh@lookeng.cn", "password": "test-password"},
            )
            self.assertEqual(good_login.status_code, 200)
            self.assertTrue(good_login.json()["authenticated"])
            self.assertEqual(good_login.json()["user"]["username"], "rexwzh@lookeng.cn")
            self.assertIn("chatevent_session", good_login.headers["set-cookie"])

            dashboard = client.get("/")
            self.assertEqual(dashboard.status_code, 200)
            self.assertIn('role="tablist"', dashboard.text)
            self.assertIn("ChatEvent Observatory", dashboard.text)
            self.assertEqual(client.get("/api/stats").status_code, 200)
            self.assertEqual(client.get("/api/platforms").status_code, 200)

            logout = client.post("/api/logout")
            self.assertEqual(logout.status_code, 403)
            logout = client.post(
                "/api/logout", headers={"X-CSRF-Token": good_login.json()["csrf_token"]}
            )
            self.assertEqual(logout.status_code, 200)
            self.assertFalse(logout.json()["authenticated"])
            self.assertIn("chatlogin", client.get("/").text)

    def test_webhook_endpoints_normalize_platform_payloads(self) -> None:
        with TemporaryDirectory() as directory:
            client = TestClient(create_app(db_path=Path(directory) / "events.db"))

            zulip = client.post(
                "/webhooks/zulip",
                json={
                    "id": 101,
                    "type": "message",
                    "message": {
                        "id": 24,
                        "timestamp": 1787047000,
                        "sender_id": 7,
                        "stream_id": 3,
                        "display_recipient": "chatevent-practice",
                        "topic": "zulip-event-queue",
                        "content": "hello from Zulip",
                    },
                },
            )
            discourse = client.post(
                "/webhooks/discourse",
                json={
                    "event_name": "post_created",
                    "post": {
                        "id": 25,
                        "topic_id": 18,
                        "post_number": 2,
                        "username": "RexWang",
                        "created_at": "2026-08-05T02:59:00Z",
                        "raw": "hello from Discourse",
                    },
                },
            )
            discourse_header_event = client.post(
                "/webhooks/discourse",
                headers={"X-Discourse-Event": "post_created"},
                json={
                    "post": {
                        "id": 26,
                        "topic_id": 18,
                        "post_number": 2,
                        "username": "RexWang",
                        "created_at": "2026-08-05T03:00:00Z",
                        "raw": "official header reply from Discourse",
                    },
                },
            )
            gitea = client.post(
                "/webhooks/gitea",
                json={
                    "action": "opened",
                    "repository": {"full_name": "ChatEvent/practice"},
                    "issue": {
                        "id": 9001,
                        "number": 42,
                        "title": "ChatEvent practice issue",
                        "created_at": "2026-08-18T09:00:00Z",
                    },
                },
            )
            github = client.post(
                "/webhooks/github",
                headers={"X-GitHub-Event": "push"},
                json={
                    "ref": "refs/heads/main",
                    "after": "abc123456789",
                    "head_commit": {
                        "id": "abc123456789",
                        "message": "feat: record ChatEvent demo loop",
                        "timestamp": "2026-08-18T10:30:00Z",
                    },
                    "repository": {"full_name": "ChatArch/ChatEvent"},
                    "sender": {"login": "RexWang"},
                },
            )
            ping = client.post(
                "/webhooks/github",
                headers={"X-GitHub-Event": "ping"},
                json={
                    "zen": "Responsive is better than fast.",
                    "hook_id": 123,
                    "repository": {"full_name": "ChatArch/ChatEvent"},
                },
            )

            self.assertEqual(zulip.status_code, 202)
            self.assertEqual(discourse.status_code, 202)
            self.assertEqual(discourse_header_event.status_code, 202)
            self.assertEqual(gitea.status_code, 202)
            self.assertEqual(github.status_code, 202)
            self.assertEqual(ping.status_code, 202)
            self.assertFalse(ping.json()["created"])
            discourse_events = client.get("/api/events", params={"source": "discourse"}).json()
            discourse_kinds = {item["event"]["id"]: item["event"]["kind"] for item in discourse_events["items"]}
            self.assertEqual(discourse_kinds["post:26"], "reply.created")
            stats = client.get("/api/stats").json()
            self.assertEqual(stats["event_count"], 5)
            self.assertEqual(
                stats["sources"],
                {"discourse": 2, "gitea": 1, "github": 1, "zulip": 1},
            )

    def test_api_events_since_returns_captured_after_checkpoint(self) -> None:
        with TemporaryDirectory() as directory:
            client = TestClient(create_app(db_path=Path(directory) / "events.db"))

            old_event = {
                "id": "post-1",
                "source": "discourse",
                "kind": "post.created",
                "occurred_at": "2026-08-18T10:00:00+00:00",
                "captured_at": "2026-08-18T10:00:01+00:00",
                "capture_mode": "webhook",
                "subscription_id": "discourse-practice",
                "payload": {"title": "old topic"},
            }
            new_event = {
                "id": "post-2",
                "source": "discourse",
                "kind": "reply.created",
                "occurred_at": "2026-08-18T10:00:04+00:00",
                "captured_at": "2026-08-18T10:00:05+00:00",
                "capture_mode": "webhook",
                "subscription_id": "discourse-practice",
                "payload": {"title": "new reply"},
            }
            client.post("/api/events", json=old_event)
            client.post("/api/events", json=new_event)

            response = client.get(
                "/api/events",
                params={
                    "source": "discourse",
                    "subscription_id": "discourse-practice",
                    "since": "2026-08-18T10:00:02+00:00",
                },
            )

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["count"], 1)
            self.assertEqual(payload["next_since"], "2026-08-18T10:00:05Z")
            self.assertEqual(payload["items"][0]["event"]["id"], "post-2")
            self.assertEqual(payload["items"][0]["event"]["kind"], "reply.created")

    def test_api_events_days_filters_recent_captures(self) -> None:
        with TemporaryDirectory() as directory:
            client = TestClient(create_app(db_path=Path(directory) / "events.db"))

            client.post(
                "/api/events",
                json={
                    "id": "old-post",
                    "source": "discourse",
                    "kind": "post.created",
                    "occurred_at": "2000-01-01T00:00:00+00:00",
                    "captured_at": "2000-01-01T00:00:00+00:00",
                    "capture_mode": "webhook",
                    "payload": {"title": "old"},
                },
            )
            client.post(
                "/api/events",
                json={
                    "id": "recent-post",
                    "source": "discourse",
                    "kind": "reply.created",
                    "occurred_at": datetime.now(timezone.utc).isoformat(),
                    "captured_at": datetime.now(timezone.utc).isoformat(),
                    "capture_mode": "webhook",
                    "payload": {"title": "recent"},
                },
            )

            response = client.get("/api/events", params={"days": "1"})

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["count"], 1)
            self.assertEqual(payload["items"][0]["event"]["id"], "recent-post")

    def test_api_events_from_to_filter_captured_range(self) -> None:
        with TemporaryDirectory() as directory:
            client = TestClient(create_app(db_path=Path(directory) / "events.db"))

            for event_id, captured_at in [
                ("before", "2026-08-15T23:59:59+00:00"),
                ("inside", "2026-08-16T12:00:00+00:00"),
                ("after", "2026-08-18T00:00:01+00:00"),
            ]:
                client.post(
                    "/api/events",
                    json={
                        "id": event_id,
                        "source": "gitea",
                        "kind": "issue.opened",
                        "occurred_at": captured_at,
                        "captured_at": captured_at,
                        "capture_mode": "webhook",
                        "payload": {"title": event_id},
                    },
                )

            response = client.get(
                "/api/events",
                params={
                    "from": "2026-08-16T00:00:00+00:00",
                    "to": "2026-08-18T00:00:00+00:00",
                },
            )

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["count"], 1)
            self.assertEqual(payload["items"][0]["event"]["id"], "inside")

    def test_webhook_subscription_id_updates_subscription_cursor(self) -> None:
        with TemporaryDirectory() as directory:
            client = TestClient(create_app(db_path=Path(directory) / "events.db"))
            client.post(
                "/api/subscriptions",
                json={
                    "id": "zulip-practice",
                    "source": "zulip",
                    "target": "stream:chatevent-practice/topic:real-loop",
                    "capture_modes": ["push"],
                },
            )

            response = client.post(
                "/webhooks/zulip?subscription_id=zulip-practice",
                json={
                    "id": 101,
                    "type": "message",
                    "message": {
                        "id": 24,
                        "timestamp": 1787047000,
                        "sender_id": 7,
                        "stream_id": 3,
                        "display_recipient": "chatevent-practice",
                        "topic": "real-loop",
                        "content": "hello from Zulip",
                    },
                },
            )
            self.assertEqual(response.status_code, 202)

            subscriptions = client.get("/api/subscriptions").json()
            self.assertEqual(len(subscriptions), 1)
            item = subscriptions[0]
            self.assertEqual(item["id"], "zulip-practice")
            self.assertEqual(item["last_cursor"], "101")
            self.assertIsNotNone(item["last_event_at"])

    def test_password_login_api_token_and_subscription_isolation(self) -> None:
        with TemporaryDirectory() as directory, patch.dict(
            "os.environ", {"CHATEVENT_ADMIN_TOKEN": "arch_bootstrap_test"}
        ):
            client = TestClient(create_app(db_path=Path(directory) / "events.db"))

            anonymous = client.get("/api/session").json()
            self.assertTrue(anonymous["admin_required"])
            self.assertFalse(anonymous["authenticated"])

            bootstrap = client.get(
                "/api/session", headers={"X-ChatEvent-Admin-Token": "arch_bootstrap_test"}
            ).json()
            self.assertTrue(bootstrap["authenticated"])
            self.assertEqual(bootstrap["user"]["role"], "admin")
            self.assertTrue(bootstrap["legacy_admin"])

            created = client.post(
                "/api/users",
                headers={"X-ChatEvent-Admin-Token": "arch_bootstrap_test"},
                json={
                    "username": "rexwzh@lookeng.cn",
                    "password": "member-password",
                    "display_name": "Rex",
                    "role": "member",
                },
            )
            self.assertEqual(created.status_code, 201)
            self.assertNotIn("token", created.json())
            self.assertNotIn("password", created.text)
            self.assertNotIn("token_hash", created.text)
            member = created.json()["user"]

            bad_login = client.post(
                "/api/login",
                json={"username": "rexwzh@lookeng.cn", "password": "wrong"},
            )
            self.assertEqual(bad_login.status_code, 401)

            good_login = client.post(
                "/api/login",
                json={"username": "rexwzh@lookeng.cn", "password": "member-password"},
            )
            self.assertEqual(good_login.status_code, 200)
            self.assertTrue(good_login.json()["authenticated"])
            self.assertEqual(good_login.json()["user"]["username"], "rexwzh@lookeng.cn")
            csrf = good_login.json()["csrf_token"]

            web_subscription = client.post(
                "/api/subscriptions",
                headers={"X-CSRF-Token": csrf},
                json={
                    "id": "member-discourse",
                    "source": "discourse",
                    "target": "topic:23",
                    "event_kinds": ["reply.created"],
                    "capture_modes": ["webhook"],
                },
            )
            self.assertEqual(web_subscription.status_code, 201)
            self.assertEqual(web_subscription.json()["owner_user_id"], member["id"])

            issued = client.post("/api/me/token", headers={"X-CSRF-Token": csrf})
            self.assertEqual(issued.status_code, 200)
            member_token = issued.json()["token"]
            self.assertTrue(member_token.startswith("arch_"))
            self.assertNotIn("token_hash", issued.text)

            logout = client.post("/api/logout", headers={"X-CSRF-Token": csrf})
            self.assertEqual(logout.status_code, 200)
            anonymous_subscriptions = client.get("/api/subscriptions")
            self.assertEqual(anonymous_subscriptions.status_code, 401)
            self.assertEqual(
                client.get(
                    "/api/subscriptions",
                    headers={"X-ChatEvent-Admin-Token": "arch_wrong"},
                ).status_code,
                401,
            )

            member_session = client.get(
                "/api/session", headers={"X-ChatEvent-Admin-Token": member_token}
            ).json()
            self.assertTrue(member_session["authenticated"])
            self.assertEqual(member_session["user"]["username"], "rexwzh@lookeng.cn")
            self.assertEqual(
                len(
                    client.get(
                        "/api/subscriptions",
                        headers={"X-ChatEvent-Admin-Token": member_token},
                    ).json()
                ),
                1,
            )
            self.assertEqual(
                len(
                    client.get(
                        "/api/subscriptions",
                        headers={"X-ChatEvent-Admin-Token": "arch_bootstrap_test"},
                    ).json()
                ),
                1,
            )

    def test_password_hash_uses_chatlogin_pbkdf2_compatibility(self) -> None:
        from chatevent.auth import password_digest, verify_password

        digest = password_digest("member-password")

        self.assertRegex(digest, r"^pbkdf2_sha256\$[0-9]+\$[0-9a-f]+\$[0-9a-f]+$")
        self.assertTrue(verify_password("member-password", digest))
        self.assertFalse(verify_password("wrong", digest))
        self.assertTrue(
            verify_password(
                "legacy-password",
                "pbkdf2_sha256$260000$00112233445566778899aabbccddeeff$"
                "37d91c594aee7e04fd769c377f76c1f16c8f36230c5813be58f6af04d14fae25",
            )
        )

    def test_cookie_session_rechecks_role_and_enabled_state(self) -> None:
        with TemporaryDirectory() as directory, patch.dict(
            "os.environ", {"CHATEVENT_ADMIN_TOKEN": "bootstrap-token"}
        ):
            db_path = Path(directory) / "events.db"
            client = TestClient(create_app(db_path=db_path))
            created = client.post(
                "/api/users",
                headers={"X-ChatEvent-Admin-Token": "bootstrap-token"},
                json={"username": "member@example.test", "password": "pw", "role": "member"},
            ).json()["user"]
            login = client.post(
                "/api/login",
                json={"username": "member@example.test", "password": "pw"},
            )
            csrf = login.json()["csrf_token"]

            store = EventStore(db_path)
            user = store.get_user(created["id"], enabled_only=False)
            assert user is not None
            store.save_user(user.model_copy(update={"role": "admin"}))
            self.assertEqual(
                client.post(
                    "/api/users",
                    headers={"X-CSRF-Token": csrf},
                    json={"username": "new-admin-action@example.test", "password": "pw"},
                ).status_code,
                201,
            )

            user = store.get_user(created["id"], enabled_only=False)
            assert user is not None
            store.save_user(user.model_copy(update={"enabled": False}))
            self.assertEqual(client.get("/api/stats").status_code, 401)

    def test_cookie_writes_require_csrf_and_bogus_api_header_does_not_bypass(self) -> None:
        with TemporaryDirectory() as directory, patch.dict(
            "os.environ", {"CHATEVENT_ADMIN_TOKEN": "bootstrap-token"}
        ):
            client = TestClient(create_app(db_path=Path(directory) / "events.db"))
            client.post(
                "/api/users",
                headers={"X-ChatEvent-Admin-Token": "bootstrap-token"},
                json={"username": "admin@example.test", "password": "pw", "role": "admin"},
            )
            login = client.post(
                "/api/login",
                json={"username": "admin@example.test", "password": "pw"},
            )
            csrf = login.json()["csrf_token"]

            body = {
                "id": "csrf-sub",
                "source": "discourse",
                "target": "topic:csrf",
                "capture_modes": ["webhook"],
            }
            self.assertEqual(client.post("/api/subscriptions", json=body).status_code, 403)
            self.assertEqual(
                client.post(
                    "/api/subscriptions",
                    headers={"X-ChatEvent-Admin-Token": "bogus"},
                    json=body,
                ).status_code,
                403,
            )
            self.assertEqual(
                client.post(
                    "/api/subscriptions",
                    headers={"X-CSRF-Token": "wrong"},
                    json=body,
                ).status_code,
                403,
            )
            self.assertEqual(
                client.post(
                    "/api/subscriptions",
                    headers={"X-CSRF-Token": csrf},
                    json=body,
                ).status_code,
                201,
            )
            self.assertEqual(client.post("/api/logout").status_code, 403)
            self.assertEqual(
                client.post("/api/logout", headers={"X-CSRF-Token": csrf}).status_code,
                200,
            )

    def test_api_tokens_remain_csrf_exempt_and_separate_from_cookie_csrf(self) -> None:
        with TemporaryDirectory() as directory, patch.dict(
            "os.environ", {"CHATEVENT_ADMIN_TOKEN": "bootstrap-token"}
        ):
            client = TestClient(create_app(db_path=Path(directory) / "events.db"))
            created = client.post(
                "/api/users",
                headers={"X-ChatEvent-Admin-Token": "bootstrap-token"},
                json={"username": "member@example.test", "password": "pw", "role": "member"},
            ).json()["user"]
            token = client.post(
                f"/api/users/{created['id']}/token",
                headers={"X-ChatEvent-Admin-Token": "bootstrap-token"},
            ).json()["token"]

            response = client.post(
                "/api/subscriptions",
                headers={"X-ChatEvent-Admin-Token": token},
                json={
                    "id": "token-sub",
                    "source": "discourse",
                    "target": "topic:token",
                    "capture_modes": ["webhook"],
                },
            )

            self.assertEqual(response.status_code, 201)
            self.assertEqual(response.json()["owner_user_id"], created["id"])

    def test_session_rotation_logout_ttl_and_capacity(self) -> None:
        with TemporaryDirectory() as directory, patch.dict(
            "os.environ",
            {
                "CHATEVENT_BOOTSTRAP_USERNAME": "admin@example.test",
                "CHATEVENT_BOOTSTRAP_PASSWORD": "pw",
                "CHATEVENT_SESSION_TTL_SECONDS": "1",
                "CHATEVENT_MAX_SESSIONS": "1",
            },
        ):
            now = [1000.0]
            app = create_app(db_path=Path(directory) / "events.db", clock=lambda: now[0])
            first = TestClient(app)
            second = TestClient(app)

            first_login = first.post(
                "/api/login",
                json={"username": "admin@example.test", "password": "pw"},
            )
            self.assertEqual(first_login.status_code, 200)
            self.assertIn("csrf_token", first_login.json())
            rotated = first.post(
                "/api/login",
                headers={"X-CSRF-Token": first_login.json()["csrf_token"]},
                json={"username": "admin@example.test", "password": "pw"},
            )
            self.assertEqual(rotated.status_code, 200)
            self.assertNotEqual(first_login.cookies.get("chatevent_session"), rotated.cookies.get("chatevent_session"))
            self.assertEqual(
                first.post(
                    "/api/logout",
                    headers={"X-CSRF-Token": rotated.json()["csrf_token"]},
                ).status_code,
                200,
            )
            self.assertEqual(first.get("/api/stats").status_code, 401)

            capacity_holder = first.post(
                "/api/login",
                json={"username": "admin@example.test", "password": "pw"},
            )
            self.assertEqual(capacity_holder.status_code, 200)
            self.assertEqual(
                second.post(
                    "/api/login",
                    json={"username": "admin@example.test", "password": "pw"},
                ).status_code,
                503,
            )
            now[0] = 1002.0
            self.assertEqual(first.get("/api/stats").status_code, 401)
            self.assertEqual(
                second.post(
                    "/api/login",
                    json={"username": "admin@example.test", "password": "pw"},
                ).status_code,
                200,
            )

    def test_shared_login_ui_assets_and_mounted_next_are_public(self) -> None:
        with TemporaryDirectory() as directory, patch.dict(
            "os.environ",
            {
                "CHATEVENT_BOOTSTRAP_USERNAME": "admin@example.test",
                "CHATEVENT_BOOTSTRAP_PASSWORD": "pw",
                "CHATEVENT_PUBLIC_ORIGIN": "http://testserver",
            },
        ):
            client = TestClient(create_app(db_path=Path(directory) / "events.db"), root_path="/mounted")

            root = client.get("/")
            self.assertEqual(root.status_code, 200)
            self.assertIn("chatlogin", root.text)
            self.assertIn("/mounted/login", root.text)
            self.assertIn("/mounted/login/assets/login.js", root.text)
            self.assertIn('data-next="/mounted/"', root.text)
            self.assertNotIn("window.location.reload()", root.text)
            self.assertEqual(client.get("/login/assets/login.js").headers["content-type"], "application/javascript; charset=utf-8")
            self.assertEqual(client.get("/login/assets/login.css").headers["content-type"], "text/css; charset=utf-8")
            self.assertIn('data-next="/mounted/"', client.get("/login?next=https://evil.test/").text)
            self.assertIn('data-next="/api/stats"', client.get("/login?next=/api/stats").text)

    def test_api_rejects_naive_time_and_unknown_fields(self) -> None:
        with TemporaryDirectory() as directory:
            client = TestClient(create_app(db_path=Path(directory) / "events.db"))
            response = client.post(
                "/api/events",
                json={
                    "id": "1",
                    "source": "gitea",
                    "kind": "issue.opened",
                    "occurred_at": "2026-08-18T00:00:00",
                    "capture_mode": "push",
                    "unknown": True,
                },
            )

            self.assertEqual(response.status_code, 422)

    def test_metadata_declares_core_and_serve_chatlogin_bounds(self) -> None:
        metadata = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

        self.assertIn("ChatLogin>=0.1.3,<0.2.0", metadata["project"]["dependencies"])
        self.assertIn(
            "ChatLogin[ui]>=0.1.3,<0.2.0",
            metadata["project"]["optional-dependencies"]["serve"],
        )

    def test_password_verify_rejects_malformed_iterations_without_hashing(self) -> None:
        from chatevent.auth import verify_password

        zero_salt = "00" * 16
        zero_digest = "00" * 32

        self.assertFalse(
            verify_password(
                "probe", f"pbkdf2_sha256$bad${zero_salt}${zero_digest}"
            )
        )
        self.assertFalse(
            verify_password(
                "probe", f"pbkdf2_sha256$0${zero_salt}${zero_digest}"
            )
        )
        self.assertFalse(
            verify_password(
                "probe", f"pbkdf2_sha256$10000001${zero_salt}${zero_digest}"
            )
        )

    def test_secure_cookie_env_defaults_and_overrides(self) -> None:
        from chatevent.server import _secure_cookie

        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(_secure_cookie())
        with patch.dict("os.environ", {"CHATEVENT_PUBLIC_ORIGIN": "https://event.example.test"}, clear=True):
            self.assertTrue(_secure_cookie())
        with patch.dict(
            "os.environ",
            {
                "CHATEVENT_PUBLIC_ORIGIN": "https://event.example.test",
                "CHATEVENT_COOKIE_SECURE": "false",
            },
            clear=True,
        ):
            self.assertFalse(_secure_cookie())
        with patch.dict(
            "os.environ",
            {"CHATEVENT_PUBLIC_ORIGIN": "http://127.0.0.1:8765", "CHATEVENT_COOKIE_SECURE": "true"},
            clear=True,
        ):
            self.assertTrue(_secure_cookie())

    def test_custom_login_ui_and_mounted_next_semantics(self) -> None:
        def renderer(context: dict[str, object]) -> str:
            return (
                "<html><body>"
                f"<main data-login='{context['login_url']}' "
                f"data-session='{context['session_url']}' "
                f"data-assets='{context['assets_path']}' "
                f"data-next='{context['next']}'>custom-login</main>"
                "</body></html>"
            )

        with TemporaryDirectory() as directory, patch.dict(
            "os.environ",
            {
                "CHATEVENT_BOOTSTRAP_USERNAME": "admin@example.test",
                "CHATEVENT_BOOTSTRAP_PASSWORD": "pw",
            },
        ):
            app = create_app(
                db_path=Path(directory) / "events.db",
                login_ui=LoginUI(renderer=renderer),
            )
            client = TestClient(app, root_path="/mounted")

            root = client.get("/")
            self.assertIn("custom-login", root.text)
            self.assertIn("data-login='/mounted/api/login'", root.text)
            self.assertIn("data-assets='/mounted/login/assets'", root.text)
            self.assertIn("data-next='/mounted/'", root.text)
            self.assertIn(
                "data-next='/outside'",
                client.get("/login?next=/outside").text,
            )
            self.assertIn(
                "data-next='/mounted/'",
                client.get("/login?next=https://evil.test/").text,
            )

            explicit_login = TestClient(app, root_path="/mounted").post(
                "/api/login",
                json={"username": "admin@example.test", "password": "pw", "next": "/outside"},
            )
            self.assertEqual(explicit_login.status_code, 200)
            self.assertEqual(explicit_login.json()["next"], "/outside")

            login = client.post(
                "/api/login",
                json={"username": "admin@example.test", "password": "pw"},
            )
            self.assertEqual(login.status_code, 200)
            self.assertEqual(login.json()["next"], "/mounted/")
            self.assertIn("csrf_token", login.json())
            self.assertEqual(client.get("/api/stats").status_code, 200)

    def test_password_mode_client_releases_temporary_sessions(self) -> None:
        with TemporaryDirectory() as directory, patch.dict(
            "os.environ",
            {
                "CHATEVENT_BOOTSTRAP_USERNAME": "admin@example.test",
                "CHATEVENT_BOOTSTRAP_PASSWORD": "pw",
                "CHATEVENT_MAX_SESSIONS": "2",
            },
        ):
            from chatevent.client import ChatEventApiClient

            app = create_app(db_path=Path(directory) / "events.db")
            client = TestClient(app)
            api_client = ChatEventApiClient(
                username="admin@example.test",
                password="pw",
            )

            class UrlopenResponse:
                def __init__(self, response) -> None:  # type: ignore[no-untyped-def]
                    self._response = response
                    self.headers = response.headers

                def __enter__(self):  # type: ignore[no-untyped-def]
                    return self

                def __exit__(self, *_exc: object) -> None:
                    return None

                def read(self) -> bytes:
                    return self._response.content

            def fake_urlopen(request, timeout: float = 0):  # type: ignore[no-untyped-def]
                method = request.get_method()
                parsed = request.full_url.removeprefix(api_client.base_url)
                return UrlopenResponse(
                    client.request(
                        method,
                        parsed,
                        content=request.data,
                        headers=dict(request.header_items()),
                    )
                )

            with patch("urllib.request.urlopen", fake_urlopen):
                self.assertEqual(api_client.stats()["event_count"], 0)
                self.assertEqual(api_client.stats()["event_count"], 0)
                self.assertEqual(api_client.stats()["event_count"], 0)

    def test_password_mode_client_logs_out_without_retrying_write(self) -> None:
        from chatevent.client import ChatEventApiClient

        calls: list[tuple[str, str, bytes | None]] = []

        class UrlopenResponse:
            def __init__(self, payload: object, *, set_cookie: str = "") -> None:
                self._payload = payload
                self.headers = {"Set-Cookie": set_cookie}

            def __enter__(self):  # type: ignore[no-untyped-def]
                return self

            def __exit__(self, *_exc: object) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps(self._payload).encode("utf-8")

            def close(self) -> None:
                return None

        def fake_urlopen(request, timeout: float = 0):  # type: ignore[no-untyped-def]
            calls.append((request.get_method(), urlparse(request.full_url).path, request.data))
            if request.full_url.endswith("/api/login"):
                return UrlopenResponse(
                    {"authenticated": True, "csrf_token": "csrf-one"},
                    set_cookie="chatevent_session=session-one; HttpOnly",
                )
            if request.full_url.endswith("/api/logout"):
                return UrlopenResponse({"authenticated": False})
            return UrlopenResponse({"created": True, "dedupe_key": "gitea:1", "seen_count": 1})

        with TemporaryDirectory() as directory:
            event_file = Path(directory) / "event.json"
            event_file.write_text('{"id":"1","source":"gitea","kind":"issue.opened","occurred_at":"2026-08-18T00:00:00Z","capture_mode":"webhook"}', encoding="utf-8")
            api_client = ChatEventApiClient(username="admin@example.test", password="pw")

            with patch("urllib.request.urlopen", fake_urlopen):
                result = api_client.record_json(event_file)

        self.assertTrue(result["created"])
        self.assertEqual(
            [(method, path) for method, path, _body in calls],
            [
                ("POST", "/api/login"),
                ("POST", "/api/events"),
                ("POST", "/api/logout"),
            ],
        )
        self.assertEqual(
            [path for _method, path, _body in calls].count("/api/events"),
            1,
        )

    def test_password_mode_client_ignores_logout_read_timeout_after_success(self) -> None:
        from chatevent.client import ChatEventApiClient

        calls: list[tuple[str, str, bytes | None]] = []

        class UrlopenResponse:
            def __init__(
                self,
                payload: object,
                *,
                set_cookie: str = "",
                read_error: BaseException | None = None,
            ) -> None:
                self._payload = payload
                self._read_error = read_error
                self.headers = {"Set-Cookie": set_cookie}

            def __enter__(self):  # type: ignore[no-untyped-def]
                return self

            def __exit__(self, *_exc: object) -> None:
                return None

            def read(self) -> bytes:
                if self._read_error is not None:
                    raise self._read_error
                return json.dumps(self._payload).encode("utf-8")

        def fake_urlopen(request, timeout: float = 0):  # type: ignore[no-untyped-def]
            calls.append((request.get_method(), urlparse(request.full_url).path, request.data))
            if request.full_url.endswith("/api/login"):
                return UrlopenResponse(
                    {"authenticated": True, "csrf_token": "csrf-one"},
                    set_cookie="chatevent_session=session-one; HttpOnly",
                )
            if request.full_url.endswith("/api/logout"):
                return UrlopenResponse({"authenticated": False}, read_error=TimeoutError("timed out"))
            return UrlopenResponse({"created": True, "dedupe_key": "gitea:1", "seen_count": 1})

        with TemporaryDirectory() as directory:
            event_file = Path(directory) / "event.json"
            event_file.write_text('{"id":"1","source":"gitea","kind":"issue.opened","occurred_at":"2026-08-18T00:00:00Z","capture_mode":"webhook"}', encoding="utf-8")
            api_client = ChatEventApiClient(username="admin@example.test", password="pw")

            with patch("urllib.request.urlopen", fake_urlopen):
                result = api_client.record_json(event_file)

        self.assertTrue(result["created"])
        self.assertEqual(
            [(method, path) for method, path, _body in calls],
            [
                ("POST", "/api/login"),
                ("POST", "/api/events"),
                ("POST", "/api/logout"),
            ],
        )
        self.assertEqual(
            [path for _method, path, _body in calls].count("/api/events"),
            1,
        )

    def test_password_mode_client_preserves_business_error_when_logout_truncates(self) -> None:
        import urllib.error

        from chatevent.client import ChatEventApiClient, ChatEventApiError

        calls: list[tuple[str, str, bytes | None]] = []

        class UrlopenResponse:
            def __init__(self, payload: object, *, set_cookie: str = "") -> None:
                self._payload = payload
                self.headers = {"Set-Cookie": set_cookie}

            def __enter__(self):  # type: ignore[no-untyped-def]
                return self

            def __exit__(self, *_exc: object) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps(self._payload).encode("utf-8")

            def close(self) -> None:
                return None

        def fake_urlopen(request, timeout: float = 0):  # type: ignore[no-untyped-def]
            calls.append((request.get_method(), urlparse(request.full_url).path, request.data))
            if request.full_url.endswith("/api/login"):
                return UrlopenResponse(
                    {"authenticated": True, "csrf_token": "csrf-one"},
                    set_cookie="chatevent_session=session-one; HttpOnly",
                )
            if request.full_url.endswith("/api/logout"):
                raise http.client.IncompleteRead(b'{"authenticated"', 4)
            raise urllib.error.HTTPError(
                request.full_url,
                500,
                "Internal Server Error",
                hdrs={},
                fp=UrlopenResponse({"detail": "business failed"}),
            )

        with TemporaryDirectory() as directory:
            event_file = Path(directory) / "event.json"
            event_file.write_text('{"id":"1","source":"gitea","kind":"issue.opened","occurred_at":"2026-08-18T00:00:00Z","capture_mode":"webhook"}', encoding="utf-8")
            api_client = ChatEventApiClient(username="admin@example.test", password="pw")

            with patch("urllib.request.urlopen", fake_urlopen):
                with self.assertRaisesRegex(ChatEventApiError, "500 Internal Server Error"):
                    api_client.record_json(event_file)

        self.assertEqual(
            [(method, path) for method, path, _body in calls],
            [
                ("POST", "/api/login"),
                ("POST", "/api/events"),
                ("POST", "/api/logout"),
            ],
        )
        self.assertEqual(
            [path for _method, path, _body in calls].count("/api/events"),
            1,
        )


if __name__ == "__main__":
    unittest.main()
