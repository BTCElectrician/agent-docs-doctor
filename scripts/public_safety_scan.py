#!/usr/bin/env python3
"""Scan public text for private paths, review attribution, secrets, or unsafe commands."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

TEXT_SUFFIXES = {".md", ".txt", ".toml", ".yaml", ".yml", ".json", ".py"}
SKIP_PARTS = {
    ".git",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "fixtures",
    "forward-test-output",
}
PATTERNS = {
    "private macOS path": re.compile(r"/Users/[A-Za-z0-9._-]+/"),
    "private Linux path": re.compile(r"/home/[A-Za-z0-9._-]+/"),
    "private Windows path": re.compile(r"[A-Za-z]:\\Users\\[A-Za-z0-9._ -]+\\"),
    "email address": re.compile(
        r"\b[A-Z0-9._%+-]+@[A-Z0-9](?:[A-Z0-9.-]*[A-Z0-9])?\.[A-Z]{2,}\b",
        re.IGNORECASE,
    ),
    "OpenAI-style secret": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}\b"),
    "GitHub-style secret": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    "destructive shell advice": re.compile(r"\brm\s+-[A-Za-z]*r[A-Za-z]*f\b", re.IGNORECASE),
    "destructive Git advice": re.compile(r"\bgit\s+reset\s+--hard\b", re.IGNORECASE),
}
ATTRIBUTION_FRAGMENTS = (
    "f" + "able review",
    "claude-" + "f" + "able",
    "co" + "dex helped review",
    "co" + "dex collaboration",
)


def public_files(root: Path) -> list[Path]:
    return sorted(
        (
            path
            for path in root.rglob("*")
            if path.is_file()
            and path.suffix.lower() in TEXT_SUFFIXES
            and not any(part in SKIP_PARTS for part in path.relative_to(root).parts)
            and path.name != ".DS_Store"
        ),
        key=lambda path: path.relative_to(root).as_posix(),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    root = args.root.resolve()
    findings: list[str] = []
    for path in public_files(root):
        text = path.read_text(encoding="utf-8", errors="replace")
        relative = path.relative_to(root).as_posix()
        for label, pattern in PATTERNS.items():
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                findings.append(f"{relative}:{line}: {label}")
        lowered = text.lower()
        for fragment in ATTRIBUTION_FRAGMENTS:
            if fragment in lowered:
                findings.append(f"{relative}: public review attribution: {fragment}")
    if findings:
        for finding in findings:
            print(f"error: {finding}", file=sys.stderr)
        return 1
    print(f"public safety scan passed ({len(public_files(root))} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
