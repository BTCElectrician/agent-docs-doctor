#!/usr/bin/env python3
"""Validate an Agent Docs Doctor audit report."""

from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent_docs_doctor.core import validate_audit  # noqa: E402
from agent_docs_doctor.report_validation import (  # noqa: E402
    ReportInputError,
    decode_report,
    read_report_file,
    read_report_stdin,
)

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
        raw = read_report_stdin(sys.stdin.buffer) if args[0] == "-" else read_report_file(Path(args[0]))
        errors = validate_audit(decode_report(raw))
    except (OSError, ReportInputError, RecursionError, MemoryError) as exc:
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
