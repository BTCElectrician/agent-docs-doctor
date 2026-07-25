#!/usr/bin/env python3
"""Deterministic, read-only evidence collection for Agent Docs Doctor."""

from __future__ import annotations

import fnmatch
import hashlib
import io
import json
import os
import re
import stat
import sys
from collections import defaultdict, deque
from collections.abc import Iterator
from contextlib import suppress
from dataclasses import dataclass
from itertools import islice
from pathlib import Path, PurePosixPath
from typing import Any

from .version import __version__

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility path
    tomllib = None  # type: ignore[assignment]

sys.dont_write_bytecode = True

SCHEMA_VERSION = "agent-docs-doctor.audit.v2"
INVENTORY_VERSION = "agent-docs-doctor.inventory.v2"
LEGACY_SCHEMA_VERSION = "agent-docs-doctor.audit.v1"
LEGACY_INVENTORY_VERSION = "agent-docs-doctor.inventory.v1"
MAX_READ_BYTES = 2_000_000
MAX_IGNORE_RULES = 10_000
MAX_IGNORE_PATTERN_CHARS = 512
MAX_IGNORE_EVALUATIONS = 2_000_000
MAX_CANDIDATE_FILES = 10_000
MAX_TOTAL_READ_BYTES = 50_000_000
MAX_IMPORT_DEPTH = 10
MAX_WALK_ENTRIES = 100_000
MAX_REFERENCES = 2_000
MAX_REFERENCES_PER_FILE = 500
MAX_PARAGRAPH_BLOCKS = 5_000
MAX_FRONTMATTER_CHARS = 64_000
MAX_FRONTMATTER_FIELDS = 256
MAX_FINDINGS = 2_000
MAX_FINDING_LOCATIONS = 500
MAX_SKIPPED_RECORDS = 5_000
MAX_WARNING_RECORDS = 5_000
MAX_DISPLAY_CHARS = 512
MAX_REPORT_BYTES = 16_000_000
MAX_VALIDATION_ERRORS = 200
MAX_VALIDATION_ERROR_MESSAGE_CHARS = 1_024
MAX_VALIDATION_ERROR_BYTES = 32_000
MAX_VALIDATION_OBJECT_KEYS = 10_000
MAX_VALIDATION_LIST_ITEMS = 10_000
MAX_VALIDATION_NESTED_ITEMS = 20_000

SECRET_NAMES = {
    ".credentials",
    ".env",
    ".npmrc",
    ".pypirc",
    ".secret",
    ".secrets",
    "credentials",
    "credentials.json",
    "secret",
    "secrets",
    "secrets.json",
    "id_rsa",
    "id_ed25519",
    "secrets.yaml",
    "secrets.yml",
}
SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".jks", ".keystore")
DEFAULT_IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    ".next",
    "coverage",
    "fixtures",
    ".fixtures",
    "testdata",
    "__pycache__",
}

EXACT_NAMES = {
    "agents.md",
    "agents.override.md",
    "claude.md",
    "claude.local.md",
    "skill.md",
    "status.md",
    "handoff.md",
    "work_queue.md",
    "work-queue.md",
    "agent_surface_rules.yaml",
    "agent_surface_rules.yml",
}

NAME_HINT_TOKENS = {
    "agent",
    "agents",
    "authority",
    "context",
    "governance",
    "handoff",
    "instruction",
    "instructions",
    "manifest",
    "plan",
    "rule",
    "rules",
    "startup",
    "status",
}

TEXT_SUFFIXES = {".md", ".mdc", ".txt", ".yaml", ".yml", ".json", ".toml"}
ARCHIVE_PARTS = {"archive", "archived", "retired", "deprecated", "history"}
MARKDOWN_LINK_START = re.compile(r"(?<!!)\[[^\]\n]+\]\(")
IMPORT_LINE = re.compile(r"(?m)^\s*@([^\s#]+)\s*$")
TOML_QUOTED_STRING = re.compile(r'"((?:\\.|[^"\\])*)"|\'([^\']*)\'')

SAFE_STATUS_VALUES = frozenset({"active", "current", "retired", "deprecated", "archived", "superseded"})
SAFE_ROLE_VALUES = frozenset(
    {
        "adapter",
        "authority",
        "configuration",
        "current-state",
        "history",
        "procedure",
        "reference",
    }
)


def _bounded_display(value: str, marker: str) -> str:
    unsafe = any(not char.isprintable() for char in value)
    if len(value) <= MAX_DISPLAY_CHARS and not unsafe:
        return value
    digest = hashlib.sha256(value.encode("utf-8", errors="surrogatepass")).hexdigest()
    return f"<{marker}:{digest}>"


def _file_identity(info: os.stat_result) -> tuple[int, int] | None:
    """Return a stable best-effort file identity without exposing path details."""

    device = int(getattr(info, "st_dev", 0))
    inode = int(getattr(info, "st_ino", 0))
    if inode <= 0:
        return None
    return device, inode


def _same_file_snapshot(left: os.stat_result, right: os.stat_result) -> bool:
    left_identity = _file_identity(left)
    right_identity = _file_identity(right)
    identity_matches = (
        left_identity == right_identity
        if left_identity is not None and right_identity is not None
        else stat.S_IFMT(left.st_mode) == stat.S_IFMT(right.st_mode)
    )
    return (
        identity_matches
        and left.st_size == right.st_size
        and getattr(left, "st_mtime_ns", None) == getattr(right, "st_mtime_ns", None)
        and getattr(left, "st_ctime_ns", None) == getattr(right, "st_ctime_ns", None)
        and getattr(left, "st_nlink", None) == getattr(right, "st_nlink", None)
    )


def _descriptor_resolved_path(descriptor: int) -> Path | None:
    """Return a best-effort path for an already opened descriptor."""

    if sys.platform.startswith("linux"):
        try:
            return Path(os.readlink(f"/proc/self/fd/{descriptor}"))
        except OSError:
            return None
    if sys.platform == "darwin":
        try:
            import fcntl

            raw = fcntl.fcntl(descriptor, fcntl.F_GETPATH, b"\0" * 1024)
            return Path(os.fsdecode(raw.split(b"\0", 1)[0]))
        except (AttributeError, OSError, ValueError):
            return None
    if os.name == "nt":  # pragma: no cover - exercised by the hosted Windows matrix
        try:
            import ctypes
            import msvcrt

            handle = msvcrt.get_osfhandle(descriptor)
            buffer = ctypes.create_unicode_buffer(32_768)
            length = ctypes.windll.kernel32.GetFinalPathNameByHandleW(
                handle,
                buffer,
                len(buffer),
                0,
            )
            if length <= 0 or length >= len(buffer):
                return None
            value = buffer.value
            if value.startswith("\\\\?\\UNC\\"):
                value = "\\\\" + value[8:]
            elif value.startswith("\\\\?\\"):
                value = value[4:]
            return Path(value)
        except (AttributeError, OSError, ValueError):
            return None
    return None


