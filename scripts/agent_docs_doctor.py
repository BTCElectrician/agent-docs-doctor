#!/usr/bin/env python3
"""Command-line entry point for deterministic Agent Docs Doctor evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from doctorlib import build_audit, build_inventory, dump_json, validate_audit


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Inventory and audit agent-facing repository documentation.")
    sub = result.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("inventory", "emit a deterministic inventory"),
        ("audit", "emit inventory plus deterministic findings"),
    ):
        command = sub.add_parser(name, help=help_text)
        command.add_argument(
            "root",
            nargs="?",
            default=".",
            help="repository root (default: current directory)",
        )
        command.add_argument("--pretty", action="store_true", help="pretty-print JSON")
    validate = sub.add_parser("validate-report", help="validate an audit JSON report")
    validate.add_argument("report", help="path to report JSON, or - for stdin")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "inventory":
            sys.stdout.write(dump_json(build_inventory(args.root), args.pretty))
            return 0
        if args.command == "audit":
            sys.stdout.write(dump_json(build_audit(args.root), args.pretty))
            return 0
        raw = sys.stdin.read() if args.report == "-" else Path(args.report).read_text(encoding="utf-8")
        errors = validate_audit(json.JSONDecoder().decode(raw))
        if errors:
            for error in errors:
                print(f"error: {error}", file=sys.stderr)
            return 1
        print("valid")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
