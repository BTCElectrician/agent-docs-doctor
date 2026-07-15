#!/usr/bin/env python3
"""Check Python syntax without writing bytecode caches."""

from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True


def python_files(values: list[str]) -> tuple[list[Path], list[str]]:
    paths: set[Path] = set()
    errors: list[str] = []
    for value in values:
        path = Path(value)
        if not path.exists():
            errors.append(f"path does not exist: {path}")
        elif path.is_dir():
            paths.update(path.rglob("*.py"))
        elif path.is_file() and path.suffix == ".py":
            paths.add(path)
        else:
            errors.append(f"not a Python file or directory: {path}")
    return sorted(paths, key=lambda item: item.as_posix()), errors


def main(argv: list[str] | None = None) -> int:
    values = sys.argv[1:] if argv is None else argv
    if not values:
        print("usage: check_python_syntax.py <file-or-directory> [...]", file=sys.stderr)
        return 2
    paths, errors = python_files(values)
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 2
    failed = False
    for path in paths:
        try:
            compile(path.read_bytes(), str(path), "exec")
        except (OSError, SyntaxError) as exc:
            print(f"error: {path}: {exc}", file=sys.stderr)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
