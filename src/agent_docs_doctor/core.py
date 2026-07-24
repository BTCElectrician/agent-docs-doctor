#!/usr/bin/env python3
"""Deterministic, read-only evidence collection for Agent Docs Doctor."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import stat
import sys
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .version import __version__

sys.dont_write_bytecode = True

SCHEMA_VERSION = "agent-docs-doctor.audit.v2"
INVENTORY_VERSION = "agent-docs-doctor.inventory.v2"
LEGACY_SCHEMA_VERSION = "agent-docs-doctor.audit.v1"
LEGACY_INVENTORY_VERSION = "agent-docs-doctor.inventory.v1"
MAX_READ_BYTES = 2_000_000
MAX_IGNORE_RULES = 10_000
MAX_CANDIDATE_FILES = 10_000
MAX_TOTAL_READ_BYTES = 50_000_000
MAX_IMPORT_DEPTH = 10

SECRET_NAMES = {
    ".env",
    ".npmrc",
    ".pypirc",
    "credentials.json",
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
CODEX_FALLBACK_LIST = re.compile(r"(?ms)^\s*project_doc_fallback_filenames\s*=\s*\[(.*?)\]")
TOML_QUOTED_STRING = re.compile(r'"((?:\\.|[^"\\])*)"|\'([^\']*)\'')


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
        for filename in (".gitignore", ".ignore", ".agent-docs-doctorignore"):
            path = root / filename
            if path.is_symlink():
                self.skipped.append({"path": filename, "reason": "ignore control symlink not followed"})
            elif path.is_file() and not is_secret_path(path):
                self.rules.extend(
                    self._parse(
                        path,
                        PurePosixPath("."),
                        PurePosixPath(filename),
                        restores_defaults=filename == ".agent-docs-doctorignore",
                        remaining_rules=MAX_IGNORE_RULES - len(self.rules),
                    )
                )

    @staticmethod
    def _parse(
        path: Path,
        base: PurePosixPath,
        display_path: PurePosixPath,
        restores_defaults: bool,
        remaining_rules: int,
    ) -> list[IgnoreRule]:
        rules: list[IgnoreRule] = []
        try:
            if path.stat().st_size > MAX_READ_BYTES:
                raise ValueError(
                    f"ignore control {display_path.as_posix()} exceeds {MAX_READ_BYTES} byte read limit"
                )
            raw = path.read_bytes()
            if len(raw) > MAX_READ_BYTES:
                raise ValueError(
                    f"ignore control {display_path.as_posix()} exceeds {MAX_READ_BYTES} byte read limit"
                )
            lines = raw.decode("utf-8", errors="replace").splitlines()
        except OSError as exc:
            raise ValueError(
                f"unable to read ignore control {display_path.as_posix()}: {exc.__class__.__name__}"
            ) from exc
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
                if len(rules) >= remaining_rules:
                    raise ValueError(
                        f"ignore controls exceed aggregate {MAX_IGNORE_RULES} rule limit "
                        f"at {display_path.as_posix()}"
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

    def add_nested_gitignore(self, directory: Path, relative: PurePosixPath) -> None:
        if relative == PurePosixPath("."):
            return
        path = directory / ".gitignore"
        if path.is_symlink():
            self.skipped.append(
                {
                    "path": PurePosixPath(relative / ".gitignore").as_posix(),
                    "reason": "ignore control symlink not followed",
                }
            )
        elif path.is_file():
            self.rules.extend(
                self._parse(
                    path,
                    relative,
                    PurePosixPath(relative / ".gitignore"),
                    restores_defaults=False,
                    remaining_rules=MAX_IGNORE_RULES - len(self.rules),
                )
            )

    def ignored(self, relative: PurePosixPath, is_dir: bool = False) -> bool:
        parts = relative.parts
        default_ignored = any(part in DEFAULT_IGNORED_DIRS for part in parts)
        ignored = default_ignored
        for rule in self.rules:
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
    name = path.name.lower()
    if name in SECRET_NAMES or name.startswith(".env."):
        return True
    return name.endswith(SECRET_SUFFIXES)


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


def codex_fallback_filenames(root: Path) -> tuple[str, ...]:
    path = root / ".codex" / "config.toml"
    matcher = IgnoreMatcher(root)
    if matcher.ignored(PurePosixPath(".codex/config.toml")):
        return ()
    text, _, _, warning = (
        read_text(path) if path.is_file() and not path.is_symlink() else (None, None, None, None)
    )
    if text is None or warning:
        return ()
    match = CODEX_FALLBACK_LIST.search(text)
    if not match:
        return ()
    names: list[str] = []
    for double_quoted, single_quoted in TOML_QUOTED_STRING.findall(match.group(1)):
        try:
            value = json.JSONDecoder().decode(f'"{double_quoted}"') if double_quoted else single_quoted
        except json.JSONDecodeError:
            continue
        if value and Path(value).name == value and not is_secret_path(PurePosixPath(value)):
            names.append(value)
    return tuple(dict.fromkeys(names))


def walk_candidates(
    root: Path,
    fallback_names: frozenset[str],
    excluded_roots: frozenset[PurePosixPath] = frozenset(),
) -> tuple[list[Path], list[dict[str, str]], IgnoreMatcher, bool]:
    matcher = IgnoreMatcher(root)
    candidates: list[Path] = []
    symlink_candidates: list[Path] = []
    skipped = matcher.skipped
    candidate_budget_exceeded = False
    for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        rel_current = current_path.relative_to(root)
        matcher.add_nested_gitignore(current_path, PurePosixPath(rel_current.as_posix()))
        kept_dirs: list[str] = []
        for dirname in sorted(dirs):
            rel = PurePosixPath((rel_current / dirname).as_posix())
            if is_link_like(current_path / dirname):
                skipped.append(
                    {
                        "path": rel.as_posix(),
                        "reason": "symlink or reparse directory not followed",
                    }
                )
                continue
            if rel in excluded_roots:
                skipped.append({"path": rel.as_posix(), "reason": "auditor's installed package excluded"})
                continue
            if matcher.ignored(rel, is_dir=True):
                if any(part in DEFAULT_IGNORED_DIRS for part in rel.parts):
                    skipped.append({"path": rel.as_posix(), "reason": "default excluded directory"})
                continue
            kept_dirs.append(dirname)
        dirs[:] = kept_dirs
        for filename in sorted(files):
            path = current_path / filename
            rel = PurePosixPath(path.relative_to(root).as_posix())
            if matcher.ignored(rel):
                continue
            if is_secret_path(rel):
                if name_has_hint(rel.stem) or rel.name.lower() in EXACT_NAMES:
                    skipped.append({"path": rel.as_posix(), "reason": "secret-like filename"})
                continue
            if is_candidate(rel, fallback_names):
                if is_link_like(path):
                    symlink_candidates.append(path)
                    continue
                if not path.is_file():
                    skipped.append({"path": rel.as_posix(), "reason": "non-regular filesystem entry"})
                    continue
                if len(candidates) >= MAX_CANDIDATE_FILES:
                    candidate_budget_exceeded = True
                    continue
                candidates.append(path)
    for path in symlink_candidates:
        rel = PurePosixPath(path.relative_to(root).as_posix())
        try:
            resolved = path.resolve(strict=True)
            target_relative = PurePosixPath(resolved.relative_to(root.resolve()).as_posix())
        except FileNotFoundError:
            skipped.append({"path": rel.as_posix(), "reason": "symlink target does not exist"})
            continue
        except (OSError, ValueError):
            skipped.append({"path": rel.as_posix(), "reason": "symlink escapes audit root"})
            continue
        if (
            is_secret_path(target_relative)
            or matcher.ignored(target_relative)
            or not resolved.is_file()
            or not is_candidate(target_relative, fallback_names)
        ):
            skipped.append({"path": rel.as_posix(), "reason": "symlink target excluded from audit"})
            continue
        if len(candidates) >= MAX_CANDIDATE_FILES:
            candidate_budget_exceeded = True
            continue
        candidates.append(path)
    candidates.sort(key=lambda p: p.relative_to(root).as_posix())
    skipped.sort(key=lambda item: item["path"])
    return candidates, skipped, matcher, candidate_budget_exceeded


def read_text(path: Path) -> tuple[str | None, str | None, int | None, str | None]:
    try:
        size = path.stat().st_size
        if size > MAX_READ_BYTES:
            return None, None, size, f"file exceeds {MAX_READ_BYTES} byte read limit"
        raw = path.read_bytes()
        if len(raw) > MAX_READ_BYTES:
            return None, None, len(raw), f"file exceeds {MAX_READ_BYTES} byte read limit"
        text = raw.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
        return text, hashlib.sha256(raw).hexdigest(), len(raw), None
    except OSError as exc:
        return None, None, None, f"unable to read: {exc.__class__.__name__}"


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str | None]:
    if not text.startswith("---\n"):
        return {}, None
    closing = re.search(r"(?m)^---[ \t]*(?:\n|$)", text[4:])
    if closing is None:
        return {}, "unclosed YAML frontmatter"
    end = 4 + closing.start()
    metadata: dict[str, Any] = {}
    for number, raw in enumerate(text[4:end].splitlines(), start=2):
        if not raw.strip() or raw.lstrip().startswith("#") or raw.startswith((" ", "\t", "-")):
            continue
        if ":" not in raw:
            return metadata, f"malformed frontmatter at line {number}"
        key, value = raw.split(":", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if not key:
            return metadata, f"empty frontmatter key at line {number}"
        lowered = value.lower()
        if lowered in {"true", "false"}:
            metadata[key] = lowered == "true"
        elif lowered in {"null", "none", "~"}:
            metadata[key] = None
        else:
            metadata[key] = value
    return metadata, None


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
    if metadata.get("role"):
        role = str(metadata["role"])
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
    for line in text.splitlines(keepends=True):
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
    if re.match(r"^[A-Za-z]:[\\/]", target):
        digest = hashlib.sha256(target.encode("utf-8")).hexdigest()
        return "<absolute-filesystem-path>", digest, "absolute-filesystem"
    if re.match(r"^~[^/\\]*[/\\]", target) or target.startswith("\\"):
        digest = hashlib.sha256(target.encode("utf-8")).hexdigest()
        return "<absolute-filesystem-path>", digest, "absolute-filesystem"
    if target.startswith("/"):
        digest = hashlib.sha256(target.encode("utf-8")).hexdigest()
        return "<root-relative-path>", digest, "root-relative"
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
    if target_kind == "absolute-filesystem":
        return None, None, False, None
    if target_kind == "relative" and re.match(r"^[a-z][a-z0-9+.-]*:", target, re.IGNORECASE):
        return None, None, None, None
    try:
        candidate = (
            (root / target.lstrip("/")).resolve()
            if target.startswith("/")
            else (root / relative.parent / target).resolve()
        )
    except (OSError, ValueError):
        return None, None, False, None
    try:
        relative_candidate = PurePosixPath(candidate.relative_to(root.resolve()).as_posix())
    except (OSError, ValueError):
        return candidate, None, False, None
    try:
        exists = candidate.exists()
    except (OSError, ValueError):
        exists = None
    return candidate, relative_candidate, True, exists


def _automatic_imports(text: str) -> Iterator[tuple[str, int]]:
    scan_text = mask_fenced_code(text)
    for match in IMPORT_LINE.finditer(scan_text):
        target = match.group(1).strip().split("#", 1)[0]
        if target:
            yield target, match.start()


def local_references(
    text: str,
    relative: PurePosixPath,
    root: Path,
    inventoried_paths: frozenset[PurePosixPath] = frozenset(),
    import_exclusions: dict[PurePosixPath, str] | None = None,
    recognize_imports: bool = False,
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    scan_text = mask_fenced_code(text)
    raw_matches = [
        (markdown_destination(raw), start, "markdown-link")
        for raw, start in markdown_link_payloads(scan_text)
    ]
    raw_matches.extend(
        (
            match.group(1).strip(),
            match.start(),
            "automatic-import" if recognize_imports else "at-reference",
        )
        for match in IMPORT_LINE.finditer(scan_text)
    )
    for raw, start, edge_type in sorted(raw_matches, key=lambda item: item[1]):
        target = raw.split("#", 1)[0]
        if not target or target.startswith("#"):
            continue
        display_target, target_sha256, target_kind = sanitized_reference_target(target)
        if target_kind == "relative" and re.match(r"^[a-z][a-z0-9+.-]*:", target, re.IGNORECASE):
            continue
        candidate, relative_candidate, inside, exists = _reference_candidate(target, relative, root)
        if (
            candidate is None
            and inside is False
            and target_kind
            not in {
                "absolute-filesystem",
                "root-relative",
            }
        ):
            display_target = "<invalid-filesystem-path>"
            target_sha256 = hashlib.sha256(target.encode("utf-8")).hexdigest()
            target_kind = "invalid-filesystem"
        if inside is True and exists is True:
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
    return refs


def paragraph_blocks(text: str, path: str) -> Iterator[dict[str, Any]]:
    offset = 0
    for chunk in re.split(r"\n\s*\n", text):
        start = text.find(chunk, offset)
        offset = max(start + len(chunk), offset)
        normalized = re.sub(r"\s+", " ", chunk.strip())
        if normalized.startswith("#") or len(normalized) < 48 or len(normalized.split()) < 7:
            continue
        yield {
            "path": path,
            "line": line_for_offset(text, start),
            "sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        }


def _bounded_read(
    path: Path,
    already_read: int,
) -> tuple[tuple[str | None, str | None, int | None, str | None], int, bool]:
    try:
        size = path.stat().st_size
    except OSError as exc:
        return (None, None, None, f"unable to read: {exc.__class__.__name__}"), already_read, False
    if already_read + size > MAX_TOTAL_READ_BYTES:
        return (
            (None, None, size, f"aggregate read budget exceeds {MAX_TOTAL_READ_BYTES} bytes"),
            already_read,
            True,
        )
    result = read_text(path)
    consumed = result[2] if result[0] is not None and result[2] is not None else 0
    return result, already_read + consumed, False


def _import_candidate_reason(
    candidate: Path | None,
    relative_candidate: PurePosixPath | None,
    inside: bool | None,
    exists: bool | None,
    matcher: IgnoreMatcher,
) -> str | None:
    if inside is not True:
        return "out-of-scope"
    if exists is not True or candidate is None or relative_candidate is None:
        return "missing" if exists is False else "unresolved"
    if is_secret_path(relative_candidate):
        return "excluded-secret"
    if matcher.ignored(relative_candidate):
        return "excluded-ignored"
    try:
        mode = candidate.stat().st_mode
    except OSError:
        return "unresolved"
    if not stat.S_ISREG(mode):
        return "excluded-non-regular"
    return None


def build_inventory(root_value: str | Path) -> dict[str, Any]:
    root = Path(root_value).resolve()
    if not root.is_dir():
        raise ValueError(f"not a directory: {root_value}")
    fallback_sequence = codex_fallback_filenames(root)
    fallback_names = frozenset(fallback_sequence)
    excluded_roots: set[PurePosixPath] = set()
    auditor_package = Path(__file__).resolve().parent.parent
    try:
        relative_package = auditor_package.relative_to(root)
    except ValueError:
        pass
    else:
        if relative_package != Path("."):
            excluded_roots.add(PurePosixPath(relative_package.as_posix()))
    paths, skipped, matcher, candidate_budget_exceeded = walk_candidates(
        root,
        fallback_names,
        frozenset(excluded_roots),
    )
    path_set = set(paths)
    imported_paths: set[PurePosixPath] = set()
    import_exclusions: dict[PurePosixPath, str] = {}
    read_results: dict[Path, tuple[str | None, str | None, int | None, str | None]] = {}
    total_read_bytes = 0
    aggregate_budget_exceeded = False

    queue: list[tuple[Path, int, bool]] = [(path, 0, False) for path in paths]
    import_expansion_depth: dict[Path, int] = {}
    queue_index = 0
    while queue_index < len(queue):
        path, depth, reached_by_import = queue[queue_index]
        queue_index += 1
        if reached_by_import:
            previous_depth = import_expansion_depth.get(path)
            if previous_depth is not None and previous_depth <= depth:
                continue
            import_expansion_depth[path] = depth
        if path not in read_results:
            result, total_read_bytes, exceeded = _bounded_read(path, total_read_bytes)
            read_results[path] = result
            aggregate_budget_exceeded = aggregate_budget_exceeded or exceeded
        text = read_results[path][0]
        if text is None:
            continue
        relative = PurePosixPath(path.relative_to(root).as_posix())
        is_claude_surface = relative.name.lower() in {"claude.md", "claude.local.md"}
        if not (is_claude_surface or reached_by_import):
            continue
        if depth >= MAX_IMPORT_DEPTH:
            for target, _ in _automatic_imports(text):
                _, relative_candidate, _, _ = _reference_candidate(target, relative, root)
                if relative_candidate is not None:
                    import_exclusions[relative_candidate] = "excluded-depth-limit"
            continue
        for target, _ in _automatic_imports(text):
            candidate, relative_candidate, inside, exists = _reference_candidate(target, relative, root)
            reason = _import_candidate_reason(
                candidate,
                relative_candidate,
                inside,
                exists,
                matcher,
            )
            if relative_candidate is not None and reason is not None:
                import_exclusions.setdefault(relative_candidate, reason)
            if reason is not None or candidate is None or relative_candidate is None:
                continue
            if candidate in path_set:
                imported_paths.add(relative_candidate)
                queue.append((candidate, depth + 1, True))
                continue
            if len(path_set) >= MAX_CANDIDATE_FILES:
                candidate_budget_exceeded = True
                import_exclusions[relative_candidate] = "excluded-candidate-budget"
                continue
            path_set.add(candidate)
            paths.append(candidate)
            imported_paths.add(relative_candidate)
            queue.append((candidate, depth + 1, True))

    paths.sort(key=lambda path: path.relative_to(root).as_posix())
    selected_codex: set[str] = set()
    by_directory: dict[PurePosixPath, dict[str, Path]] = defaultdict(dict)
    for path in paths:
        relative = PurePosixPath(path.relative_to(root).as_posix())
        result = read_results[path]
        if result[2] is not None and result[2] > 0:
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
    for path in paths:
        relative = PurePosixPath(path.relative_to(root).as_posix())
        text, digest, byte_count, warning = read_results[path]
        if warning:
            warnings.append({"path": relative.as_posix(), "message": warning})
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
            )
            lines = len(text.splitlines())
            all_blocks.extend(paragraph_blocks(text, relative.as_posix()))
        if metadata_error:
            warnings.append({"path": relative.as_posix(), "message": metadata_error})
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
            "path": relative.as_posix(),
            "bytes": byte_count,
            "lines": lines,
            "sha256": digest,
            "metadata": metadata,
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

    partial = (
        candidate_budget_exceeded
        or aggregate_budget_exceeded
        or any(item["sha256"] is None for item in files)
    )
    if candidate_budget_exceeded:
        skipped.append({"path": ".", "reason": "candidate file budget exceeded"})
    skipped.sort(key=lambda item: (item["path"], item["reason"]))
    return {
        "schema_version": INVENTORY_VERSION,
        "root": ".",
        "coverage": {
            "status": "partial" if partial else "complete",
            "candidate_files": len(files),
            "read_bytes": total_read_bytes,
            "limits": {
                "max_candidate_files": MAX_CANDIDATE_FILES,
                "max_total_read_bytes": MAX_TOTAL_READ_BYTES,
                "max_file_read_bytes": MAX_READ_BYTES,
                "max_import_depth": MAX_IMPORT_DEPTH,
            },
        },
        "files": files,
        "exact_overlap_groups": overlaps,
        "skipped": skipped,
        "warnings": sorted(warnings, key=lambda item: (item["path"], item["message"])),
    }


def deterministic_findings(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for group in inventory["exact_overlap_groups"]:
        locations = [{"path": item["path"], "line": item["line"]} for item in group["occurrences"]]
        findings.append(
            {
                "id": f"exact-overlap:{group['sha256'][:12]}",
                "severity": "medium",
                "evidence_type": "deterministic",
                "category": "exact-duplication",
                "summary": "An identical substantive block occurs in multiple files.",
                "locations": locations,
                "uncertainty": "Intent and necessity require human or model judgment.",
            }
        )
    status_files = [
        item for item in inventory["files"] if item["role"] == "current-state" and not item["archive"]
    ]
    if len(status_files) > 1:
        findings.append(
            {
                "id": "current-state:multiple-surfaces",
                "severity": "medium",
                "evidence_type": "deterministic",
                "category": "competing-current-truth",
                "summary": "Multiple non-archived files appear to represent current state.",
                "locations": [{"path": item["path"]} for item in status_files],
                "uncertainty": "The files may have intentionally distinct scopes.",
            }
        )
    for item in inventory["files"]:
        if item["retired_metadata"] and not item["archive"]:
            findings.append(
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
        for ref in item["references"]:
            if ref["inside_root"] and not ref["exists"]:
                findings.append(
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
    return sorted(findings, key=lambda item: item["id"])


def build_audit(root_value: str | Path) -> dict[str, Any]:
    inventory = build_inventory(root_value)
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "read-only",
        "engine": {
            "name": "agent-docs-doctor",
            "version": __version__,
            "configuration": {
                "max_read_bytes": MAX_READ_BYTES,
                "max_ignore_rules": MAX_IGNORE_RULES,
                "max_candidate_files": MAX_CANDIDATE_FILES,
                "max_total_read_bytes": MAX_TOTAL_READ_BYTES,
                "max_import_depth": MAX_IMPORT_DEPTH,
            },
        },
        "inventory": inventory,
        "findings": deterministic_findings(inventory),
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


def validate_audit(data: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["report must be a JSON object"]
    schema_version = data.get("schema_version")
    if schema_version not in {SCHEMA_VERSION, LEGACY_SCHEMA_VERSION}:
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
                "max_candidate_files",
                "max_total_read_bytes",
                "max_import_depth",
            }
            if not isinstance(configuration, dict):
                errors.append("engine.configuration must be an object")
            else:
                for key in sorted(required_configuration):
                    value = configuration.get(key)
                    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                        errors.append(f"engine.configuration.{key} must be a positive integer")
                for key, value in configuration.items():
                    if key in required_configuration:
                        continue
                    if not isinstance(key, str):
                        errors.append("engine.configuration keys must be strings")
                    elif not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                        errors.append(f"engine.configuration.{key} must be a positive integer")
    for key in ("judgment_queue", "limitations"):
        value = data.get(key)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
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
                if coverage.get("status") not in {"complete", "partial"}:
                    errors.append("inventory.coverage.status must be 'complete' or 'partial'")
                for key in ("candidate_files", "read_bytes"):
                    value = coverage.get(key)
                    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                        errors.append(f"inventory.coverage.{key} must be a non-negative integer")
                limits = coverage.get("limits")
                if not isinstance(limits, dict):
                    errors.append("inventory.coverage.limits must be an object")
                else:
                    required_limits = {
                        "max_candidate_files",
                        "max_total_read_bytes",
                        "max_file_read_bytes",
                        "max_import_depth",
                    }
                    for key in sorted(required_limits):
                        value = limits.get(key)
                        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                            errors.append(f"inventory.coverage.limits.{key} must be a positive integer")
                    for key, value in limits.items():
                        if key in required_limits:
                            continue
                        if not isinstance(key, str):
                            errors.append("inventory.coverage.limits keys must be strings")
                        elif not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                            errors.append(f"inventory.coverage.limits.{key} must be a positive integer")
        files = inventory.get("files")
        if isinstance(files, list):
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
            for index, entry in enumerate(files):
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
                references = entry.get("references")
                if not isinstance(references, list):
                    errors.append(f"inventory.files[{index}].references must be an array")
                else:
                    for ref_index, reference in enumerate(references):
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
                        if current and reference.get("edge_type") not in {
                            "markdown-link",
                            "automatic-import",
                            "at-reference",
                        }:
                            errors.append(f"{prefix}.edge_type is invalid")
                        if current and reference.get("resolution") not in {
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
                        }:
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
                if not isinstance(entry.get("platforms"), list) or not all(
                    isinstance(item, str) for item in entry.get("platforms", [])
                ):
                    errors.append(f"inventory.files[{index}].platforms must be an array of strings")
                for key in ("kind", "loading", "role", "classification_basis"):
                    if not isinstance(entry.get(key), str):
                        errors.append(f"inventory.files[{index}].{key} must be a string")
                for key in ("archive", "retired_metadata"):
                    if not isinstance(entry.get(key), bool):
                        errors.append(f"inventory.files[{index}].{key} must be boolean")
                if current and entry.get("discovered_by") not in {
                    "filename",
                    "automatic-import",
                }:
                    errors.append(f"inventory.files[{index}].discovered_by is invalid")
        overlaps = inventory.get("exact_overlap_groups")
        if isinstance(overlaps, list):
            for index, group in enumerate(overlaps):
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
                for occurrence_index, occurrence in enumerate(occurrences):
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
        for key, message_key in (("skipped", "reason"), ("warnings", "message")):
            items = inventory.get(key)
            if isinstance(items, list):
                for index, item in enumerate(items):
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
        seen: set[str] = set()
        for index, finding in enumerate(findings):
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
                    errors.append(f"duplicate finding id: {identifier}")
                seen.add(identifier)
            for key in ("category", "summary", "uncertainty"):
                if not isinstance(finding.get(key), str):
                    errors.append(f"findings[{index}].{key} must be a string")
            locations = finding.get("locations")
            if not isinstance(locations, list):
                errors.append(f"findings[{index}].locations must be an array")
            else:
                for location_index, location in enumerate(locations):
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
            if "evidence" in finding and not isinstance(finding["evidence"], dict):
                errors.append(f"findings[{index}].evidence must be an object")
            if finding.get("severity") not in {"critical", "high", "medium", "low", "informational"}:
                errors.append(f"findings[{index}] has invalid severity")
            if finding.get("evidence_type") not in {"deterministic", "model-judgment", "user-decision"}:
                errors.append(f"findings[{index}] has invalid evidence_type")
    return errors


def dump_json(data: Any, pretty: bool = False) -> str:
    return json.dumps(data, indent=2 if pretty else None, sort_keys=True, ensure_ascii=False) + "\n"