def read_bounded_input(
    path: str | Path,
    max_bytes: int,
    *,
    allow_symlink: bool = False,
    allowed_root: Path | None = None,
    forbidden_identities: frozenset[tuple[int, int]] = frozenset(),
) -> bytes:
    """Read one regular file through one nonblocking descriptor.

    The opened descriptor, rather than a pre-open pathname check, is the source
    of truth. Link-count and identity checks fail closed around hard-link
    aliases, and ``O_NOFOLLOW`` prevents a last-moment symlink substitution.
    """

    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 0:
        raise ValueError("max_bytes must be a non-negative integer")
    source = Path(path)
    open_path = source
    resolved_allowed_root = (
        Path(os.path.abspath(os.fspath(allowed_root))) if allowed_root is not None else None
    )
    if resolved_allowed_root is not None:
        try:
            Path(os.path.abspath(os.fspath(source))).relative_to(resolved_allowed_root)
        except ValueError as exc:
            raise ValueError("input path escapes the allowed root") from exc
    try:
        initial = source.lstat()
    except OSError as exc:
        raise OSError(f"unable to inspect input: {exc.__class__.__name__}") from exc
    if stat.S_ISLNK(initial.st_mode):
        if not allow_symlink:
            raise ValueError("symbolic-link input is not allowed")
        try:
            open_path = source.resolve(strict=True)
        except OSError as exc:
            raise OSError(f"unable to resolve input: {exc.__class__.__name__}") from exc
        if resolved_allowed_root is not None:
            try:
                relative_target = PurePosixPath(open_path.relative_to(resolved_allowed_root).as_posix())
            except (OSError, ValueError) as exc:
                raise ValueError("symbolic-link input escapes the allowed root") from exc
            if is_secret_path(relative_target):
                raise ValueError("symbolic-link input targets a secret-like path")
        try:
            expected = open_path.lstat()
        except OSError as exc:
            raise OSError(f"unable to inspect resolved input: {exc.__class__.__name__}") from exc
        if not stat.S_ISREG(expected.st_mode):
            raise ValueError("symbolic-link input does not target a regular file")
    elif not stat.S_ISREG(initial.st_mode):
        raise ValueError("input is not a regular file")
    else:
        expected = initial

    flags = os.O_RDONLY
    flags |= getattr(os, "O_NONBLOCK", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(open_path, flags)
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise ValueError("input is not a regular file")
        if not _same_file_snapshot(expected, opened):
            raise ValueError("input changed before it could be read")
        descriptor_path = _descriptor_resolved_path(descriptor)
        if resolved_allowed_root is not None:
            if descriptor_path is None:
                raise ValueError("opened input location could not be verified")
            actual_path = Path(os.path.abspath(os.fspath(descriptor_path)))
            expected_path = Path(os.path.abspath(os.fspath(open_path)))
            try:
                relative_actual = PurePosixPath(actual_path.relative_to(resolved_allowed_root).as_posix())
            except (OSError, ValueError) as exc:
                raise ValueError("opened input escapes the allowed root") from exc
            if os.path.normcase(os.fspath(actual_path)) != os.path.normcase(os.fspath(expected_path)):
                raise ValueError("opened input path changed while it was being verified")
            if is_secret_path(relative_actual):
                raise ValueError("opened input targets a secret-like path")
        identity = _file_identity(opened)
        if identity is not None and identity in forbidden_identities:
            raise ValueError("input aliases a secret-like file")
        # When a platform reports multiple names but cannot supply a usable
        # identity, and for aliases not known during discovery, failing closed
        # prevents a secret-named hard link from being read through a safe name.
        if int(getattr(opened, "st_nlink", 1)) > 1:
            raise ValueError("hard-linked input is excluded by the never-read boundary")
        size = int(opened.st_size)
        if size > max_bytes:
            raise ValueError(f"input exceeds {max_bytes} byte read limit")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(65_536, max_bytes - total + 1))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes:
                raise ValueError(f"input exceeds {max_bytes} byte read limit")
        final = os.fstat(descriptor)
        if not _same_file_snapshot(opened, final):
            raise ValueError("input changed while it was being read")
        return b"".join(chunks)
    except OSError as exc:
        raise OSError(f"unable to read input: {exc.__class__.__name__}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


@dataclass(frozen=True)
class IgnoreRule:
    pattern: str
    negate: bool
    directory_only: bool
    anchored: bool
    base: PurePosixPath
    restores_defaults: bool


class IgnoreMatcher:
    """Small deterministic gitignore-style matcher for non-git and test repos."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.rules: list[IgnoreRule] = []
        self.skipped: list[dict[str, str]] = []
        self.coverage_reasons: set[str] = set()
        self.traversed_entries = 0
        self.ignore_evaluations = 0
        for filename in (".gitignore", ".ignore", ".agent-docs-doctorignore"):
            path = root / filename
            relative = PurePosixPath(filename)
            try:
                control_info = path.lstat()
            except FileNotFoundError:
                continue
            except OSError:
                self.skipped.append({"path": filename, "reason": "ignore control could not be inspected"})
                self.coverage_reasons.add("ignore control could not be read safely")
                continue
            if filename != ".gitignore" and self.ignored(relative):
                self.skipped.append({"path": filename, "reason": "ignored discovery control not inspected"})
                self.coverage_reasons.add("custom ignored discovery control not inspected")
            elif is_link_like(path):
                self.skipped.append({"path": filename, "reason": "ignore control symlink not followed"})
                self.coverage_reasons.add("ignore control could not be read safely")
            elif stat.S_ISREG(control_info.st_mode) and not is_secret_path(relative):
                self.rules.extend(
                    self._parse(
                        path,
                        PurePosixPath("."),
                        PurePosixPath(filename),
                        restores_defaults=filename == ".agent-docs-doctorignore",
                        remaining_rules=MAX_IGNORE_RULES - len(self.rules),
                        allowed_root=self.root,
                    )
                )
            else:
                self.skipped.append({"path": filename, "reason": "non-regular ignore control not inspected"})
                self.coverage_reasons.add("ignore control could not be read safely")

    @staticmethod
    def _parse(
        path: Path,
        base: PurePosixPath,
        display_path: PurePosixPath,
        restores_defaults: bool,
        remaining_rules: int,
        allowed_root: Path,
    ) -> list[IgnoreRule]:
        rules: list[IgnoreRule] = []
        display = _bounded_display(display_path.as_posix(), "long-relative-path")
        try:
            raw = read_bounded_input(path, MAX_READ_BYTES, allowed_root=allowed_root)
            lines = raw.decode("utf-8").splitlines()
        except UnicodeDecodeError as exc:
            raise ValueError(f"unable to read ignore control {display}: invalid UTF-8") from exc
        except ValueError as exc:
            raise ValueError(f"unable to read ignore control {display}: {exc}") from exc
        except OSError as exc:
            raise ValueError(f"unable to read ignore control {display}: {exc.__class__.__name__}") from exc
        for raw in lines:
            line = raw.strip()
            if not line:
                continue
            escaped_marker = line.startswith(("\\#", "\\!"))
            if escaped_marker:
                line = line[1:]
            elif line.startswith("#"):
                continue
            negate = not escaped_marker and line.startswith("!")
            if negate:
                line = line[1:]
            anchored = line.startswith("/")
            line = line.lstrip("/")
            directory_only = line.endswith("/")
            line = line.rstrip("/")
            if line:
                if len(line) > MAX_IGNORE_PATTERN_CHARS:
                    raise ValueError(
                        f"ignore pattern exceeds {MAX_IGNORE_PATTERN_CHARS} character limit at {display}"
                    )
                if len(rules) >= remaining_rules:
                    raise ValueError(
                        f"ignore controls exceed aggregate {MAX_IGNORE_RULES} rule limit at {display}"
                    )
                rules.append(
                    IgnoreRule(
                        line,
                        negate,
                        directory_only,
                        anchored,
                        base,
                        restores_defaults,
                    )
                )
        return rules

    def add_nested_gitignore(self, directory: Path, relative: PurePosixPath) -> bool:
        if relative == PurePosixPath("."):
            return True
        path = directory / ".gitignore"
        control_relative = PurePosixPath(relative / ".gitignore")
        try:
            control_info = path.lstat()
        except FileNotFoundError:
            return True
        except OSError:
            self.skipped.append(
                {
                    "path": control_relative.as_posix(),
                    "reason": "ignore control could not be inspected",
                }
            )
            self.coverage_reasons.add("ignore control could not be read safely")
            return False
        if self.ignored(control_relative):
            self.skipped.append(
                {
                    "path": control_relative.as_posix(),
                    "reason": "ignored discovery control not inspected",
                }
            )
            self.coverage_reasons.add("custom ignored discovery control not inspected")
            return False
        if is_link_like(path):
            self.skipped.append(
                {
                    "path": control_relative.as_posix(),
                    "reason": "ignore control symlink not followed",
                }
            )
            self.coverage_reasons.add("ignore control could not be read safely")
            return False
        if stat.S_ISREG(control_info.st_mode):
            self.rules.extend(
                self._parse(
                    path,
                    relative,
                    control_relative,
                    restores_defaults=False,
                    remaining_rules=MAX_IGNORE_RULES - len(self.rules),
                    allowed_root=self.root,
                )
            )
            return True
        self.skipped.append(
            {
                "path": control_relative.as_posix(),
                "reason": "non-regular ignore control not inspected",
            }
        )
        self.coverage_reasons.add("ignore control could not be read safely")
        return False

    def ignored(self, relative: PurePosixPath, is_dir: bool = False) -> bool:
        parts = relative.parts
        default_ignored = any(part in DEFAULT_IGNORED_DIRS for part in parts)
        ignored = default_ignored
        for rule in self.rules:
            if self.ignore_evaluations >= MAX_IGNORE_EVALUATIONS:
                self.coverage_reasons.add("ignore rule evaluation budget exceeded")
                return True
            self.ignore_evaluations += 1
            try:
                scoped = relative.relative_to(rule.base)
            except ValueError:
                continue
            scoped_text = scoped.as_posix()
            scoped_parts = scoped.parts
            if rule.directory_only:
                if rule.anchored or "/" in rule.pattern:
                    directory_parts = scoped_parts if is_dir else scoped_parts[:-1]
                    directory_paths = (
                        PurePosixPath(*directory_parts[:index]).as_posix()
                        for index in range(1, len(directory_parts) + 1)
                    )
                    matched = any(path_pattern_matches(path, rule.pattern) for path in directory_paths)
                else:
                    directory_parts = scoped_parts if is_dir else scoped_parts[:-1]
                    matched = any(fnmatch.fnmatchcase(part, rule.pattern) for part in directory_parts)
            elif rule.anchored or "/" in rule.pattern:
                matched = path_pattern_matches(scoped_text, rule.pattern)
            else:
                matched = any(fnmatch.fnmatchcase(part, rule.pattern) for part in scoped_parts)
            if matched:
                if rule.negate and default_ignored and not rule.restores_defaults:
                    continue
                ignored = not rule.negate
        return ignored


def path_pattern_matches(path: str, pattern: str) -> bool:
    """Match slash-separated ignore patterns without letting * cross a slash."""

    path_parts = PurePosixPath(path).parts
    pattern_parts = PurePosixPath(pattern).parts
    reachable = {0}
    for pattern_index, segment in enumerate(pattern_parts):
        if not reachable:
            return False
        if segment == "**":
            if pattern_index == len(pattern_parts) - 1:
                return any(path_index < len(path_parts) for path_index in reachable)
            earliest = min(reachable)
            reachable = set(range(earliest, len(path_parts) + 1))
            continue
        reachable = {
            path_index + 1
            for path_index in reachable
            if path_index < len(path_parts) and fnmatch.fnmatchcase(path_parts[path_index], segment)
        }
    return len(path_parts) in reachable


def name_tokens(stem: str) -> set[str]:
    separated = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", stem)
    separated = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", separated)
    return set(re.findall(r"[A-Za-z0-9]+", separated.lower()))


def name_has_hint(stem: str) -> bool:
    tokens = name_tokens(stem)
    return bool(
        tokens & NAME_HINT_TOKENS
        or {"work", "queue"}.issubset(tokens)
        or {"current", "state"}.issubset(tokens)
        or ("model" in tokens and bool(tokens & {"config", "configs"}))
    )


def in_rules_tree(parts: tuple[str, ...], platform_directory: str) -> bool:
    return any(parts[index : index + 2] == (platform_directory, "rules") for index in range(len(parts) - 1))


def is_secret_path(path: Path | PurePosixPath) -> bool:
    for part in path.parts:
        name = part.lower()
        if name in SECRET_NAMES or name.startswith(".env.") or name.endswith(SECRET_SUFFIXES):
            return True
    return False


def is_link_like(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        if callable(is_junction) and is_junction():
            return True
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        return bool(attributes & reparse_flag)
    except OSError:
        return False


def _stat_is_reparse_point(value: os.stat_result) -> bool:
    attributes = getattr(value, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_flag)


def _open_pinned_directory(path: Path, allowed_root: Path) -> tuple[int | Path, Any]:
    """Pin a directory against path replacement for one bounded enumeration."""

    if os.name != "nt":
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_DIRECTORY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISDIR(opened.st_mode):
                raise OSError("filesystem entry is not a directory")
            descriptor_path = _descriptor_resolved_path(descriptor)
            if descriptor_path is None:
                raise OSError("pinned directory location could not be verified")
            actual = Path(os.path.abspath(os.fspath(descriptor_path)))
            expected = Path(os.path.abspath(os.fspath(path)))
            try:
                actual.relative_to(Path(os.path.abspath(os.fspath(allowed_root))))
            except ValueError as exc:
                raise OSError("pinned directory escapes the allowed root") from exc
            if os.path.normcase(os.fspath(actual)) != os.path.normcase(os.fspath(expected)):
                raise OSError("directory path changed while it was being pinned")
        except (OSError, ValueError):
            os.close(descriptor)
            raise
        return descriptor, lambda: os.close(descriptor)

    # Windows lacks dir_fd support for scandir. Hold a native directory handle
    # without FILE_SHARE_DELETE so the verified path cannot be exchanged while
    # path-based enumeration is in progress.
    try:  # pragma: no cover - exercised by the hosted Windows matrix
        import ctypes
        from ctypes import wintypes

        create_file = ctypes.windll.kernel32.CreateFileW
        create_file.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        create_file.restype = wintypes.HANDLE
        handle = create_file(
            os.fspath(path),
            0x80,  # FILE_READ_ATTRIBUTES
            0x1 | 0x2,  # FILE_SHARE_READ | FILE_SHARE_WRITE
            None,
            3,  # OPEN_EXISTING
            0x02000000 | 0x00200000,  # BACKUP_SEMANTICS | OPEN_REPARSE_POINT
            None,
        )
        invalid_handle = ctypes.c_void_p(-1).value
        if handle in (None, invalid_handle):
            raise OSError("directory could not be pinned")

        buffer = ctypes.create_unicode_buffer(32_768)
        length = ctypes.windll.kernel32.GetFinalPathNameByHandleW(
            handle,
            buffer,
            len(buffer),
            0,
        )
        if length <= 0 or length >= len(buffer):
            ctypes.windll.kernel32.CloseHandle(handle)
            raise OSError("pinned directory path could not be verified")
        actual_path = buffer.value
        if actual_path.startswith("\\\\?\\UNC\\"):
            actual_path = "\\\\" + actual_path[8:]
        elif actual_path.startswith("\\\\?\\"):
            actual_path = actual_path[4:]
        actual = Path(os.path.abspath(actual_path))
        expected = Path(os.path.abspath(os.fspath(path)))
        try:
            actual.relative_to(Path(os.path.abspath(os.fspath(allowed_root))))
        except ValueError:
            ctypes.windll.kernel32.CloseHandle(handle)
            raise OSError("pinned directory escaped the audit root") from None
        if os.path.normcase(os.fspath(actual)) != os.path.normcase(os.fspath(expected)):
            ctypes.windll.kernel32.CloseHandle(handle)
            raise OSError("directory path contains an alias or changed while opening")

        attributes = ctypes.windll.kernel32.GetFileAttributesW(os.fspath(path))
        if attributes == 0xFFFFFFFF or not attributes & 0x10 or attributes & 0x400:
            ctypes.windll.kernel32.CloseHandle(handle)
            raise OSError("filesystem entry is not a safe directory")

        def close_handle() -> None:
            ctypes.windll.kernel32.CloseHandle(handle)

        return path, close_handle
    except (AttributeError, OSError, ValueError) as exc:
        raise OSError("directory could not be pinned safely") from exc


def is_candidate(relative: PurePosixPath, fallback_names: frozenset[str] = frozenset()) -> bool:
    if is_secret_path(relative):
        return False
    name = relative.name.lower()
    suffix = relative.suffix.lower()
    parts_lower = tuple(part.lower() for part in relative.parts)
    if name in EXACT_NAMES:
        return True
    if relative.name in fallback_names:
        return True
    if in_rules_tree(parts_lower, ".claude") or in_rules_tree(parts_lower, ".cursor"):
        return suffix in {".md", ".mdc"}
    if name == "config.toml" and ".codex" in parts_lower:
        return True
    if name in {"settings.json", "settings.local.json"} and ".claude" in parts_lower:
        return True
    if name in {".cursorignore", ".cursorindexingignore"}:
        return True
    return suffix in TEXT_SUFFIXES and name_has_hint(relative.stem)


def is_discovery_control(relative: PurePosixPath) -> bool:
    return (
        relative.name.lower()
        in {
            ".agent-docs-doctorignore",
            ".gitignore",
            ".ignore",
        }
        or relative.as_posix().lower() == ".codex/config.toml"
    )


def _visible_toml_lines(text: str) -> Iterator[str]:
    """Yield TOML outside comments and multiline strings, preserving quotes."""

    multiline: str | None = None
    for raw_line in io.StringIO(text):
        line = raw_line.rstrip("\r\n")
        visible: list[str] = []
        index = 0
        quote: str | None = None
        escaped = False
        while index < len(line):
            if multiline is not None:
                closing = line.find(multiline, index)
                if closing < 0:
                    index = len(line)
                    continue
                index = closing + 3
                multiline = None
                continue
            char = line[index]
            if quote is not None:
                visible.append(char)
                if quote == '"' and escaped:
                    escaped = False
                elif quote == '"' and char == "\\":
                    escaped = True
                elif char == quote:
                    quote = None
                index += 1
                continue
            if char == "#":
                break
            triple = line[index : index + 3]
            if triple in {'"""', "'''"}:
                multiline = triple
                index += 3
                continue
            if char in {'"', "'"}:
                quote = char
            visible.append(char)
            index += 1
        yield "".join(visible)


def _fallback_names_from_toml(text: str) -> tuple[str, ...]:
    key = "project_doc_fallback_filenames"
    values: Any = None
    if tomllib is not None:
        try:
            parsed = tomllib.loads(text)
        except (tomllib.TOMLDecodeError, MemoryError, RecursionError):
            parsed = None
        if isinstance(parsed, dict):
            values = parsed.get(key)
    if values is None:
        assignment = re.compile(rf"^\s*{re.escape(key)}\s*=\s*\[(.*)$")
        at_top_level = True
        visible_lines = iter(_visible_toml_lines(text))
        for line in visible_lines:
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                at_top_level = False
                continue
            match = assignment.match(line) if at_top_level else None
            if match:
                payload_lines = [match.group(1)]
                while not re.search(r"\]\s*$", payload_lines[-1]):
                    try:
                        continuation = next(visible_lines)
                    except StopIteration:
                        break
                    payload_lines.append(continuation)
                payload = "\n".join(payload_lines)
                closing = re.search(r"\]\s*$", payload)
                if closing is None:
                    break
                payload = payload[: closing.start()]
                values = []
                for double_quoted, single_quoted in TOML_QUOTED_STRING.findall(payload):
                    try:
                        value = (
                            json.JSONDecoder().decode(f'"{double_quoted}"')
                            if double_quoted
                            else single_quoted
                        )
                    except json.JSONDecodeError:
                        continue
                    values.append(value)
                break
    if not isinstance(values, list):
        return ()
    names: list[str] = []
    for value in values:
        if (
            isinstance(value, str)
            and value
            and Path(value).name == value
            and not is_secret_path(PurePosixPath(value))
        ):
            names.append(value)
    return tuple(dict.fromkeys(names))


def codex_fallback_filenames(root: Path) -> tuple[str, ...]:
    path = root / ".codex" / "config.toml"
    matcher = IgnoreMatcher(root)
    if matcher.ignored(PurePosixPath(".codex/config.toml")):
        return ()
    try:
        config_info = path.lstat()
    except OSError:
        return ()
    text, _, _, warning = (
        read_text(path, root=root, matcher=matcher)
        if stat.S_ISREG(config_info.st_mode) and not is_link_like(path)
        else (None, None, None, None)
    )
    if text is None or warning:
        return ()
    return _fallback_names_from_toml(text)


def walk_candidates(
    root: Path,
    fallback_names: frozenset[str],
) -> tuple[list[Path], list[dict[str, str]], IgnoreMatcher, bool]:
    matcher = IgnoreMatcher(root)
    candidates: list[Path] = []
    symlink_candidates: list[Path] = []
    skipped = matcher.skipped
    incomplete = False
    secret_identities: set[tuple[int, int]] = set()

    def walk_error(path: Path, exc: OSError) -> None:
        nonlocal incomplete
        incomplete = True
        matcher.coverage_reasons.add("filesystem traversal error")
        display_path = "."
        with suppress(OSError, ValueError):
            display_path = path.relative_to(root).as_posix()
        skipped.append({"path": display_path, "reason": f"walk error: {exc.__class__.__name__}"})

    stop_walk = False
    directories = [root]
    while directories and not stop_walk:
        current_path = directories.pop()
        rel_current = current_path.relative_to(root)
        try:
            scan_target, close_pinned = _open_pinned_directory(current_path, root)
        except OSError as exc:
            walk_error(current_path, exc)
            continue
        entry_records: list[tuple[str, os.stat_result | None, bool]] = []
        overflow = False
        try:
            if not matcher.add_nested_gitignore(
                current_path,
                PurePosixPath(rel_current.as_posix()),
            ):
                incomplete = True
                continue
            remaining = MAX_WALK_ENTRIES - matcher.traversed_entries
            with os.scandir(scan_target) as entries:
                for entry in entries:
                    if len(entry_records) >= remaining:
                        overflow = True
                        break
                    try:
                        entry_info = entry.stat(follow_symlinks=False)
                        link_like = entry.is_symlink() or _stat_is_reparse_point(entry_info)
                    except OSError:
                        entry_info = None
                        link_like = False
                    entry_records.append((entry.name, entry_info, link_like))
            try:
                current_info = current_path.lstat()
                if isinstance(scan_target, int):
                    pinned_info = os.fstat(scan_target)
                    directory_changed = not stat.S_ISDIR(current_info.st_mode) or not _same_file_snapshot(
                        pinned_info, current_info
                    )
                else:
                    directory_changed = (
                        not stat.S_ISDIR(current_info.st_mode)
                        or is_link_like(current_path)
                        or _stat_is_reparse_point(current_info)
                    )
            except OSError:
                directory_changed = True
            if directory_changed:
                entry_records.clear()
                incomplete = True
                matcher.coverage_reasons.add("directory changed during traversal")
                skipped.append(
                    {
                        "path": PurePosixPath(rel_current.as_posix()).as_posix(),
                        "reason": "directory changed during traversal",
                    }
                )
        except OSError as exc:
            walk_error(current_path, exc)
            continue
        finally:
            with suppress(OSError):
                close_pinned()
        if overflow:
            matcher.traversed_entries = MAX_WALK_ENTRIES
            incomplete = True
            stop_walk = True
            matcher.coverage_reasons.add("filesystem entry budget exceeded")
            break
        matcher.traversed_entries += len(entry_records)

        kept_dirs: list[Path] = []
        file_paths: list[tuple[Path, os.stat_result]] = []
        for name, entry_info, link_like in sorted(entry_records, key=lambda item: item[0]):
            path = current_path / name
            if entry_info is None:
                display = PurePosixPath(path.relative_to(root).as_posix())
                skipped.append(
                    {
                        "path": display.as_posix(),
                        "reason": "filesystem entry could not be inspected",
                    }
                )
                incomplete = True
                matcher.coverage_reasons.add("filesystem entry inspection failed")
                continue
            rel = PurePosixPath(path.relative_to(root).as_posix())
            if link_like:
                ignored = matcher.ignored(rel, is_dir=True) or matcher.ignored(rel)
                default_ignored = any(part in DEFAULT_IGNORED_DIRS for part in rel.parts)
                if ignored and default_ignored:
                    skipped.append({"path": rel.as_posix(), "reason": "default excluded directory"})
                elif ignored and is_candidate(rel, fallback_names):
                    skipped.append({"path": rel.as_posix(), "reason": "ignored candidate not inspected"})
                    incomplete = True
                    matcher.coverage_reasons.add("custom ignored candidate not inspected")
                elif ignored:
                    if not (
                        is_discovery_control(rel) and any(item["path"] == rel.as_posix() for item in skipped)
                    ):
                        skipped.append(
                            {
                                "path": rel.as_posix(),
                                "reason": "ignored linked filesystem entry not inspected",
                            }
                        )
                    incomplete = True
                    matcher.coverage_reasons.add("custom ignored filesystem entry not inspected")
                elif is_candidate(rel, fallback_names):
                    symlink_candidates.append(path)
                elif is_discovery_control(rel) and any(item["path"] == rel.as_posix() for item in skipped):
                    continue
                else:
                    skipped.append(
                        {
                            "path": rel.as_posix(),
                            "reason": "symlink or reparse filesystem entry not followed",
                        }
                    )
                    incomplete = True
                    matcher.coverage_reasons.add("linked filesystem entry not inspected")
                continue
            if stat.S_ISDIR(entry_info.st_mode):
                if is_secret_path(rel):
                    skipped.append(
                        {
                            "path": _bounded_display(rel.as_posix(), "secret-like-path"),
                            "reason": "secret-like directory not inspected",
                        }
                    )
                    continue
                ignored = matcher.ignored(rel, is_dir=True)
                default_ignored = any(part in DEFAULT_IGNORED_DIRS for part in rel.parts)
                if ignored and default_ignored:
                    skipped.append({"path": rel.as_posix(), "reason": "default excluded directory"})
                    continue
                if ignored:
                    skipped.append({"path": rel.as_posix(), "reason": "ignored directory not inspected"})
                    incomplete = True
                    matcher.coverage_reasons.add("custom ignored directory not inspected")
                    continue
                kept_dirs.append(path)
            else:
                file_paths.append((path, entry_info))
        directories.extend(reversed(kept_dirs))

        for path, discovered_info in file_paths:
            rel = PurePosixPath(path.relative_to(root).as_posix())
            ignored = matcher.ignored(rel)
            if ignored:
                if is_candidate(rel, fallback_names):
                    skipped.append({"path": rel.as_posix(), "reason": "ignored candidate not inspected"})
                    incomplete = True
                    matcher.coverage_reasons.add("custom ignored candidate not inspected")
                elif is_discovery_control(rel):
                    if not any(
                        item["path"] == rel.as_posix()
                        and item["reason"] == "ignored discovery control not inspected"
                        for item in skipped
                    ):
                        skipped.append(
                            {
                                "path": rel.as_posix(),
                                "reason": "ignored discovery control not inspected",
                            }
                        )
                    incomplete = True
                    matcher.coverage_reasons.add("custom ignored discovery control not inspected")
                continue
            if is_secret_path(rel):
                if stat.S_ISREG(discovered_info.st_mode):
                    identity = _file_identity(discovered_info)
                    if identity is not None:
                        secret_identities.add(identity)
                if name_has_hint(rel.stem) or rel.name.lower() in EXACT_NAMES:
                    skipped.append({"path": rel.as_posix(), "reason": "secret-like filename"})
                continue
            if not is_candidate(rel, fallback_names):
                continue
            if not stat.S_ISREG(discovered_info.st_mode):
                skipped.append({"path": rel.as_posix(), "reason": "non-regular filesystem entry"})
                incomplete = True
                matcher.coverage_reasons.add("candidate was not a readable regular file")
                continue
            identity = _file_identity(discovered_info)
            if int(getattr(discovered_info, "st_nlink", 1)) > 1 or (
                identity is not None and identity in secret_identities
            ):
                skipped.append(
                    {
                        "path": rel.as_posix(),
                        "reason": "hard-linked candidate excluded by never-read boundary",
                    }
                )
                incomplete = True
                matcher.coverage_reasons.add("hard-linked candidate not inspected")
                continue
            if len(candidates) >= MAX_CANDIDATE_FILES:
                incomplete = True
                matcher.coverage_reasons.add("candidate file budget exceeded")
                continue
            candidates.append(path)

    for path in symlink_candidates:
        rel = PurePosixPath(path.relative_to(root).as_posix())
        try:
            resolved = path.resolve(strict=True)
            target_relative = PurePosixPath(resolved.relative_to(root.resolve()).as_posix())
        except FileNotFoundError:
            skipped.append({"path": rel.as_posix(), "reason": "symlink target does not exist"})
            incomplete = True
            matcher.coverage_reasons.add("linked candidate not inspected")
            continue
        except (OSError, ValueError):
            skipped.append({"path": rel.as_posix(), "reason": "symlink escapes audit root"})
            incomplete = True
            matcher.coverage_reasons.add("linked candidate not inspected")
            continue
        if (
            is_secret_path(target_relative)
            or matcher.ignored(target_relative)
            or not resolved.is_file()
            or not is_candidate(target_relative, fallback_names)
        ):
            skipped.append({"path": rel.as_posix(), "reason": "symlink target excluded from audit"})
            incomplete = True
            matcher.coverage_reasons.add("linked candidate not inspected")
            continue
        try:
            target_info = resolved.stat()
        except OSError:
            skipped.append({"path": rel.as_posix(), "reason": "symlink target became unavailable"})
            incomplete = True
            matcher.coverage_reasons.add("candidate changed during discovery")
            continue
        target_identity = _file_identity(target_info)
        if int(getattr(target_info, "st_nlink", 1)) > 1 or (
            target_identity is not None and target_identity in secret_identities
        ):
            skipped.append(
                {
                    "path": rel.as_posix(),
                    "reason": "hard-linked symlink target excluded by never-read boundary",
                }
            )
            incomplete = True
            matcher.coverage_reasons.add("hard-linked candidate not inspected")
            continue
        if len(candidates) >= MAX_CANDIDATE_FILES:
            incomplete = True
            matcher.coverage_reasons.add("candidate file budget exceeded")
            continue
        candidates.append(path)
    if stop_walk:
        skipped.append({"path": ".", "reason": "filesystem entry budget exceeded"})
    candidates.sort(key=lambda p: p.relative_to(root).as_posix())
    skipped.sort(key=lambda item: item["path"])
    return candidates, skipped, matcher, incomplete


def read_text(
    path: Path,
    *,
    max_bytes: int = MAX_READ_BYTES,
    root: Path | None = None,
    matcher: IgnoreMatcher | None = None,
    forbidden_identities: frozenset[tuple[int, int]] = frozenset(),
) -> tuple[str | None, str | None, int | None, str | None]:
    try:
        read_path = path
        if path.is_symlink():
            if root is None:
                raise ValueError("symbolic-link file requires an allowed root")
            resolved = path.resolve(strict=True)
            target_relative = PurePosixPath(resolved.relative_to(root.resolve()).as_posix())
            if is_secret_path(target_relative):
                raise ValueError("symbolic-link file targets a secret-like path")
            if matcher is not None and matcher.ignored(target_relative):
                raise ValueError("symbolic-link input targets an ignored path")
            read_path = resolved
        raw = read_bounded_input(
            read_path,
            max_bytes,
            allow_symlink=False,
            allowed_root=root,
            forbidden_identities=forbidden_identities,
        )
        decode_warning = None
        try:
            decoded = raw.decode("utf-8")
        except UnicodeDecodeError:
            decoded = raw.decode("utf-8", errors="replace")
            decode_warning = "invalid UTF-8 replaced during decoding"
        text = decoded.replace("\r\n", "\n").replace("\r", "\n")
        return text, hashlib.sha256(raw).hexdigest(), len(raw), decode_warning
    except ValueError as exc:
        try:
            size = path.lstat().st_size
        except OSError:
            size = None
        message = str(exc).replace("input", "file")
        return None, None, size, message
    except OSError as exc:
        return None, None, None, f"unable to read: {exc.__class__.__name__}"


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str | None]:
    if not text.startswith("---\n"):
        return {}, None
    closing = re.search(r"(?m)^---[ \t]*(?:\n|$)", text[4:])
    if closing is None:
        return {}, "unclosed YAML frontmatter"
    end = 4 + closing.start()
    if end - 4 > MAX_FRONTMATTER_CHARS:
        return {}, f"frontmatter exceeds {MAX_FRONTMATTER_CHARS} character limit"
    metadata: dict[str, Any] = {}
    fields = 0
    for number, raw_line in enumerate(io.StringIO(text[4:end]), start=2):
        raw = raw_line.rstrip("\r\n")
        if not raw.strip() or raw.lstrip().startswith("#") or raw.startswith((" ", "\t", "-")):
            continue
        if ":" not in raw:
            return metadata, f"malformed frontmatter at line {number}"
        key, value = raw.split(":", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if not key:
            return metadata, f"empty frontmatter key at line {number}"
        fields += 1
        if fields > MAX_FRONTMATTER_FIELDS:
            return {}, f"frontmatter exceeds {MAX_FRONTMATTER_FIELDS} field limit"
        lowered = value.lower()
        if lowered in {"true", "false"}:
            metadata[key] = lowered == "true"
        elif lowered in {"null", "none", "~"}:
            metadata[key] = None
        else:
            metadata[key] = value
    return metadata, None


def public_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Return classification signals without carrying arbitrary user content."""

    public: dict[str, Any] = {}
    always_apply = metadata.get("alwaysApply")
    if isinstance(always_apply, bool):
        public["alwaysApply"] = always_apply
    retired = metadata.get("retired")
    if isinstance(retired, bool):
        public["retired"] = retired
    status = metadata.get("status")
    if isinstance(status, str) and status.lower() in SAFE_STATUS_VALUES:
        public["status"] = status.lower()
    role = metadata.get("role")
    if isinstance(role, str) and role.lower() in SAFE_ROLE_VALUES:
        public["role"] = role.lower()
    for key in ("description", "globs", "paths"):
        if key in metadata:
            public[f"has_{key}"] = bool(metadata[key])
    return public


def classify(
    relative: PurePosixPath,
    metadata: dict[str, Any],
    fallback_names: frozenset[str],
    selected_codex_paths: frozenset[str],
) -> dict[str, Any]:
    name = relative.name.lower()
    tokens = name_tokens(relative.stem)
    parts = tuple(part.lower() for part in relative.parts)
    archive = any(part in ARCHIVE_PARTS for part in parts[:-1])
    status_value = str(metadata.get("status", "")).lower()
    retired = status_value in {"retired", "deprecated", "archived", "superseded"} or bool(
        metadata.get("retired")
    )

    relative_text = relative.as_posix()
    selected_by_codex = relative_text in selected_codex_paths

    if name == "agents.override.md":
        kind, platforms, loading, role = "instruction", ["codex"], "automatic", "authority"
    elif name == "agents.md":
        platforms = ["cursor"] + (["codex"] if selected_by_codex else [])
        kind, loading, role = "instruction", "automatic", "authority"
    elif relative.name in fallback_names:
        kind, platforms = "instruction-candidate", ["codex"]
        loading = "automatic" if selected_by_codex else "not-loaded"
        role = "authority" if selected_by_codex else "reference"
    elif name in {"claude.md", "claude.local.md"}:
        kind, platforms, loading, role = "instruction", ["claude-code"], "automatic", "adapter"
    elif in_rules_tree(parts, ".claude"):
        scoped = "paths" in metadata
        kind, platforms, loading, role = (
            "scoped-rule",
            ["claude-code"],
            "conditional" if scoped else "automatic",
            "procedure",
        )
    elif in_rules_tree(parts, ".cursor"):
        if relative.suffix.lower() != ".mdc":
            kind, platforms, loading, role = "rule-like-file", ["cursor"], "not-loaded", "reference"
        else:
            always = str(metadata.get("alwaysApply", "")).lower() == "true"
            conditional = "globs" in metadata or bool(metadata.get("description"))
            load_mode = "automatic" if always else "conditional" if conditional else "manual"
            kind, platforms, loading, role = "scoped-rule", ["cursor"], load_mode, "procedure"
    elif name == "skill.md":
        kind, platforms, loading, role = "skill", ["agent-skills"], "conditional", "procedure"
    elif "status" in tokens or "handoff" in tokens or {"work", "queue"}.issubset(tokens):
        kind, platforms, loading, role = "state", [], "manual", "current-state"
    elif archive or retired:
        kind, platforms, loading, role = "history", [], "manual", "history"
    elif name.endswith((".json", ".yaml", ".yml", ".toml")):
        kind, platforms, loading, role = "configuration", [], "platform-dependent", "configuration"
    else:
        kind, platforms, loading, role = "reference", [], "manual", "reference"
    metadata_role = metadata.get("role")
    if isinstance(metadata_role, str) and metadata_role.lower() in SAFE_ROLE_VALUES:
        role = metadata_role.lower()
    return {
        "kind": kind,
        "platforms": platforms,
        "loading": loading,
        "role": role,
        "archive": archive,
        "retired_metadata": retired,
        "classification_basis": "filename-and-metadata inference",
    }


def line_for_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def column_for_offset(text: str, offset: int) -> int:
    return offset - text.rfind("\n", 0, offset)


def mask_fenced_code(text: str) -> str:
    """Mask Markdown fenced code while preserving offsets and line structure."""

    masked = list(text)
    opener = re.compile(r"(?m)^ {0,3}(`{3,}|~{3,})[^\n]*(?:\n|$)")
    search_from = 0
    while match := opener.search(text, search_from):
        fence = match.group(1)
        closer = re.compile(rf"(?m)^ {{0,3}}{re.escape(fence[0])}{{{len(fence)},}}[ \t]*(?:\n|$)")
        closing_match = closer.search(text, match.end())
        end = closing_match.end() if closing_match else len(text)
        for index in range(match.start(), end):
            if masked[index] != "\n":
                masked[index] = " "
        search_from = end
    return "".join(masked)


def markdown_link_payloads(text: str) -> Iterator[tuple[str, int]]:
    offset = 0
    for line in io.StringIO(text):
        search_from = 0
        while match := MARKDOWN_LINK_START.search(line, search_from):
            index = match.end()
            start = index
            depth = 1
            escaped = False
            while index < len(line) and line[index] not in "\r\n":
                char = line[index]
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == "(":
                    depth += 1
                elif char == ")":
                    depth -= 1
                    if depth == 0:
                        yield line[start:index], offset + match.start()
                        search_from = index + 1
                        break
                index += 1
            else:
                break
            if depth != 0:
                break
        offset += len(line)


def markdown_destination(payload: str) -> str:
    value = payload.strip()
    if value.startswith("<") and ">" in value:
        return value[1 : value.index(">")]
    escaped = False
    for index, char in enumerate(value):
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char.isspace():
            return value[:index]
    return value


def sanitized_reference_target(target: str) -> tuple[str, str | None, str]:
    if "\x00" in target:
        digest = hashlib.sha256(target.encode("utf-8")).hexdigest()
        return "<invalid-filesystem-path>", digest, "invalid-filesystem"
    if re.match(r"^file:", target, re.IGNORECASE):
        digest = hashlib.sha256(target.encode("utf-8")).hexdigest()
        return "<absolute-filesystem-path>", digest, "absolute-filesystem"
    if re.match(r"^[A-Za-z]:[\\/]", target):
        digest = hashlib.sha256(target.encode("utf-8")).hexdigest()
        return "<absolute-filesystem-path>", digest, "absolute-filesystem"
    if re.match(r"^~[^/\\]*[/\\]", target) or target.startswith(("//", "\\")):
        digest = hashlib.sha256(target.encode("utf-8")).hexdigest()
        return "<absolute-filesystem-path>", digest, "absolute-filesystem"
    if target.startswith("/"):
        digest = hashlib.sha256(target.encode("utf-8")).hexdigest()
        return "<root-relative-path>", digest, "root-relative"
    if len(target) > MAX_DISPLAY_CHARS:
        digest = hashlib.sha256(target.encode("utf-8")).hexdigest()
        return "<long-reference-target>", digest, "long-relative"
    return target, None, "relative"


def _reference_candidate(
    target: str,
    relative: PurePosixPath,
    root: Path,
) -> tuple[Path | None, PurePosixPath | None, bool | None, bool | None]:
    """Resolve a local target without opening it.

    Returns the absolute candidate, its root-relative path, whether it is inside
    the audit root, and whether it exists. Absolute home/drive/UNC paths are
    intentionally out of scope and never resolved.
    """

    _, _, target_kind = sanitized_reference_target(target)
    if target_kind in {"absolute-filesystem", "invalid-filesystem"}:
        return None, None, False, None
    if target_kind in {"relative", "long-relative"} and re.match(
        r"^[a-z][a-z0-9+.-]*:",
        target,
        re.IGNORECASE,
    ):
        return None, None, None, None
    resolved_root = Path(os.path.abspath(os.fspath(root)))
    try:
        unresolved = root / target.lstrip("/") if target.startswith("/") else root / relative.parent / target
        lexical_candidate = Path(os.path.abspath(os.fspath(unresolved)))
        lexical_relative = PurePosixPath(lexical_candidate.relative_to(resolved_root).as_posix())
    except (OSError, ValueError):
        return None, None, False, None
    if is_secret_path(lexical_relative):
        return None, lexical_relative, True, None
    try:
        candidate = lexical_candidate.resolve()
        relative_candidate = PurePosixPath(candidate.relative_to(resolved_root).as_posix())
    except (OSError, ValueError):
        return None, None, False, None
    if is_secret_path(relative_candidate):
        return None, relative_candidate, True, None
    try:
        exists = candidate.exists()
    except (OSError, ValueError):
        exists = None
    return candidate, relative_candidate, True, exists


def _automatic_imports(text: str, limit: int = MAX_REFERENCES_PER_FILE) -> Iterator[tuple[str, int]]:
    scan_text = mask_fenced_code(text)
    for index, match in enumerate(IMPORT_LINE.finditer(scan_text)):
        if index >= limit:
            return
        target = match.group(1).strip().split("#", 1)[0]
        if target:
            yield target, match.start()


@dataclass
class ScanBudget:
    references: int = 0
    paragraph_blocks: int = 0
    references_truncated: bool = False
    paragraph_blocks_truncated: bool = False


def local_references(
    text: str,
    relative: PurePosixPath,
    root: Path,
    inventoried_paths: frozenset[PurePosixPath] = frozenset(),
    import_exclusions: dict[PurePosixPath, str] | None = None,
    recognize_imports: bool = False,
    budget: ScanBudget | None = None,
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    scan_budget = budget if budget is not None else ScanBudget()
    scan_text = mask_fenced_code(text)
    raw_matches: list[tuple[str, int, str]] = []
    markdown_overflow = False
    for index, (raw, start) in enumerate(markdown_link_payloads(scan_text)):
        if index >= MAX_REFERENCES_PER_FILE:
            markdown_overflow = True
            break
        raw_matches.append((markdown_destination(raw), start, "markdown-link"))
    import_overflow = False
    for index, match in enumerate(IMPORT_LINE.finditer(scan_text)):
        if index >= MAX_REFERENCES_PER_FILE:
            import_overflow = True
            break
        raw_matches.append(
            (
                match.group(1).strip(),
                match.start(),
                "automatic-import" if recognize_imports else "at-reference",
            )
        )
    file_references = 0
    for raw, start, edge_type in sorted(raw_matches, key=lambda item: (item[1], item[2])):
        if file_references >= MAX_REFERENCES_PER_FILE or scan_budget.references >= MAX_REFERENCES:
            scan_budget.references_truncated = True
            break
        target = raw.split("#", 1)[0]
        if not target or target.startswith("#"):
            continue
        display_target, target_sha256, target_kind = sanitized_reference_target(target)
        if target_kind in {"relative", "long-relative"} and re.match(
            r"^[a-z][a-z0-9+.-]*:",
            target,
            re.IGNORECASE,
        ):
            continue
        candidate, relative_candidate, inside, exists = _reference_candidate(target, relative, root)
        if relative_candidate is not None and is_secret_path(relative_candidate):
            display_target = "<secret-like-path>"
            target_sha256 = hashlib.sha256(target.encode("utf-8")).hexdigest()
            target_kind = "secret-like"
        if inside is False and target_kind in {"relative", "root-relative"}:
            display_target = "<out-of-root-path>"
            target_sha256 = hashlib.sha256(target.encode("utf-8")).hexdigest()
            target_kind = "out-of-root"
        if (
            candidate is None
            and inside is False
            and target_kind
            not in {
                "absolute-filesystem",
                "out-of-root",
                "root-relative",
            }
        ):
            display_target = "<invalid-filesystem-path>"
            target_sha256 = hashlib.sha256(target.encode("utf-8")).hexdigest()
            target_kind = "invalid-filesystem"
        if relative_candidate is not None and is_secret_path(relative_candidate):
            resolution = "excluded-secret"
        elif inside is True and exists is True:
            resolution = "in-scope"
        elif inside is True and exists is False:
            resolution = "missing"
        elif inside is False:
            resolution = "out-of-scope"
        else:
            resolution = "unresolved"
        if edge_type == "automatic-import" and relative_candidate is not None:
            if relative_candidate in inventoried_paths:
                resolution = "inventoried"
            elif import_exclusions and relative_candidate in import_exclusions:
                resolution = import_exclusions[relative_candidate]
        reference = {
            "target": display_target,
            "target_kind": target_kind,
            "edge_type": edge_type,
            "resolution": resolution,
            "line": line_for_offset(text, start),
            "column": column_for_offset(text, start),
            "inside_root": inside,
            "exists": exists,
        }
        if target_sha256:
            reference["target_sha256"] = target_sha256
        refs.append(reference)
        file_references += 1
        scan_budget.references += 1
    if markdown_overflow or import_overflow or len(raw_matches) > file_references:
        # ``len(raw_matches)`` also includes ignored external anchors/schemes, so
        # only mark it when a hard cap was actually reached.
        scan_budget.references_truncated = scan_budget.references_truncated or (
            markdown_overflow
            or import_overflow
            or file_references >= MAX_REFERENCES_PER_FILE
            or scan_budget.references >= MAX_REFERENCES
        )
    return refs


def paragraph_blocks(
    text: str,
    path: str,
    budget: ScanBudget | None = None,
) -> Iterator[dict[str, Any]]:
    scan_budget = budget if budget is not None else ScanBudget()
    start = 0
    start_line = 1
    separators = re.finditer(r"\n\s*\n", text)
    while True:
        separator = next(separators, None)
        end = separator.start() if separator is not None else len(text)
        chunk = text[start:end]
        normalized = re.sub(r"\s+", " ", chunk.strip())
        word_count = 0
        for _ in re.finditer(r"\S+", normalized):
            word_count += 1
            if word_count >= 7:
                break
        if not normalized.startswith("#") and len(normalized) >= 48 and word_count >= 7:
            if scan_budget.paragraph_blocks >= MAX_PARAGRAPH_BLOCKS:
                scan_budget.paragraph_blocks_truncated = True
                return
            scan_budget.paragraph_blocks += 1
            yield {
                "path": path,
                "line": start_line,
                "sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
            }
        if separator is None:
            return
        start_line += text.count("\n", start, separator.end())
        start = separator.end()


def _bounded_read(
    path: Path,
    already_read: int,
    root: Path,
    matcher: IgnoreMatcher,
) -> tuple[tuple[str | None, str | None, int | None, str | None], int, bool]:
    try:
        size = path.lstat().st_size
    except OSError as exc:
        return (None, None, None, f"unable to read: {exc.__class__.__name__}"), already_read, False
    if already_read + size > MAX_TOTAL_READ_BYTES:
        return (
            (None, None, size, f"aggregate read budget exceeds {MAX_TOTAL_READ_BYTES} bytes"),
            already_read,
            True,
        )
    remaining = MAX_TOTAL_READ_BYTES - already_read
    result = read_text(
        path,
        max_bytes=min(MAX_READ_BYTES, remaining),
        root=root,
        matcher=matcher,
    )
    consumed = result[2] if result[0] is not None and result[2] is not None else 0
    aggregate_exceeded = result[0] is None and size > remaining
    if aggregate_exceeded:
        result = (
            None,
            None,
            size,
            f"aggregate read budget exceeds {MAX_TOTAL_READ_BYTES} bytes",
        )
    return result, already_read + consumed, aggregate_exceeded


def _import_candidate_reason(
    candidate: Path | None,
    relative_candidate: PurePosixPath | None,
    inside: bool | None,
    exists: bool | None,
    matcher: IgnoreMatcher,
) -> str | None:
    if inside is not True:
        return "out-of-scope"
    if relative_candidate is not None and is_secret_path(relative_candidate):
        return "excluded-secret"
    if exists is not True or candidate is None or relative_candidate is None:
        return "missing" if exists is False else "unresolved"
    if matcher.ignored(relative_candidate):
        return "excluded-ignored"
    try:
        info = candidate.stat()
    except OSError:
        return "unresolved"
    if not stat.S_ISREG(info.st_mode):
        return "excluded-non-regular"
    if int(getattr(info, "st_nlink", 1)) > 1:
        return "excluded-non-regular"
    return None


def _cap_records(
    records: list[dict[str, str]],
    limit: int,
    marker: dict[str, str],
    *,
    message_key: str,
) -> tuple[list[dict[str, str]], bool]:
    bounded = [{**item, "path": _bounded_display(item["path"], "long-relative-path")} for item in records]
    ordered = sorted(bounded, key=lambda item: (item["path"], item[message_key]))
    if len(ordered) <= limit:
        return ordered, False
    retained = ordered[: max(0, limit - 1)]
    retained.append(marker)
    retained.sort(key=lambda item: (item["path"], item[message_key]))
    return retained, True


def _collect_inventory(root_value: str | Path) -> dict[str, Any]:
    try:
        root = Path(root_value).resolve()
    except (OSError, ValueError) as exc:
        raise ValueError("audit root cannot be safely resolved") from exc
    if not root.is_dir():
        raise ValueError("audit root is not a directory")
    fallback_sequence = codex_fallback_filenames(root)
    fallback_names = frozenset(fallback_sequence)
    paths, skipped, matcher, discovery_incomplete = walk_candidates(root, fallback_names)
    path_set = set(paths)
    imported_paths: set[PurePosixPath] = set()
    import_exclusions: dict[PurePosixPath, str] = {}
    read_results: dict[Path, tuple[str | None, str | None, int | None, str | None]] = {}
    total_read_bytes = 0
    aggregate_budget_exceeded = False
    import_reference_budget_exceeded = False
    import_expansion_budget_exceeded = False

    queue = deque((path, 0, False) for path in paths)
    import_expansion_depth: dict[Path, int] = {}
    queued_import_depth: dict[Path, int] = {}
    expansion_edges: set[tuple[PurePosixPath, str]] = set()
    while queue:
        path, depth, reached_by_import = queue.popleft()
        if reached_by_import:
            previous_depth = import_expansion_depth.get(path)
            if previous_depth is not None and previous_depth <= depth:
                continue
            import_expansion_depth[path] = depth
        if path not in read_results:
            result, total_read_bytes, exceeded = _bounded_read(
                path,
                total_read_bytes,
                root,
                matcher,
            )
            read_results[path] = result
            aggregate_budget_exceeded = aggregate_budget_exceeded or exceeded
        text = read_results[path][0]
        if text is None:
            continue
        relative = PurePosixPath(path.relative_to(root).as_posix())
        is_claude_surface = relative.name.lower() in {"claude.md", "claude.local.md"}
        if not (is_claude_surface or reached_by_import):
            continue
        masked_import_text = mask_fenced_code(text)
        if (
            next(
                islice(
                    IMPORT_LINE.finditer(masked_import_text),
                    MAX_REFERENCES_PER_FILE,
                    MAX_REFERENCES_PER_FILE + 1,
                ),
                None,
            )
            is not None
        ):
            import_reference_budget_exceeded = True
            matcher.coverage_reasons.add("automatic import reference budget exceeded")
        if import_expansion_budget_exceeded:
            continue
        for target, _ in _automatic_imports(text):
            edge = (relative, target)
            if edge in expansion_edges:
                continue
            if len(expansion_edges) >= MAX_REFERENCES:
                import_expansion_budget_exceeded = True
                import_reference_budget_exceeded = True
                matcher.coverage_reasons.add("automatic import reference budget exceeded")
                break
            expansion_edges.add(edge)
            candidate, relative_candidate, inside, exists = _reference_candidate(target, relative, root)
            if depth >= MAX_IMPORT_DEPTH:
                if relative_candidate is not None:
                    import_exclusions[relative_candidate] = "excluded-depth-limit"
                continue
            reason = _import_candidate_reason(
                candidate,
                relative_candidate,
                inside,
                exists,
                matcher,
            )
            if relative_candidate is not None and reason is not None:
                import_exclusions.setdefault(relative_candidate, reason)
                if reason in {"excluded-ignored", "excluded-non-regular", "unresolved"}:
                    matcher.coverage_reasons.add("automatic import target was not inspected")
            if reason is not None or candidate is None or relative_candidate is None:
                continue
            next_depth = depth + 1
            processed_depth = import_expansion_depth.get(candidate)
            scheduled_depth = queued_import_depth.get(candidate)
            if (processed_depth is not None and processed_depth <= next_depth) or (
                scheduled_depth is not None and scheduled_depth <= next_depth
            ):
                imported_paths.add(relative_candidate)
                continue
            queued_import_depth[candidate] = next_depth
            if candidate in path_set:
                imported_paths.add(relative_candidate)
                queue.append((candidate, next_depth, True))
                continue
            if len(path_set) >= MAX_CANDIDATE_FILES:
                discovery_incomplete = True
                matcher.coverage_reasons.add("candidate file budget exceeded")
                import_exclusions[relative_candidate] = "excluded-candidate-budget"
                continue
            path_set.add(candidate)
            paths.append(candidate)
            imported_paths.add(relative_candidate)
            queue.append((candidate, next_depth, True))

    paths.sort(key=lambda path: path.relative_to(root).as_posix())
    selected_codex: set[str] = set()
    by_directory: dict[PurePosixPath, dict[str, Path]] = defaultdict(dict)
    for path in paths:
        relative = PurePosixPath(path.relative_to(root).as_posix())
        result = read_results[path]
        if result[0] is not None:
            by_directory[relative.parent][relative.name] = path
    for directory, names in by_directory.items():
        for candidate_name in ("AGENTS.override.md", "AGENTS.md", *fallback_sequence):
            if candidate_name in names:
                selected = PurePosixPath(directory / candidate_name).as_posix()
                selected_codex.add(selected)
                break
    selected_codex_paths = frozenset(selected_codex)
    inventoried_paths = frozenset(PurePosixPath(path.relative_to(root).as_posix()) for path in paths)
    files: list[dict[str, Any]] = []
    warnings: list[dict[str, str]] = []
    all_blocks: list[dict[str, Any]] = []
    scan_budget = ScanBudget()
    for path in paths:
        relative = PurePosixPath(path.relative_to(root).as_posix())
        text, digest, byte_count, warning = read_results[path]
        if warning:
            warnings.append({"path": relative.as_posix(), "message": warning})
            matcher.coverage_reasons.add("candidate read or text decoding was incomplete")
        metadata: dict[str, Any] = {}
        metadata_error = None
        refs: list[dict[str, Any]] = []
        lines = None
        if text is not None:
            metadata, metadata_error = parse_frontmatter(text)
            refs = local_references(
                text,
                relative,
                root,
                inventoried_paths,
                import_exclusions,
                relative.name.lower() in {"claude.md", "claude.local.md"} or relative in imported_paths,
                scan_budget,
            )
            lines = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
            all_blocks.extend(
                paragraph_blocks(
                    text,
                    _bounded_display(relative.as_posix(), "long-relative-path"),
                    scan_budget,
                )
            )
        if metadata_error:
            warnings.append({"path": relative.as_posix(), "message": metadata_error})
            matcher.coverage_reasons.add("frontmatter interpretation was incomplete")
        classification = classify(relative, metadata, fallback_names, selected_codex_paths)
        if relative in imported_paths:
            platforms = list(dict.fromkeys([*classification["platforms"], "claude-code"]))
            classification = {
                **classification,
                "platforms": platforms,
                "loading": "automatic",
                "classification_basis": "recognized automatic import",
            }
            if classification["kind"] == "reference":
                classification["kind"] = "imported-authority"
                classification["role"] = "authority"
        entry = {
            "path": _bounded_display(relative.as_posix(), "long-relative-path"),
            "bytes": byte_count,
            "lines": lines,
            "sha256": digest,
            "metadata": public_metadata(metadata),
            "references": refs,
            "discovered_by": "automatic-import" if relative in imported_paths else "filename",
            **classification,
        }
        files.append(entry)

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for block in all_blocks:
        groups[block["sha256"]].append(block)
    overlaps = []
    for digest, occurrences in sorted(groups.items()):
        distinct_paths = {item["path"] for item in occurrences}
        if len(distinct_paths) > 1:
            overlaps.append({"sha256": digest, "occurrences": occurrences})

    if any(item["sha256"] is None for item in files):
        matcher.coverage_reasons.add("candidate file could not be read completely")
    partial = (
        discovery_incomplete
        or aggregate_budget_exceeded
        or import_reference_budget_exceeded
        or scan_budget.references_truncated
        or scan_budget.paragraph_blocks_truncated
        or bool(matcher.coverage_reasons)
        or any(item["sha256"] is None for item in files)
    )
    if "candidate file budget exceeded" in matcher.coverage_reasons:
        skipped.append({"path": ".", "reason": "candidate file budget exceeded"})
    if import_reference_budget_exceeded or scan_budget.references_truncated:
        skipped.append({"path": ".", "reason": "reference record budget exceeded"})
        matcher.coverage_reasons.add("reference record budget exceeded")
    if scan_budget.paragraph_blocks_truncated:
        skipped.append({"path": ".", "reason": "paragraph block budget exceeded"})
        matcher.coverage_reasons.add("paragraph block budget exceeded")
    skipped, skipped_truncated = _cap_records(
        skipped,
        MAX_SKIPPED_RECORDS,
        {"path": ".", "reason": "additional skipped records omitted by output cap"},
        message_key="reason",
    )
    warnings, warnings_truncated = _cap_records(
        warnings,
        MAX_WARNING_RECORDS,
        {"path": ".", "message": "additional warnings omitted by output cap"},
        message_key="message",
    )
    if skipped_truncated:
        partial = True
        matcher.coverage_reasons.add("skipped record output cap exceeded")
    if warnings_truncated:
        partial = True
        matcher.coverage_reasons.add("warning record output cap exceeded")
    return {
        "schema_version": INVENTORY_VERSION,
        "root": ".",
        "coverage": {
            "status": "partial" if partial else "complete",
            "candidate_files": len(files),
            "read_bytes": total_read_bytes,
            "traversed_entries": matcher.traversed_entries,
            "reference_records": scan_budget.references,
            "paragraph_blocks": scan_budget.paragraph_blocks,
            "partial_reasons": sorted(matcher.coverage_reasons),
            "limits": {
                "max_candidate_files": MAX_CANDIDATE_FILES,
                "max_ignore_rules": MAX_IGNORE_RULES,
                "max_ignore_pattern_chars": MAX_IGNORE_PATTERN_CHARS,
                "max_ignore_evaluations": MAX_IGNORE_EVALUATIONS,
                "max_total_read_bytes": MAX_TOTAL_READ_BYTES,
                "max_file_read_bytes": MAX_READ_BYTES,
                "max_import_depth": MAX_IMPORT_DEPTH,
                "max_walk_entries": MAX_WALK_ENTRIES,
                "max_references": MAX_REFERENCES,
                "max_references_per_file": MAX_REFERENCES_PER_FILE,
                "max_paragraph_blocks": MAX_PARAGRAPH_BLOCKS,
                "max_frontmatter_chars": MAX_FRONTMATTER_CHARS,
                "max_frontmatter_fields": MAX_FRONTMATTER_FIELDS,
                "max_findings": MAX_FINDINGS,
                "max_finding_locations": MAX_FINDING_LOCATIONS,
                "max_skipped_records": MAX_SKIPPED_RECORDS,
                "max_warning_records": MAX_WARNING_RECORDS,
                "max_display_chars": MAX_DISPLAY_CHARS,
                "max_report_bytes": MAX_REPORT_BYTES,
            },
        },
        "files": files,
        "exact_overlap_groups": overlaps,
        "skipped": skipped,
        "warnings": warnings,
    }


def deterministic_findings(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    truncated = False
    locations_truncated = False

    def append_finding(finding: dict[str, Any]) -> bool:
        nonlocal truncated
        if len(findings) >= MAX_FINDINGS:
            truncated = True
            return False
        findings.append(finding)
        return True

    def bounded_locations(locations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        nonlocal locations_truncated
        if len(locations) > MAX_FINDING_LOCATIONS:
            locations_truncated = True
            return locations[:MAX_FINDING_LOCATIONS]
        return locations

    for group in inventory["exact_overlap_groups"]:
        locations = bounded_locations(
            [{"path": item["path"], "line": item["line"]} for item in group["occurrences"]]
        )
        if not append_finding(
            {
                "id": f"exact-overlap:{group['sha256'][:12]}",
                "severity": "medium",
                "evidence_type": "deterministic",
                "category": "exact-duplication",
                "summary": "An identical substantive block occurs in multiple files.",
                "locations": locations,
                "uncertainty": "Intent and necessity require human or model judgment.",
            }
        ):
            break
    status_files = [
        item for item in inventory["files"] if item["role"] == "current-state" and not item["archive"]
    ]
    if len(status_files) > 1:
        append_finding(
            {
                "id": "current-state:multiple-surfaces",
                "severity": "medium",
                "evidence_type": "deterministic",
                "category": "competing-current-truth",
                "summary": "Multiple non-archived files appear to represent current state.",
                "locations": bounded_locations([{"path": item["path"]} for item in status_files]),
                "uncertainty": "The files may have intentionally distinct scopes.",
            }
        )
    for item in inventory["files"]:
        if truncated:
            break
        if (
            item["retired_metadata"]
            and not item["archive"]
            and not append_finding(
                {
                    "id": f"retired-outside-archive:{item['path']}",
                    "severity": "high",
                    "evidence_type": "deterministic",
                    "category": "archive-boundary",
                    "summary": "Retired metadata appears outside an archive-like path.",
                    "locations": [{"path": item["path"]}],
                    "uncertainty": "Repository policy may intentionally retain a redirect stub here.",
                }
            )
        ):
            break
        for ref in item["references"]:
            if (
                ref["inside_root"] is True
                and ref["exists"] is False
                and not append_finding(
                    {
                        "id": (
                            f"broken-reference:{item['path']}:{ref['line']}:{ref['column']}:{ref['target']}"
                        ),
                        "severity": "medium",
                        "evidence_type": "deterministic",
                        "category": "broken-reference",
                        "summary": "A local Markdown reference does not resolve.",
                        "locations": [{"path": item["path"], "line": ref["line"], "column": ref["column"]}],
                        "evidence": {"target": ref["target"]},
                        "uncertainty": "Generated-at-runtime targets may be intentionally absent.",
                    }
                )
            ):
                break
    if truncated or locations_truncated:
        coverage = inventory.get("coverage")
        if isinstance(coverage, dict):
            coverage["status"] = "partial"
            reasons = coverage.setdefault("partial_reasons", [])
            new_reasons = []
            if truncated:
                new_reasons.append("finding record budget exceeded")
            if locations_truncated:
                new_reasons.append("finding location budget exceeded")
            for reason in new_reasons:
                if reason not in reasons:
                    reasons.append(reason)
            reasons.sort()
            coverage["finding_records"] = len(findings)
        skipped = inventory.get("skipped")
        if isinstance(skipped, list):
            skipped.append(
                {
                    "path": ".",
                    "reason": ("finding output budget exceeded"),
                }
            )
            capped, _ = _cap_records(
                skipped,
                MAX_SKIPPED_RECORDS,
                {"path": ".", "reason": "additional skipped records omitted by output cap"},
                message_key="reason",
            )
            inventory["skipped"] = capped
    else:
        coverage = inventory.get("coverage")
        if isinstance(coverage, dict):
            coverage["finding_records"] = len(findings)
    return sorted(findings, key=lambda item: item["id"])


def build_inventory(root_value: str | Path) -> dict[str, Any]:
    """Build a standalone inventory with the same finalized coverage shape as an audit."""

    inventory = _collect_inventory(root_value)
    deterministic_findings(inventory)
    return inventory


def build_audit(root_value: str | Path) -> dict[str, Any]:
    inventory = _collect_inventory(root_value)
    findings = deterministic_findings(inventory)
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "read-only",
        "engine": {
            "name": "agent-docs-doctor",
            "version": __version__,
            "configuration": {
                "max_read_bytes": MAX_READ_BYTES,
                "max_ignore_rules": MAX_IGNORE_RULES,
                "max_ignore_pattern_chars": MAX_IGNORE_PATTERN_CHARS,
                "max_ignore_evaluations": MAX_IGNORE_EVALUATIONS,
                "max_candidate_files": MAX_CANDIDATE_FILES,
                "max_total_read_bytes": MAX_TOTAL_READ_BYTES,
                "max_import_depth": MAX_IMPORT_DEPTH,
                "max_walk_entries": MAX_WALK_ENTRIES,
                "max_references": MAX_REFERENCES,
                "max_references_per_file": MAX_REFERENCES_PER_FILE,
                "max_paragraph_blocks": MAX_PARAGRAPH_BLOCKS,
                "max_frontmatter_chars": MAX_FRONTMATTER_CHARS,
                "max_frontmatter_fields": MAX_FRONTMATTER_FIELDS,
                "max_findings": MAX_FINDINGS,
                "max_finding_locations": MAX_FINDING_LOCATIONS,
                "max_skipped_records": MAX_SKIPPED_RECORDS,
                "max_warning_records": MAX_WARNING_RECORDS,
                "max_display_chars": MAX_DISPLAY_CHARS,
                "max_report_bytes": MAX_REPORT_BYTES,
            },
        },
        "inventory": inventory,
        "findings": findings,
        "judgment_queue": [
            "Review apparent duplication for intentional safety or cross-platform boundaries.",
            "Review possible contradictions with scope, precedence, and confidence.",
            "Review authority and current-state claims against repository evidence.",
            "Decide whether procedures belong in docs, scoped rules, skills, scripts, hooks, or tests.",
        ],
        "limitations": [
            "Filename and metadata classifications are inferences unless platform documentation "
            "confirms loading.",
            "Semantic contradiction, staleness, and operational necessity require judgment.",
            "Ignored, secret-like, unreadable, and over-limit files are not inspected.",
            "Concurrent repository mutation can produce a mixed snapshot; rerun against a stable "
            "checkout when the evidence is material.",
            "Default-pruned directories are listed in inventory.skipped; restore a needed default "
            "with an explicit negation in .agent-docs-doctorignore.",
        ],
    }


class _ValidationErrors(list[str]):
    def __init__(self) -> None:
        super().__init__()
        self._truncated = False
        self._message_bytes = 0

    def append(self, value: str) -> None:
        if self._truncated:
            return
        safe = "".join(
            character if character.isprintable() and character not in "\r\n" else f"\\u{ord(character):04x}"
            for character in value
        )
        if len(safe) > MAX_VALIDATION_ERROR_MESSAGE_CHARS:
            safe = safe[: MAX_VALIDATION_ERROR_MESSAGE_CHARS - 20] + "...<message omitted>"
        encoded_bytes = len(safe.encode("utf-8"))
        if (
            len(self) < MAX_VALIDATION_ERRORS - 1
            and self._message_bytes + encoded_bytes <= MAX_VALIDATION_ERROR_BYTES
        ):
            super().append(safe)
            self._message_bytes += encoded_bytes
            return
        notice = "additional validation errors omitted by output safety limits"
        if self._message_bytes + len(notice) <= MAX_VALIDATION_ERROR_BYTES:
            super().append(notice)
            self._message_bytes += len(notice)
        self._truncated = True


def validate_audit(data: Any) -> list[str]:
    errors = _ValidationErrors()
    if not isinstance(data, dict):
        return ["report must be a JSON object"]
    schema_version = data.get("schema_version")
    if not isinstance(schema_version, str) or schema_version not in (
        SCHEMA_VERSION,
        LEGACY_SCHEMA_VERSION,
    ):
        errors.append(f"schema_version must be {SCHEMA_VERSION!r} or {LEGACY_SCHEMA_VERSION!r}")
    current = schema_version == SCHEMA_VERSION
    if data.get("mode") != "read-only":
        errors.append("mode must be 'read-only'")
    for key in ("inventory", "findings", "judgment_queue", "limitations"):
        if key not in data:
            errors.append(f"report missing {key}")
    engine = data.get("engine")
    if current:
        if not isinstance(engine, dict):
            errors.append("engine must be an object")
        else:
            if engine.get("name") != "agent-docs-doctor":
                errors.append("engine.name must be 'agent-docs-doctor'")
            if not isinstance(engine.get("version"), str) or not engine["version"]:
                errors.append("engine.version must be a non-empty string")
            configuration = engine.get("configuration")
            required_configuration = {
                "max_read_bytes",
                "max_ignore_rules",
                "max_ignore_pattern_chars",
                "max_ignore_evaluations",
                "max_candidate_files",
                "max_total_read_bytes",
                "max_import_depth",
                "max_walk_entries",
                "max_references",
                "max_references_per_file",
                "max_paragraph_blocks",
                "max_frontmatter_chars",
                "max_frontmatter_fields",
                "max_findings",
                "max_finding_locations",
                "max_skipped_records",
                "max_warning_records",
                "max_display_chars",
                "max_report_bytes",
            }
            if not isinstance(configuration, dict):
                errors.append("engine.configuration must be an object")
            else:
                for key in sorted(required_configuration):
                    value = configuration.get(key)
                    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                        errors.append(f"engine.configuration.{key} must be a positive integer")
                if len(configuration) > MAX_VALIDATION_OBJECT_KEYS:
                    errors.append("engine.configuration exceeds the safe validation object-key limit")
                for key, value in islice(configuration.items(), MAX_VALIDATION_OBJECT_KEYS):
                    if key in required_configuration:
                        continue
                    if not isinstance(key, str):
                        errors.append("engine.configuration keys must be strings")
                    elif not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                        errors.append(
                            "engine.configuration contains an additive value that is not a positive integer"
                        )
    for key in ("judgment_queue", "limitations"):
        value = data.get(key)
        if not isinstance(value, list):
            errors.append(f"{key} must be an array of strings")
        else:
            if len(value) > MAX_VALIDATION_LIST_ITEMS:
                errors.append(f"{key} exceeds the safe validation item limit")
            if not all(isinstance(item, str) for item in islice(value, MAX_VALIDATION_LIST_ITEMS)):
                errors.append(f"{key} must be an array of strings")
    inventory = data.get("inventory")
    if not isinstance(inventory, dict):
        errors.append("inventory must be an object")
    else:
        expected_inventory_version = INVENTORY_VERSION if current else LEGACY_INVENTORY_VERSION
        if inventory.get("schema_version") != expected_inventory_version:
            errors.append(f"inventory.schema_version must be {expected_inventory_version!r}")
        inventory_types = {
            "root": str,
            "files": list,
            "exact_overlap_groups": list,
            "skipped": list,
            "warnings": list,
        }
        for key, expected_type in inventory_types.items():
            if key not in inventory:
                errors.append(f"inventory missing {key}")
            elif not isinstance(inventory[key], expected_type):
                errors.append(f"inventory.{key} must be a {expected_type.__name__}")
        if inventory.get("root") != ".":
            errors.append("inventory.root must be '.'")
        coverage = inventory.get("coverage")
        if current:
            if not isinstance(coverage, dict):
                errors.append("inventory.coverage must be an object")
            else:
                if coverage.get("status") not in ("complete", "partial"):
                    errors.append("inventory.coverage.status must be 'complete' or 'partial'")
                for key in (
                    "candidate_files",
                    "read_bytes",
                    "traversed_entries",
                    "reference_records",
                    "paragraph_blocks",
                    "finding_records",
                ):
                    value = coverage.get(key)
                    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                        errors.append(f"inventory.coverage.{key} must be a non-negative integer")
                partial_reasons = coverage.get("partial_reasons")
                if not isinstance(partial_reasons, list):
                    errors.append("inventory.coverage.partial_reasons must be an array of strings")
                else:
                    bounded_reasons = list(islice(partial_reasons, MAX_VALIDATION_LIST_ITEMS))
                    if len(partial_reasons) > MAX_VALIDATION_LIST_ITEMS:
                        errors.append(
                            "inventory.coverage.partial_reasons exceeds the safe validation item limit"
                        )
                    if not all(isinstance(item, str) for item in bounded_reasons):
                        errors.append("inventory.coverage.partial_reasons must be an array of strings")
                    elif len(bounded_reasons) != len(set(bounded_reasons)):
                        errors.append("inventory.coverage.partial_reasons must contain unique values")
                    elif coverage.get("status") == "complete" and partial_reasons:
                        errors.append(
                            "inventory.coverage.partial_reasons must be empty for complete coverage"
                        )
                    elif coverage.get("status") == "partial" and not partial_reasons:
                        errors.append("inventory.coverage.partial_reasons must explain partial coverage")
                limits = coverage.get("limits")
                if not isinstance(limits, dict):
                    errors.append("inventory.coverage.limits must be an object")
                else:
                    required_limits = {
                        "max_candidate_files",
                        "max_ignore_rules",
                        "max_ignore_pattern_chars",
                        "max_ignore_evaluations",
                        "max_total_read_bytes",
                        "max_file_read_bytes",
                        "max_import_depth",
                        "max_walk_entries",
                        "max_references",
                        "max_references_per_file",
                        "max_paragraph_blocks",
                        "max_frontmatter_chars",
                        "max_frontmatter_fields",
                        "max_findings",
                        "max_finding_locations",
                        "max_skipped_records",
                        "max_warning_records",
                        "max_display_chars",
                        "max_report_bytes",
                    }
                    for key in sorted(required_limits):
                        value = limits.get(key)
                        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                            errors.append(f"inventory.coverage.limits.{key} must be a positive integer")
                    if len(limits) > MAX_VALIDATION_OBJECT_KEYS:
                        errors.append(
                            "inventory.coverage.limits exceeds the safe validation object-key limit"
                        )
                    for key, value in islice(limits.items(), MAX_VALIDATION_OBJECT_KEYS):
                        if key in required_limits:
                            continue
                        if not isinstance(key, str):
                            errors.append("inventory.coverage.limits keys must be strings")
                        elif not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                            errors.append(
                                "inventory.coverage.limits contains an additive value "
                                "that is not a positive integer"
                            )
        files = inventory.get("files")
        if isinstance(files, list):
            if len(files) > MAX_CANDIDATE_FILES:
                errors.append(f"inventory.files exceeds the {MAX_CANDIDATE_FILES} item limit")
            required_file_keys = {
                "path",
                "bytes",
                "lines",
                "sha256",
                "metadata",
                "references",
                "kind",
                "platforms",
                "loading",
                "role",
                "archive",
                "retired_metadata",
                "classification_basis",
            }
            if current:
                required_file_keys.add("discovered_by")
            validated_references = 0
            validated_platforms = 0
            for index, entry in enumerate(islice(files, MAX_CANDIDATE_FILES)):
                if not isinstance(entry, dict):
                    errors.append(f"inventory.files[{index}] must be an object")
                    continue
                missing = sorted(required_file_keys - entry.keys())
                for key in missing:
                    errors.append(f"inventory.files[{index}] missing {key}")
                if not isinstance(entry.get("path"), str):
                    errors.append(f"inventory.files[{index}].path must be a string")
                for key in ("bytes", "lines"):
                    value = entry.get(key)
                    if value is not None and (
                        not isinstance(value, int) or isinstance(value, bool) or value < 0
                    ):
                        errors.append(
                            f"inventory.files[{index}].{key} must be null or a non-negative integer"
                        )
                digest = entry.get("sha256")
                if digest is not None and (
                    not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None
                ):
                    errors.append(f"inventory.files[{index}].sha256 must be null or a SHA-256 hex string")
                if not isinstance(entry.get("metadata"), dict):
                    errors.append(f"inventory.files[{index}].metadata must be an object")
                else:
                    metadata = entry["metadata"]
                    allowed_metadata = {
                        "alwaysApply",
                        "retired",
                        "status",
                        "role",
                        "has_description",
                        "has_globs",
                        "has_paths",
                    }
                    if len(metadata) > len(allowed_metadata):
                        errors.append(f"inventory.files[{index}].metadata exceeds its allowed key limit")
                    for metadata_key in islice(metadata, len(allowed_metadata) + 1):
                        if metadata_key not in allowed_metadata:
                            errors.append(f"inventory.files[{index}].metadata contains an unrecognized key")
                    for metadata_key in (
                        "alwaysApply",
                        "retired",
                        "has_description",
                        "has_globs",
                        "has_paths",
                    ):
                        if metadata_key in metadata and not isinstance(metadata[metadata_key], bool):
                            errors.append(f"inventory.files[{index}].metadata.{metadata_key} must be boolean")
                    if "status" in metadata and (
                        not isinstance(metadata["status"], str)
                        or metadata["status"] not in SAFE_STATUS_VALUES
                    ):
                        errors.append(f"inventory.files[{index}].metadata.status is invalid")
                    if "role" in metadata and (
                        not isinstance(metadata["role"], str) or metadata["role"] not in SAFE_ROLE_VALUES
                    ):
                        errors.append(f"inventory.files[{index}].metadata.role is invalid")
                references = entry.get("references")
                if not isinstance(references, list):
                    errors.append(f"inventory.files[{index}].references must be an array")
                else:
                    if current and len(references) > MAX_REFERENCES_PER_FILE:
                        errors.append(
                            f"inventory.files[{index}].references exceeds "
                            f"{MAX_REFERENCES_PER_FILE} item limit"
                        )
                    remaining_references = max(
                        0,
                        MAX_REFERENCES - validated_references,
                    )
                    if len(references) > remaining_references:
                        errors.append("inventory references exceed the aggregate safe validation item limit")
                    bounded_reference_count = min(
                        len(references),
                        MAX_REFERENCES_PER_FILE,
                        remaining_references,
                    )
                    for ref_index, reference in enumerate(islice(references, bounded_reference_count)):
                        prefix = f"inventory.files[{index}].references[{ref_index}]"
                        if not isinstance(reference, dict):
                            errors.append(f"{prefix} must be an object")
                            continue
                        required_reference_keys = {
                            "target",
                            "target_kind",
                            "line",
                            "column",
                            "inside_root",
                            "exists",
                        }
                        if current:
                            required_reference_keys.update({"edge_type", "resolution"})
                        for key in sorted(required_reference_keys - reference.keys()):
                            errors.append(f"{prefix} missing {key}")
                        if not isinstance(reference.get("target"), str):
                            errors.append(f"{prefix}.target must be a string")
                        if not isinstance(reference.get("target_kind"), str):
                            errors.append(f"{prefix}.target_kind must be a string")
                        if current and reference.get("edge_type") not in (
                            "markdown-link",
                            "automatic-import",
                            "at-reference",
                        ):
                            errors.append(f"{prefix}.edge_type is invalid")
                        if current and reference.get("resolution") not in (
                            "in-scope",
                            "inventoried",
                            "missing",
                            "out-of-scope",
                            "unresolved",
                            "excluded-secret",
                            "excluded-ignored",
                            "excluded-non-regular",
                            "excluded-depth-limit",
                            "excluded-candidate-budget",
                        ):
                            errors.append(f"{prefix}.resolution is invalid")
                        for key in ("line", "column"):
                            value = reference.get(key)
                            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                                errors.append(f"{prefix}.{key} must be a positive integer")
                        for key in ("inside_root", "exists"):
                            value = reference.get(key)
                            if value is not None and not isinstance(value, bool):
                                errors.append(f"{prefix}.{key} must be boolean or null")
                        target_digest = reference.get("target_sha256")
                        if target_digest is not None and (
                            not isinstance(target_digest, str)
                            or re.fullmatch(r"[0-9a-f]{64}", target_digest) is None
                        ):
                            errors.append(f"{prefix}.target_sha256 must be a SHA-256 hex string")
                    validated_references += bounded_reference_count
                platforms = entry.get("platforms")
                remaining_platforms = max(
                    0,
                    MAX_VALIDATION_NESTED_ITEMS - validated_platforms,
                )
                if (
                    not isinstance(platforms, list)
                    or len(platforms) > remaining_platforms
                    or not all(isinstance(item, str) for item in islice(platforms, remaining_platforms))
                ):
                    errors.append(f"inventory.files[{index}].platforms must be an array of strings")
                if isinstance(platforms, list):
                    validated_platforms += min(len(platforms), remaining_platforms)
                for key in ("kind", "loading", "role", "classification_basis"):
                    if not isinstance(entry.get(key), str):
                        errors.append(f"inventory.files[{index}].{key} must be a string")
                for key in ("archive", "retired_metadata"):
                    if not isinstance(entry.get(key), bool):
                        errors.append(f"inventory.files[{index}].{key} must be boolean")
                if current and entry.get("discovered_by") not in (
                    "filename",
                    "automatic-import",
                ):
                    errors.append(f"inventory.files[{index}].discovered_by is invalid")
        overlaps = inventory.get("exact_overlap_groups")
        if isinstance(overlaps, list):
            if len(overlaps) > MAX_PARAGRAPH_BLOCKS:
                errors.append("inventory.exact_overlap_groups exceeds the safe validation item limit")
            validated_occurrences = 0
            for index, group in enumerate(islice(overlaps, MAX_PARAGRAPH_BLOCKS)):
                prefix = f"inventory.exact_overlap_groups[{index}]"
                if not isinstance(group, dict):
                    errors.append(f"{prefix} must be an object")
                    continue
                digest = group.get("sha256")
                if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                    errors.append(f"{prefix}.sha256 must be a SHA-256 hex string")
                occurrences = group.get("occurrences")
                if not isinstance(occurrences, list):
                    errors.append(f"{prefix}.occurrences must be an array")
                    continue
                if current and len(occurrences) < 2:
                    errors.append(f"{prefix}.occurrences must contain at least two items")
                remaining_occurrences = max(
                    0,
                    MAX_PARAGRAPH_BLOCKS - validated_occurrences,
                )
                if len(occurrences) > remaining_occurrences:
                    errors.append(
                        "inventory overlap occurrences exceed the aggregate safe validation item limit"
                    )
                bounded_occurrence_count = min(
                    len(occurrences),
                    remaining_occurrences,
                )
                for occurrence_index, occurrence in enumerate(islice(occurrences, bounded_occurrence_count)):
                    occurrence_prefix = f"{prefix}.occurrences[{occurrence_index}]"
                    if not isinstance(occurrence, dict):
                        errors.append(f"{occurrence_prefix} must be an object")
                        continue
                    if not isinstance(occurrence.get("path"), str):
                        errors.append(f"{occurrence_prefix}.path must be a string")
                    line = occurrence.get("line")
                    if not isinstance(line, int) or isinstance(line, bool) or line < 1:
                        errors.append(f"{occurrence_prefix}.line must be a positive integer")
                    if occurrence.get("sha256") != digest:
                        errors.append(f"{occurrence_prefix}.sha256 must match its group")
                validated_occurrences += bounded_occurrence_count
        for key, message_key in (("skipped", "reason"), ("warnings", "message")):
            items = inventory.get(key)
            if isinstance(items, list):
                limit = MAX_SKIPPED_RECORDS if key == "skipped" else MAX_WARNING_RECORDS
                if current and len(items) > limit:
                    errors.append(f"inventory.{key} exceeds {limit} item limit")
                for index, item in enumerate(islice(items, limit)):
                    prefix = f"inventory.{key}[{index}]"
                    if not isinstance(item, dict):
                        errors.append(f"{prefix} must be an object")
                        continue
                    if not isinstance(item.get("path"), str):
                        errors.append(f"{prefix}.path must be a string")
                    if not isinstance(item.get(message_key), str):
                        errors.append(f"{prefix}.{message_key} must be a string")
    findings = data.get("findings")
    if not isinstance(findings, list):
        errors.append("findings must be an array")
    else:
        if current and len(findings) > MAX_FINDINGS:
            errors.append(f"findings exceeds {MAX_FINDINGS} item limit")
        seen: set[str] = set()
        validated_locations = 0
        for index, finding in enumerate(islice(findings, MAX_FINDINGS)):
            if not isinstance(finding, dict):
                errors.append(f"findings[{index}] must be an object")
                continue
            for key in ("id", "severity", "evidence_type", "category", "summary", "locations", "uncertainty"):
                if key not in finding:
                    errors.append(f"findings[{index}] missing {key}")
            identifier = finding.get("id")
            if not isinstance(identifier, str) or not identifier:
                errors.append(f"findings[{index}].id must be a non-empty string")
            else:
                if identifier in seen:
                    errors.append(f"findings[{index}].id duplicates an earlier finding id")
                seen.add(identifier)
            for key in ("category", "summary", "uncertainty"):
                if not isinstance(finding.get(key), str):
                    errors.append(f"findings[{index}].{key} must be a string")
            locations = finding.get("locations")
            if not isinstance(locations, list):
                errors.append(f"findings[{index}].locations must be an array")
            else:
                remaining_locations = max(
                    0,
                    MAX_VALIDATION_NESTED_ITEMS - validated_locations,
                )
                if len(locations) > min(MAX_FINDING_LOCATIONS, remaining_locations):
                    errors.append(
                        f"findings[{index}].locations exceeds "
                        "the per-finding or aggregate safe validation item limit"
                    )
                bounded_location_count = min(
                    len(locations),
                    MAX_FINDING_LOCATIONS,
                    remaining_locations,
                )
                for location_index, location in enumerate(islice(locations, bounded_location_count)):
                    prefix = f"findings[{index}].locations[{location_index}]"
                    if not isinstance(location, dict):
                        errors.append(f"{prefix} must be an object")
                        continue
                    if not isinstance(location.get("path"), str):
                        errors.append(f"{prefix}.path must be a string")
                    for key in ("line", "column"):
                        value = location.get(key)
                        if value is not None and (
                            not isinstance(value, int) or isinstance(value, bool) or value < 1
                        ):
                            errors.append(f"{prefix}.{key} must be a positive integer")
                validated_locations += bounded_location_count
            if "evidence" in finding and not isinstance(finding["evidence"], dict):
                errors.append(f"findings[{index}].evidence must be an object")
            if finding.get("severity") not in (
                "critical",
                "high",
                "medium",
                "low",
                "informational",
            ):
                errors.append(f"findings[{index}] has invalid severity")
            if finding.get("evidence_type") not in (
                "deterministic",
                "model-judgment",
                "user-decision",
            ):
                errors.append(f"findings[{index}] has invalid evidence_type")

    if current and isinstance(inventory, dict):
        coverage_summary = inventory.get("coverage")
        inventory_files = inventory.get("files")
        if isinstance(coverage_summary, dict) and isinstance(inventory_files, list):
            if len(inventory_files) <= MAX_CANDIDATE_FILES and coverage_summary.get("candidate_files") != len(
                inventory_files
            ):
                errors.append("inventory.coverage.candidate_files must equal the emitted file count")

            reference_count = 0
            reference_count_is_bounded = len(inventory_files) <= MAX_CANDIDATE_FILES
            if reference_count_is_bounded:
                for entry in inventory_files:
                    if not isinstance(entry, dict):
                        reference_count_is_bounded = False
                        break
                    references = entry.get("references")
                    if not isinstance(references, list) or len(references) > MAX_REFERENCES_PER_FILE:
                        reference_count_is_bounded = False
                        break
                    reference_count += len(references)
                    if reference_count > MAX_REFERENCES:
                        reference_count_is_bounded = False
                        break
            if reference_count_is_bounded and coverage_summary.get("reference_records") != reference_count:
                errors.append("inventory.coverage.reference_records must equal the emitted reference count")

            if (
                isinstance(findings, list)
                and len(findings) <= MAX_FINDINGS
                and coverage_summary.get("finding_records") != len(findings)
            ):
                errors.append("inventory.coverage.finding_records must equal the emitted finding count")

            report_engine = data.get("engine")
            engine_configuration = (
                report_engine.get("configuration") if isinstance(report_engine, dict) else None
            )
            coverage_limits = coverage_summary.get("limits")
            if isinstance(engine_configuration, dict) and isinstance(coverage_limits, dict):
                shared_limits = (
                    ("max_read_bytes", "max_file_read_bytes"),
                    ("max_ignore_rules", "max_ignore_rules"),
                    ("max_ignore_pattern_chars", "max_ignore_pattern_chars"),
                    ("max_ignore_evaluations", "max_ignore_evaluations"),
                    ("max_candidate_files", "max_candidate_files"),
                    ("max_total_read_bytes", "max_total_read_bytes"),
                    ("max_import_depth", "max_import_depth"),
                    ("max_walk_entries", "max_walk_entries"),
                    ("max_references", "max_references"),
                    ("max_references_per_file", "max_references_per_file"),
                    ("max_paragraph_blocks", "max_paragraph_blocks"),
                    ("max_frontmatter_chars", "max_frontmatter_chars"),
                    ("max_frontmatter_fields", "max_frontmatter_fields"),
                    ("max_findings", "max_findings"),
                    ("max_finding_locations", "max_finding_locations"),
                    ("max_skipped_records", "max_skipped_records"),
                    ("max_warning_records", "max_warning_records"),
                    ("max_display_chars", "max_display_chars"),
                    ("max_report_bytes", "max_report_bytes"),
                )
                for engine_key, coverage_key in shared_limits:
                    if (
                        engine_key in engine_configuration
                        and coverage_key in coverage_limits
                        and engine_configuration[engine_key] != coverage_limits[coverage_key]
                    ):
                        errors.append(
                            f"engine.configuration.{engine_key} must match "
                            f"inventory.coverage.limits.{coverage_key}"
                        )

                def declared_limit(key: str) -> int | None:
                    value = coverage_limits.get(key)
                    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                        return value
                    return None

                def non_negative_counter(key: str) -> int | None:
                    value = coverage_summary.get(key)
                    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                        return value
                    return None

                counter_limits = (
                    ("candidate_files", "max_candidate_files"),
                    ("read_bytes", "max_total_read_bytes"),
                    ("traversed_entries", "max_walk_entries"),
                    ("reference_records", "max_references"),
                    ("paragraph_blocks", "max_paragraph_blocks"),
                    ("finding_records", "max_findings"),
                )
                for counter_key, limit_key in counter_limits:
                    counter = non_negative_counter(counter_key)
                    limit = declared_limit(limit_key)
                    if counter is not None and limit is not None and counter > limit:
                        errors.append(f"inventory.coverage.{counter_key} exceeds its declared {limit_key}")

                candidate_limit = declared_limit("max_candidate_files")
                if candidate_limit is not None and len(inventory_files) > candidate_limit:
                    errors.append("inventory.files exceeds its declared max_candidate_files")

                reference_limit = declared_limit("max_references")
                references_per_file_limit = declared_limit("max_references_per_file")
                if reference_count_is_bounded and reference_limit is not None:
                    if reference_count > reference_limit:
                        errors.append("inventory references exceed their declared max_references")
                    if references_per_file_limit is not None:
                        for index, entry in enumerate(inventory_files):
                            references = entry.get("references") if isinstance(entry, dict) else None
                            if isinstance(references, list) and len(references) > references_per_file_limit:
                                errors.append(
                                    f"inventory.files[{index}].references exceeds its declared "
                                    "max_references_per_file"
                                )

                paragraph_limit = declared_limit("max_paragraph_blocks")
                overlaps = inventory.get("exact_overlap_groups")
                if isinstance(overlaps, list) and paragraph_limit is not None:
                    if len(overlaps) > paragraph_limit:
                        errors.append(
                            "inventory.exact_overlap_groups exceeds its declared max_paragraph_blocks"
                        )
                    emitted_occurrences = 0
                    occurrences_are_bounded = len(overlaps) <= MAX_PARAGRAPH_BLOCKS
                    if occurrences_are_bounded:
                        for group in overlaps:
                            occurrences = group.get("occurrences") if isinstance(group, dict) else None
                            if not isinstance(occurrences, list):
                                occurrences_are_bounded = False
                                break
                            emitted_occurrences += len(occurrences)
                            if emitted_occurrences > MAX_PARAGRAPH_BLOCKS:
                                occurrences_are_bounded = False
                                break
                    if occurrences_are_bounded:
                        if emitted_occurrences > paragraph_limit:
                            errors.append(
                                "inventory overlap occurrences exceed their declared max_paragraph_blocks"
                            )
                        paragraph_count = non_negative_counter("paragraph_blocks")
                        if paragraph_count is not None and emitted_occurrences > paragraph_count:
                            errors.append("inventory overlap occurrences exceed the recorded paragraph count")

                finding_limit = declared_limit("max_findings")
                location_limit = declared_limit("max_finding_locations")
                if isinstance(findings, list):
                    if finding_limit is not None and len(findings) > finding_limit:
                        errors.append("findings exceeds its declared max_findings")
                    if location_limit is not None and len(findings) <= MAX_FINDINGS:
                        for index, finding in enumerate(findings):
                            locations = finding.get("locations") if isinstance(finding, dict) else None
                            if isinstance(locations, list) and len(locations) > location_limit:
                                errors.append(
                                    f"findings[{index}].locations exceeds its declared max_finding_locations"
                                )

                for records_key, limit_key in (
                    ("skipped", "max_skipped_records"),
                    ("warnings", "max_warning_records"),
                ):
                    records = inventory.get(records_key)
                    limit = declared_limit(limit_key)
                    if isinstance(records, list) and limit is not None and len(records) > limit:
                        errors.append(f"inventory.{records_key} exceeds its declared {limit_key}")
    try:
        serialized_size = len(
            json.dumps(
                data,
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        )
    except (RecursionError, TypeError, ValueError):
        errors.append("report cannot be serialized as bounded JSON")
    else:
        if serialized_size > MAX_REPORT_BYTES:
            errors.append(f"report exceeds {MAX_REPORT_BYTES} byte serialized limit")
    return errors


def dump_json(data: Any, pretty: bool = False) -> str:
    rendered = (
        json.dumps(
            data,
            indent=2 if pretty else None,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )
    if len(rendered.encode("utf-8")) > MAX_REPORT_BYTES:
        raise ValueError(f"serialized output exceeds {MAX_REPORT_BYTES} byte limit")
    return rendered
