import unittest

from chatevent.catalog import SUPPORTED_PLATFORM_IDS, get_platform_spec
from chatevent.model import CaptureMode


class PlatformCatalogTests(unittest.TestCase):
    def test_v1_catalog_lists_supported_platforms(self) -> None:
        self.assertEqual(
            SUPPORTED_PLATFORM_IDS,
            ("discourse", "gitea", "github", "x", "zulip"),
        )

    def test_each_platform_registers_supported_actions(self) -> None:
        expectations = {
            "zulip": {"message.created", "message.updated", "reaction.added", "mention.created"},
            "discourse": {"topic.created", "post.created", "post.edited", "reply.created", "mention.created"},
            "gitea": {"push", "issue.opened", "issue.commented", "pull_request.opened", "pull_request.merged", "release.published"},
            "github": {"push", "commit.pushed", "issue.opened", "issue.commented", "pull_request.opened", "pull_request.merged", "workflow_run.requested", "workflow_run.in_progress", "workflow_run.completed", "release.published"},
            "x": {"post.created"},
        }
        for platform, kinds in expectations.items():
            spec = get_platform_spec(platform)
            self.assertTrue(kinds.issubset({action.kind for action in spec.actions}))
            for action in spec.actions:
                self.assertTrue(action.target_types, f"{platform}:{action.kind} should declare target types")

    def test_action_catalog_declares_known_carrier_target_types(self) -> None:
        github = get_platform_spec("github")
        by_kind = {action.kind: action for action in github.actions}

        self.assertIn("repo", by_kind["commit.pushed"].target_types)
        self.assertIn("pull_request", by_kind["pull_request.opened"].target_types)
        self.assertIn("issue", by_kind["issue.commented"].target_types)
        self.assertIn("workflow_run", by_kind["workflow_run.completed"].target_types)

        zulip = get_platform_spec("zulip")
        message = {action.kind: action for action in zulip.actions}["message.created"]
        self.assertIn("zulip_stream", message.target_types)
        self.assertIn("zulip_topic", message.target_types)

        x = get_platform_spec("x")
        post = {action.kind: action for action in x.actions}["post.created"]
        self.assertIn("x_user", post.target_types)
        self.assertIn("x_post", post.target_types)

    def test_acquisition_modes_are_not_only_push_pull(self) -> None:
        self.assertEqual(CaptureMode.WEBHOOK.value, "webhook")
        self.assertEqual(CaptureMode.EVENT_QUEUE.value, "event_queue")
        self.assertEqual(CaptureMode.API_CURSOR.value, "api_cursor")
        self.assertEqual(CaptureMode.POLL.value, "poll")

        # Legacy compatibility remains so old events/subscriptions can still read.
        self.assertEqual(CaptureMode.PUSH.value, "push")
        self.assertEqual(CaptureMode.PULL.value, "pull")


if __name__ == "__main__":
    unittest.main()
