"""Command line interface for ChatEvent."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from pathlib import Path

from . import __version__


TREE = """chatevent
  --tree                         Print this command tree
  --version                      Print package version
  paths [--json]                 Show ChatArch-owned runtime paths
  serve [--host HOST] [--port PORT] [--db DB]
                                 Run the local Event Observatory
  schema event|subscription      Print JSON Schema contracts
  platforms [--json]             List supported platforms and action kinds
  record-json FILE [--db DB]     Validate and write one ChatEvent JSON file
  api health                     GET /api/health from a running Event Hub
  api stats                      GET /api/stats
  api platforms                  GET /api/platforms
  api session                    GET /api/session
  api users                      GET /api/users
  api create-user USERNAME       POST /api/users and print one-time arch_ token
  api delete-user ID             DELETE /api/users/{id}
  api schema event|subscription  GET /api/schema/{kind}
  api subscriptions [--enabled]  GET /api/subscriptions
  api subscription ID            GET /api/subscriptions/{id}
  api events [filters]           GET /api/events
  api event DEDUPE_KEY           GET /api/events/{dedupe_key}
  api record-json FILE           POST /api/events
  api save-subscription FILE     POST /api/subscriptions
  api delete-subscription ID     DELETE /api/subscriptions/{id}
  capture zulip-once [options]   Official Zulip event-queue capture pass
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chatevent",
        description="Capture and inspect normalized collaboration events.",
    )
    parser.add_argument("--tree", action="store_true", help="print the CLI command tree and exit")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    paths = subparsers.add_parser("paths", help="show ChatArch-owned runtime paths")
    paths.add_argument("--json", action="store_true", help="print paths as JSON")

    serve = subparsers.add_parser("serve", help="run the local Event Observatory")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument(
        "--db",
        type=Path,
        default=None,
        help="SQLite path (default: $CHATARCH_HOME/chatevent/events.db or ~/.chatarch/chatevent/events.db)",
    )

    schema = subparsers.add_parser("schema", help="print JSON Schema contracts")
    schema.add_argument("kind", choices=("event", "subscription"))

    platforms = subparsers.add_parser(
        "platforms", help="list supported platforms and action kinds"
    )
    platforms.add_argument(
        "--json",
        action="store_true",
        help="print the complete platform catalog as JSON",
    )

    record = subparsers.add_parser("record-json", help="validate and write one ChatEvent JSON file")
    record.add_argument("file", type=Path)
    record.add_argument(
        "--db",
        type=Path,
        default=None,
        help="SQLite path (default: $CHATARCH_HOME/chatevent/events.db or ~/.chatarch/chatevent/events.db)",
    )

    api = subparsers.add_parser("api", help="call a running ChatEvent REST API server")
    api_subparsers = api.add_subparsers(dest="api_command", required=True)
    api_common = argparse.ArgumentParser(add_help=False)
    api_common.add_argument(
        "--base-url",
        default=os.environ.get("CHATEVENT_API_URL", "http://127.0.0.1:8765"),
        help="ChatEvent API base URL (default: CHATEVENT_API_URL or http://127.0.0.1:8765)",
    )
    api_common.add_argument("--timeout", type=float, default=20.0)
    api_common.add_argument(
        "--admin-token",
        default=os.environ.get("CHATEVENT_ADMIN_TOKEN"),
        help="admin token for subscription mutations; can also use CHATEVENT_ADMIN_TOKEN",
    )

    api_subparsers.add_parser("health", parents=[api_common], help="GET /api/health")
    api_subparsers.add_parser("stats", parents=[api_common], help="GET /api/stats")
    api_subparsers.add_parser("platforms", parents=[api_common], help="GET /api/platforms")
    api_subparsers.add_parser("session", parents=[api_common], help="GET /api/session")
    api_subparsers.add_parser("users", parents=[api_common], help="GET /api/users")

    api_create_user = api_subparsers.add_parser(
        "create-user", parents=[api_common], help="POST /api/users"
    )
    api_create_user.add_argument("username")
    api_create_user.add_argument("--display-name", default=None)
    api_create_user.add_argument("--role", choices=("admin", "member"), default="member")

    api_delete_user = api_subparsers.add_parser(
        "delete-user", parents=[api_common], help="DELETE /api/users/{id}"
    )
    api_delete_user.add_argument("id")

    api_schema = api_subparsers.add_parser(
        "schema", parents=[api_common], help="GET /api/schema/{kind}"
    )
    api_schema.add_argument("kind", choices=("event", "subscription"))

    api_subscriptions = api_subparsers.add_parser(
        "subscriptions", parents=[api_common], help="GET /api/subscriptions"
    )
    api_subscriptions.add_argument(
        "--enabled",
        choices=("true", "false"),
        default=None,
        help="optional enabled filter",
    )

    api_subscription = api_subparsers.add_parser(
        "subscription", parents=[api_common], help="GET /api/subscriptions/{id}"
    )
    api_subscription.add_argument("id")

    api_events = api_subparsers.add_parser(
        "events", parents=[api_common], help="GET /api/events"
    )
    api_events.add_argument("--source", default=None)
    api_events.add_argument("--kind", default=None)
    api_events.add_argument("--subscription-id", default=None)
    api_events.add_argument("--q", default=None, help="keyword query")
    api_events.add_argument("--since", default=None, help="consumer checkpoint timestamp")
    api_events.add_argument("--days", default=None, help="recent-day window")
    api_events.add_argument("--from", dest="from_", default=None, help="captured-at range start")
    api_events.add_argument("--to", default=None, help="captured-at range end")
    api_events.add_argument("--limit", type=int, default=100)

    api_event = api_subparsers.add_parser(
        "event", parents=[api_common], help="GET /api/events/{dedupe_key}"
    )
    api_event.add_argument("dedupe_key")

    api_record = api_subparsers.add_parser(
        "record-json", parents=[api_common], help="POST /api/events"
    )
    api_record.add_argument("file", type=Path)

    api_save_subscription = api_subparsers.add_parser(
        "save-subscription", parents=[api_common], help="POST /api/subscriptions"
    )
    api_save_subscription.add_argument("file", type=Path)

    api_delete_subscription = api_subparsers.add_parser(
        "delete-subscription", parents=[api_common], help="DELETE /api/subscriptions/{id}"
    )
    api_delete_subscription.add_argument("id")

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
        help="SQLite path (default: $CHATARCH_HOME/chatevent/events.db or ~/.chatarch/chatevent/events.db)",
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


