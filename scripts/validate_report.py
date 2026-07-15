#!/usr/bin/env python3
"""Validate an Agent Docs Doctor audit report."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True

from doctorlib import validate_audit  # noqa: E402

USAGE = "usage: validate_report.py <report.json|->"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args in (["-h"], ["--help"]):
        print(USAGE)
        print()
        print("Validate an Agent Docs Doctor audit JSON report.")
        print("Use - to read the report from standard input.")
        return 0
    if len(args) != 1:
        print(USAGE, file=sys.stderr)
        return 2
    try:
        raw = sys.stdin.read() if args[0] == "-" else Path(args[0]).read_text(encoding="utf-8")
        errors = validate_audit(json.JSONDecoder().decode(raw))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    print("valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
