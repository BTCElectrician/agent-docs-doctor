#!/usr/bin/env python3
"""Validate an Agent Docs Doctor audit report."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from doctorlib import validate_audit


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: validate_report.py <report.json|->", file=sys.stderr)
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
