#!/usr/bin/env python3
"""Scan public text for private paths, review attribution, secrets, or unsafe commands."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import stat
import subprocess
import sys
import threading
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent_docs_doctor.core import read_bounded_input  # noqa: E402

TEXT_SUFFIXES = {
    ".cfg",
    ".css",
    ".csv",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".jsx",
    ".lock",
    ".md",
    ".mdc",
    ".ps1",
    ".py",
    ".rst",
    ".sh",
    ".sql",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
TEXT_NAMES = {
    ".agent-docs-doctorignore",
    ".gitignore",
    ".ignore",
    "dockerfile",
    "license",
    "makefile",
}
SKIP_PARTS = {
    ".git",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
}
MAX_TRACKED_PATHS = 100_000
MAX_PATH_BYTES = 50_000_000
MAX_FILE_BYTES = 2_000_000
MAX_TOTAL_BYTES = 50_000_000
MAX_FINDINGS = 1_000
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


def _git_paths(root: Path, arguments: list[str]) -> list[bytes]:
    command = [
        "git",
        "-C",
        os.fspath(root),
        "ls-files",
        "-z",
        *arguments,
    ]
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise ValueError("unable to start Git public-file discovery") from exc
    stdout = process.stdout
    if stdout is None:
        process.kill()
        process.wait()
        raise ValueError("Git public-file discovery did not provide an output stream")
    chunks: list[bytes] = []
    failures: list[str] = []

    def read_stdout() -> None:
        total = 0
        try:
            while chunk := stdout.read(64 * 1024):
                total += len(chunk)
                if total > MAX_PATH_BYTES:
                    failures.append("Git public-file discovery exceeded its path-byte limit")
                    process.kill()
                    return
                chunks.append(chunk)
        except (OSError, ValueError):
            failures.append("Git public-file discovery did not complete safely")
            process.kill()

    reader = threading.Thread(target=read_stdout, daemon=True)
    reader.start()
    reader.join(timeout=30)
    try:
        if reader.is_alive():
            process.kill()
            stdout.close()
            reader.join(timeout=5)
            raise ValueError("Git public-file discovery did not complete safely")
        return_code = process.wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired) as exc:
        process.kill()
        process.wait()
        raise ValueError("Git public-file discovery did not complete safely") from exc
    if failures:
        process.wait()
        raise ValueError(failures[0])
    if return_code != 0:
        raise ValueError("public safety scan requires a readable Git worktree")

    raw = b"".join(chunks)
    values = [value for value in raw.split(b"\0") if value]
    if len(values) > MAX_TRACKED_PATHS:
        raise ValueError("Git public-file discovery exceeded its entry limit")
    return values


def _public_paths(root: Path) -> list[Path]:
    """Return every tracked path plus text-like unignored pending paths."""

    tracked = _git_paths(root, ["--cached"])
    pending = _git_paths(root, ["--others", "--exclude-standard"])
    if len(tracked) + len(pending) > MAX_TRACKED_PATHS:
        raise ValueError("Git public-file discovery exceeded its entry limit")
    if sum(len(value) + 1 for value in (*tracked, *pending)) > MAX_PATH_BYTES:
        raise ValueError("Git public-file discovery exceeded its path-byte limit")
    paths: set[Path] = set()
    for raw_relative, is_tracked in (
        *((value, True) for value in tracked),
        *((value, False) for value in pending),
    ):
        relative = Path(os.fsdecode(raw_relative))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Git returned an unsafe public path")
        if not is_tracked and (
            relative.name == ".DS_Store"
            or any(part in SKIP_PARTS for part in relative.parts)
            or (relative.suffix.lower() not in TEXT_SUFFIXES and relative.name.lower() not in TEXT_NAMES)
        ):
            continue
        paths.add(root / relative)
    return sorted(paths, key=lambda path: path.relative_to(root).as_posix())


def _is_reparse_point(value: os.stat_result) -> bool:
    attributes = getattr(value, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_flag)


def _display_relative(value: str) -> str:
    unsafe = any(not character.isprintable() for character in value)
    if len(value) <= 512 and not unsafe:
        return value
    digest = hashlib.sha256(value.encode("utf-8", errors="surrogatepass")).hexdigest()
    return f"<public-path:{digest}>"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    root = args.root.resolve()
    findings: list[str] = []

    def record(finding: str) -> bool:
        if len(findings) < MAX_FINDINGS - 1:
            findings.append(finding)
            return True
        if len(findings) == MAX_FINDINGS - 1:
            findings.append("additional public-safety findings omitted by output cap")
        return False

    try:
        paths = _public_paths(root)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    total_bytes = 0
    scanned_files = 0
    for path in paths:
        if len(findings) >= MAX_FINDINGS:
            break
        relative = _display_relative(path.relative_to(root).as_posix())
        try:
            value = path.lstat()
        except OSError:
            record(f"{relative}: public file could not be inspected safely")
            continue
        if stat.S_ISLNK(value.st_mode) or _is_reparse_point(value):
            record(f"{relative}: public text link or reparse point was not followed")
            continue
        if not stat.S_ISREG(value.st_mode):
            record(f"{relative}: public text path is not a regular file")
            continue
        if value.st_nlink != 1:
            record(f"{relative}: multiply-linked public text was not read")
            continue
        if value.st_size > MAX_FILE_BYTES or total_bytes + value.st_size > MAX_TOTAL_BYTES:
            record(f"{relative}: public text exceeds the safety scan byte limit")
            continue
        try:
            raw = read_bounded_input(path, MAX_FILE_BYTES, allowed_root=root)
        except (OSError, ValueError):
            record(f"{relative}: public text could not be read safely")
            continue
        total_bytes += len(raw)
        scanned_files += 1
        text = raw.decode("utf-8", errors="replace")
        pattern_hits: list[tuple[int, str]] = []
        for label, pattern in PATTERNS.items():
            match = pattern.search(text)
            if match is not None:
                pattern_hits.append((match.start(), label))
        line = 1
        cursor = 0
        for position, label in sorted(pattern_hits):
            line += text.count("\n", cursor, position)
            cursor = position
            if not record(f"{relative}:{line}: {label}"):
                break
        lowered = text.lower()
        for fragment in ATTRIBUTION_FRAGMENTS:
            if fragment in lowered and not record(f"{relative}: public review attribution: {fragment}"):
                break
    if findings:
        for finding in findings:
            print(f"error: {finding}", file=sys.stderr)
        return 1
    print(f"public safety scan passed ({scanned_files} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
