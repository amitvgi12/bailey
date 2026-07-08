"""bailey CLI — portable bridges for AI agents into enterprise APIs.

Agent-first contract:
- Output is ALWAYS JSON on stdout. Humans get the same truth agents do.
- Errors are JSON on stderr with stable exit codes:
      0 ok · 1 error · 2 usage · 3 auth · 4 not found · 5 version conflict
- No interactive prompts, ever. Everything comes from args, files, or stdin.
- Mutating commands support --dry-run.
"""
from __future__ import annotations

import argparse
import json
import sys

from ._http import BridgeError
from .confluence import Confluence
from .jira import Jira

__version__ = "0.1.0"


def _emit(data) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def _fail(err: BridgeError) -> None:
    print(json.dumps({"error": str(err), "exit_code": err.exit_code}),
          file=sys.stderr)
    sys.exit(err.exit_code)


def _read_body(args) -> str:
    if getattr(args, "file", None):
        if args.file == "-":
            return sys.stdin.read()
        with open(args.file, "r", encoding="utf-8") as fh:
            return fh.read()
    raise SystemExit("--file is required (use '-' to read stdin)")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bailey",
        description="Portable bridges for AI agents into enterprise APIs. "
                    "Zero dependencies, JSON-only output, stable exit codes.")
    p.add_argument("--version", action="version", version=f"bailey {__version__}")
    services = p.add_subparsers(dest="service", required=True)

    # ---------------------------------------------------------- confluence
    conf = services.add_parser("confluence", help="Confluence bridge")
    cc = conf.add_subparsers(dest="command", required=True)

    gp = cc.add_parser("get-page", help="Fetch a page (storage body + version)")
    gp.add_argument("--id", required=True)
    gp.add_argument("--text", action="store_true",
                    help="return plain text instead of storage format")

    se = cc.add_parser("search", help="Search content with CQL")
    se.add_argument("--cql", required=True)
    se.add_argument("--limit", type=int, default=25)

    cc.add_parser("spaces", help="List visible spaces")

    cp = cc.add_parser("create-page", help="Create a page from a storage-format file")
    cp.add_argument("--space", required=True)
    cp.add_argument("--title", required=True)
    cp.add_argument("--file", required=True, help="storage-format body ('-' = stdin)")
    cp.add_argument("--parent-id")

    up = cc.add_parser("update-page",
                       help="Update a page with optimistic version safety")
    up.add_argument("--id", required=True)
    up.add_argument("--file", help="new storage-format body ('-' = stdin)")
    up.add_argument("--title")
    up.add_argument("--expect-version", type=int,
                    help="abort with exit 5 if the live version differs")
    up.add_argument("--message", default="", help="version comment")
    up.add_argument("--minor", action="store_true")
    up.add_argument("--dry-run", action="store_true")

    # ---------------------------------------------------------------- jira
    jira = services.add_parser("jira", help="Jira bridge")
    jc = jira.add_subparsers(dest="command", required=True)

    gi = jc.add_parser("get-issue", help="Fetch an issue")
    gi.add_argument("--key", required=True)

    js = jc.add_parser("search", help="Search issues with JQL")
    js.add_argument("--jql", required=True)
    js.add_argument("--limit", type=int, default=25)

    jm = jc.add_parser("comment", help="Add a comment to an issue")
    jm.add_argument("--key", required=True)
    jm.add_argument("--body", required=True)
    jm.add_argument("--dry-run", action="store_true")

    return p


def main(argv=None) -> None:
    args = build_parser().parse_args(argv)
    try:
        if args.service == "confluence":
            client = Confluence.from_env()
            if args.command == "get-page":
                _emit(client.page_text(args.id) if args.text
                      else client.get_page(args.id))
            elif args.command == "search":
                _emit(client.search(args.cql, args.limit))
            elif args.command == "spaces":
                _emit(client.spaces())
            elif args.command == "create-page":
                _emit(client.create_page(args.space, args.title,
                                         _read_body(args),
                                         parent_id=args.parent_id))
            elif args.command == "update-page":
                body = _read_body(args) if args.file else None
                _emit(client.update_page(
                    args.id, storage_body=body, title=args.title,
                    expect_version=args.expect_version,
                    message=args.message, minor_edit=args.minor,
                    dry_run=args.dry_run))
        elif args.service == "jira":
            client = Jira.from_env()
            if args.command == "get-issue":
                _emit(client.get_issue(args.key))
            elif args.command == "search":
                _emit(client.search(args.jql, args.limit))
            elif args.command == "comment":
                _emit(client.add_comment(args.key, args.body,
                                         dry_run=args.dry_run))
    except BridgeError as err:
        _fail(err)


if __name__ == "__main__":
    main()
