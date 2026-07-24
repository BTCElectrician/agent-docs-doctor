#!/usr/bin/env python3
"""Prove that an audit leaves the requested repository byte-for-byte unchanged."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent_docs_doctor import build_audit, validate_audit  # noqa: E402


def snapshot(root: Path) -> tuple[tuple[str, str, int], ...]:
    values: list[tuple[str, str, int]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            values.append((relative, f"symlink:{path.readlink()}", 0))
        elif path.is_file():
            raw = path.read_bytes()
            values.append((relative, hashlib.sha256(raw).hexdigest(), len(raw)))
        elif path.is_dir():
            values.append((relative + "/", "directory", 0))
        else:
            values.append((relative, "non-regular", 0))
    return tuple(values)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if not root.is_dir():
        print(f"error: not a directory: {args.root}", file=sys.stderr)
        return 2
    before = snapshot(root)
    errors = validate_audit(build_audit(root))
    after = snapshot(root)
    if errors:
        print(f"error: generated report is invalid: {errors[0]}", file=sys.stderr)
        return 1
    if before != after:
        print("error: repository filesystem changed during audit", file=sys.stderr)
        return 1
    print("unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
