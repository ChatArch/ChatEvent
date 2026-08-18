import unittest

from chatevent.catalog import SUPPORTED_PLATFORM_IDS, get_platform_spec
from chatevent.model import CaptureMode


class PlatformCatalogTests(unittest.TestCase):
    def test_v1_catalog_is_scoped_to_four_platforms(self) -> None:
        self.assertEqual(
            SUPPORTED_PLATFORM_IDS,
            ("discourse", "gitea", "github", "zulip"),
        )

    def test_each_platform_registers_supported_actions(self) -> None:
        expectations = {
            "zulip": {"message.created", "message.updated", "reaction.added", "mention.created"},
            "discourse": {"topic.created", "post.created", "post.edited", "reply.created", "mention.created"},
            "gitea": {"push", "issue.opened", "issue.commented", "pull_request.opened", "pull_request.merged", "release.published"},
            "github": {"push", "commit.pushed", "issue.opened", "issue.commented", "pull_request.opened", "pull_request.merged", "workflow_run.completed", "release.published"},
        }
        for platform, kinds in expectations.items():
            spec = get_platform_spec(platform)
            self.assertTrue(kinds.issubset({action.kind for action in spec.actions}))

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
