from __future__ import annotations

import argparse
import sys

from breadcrumbs.config import Settings
from breadcrumbs.storage import SQLiteStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="breadcrumbs")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("init-db", help="Create or migrate the local SQLite database")
    subcommands.add_parser("api", help="Run the local FastAPI server")
    subcommands.add_parser("overlay", help="Run the always-on-top overlay bubble")
    args = parser.parse_args(argv)

    settings = Settings.from_env()
    settings.ensure_dirs()

    if args.command == "init-db":
        SQLiteStore(settings.db_path).init_db()
        print(f"Initialized {settings.db_path}")
        return 0

    if args.command == "api":
        try:
            import uvicorn
        except ImportError:
            print("uvicorn is not installed. Install dependencies with `pip install -e .`.", file=sys.stderr)
            return 1
        from breadcrumbs.api import create_app

        uvicorn.run(create_app(settings=settings), host=settings.host, port=settings.port)
        return 0

    if args.command == "overlay":
        from breadcrumbs.overlay import run_overlay

        return run_overlay(f"http://{settings.host}:{settings.port}")

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