def _optional_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    return value == "true"


def _handle_api_command(args: argparse.Namespace) -> None:
    from .client import ChatEventApiClient, ChatEventApiError

    client = ChatEventApiClient(
        base_url=args.base_url,
        timeout=args.timeout,
        admin_token=args.admin_token,
    )
    try:
        if args.api_command == "health":
            result = client.health()
        elif args.api_command == "stats":
            result = client.stats()
        elif args.api_command == "platforms":
            result = client.platforms()
        elif args.api_command == "session":
            result = client.session()
        elif args.api_command == "users":
            result = client.list_users()
        elif args.api_command == "create-user":
            result = client.create_user(
                username=args.username,
                display_name=args.display_name,
                role=args.role,
            )
        elif args.api_command == "delete-user":
            result = client.delete_user(args.id)
        elif args.api_command == "schema":
            result = client.schema(args.kind)
        elif args.api_command == "subscriptions":
            result = client.list_subscriptions(enabled=_optional_bool(args.enabled))
        elif args.api_command == "subscription":
            result = client.get_subscription(args.id)
        elif args.api_command == "events":
            result = client.list_events(
                source=args.source,
                kind=args.kind,
                subscription_id=args.subscription_id,
                q=args.q,
                since=args.since,
                days=args.days,
                from_=args.from_,
                to=args.to,
                limit=args.limit,
            )
        elif args.api_command == "event":
            result = client.get_event(args.dedupe_key)
        elif args.api_command == "record-json":
            result = client.record_json(args.file)
        elif args.api_command == "save-subscription":
            result = client.save_subscription(args.file)
        elif args.api_command == "delete-subscription":
            result = client.delete_subscription(args.id)
        else:  # pragma: no cover - argparse prevents this branch
            raise SystemExit(f"unsupported api command: {args.api_command}")
    except ChatEventApiError as error:
        raise SystemExit(str(error)) from error
    _print_json(result)


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.tree:
        print(TREE, end="")
        return
    if args.command is None:
        build_parser().print_help()
        return
    if args.command == "paths":
        from .state import state_paths

        payload = state_paths(create=True).as_dict()
        if args.json:
            _print_json(payload)
        else:
            for key, value in payload.items():
                print(f"{key}: {value}")
        return
    if args.command == "serve":
        try:
            import uvicorn
        except ImportError as error:
            raise SystemExit(
                "Web dependencies are missing. Install with: pip install 'chatevent[serve]'"
            ) from error

        from .server import create_app
        from .state import default_database_path

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
    if args.command == "platforms":
        from .catalog import list_platform_specs

        specs = list(list_platform_specs())
        if args.json:
            _print_json(
                {
                    "items": [spec.model_dump(mode="json") for spec in specs],
                    "count": len(specs),
                }
            )
        else:
            for spec in specs:
                actions = ", ".join(action.kind for action in spec.actions)
                modes = ", ".join(mode.value for mode in spec.primary_acquisition_modes)
                print(f"{spec.id}\t{modes}\t{actions}")
        return
    if args.command == "record-json":
        from .model import ChatEvent
        from .server import EventWriteResult
        from .state import default_database_path
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
    if args.command == "api":
        _handle_api_command(args)
        return
    if args.command == "capture" and args.capture_command == "zulip-once":
        from .capture import capture_zulip_once
        from .state import default_database_path

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
