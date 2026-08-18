"""Command line interface for ChatEvent."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chatevent",
        description="Capture and inspect normalized collaboration events.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    serve = subparsers.add_parser("serve", help="run the local Event Observatory")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument(
        "--db",
        type=Path,
        default=None,
        help="SQLite path (default: ~/.chatevent/events.db)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
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
