"""Command line interface for ChatEvent."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path


TREE = """chatevent
  --tree                         Print this command tree
  serve [--host HOST] [--port PORT] [--db DB]
                                 Run the local Event Observatory
  schema event|subscription      Print JSON Schema contracts
  record-json FILE [--db DB]     Validate and write one ChatEvent JSON file
  capture zulip-once [options]   Official Zulip event-queue capture pass
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chatevent",
        description="Capture and inspect normalized collaboration events.",
    )
    parser.add_argument("--tree", action="store_true", help="print the CLI command tree and exit")
    subparsers = parser.add_subparsers(dest="command")

    serve = subparsers.add_parser("serve", help="run the local Event Observatory")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument(
        "--db",
        type=Path,
        default=None,
        help="SQLite path (default: ~/.chatevent/events.db)",
    )

    schema = subparsers.add_parser("schema", help="print JSON Schema contracts")
    schema.add_argument("kind", choices=("event", "subscription"))

    record = subparsers.add_parser("record-json", help="validate and write one ChatEvent JSON file")
    record.add_argument("file", type=Path)
    record.add_argument(
        "--db",
        type=Path,
        default=None,
        help="SQLite path (default: ~/.chatevent/events.db)",
    )

    capture = subparsers.add_parser("capture", help="run one bounded official capture pass")
    capture_subparsers = capture.add_subparsers(dest="capture_command", required=True)
    zulip = capture_subparsers.add_parser(
        "zulip-once",
        help="capture one Zulip official event-queue pass",
    )
    zulip.add_argument(
        "--db",
        type=Path,
        default=None,
        help="SQLite path (default: ~/.chatevent/events.db)",
    )
    zulip.add_argument(
        "--env-file",
        type=Path,
        default=Path("~/.chatarch/envs/Zulip/.env"),
        help="Zulip env file containing ZULIP_SITE/BOT_EMAIL/BOT_API_KEY",
    )
    zulip.add_argument("--stream", default=None, help="Zulip stream name")
    zulip.add_argument("--topic", default=None, help="Zulip topic")
    zulip.add_argument(
        "--content",
        default=None,
        help="optional test message to emit before polling the event queue",
    )
    zulip.add_argument("--timeout", type=float, default=10.0)
    zulip.add_argument("--subscription-id", default="zulip-practice")
    return parser


def _print_json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.tree:
        print(TREE, end="")
        return
    if args.command is None:
        build_parser().print_help()
        return
    if args.command == "serve":
        try:
            import uvicorn
        except ImportError as error:
            raise SystemExit(
                "Web dependencies are missing. Install with: pip install 'chatevent[serve]'"
            ) from error

        from .server import create_app, default_database_path

        db_path = args.db or default_database_path()
        print(f"ChatEvent Observatory: http://{args.host}:{args.port}")
        print(f"Event database: {db_path}")
        uvicorn.run(create_app(db_path=db_path), host=args.host, port=args.port)
        return
    if args.command == "schema":
        from .model import ChatEvent
        from .subscription import Subscription

        if args.kind == "event":
            _print_json(ChatEvent.model_json_schema())
        else:
            _print_json(Subscription.model_json_schema())
        return
    if args.command == "record-json":
        from .model import ChatEvent
        from .server import EventWriteResult, default_database_path
        from .store import EventStore

        event = ChatEvent.model_validate_json(args.file.read_text(encoding="utf-8"))
        store = EventStore(args.db or default_database_path())
        stored, created = store.record_event(event)
        _print_json(
            EventWriteResult(
                created=created,
                dedupe_key=event.dedupe_key,
                seen_count=stored.seen_count,
            ).model_dump(mode="json")
        )
        return
    if args.command == "capture" and args.capture_command == "zulip-once":
        from .capture import capture_zulip_once
        from .server import default_database_path

        summary = capture_zulip_once(
            db_path=args.db or default_database_path(),
            env_file=args.env_file,
            stream=args.stream,
            topic=args.topic,
            content=args.content,
            timeout_seconds=args.timeout,
            subscription_id=args.subscription_id,
        )
        _print_json(summary.to_dict())
        return
    raise SystemExit(f"unsupported command: {args.command}")
