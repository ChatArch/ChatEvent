import unittest
from datetime import timezone

from chatevent import CaptureMode
from chatevent.adapters import normalize_github_event


class GitHubAdapterTests(unittest.TestCase):
    def test_push_webhook_normalizes_commit_pushed(self) -> None:
        event = normalize_github_event(
            "push",
            {
                "ref": "refs/heads/main",
                "after": "abc123456789",
                "head_commit": {
                    "id": "abc123456789",
                    "message": "feat: track ChatEvent actions",
                    "timestamp": "2026-08-18T10:30:00Z",
                    "url": "https://github.com/ChatArch/ChatEvent/commit/abc123456789",
                    "author": {"username": "RexWang", "name": "Rex Wang"},
                },
                "repository": {
                    "full_name": "ChatArch/ChatEvent",
                    "html_url": "https://github.com/ChatArch/ChatEvent",
                },
                "sender": {"login": "RexWang", "id": 7},
            },
            subscription_id="github-chatevent",
        )

        self.assertEqual(event.source, "github")
        self.assertEqual(event.kind, "commit.pushed")
        self.assertEqual(event.id, "commit:ChatArch/ChatEvent:abc123456789")
        self.assertEqual(event.capture_mode, CaptureMode.WEBHOOK)
        self.assertEqual(event.actor_id, "user:RexWang")
        self.assertEqual(event.conversation_id, "repo:ChatArch/ChatEvent")
        self.assertEqual(event.subject_id, "commit:abc123456789")
        self.assertEqual(event.subject_type, "commit")
        self.assertEqual(event.action.kind, "commit.pushed")
        self.assertEqual(event.action.object_type, "commit")
        self.assertEqual(event.action.verb, "pushed")
        self.assertEqual(event.target.type, "commit")
        self.assertEqual(event.target.key, "abc123456789")
        self.assertEqual(event.target.parent.type, "repo")
        self.assertEqual(event.target.parent.key, "ChatArch/ChatEvent")
        self.assertEqual(event.cursor, "abc123456789")
        self.assertEqual(event.payload["title"], "feat: track ChatEvent actions")
        self.assertEqual(event.metadata["github_event"], "push")
        self.assertIn("github", event.tags)
        self.assertEqual(event.occurred_at.tzinfo, timezone.utc)

    def test_pull_request_webhook_normalizes_actions(self) -> None:
        event = normalize_github_event(
            "pull_request",
            {
                "action": "opened",
                "number": 12,
                "pull_request": {
                    "id": 99,
                    "number": 12,
                    "title": "Add ChatEvent GitHub catalog",
                    "html_url": "https://github.com/ChatArch/ChatEvent/pull/12",
                    "created_at": "2026-08-18T10:35:00Z",
                    "user": {"login": "RexWang"},
                    "base": {"repo": {"full_name": "ChatArch/ChatEvent"}},
                },
                "repository": {"full_name": "ChatArch/ChatEvent"},
                "sender": {"login": "RexWang"},
            },
            subscription_id="github-chatevent",
        )

        self.assertEqual(event.kind, "pull_request.opened")
        self.assertEqual(event.id, "pull_request:ChatArch/ChatEvent:12")
        self.assertEqual(event.subject_type, "pull_request")
        self.assertEqual(event.conversation_id, "repo:ChatArch/ChatEvent")
        self.assertEqual(event.action.kind, "pull_request.opened")
        self.assertEqual(event.action.object_type, "pull_request")
        self.assertEqual(event.target.type, "pull_request")
        self.assertEqual(event.target.key, "ChatArch/ChatEvent#12")
        self.assertEqual(event.target.parent.type, "repo")
        self.assertEqual(event.target.parent.key, "ChatArch/ChatEvent")

    def test_issue_comment_webhook_targets_comment_inside_issue_or_pr(self) -> None:
        event = normalize_github_event(
            "issue_comment",
            {
                "action": "created",
                "issue": {
                    "number": 12,
                    "title": "Add ChatEvent GitHub catalog",
                    "html_url": "https://github.com/ChatArch/ChatEvent/pull/12",
                    "pull_request": {"url": "https://api.github.com/repos/ChatArch/ChatEvent/pulls/12"},
                },
                "comment": {
                    "id": 1234,
                    "body": "Looks good",
                    "html_url": "https://github.com/ChatArch/ChatEvent/pull/12#issuecomment-1234",
                    "created_at": "2026-08-18T10:40:00Z",
                    "author_association": "MEMBER",
                    "user": {"login": "RexWang"},
                },
                "repository": {"full_name": "ChatArch/ChatEvent"},
                "sender": {"login": "RexWang"},
            },
            subscription_id="github-chatevent",
        )

        self.assertEqual(event.kind, "issue.commented")
        self.assertEqual(event.action.kind, "issue.commented")
        self.assertEqual(event.action.object_type, "issue_comment")
        self.assertEqual(event.actor.role, "member")
        self.assertEqual(event.target.type, "issue_comment")
        self.assertEqual(event.target.key, "1234")
        self.assertEqual(event.target.parent.type, "pull_request")
        self.assertEqual(event.target.parent.key, "ChatArch/ChatEvent#12")
        self.assertEqual(event.target.parent.parent.type, "repo")


if __name__ == "__main__":
    unittest.main()
