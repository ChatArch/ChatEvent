import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from chatevent.capture import (
    capture_x_user_once,
    extract_x_status_created_at,
    extract_x_status_ids_from_user_html,
    fetch_x_status_payload,
    load_proxy_env_file,
    parse_x_status_url,
)
from chatevent.store import EventStore


class FakeHeaders:
    def get_content_charset(self) -> str:
        return "utf-8"


class FakeHttpResponse:
    def __init__(self, text: str) -> None:
        self.text = text
        self.headers = FakeHeaders()

    def __enter__(self) -> "FakeHttpResponse":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def read(self) -> bytes:
        return self.text.encode("utf-8")


class XCaptureTests(unittest.TestCase):
    def test_extract_status_ids_from_user_html_preserves_order(self) -> None:
        html = """
        <a href="/thsottiaux/status/2090887457915232269">one</a>
        <a href="https://x.com/thsottiaux/status/2090766694897619318">two</a>
        <a href="/someone/status/111">other user</a>
        <a href="/thsottiaux/status/2090887457915232269">duplicate</a>
        """

        self.assertEqual(
            extract_x_status_ids_from_user_html(html, "@thsottiaux"),
            ["2090887457915232269", "2090766694897619318"],
        )

    def test_extract_status_created_at_finds_iso_timestamp(self) -> None:
        html = '{"rest_id":"2087423996115681767","createdAt":"2026-08-12T06:20:37.000Z"}'

        self.assertEqual(
            extract_x_status_created_at(html, "2087423996115681767"),
            "2026-08-12T06:20:37.000Z",
        )

    def test_extract_status_created_at_prefers_timestamp_near_status_id(self) -> None:
        html = (
            '"createdAt":"2026-01-01T00:00:00.000Z"'
            + "x" * 9000
            + '{"rest_id":"2087423996115681767","createdAt":"2026-08-12T06:20:37.000Z"}'
        )

        self.assertEqual(
            extract_x_status_created_at(html, "2087423996115681767"),
            "2026-08-12T06:20:37.000Z",
        )

    def test_fetch_x_status_payload_uses_oembed_and_web_timestamp(self) -> None:
        def fake_urlopen(request, timeout: float = 0):  # type: ignore[no-untyped-def]
            url = request.full_url
            if "publish.twitter.com/oembed" in url:
                return FakeHttpResponse(
                    json.dumps(
                        {
                            "author_name": "Tibo",
                            "author_url": "https://x.com/thsottiaux",
                            "html": (
                                '<blockquote><p>Little surprise for you tomorrow.</p>'
                                '&mdash; Tibo (@thsottiaux) August 12, 2026</blockquote>'
                            ),
                        }
                    )
                )
            if url == "https://x.com/thsottiaux/status/2087423996115681767":
                return FakeHttpResponse(
                    '{"rest_id":"2087423996115681767","created_at":"2026-08-12T06:20:37.000Z"}'
                )
            raise AssertionError(f"unexpected URL {url}")

        with patch("chatevent.capture.urlopen", fake_urlopen):
            payload = fetch_x_status_payload(
                "https://twitter.com/thsottiaux/status/2087423996115681767"
            )

        self.assertEqual(payload["status_id"], "2087423996115681767")
        self.assertEqual(payload["status_url"], "https://x.com/thsottiaux/status/2087423996115681767")
        self.assertEqual(payload["author_handle"], "thsottiaux")
        self.assertEqual(payload["author_name"], "Tibo")
        self.assertEqual(payload["text"], "Little surprise for you tomorrow.")
        self.assertEqual(payload["created_at"], "2026-08-12T06:20:37.000Z")
        self.assertEqual(payload["timestamp_source"], "x-web-html")
        self.assertEqual(payload["acquisition"], "x-web-url")

    def test_capture_x_user_once_records_recent_posts_and_dedupes(self) -> None:
        def fake_urlopen(request, timeout: float = 0):  # type: ignore[no-untyped-def]
            url = request.full_url
            if url == "https://x.com/thsottiaux":
                return FakeHttpResponse(
                    '<a href="/thsottiaux/status/2090887457915232269">new</a>'
                    '<a href="/thsottiaux/status/2090766694897619318">older</a>'
                )
            if "2090887457915232269" in url and "oembed" in url:
                return FakeHttpResponse(
                    json.dumps(
                        {
                            "author_name": "Tibo",
                            "author_url": "https://x.com/thsottiaux",
                            "html": "<p>first recent post</p> &mdash; Tibo (@thsottiaux) August 22, 2026",
                        }
                    )
                )
            if "2090766694897619318" in url and "oembed" in url:
                return FakeHttpResponse(
                    json.dumps(
                        {
                            "author_name": "Tibo",
                            "author_url": "https://x.com/thsottiaux",
                            "html": "<p>second recent post</p> &mdash; Tibo (@thsottiaux) August 21, 2026",
                        }
                    )
                )
            if url.endswith("/2090887457915232269"):
                return FakeHttpResponse('2026-08-22T01:02:03.000Z')
            if url.endswith("/2090766694897619318"):
                return FakeHttpResponse('2026-08-21T01:02:03.000Z')
            raise AssertionError(f"unexpected URL {url}")

        with TemporaryDirectory() as directory:
            db = Path(directory) / "events.db"
            with patch("chatevent.capture.urlopen", fake_urlopen):
                first = capture_x_user_once(db_path=db, handle="thsottiaux", limit=2)
                second = capture_x_user_once(db_path=db, handle="thsottiaux", limit=2)
            store = EventStore(db)
            events = store.list_events(source="x", limit=10)

        self.assertEqual(first.captured, 2)
        self.assertEqual(first.created, 2)
        self.assertEqual(second.captured, 2)
        self.assertEqual(second.created, 0)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].event.source, "x")
        self.assertEqual(events[0].seen_count, 2)
        self.assertEqual(events[0].event.payload["status_url"], events[0].event.url)
        self.assertIn("recent post", events[0].event.payload["content"])

    def test_proxy_env_file_loads_only_proxy_keys(self) -> None:
        with TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text(
                "export https_proxy=http://127.0.0.1:7890\n"
                "http_proxy=$https_proxy\n"
                "TOKEN=secret\n"
                "no_proxy=localhost\n",
                encoding="utf-8",
            )

            loaded = load_proxy_env_file(env_file)

        self.assertEqual(set(loaded), {"https_proxy", "http_proxy", "no_proxy"})
        self.assertEqual(loaded["http_proxy"], "http://127.0.0.1:7890")
        self.assertEqual(loaded["no_proxy"], "localhost")

    def test_parse_x_status_url_accepts_x_and_twitter(self) -> None:
        self.assertEqual(
            parse_x_status_url("https://x.com/thsottiaux/status/2087423996115681767"),
            ("thsottiaux", "2087423996115681767"),
        )
        self.assertEqual(
            parse_x_status_url("https://twitter.com/thsottiaux/status/2087423996115681767"),
            ("thsottiaux", "2087423996115681767"),
        )


if __name__ == "__main__":
    unittest.main()
