#!/usr/bin/env python3
"""Deterministic, read-only evidence collection for Agent Docs Doctor."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from functools import cache
from pathlib import Path, PurePosixPath
from typing import Any

sys.dont_write_bytecode = True

SCHEMA_VERSION = "agent-docs-doctor.audit.v1"
INVENTORY_VERSION = "agent-docs-doctor.inventory.v1"
MAX_READ_BYTES = 2_000_000
MAX_IGNORE_RULES = 10_000

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
                    )
                )

    @staticmethod
    def _parse(
        path: Path,
        base: PurePosixPath,
        display_path: PurePosixPath,
        restores_defaults: bool,
    ) -> list[IgnoreRule]:
        rules: list[IgnoreRule] = []
        try:
            if path.stat().st_size > MAX_READ_BYTES:
                raise ValueError(
                    f"ignore control {display_path.as_posix()} exceeds " f"{MAX_READ_BYTES} byte read limit"
                )
            raw = path.read_bytes()
            if len(raw) > MAX_READ_BYTES:
                raise ValueError(
                    f"ignore control {display_path.as_posix()} exceeds " f"{MAX_READ_BYTES} byte read limit"
                )
            lines = raw.decode("utf-8", errors="replace").splitlines()
        except OSError as exc:
            raise ValueError(
                f"unable to read ignore control {display_path.as_posix()}: " f"{exc.__class__.__name__}"
            ) from exc
        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            negate = line.startswith("!")
            if negate:
                line = line[1:]
            anchored = line.startswith("/")
            line = line.lstrip("/")
            directory_only = line.endswith("/")
            line = line.rstrip("/")
            if line:
                if len(rules) >= MAX_IGNORE_RULES:
                    raise ValueError(
                        f"ignore control {display_path.as_posix()} exceeds " f"{MAX_IGNORE_RULES} rule limit"
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

    @cache
    def match(path_index: int, pattern_index: int) -> bool:
        if pattern_index == len(pattern_parts):
            return path_index == len(path_parts)
        segment = pattern_parts[pattern_index]
        if segment == "**":
            if pattern_index == len(pattern_parts) - 1:
                return path_index < len(path_parts)
            return match(path_index, pattern_index + 1) or (
                path_index < len(path_parts) and match(path_index + 1, pattern_index)
            )
        return (
            path_index < len(path_parts)
            and fnmatch.fnmatchcase(path_parts[path_index], segment)
            and match(path_index + 1, pattern_index + 1)
        )

    return match(0, 0)


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
) -> tuple[list[Path], list[dict[str, str]]]:
    matcher = IgnoreMatcher(root)
    candidates: list[Path] = []
    symlink_candidates: list[Path] = []
    skipped = matcher.skipped
    for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        rel_current = current_path.relative_to(root)
        matcher.add_nested_gitignore(current_path, PurePosixPath(rel_current.as_posix()))
        kept_dirs: list[str] = []
        for dirname in sorted(dirs):
            rel = PurePosixPath((rel_current / dirname).as_posix())
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
                if path.is_symlink():
                    symlink_candidates.append(path)
                    continue
                if not path.is_file():
                    skipped.append({"path": rel.as_posix(), "reason": "non-regular filesystem entry"})
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
        candidates.append(path)
    candidates.sort(key=lambda p: p.relative_to(root).as_posix())
    skipped.sort(key=lambda item: item["path"])
    return candidates, skipped


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
    if re.match(r"^~[^/\\]*[/\\]", target) or target.startswith("\\\\"):
        digest = hashlib.sha256(target.encode("utf-8")).hexdigest()
        return "<absolute-filesystem-path>", digest, "absolute-filesystem"
    if target.startswith("/"):
        digest = hashlib.sha256(target.encode("utf-8")).hexdigest()
        return "<root-relative-path>", digest, "root-relative"
    return target, None, "relative"


def local_references(text: str, relative: PurePosixPath, root: Path) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    scan_text = mask_fenced_code(text)
    raw_matches = [(markdown_destination(raw), start) for raw, start in markdown_link_payloads(scan_text)]
    raw_matches.extend((match.group(1).strip(), match.start()) for match in IMPORT_LINE.finditer(scan_text))
    for raw, start in sorted(raw_matches, key=lambda item: item[1]):
        target = raw.split("#", 1)[0]
        if not target or target.startswith("#"):
            continue
        display_target, target_sha256, target_kind = sanitized_reference_target(target)
        if target_kind == "relative" and re.match(r"^[a-z][a-z0-9+.-]*:", target, re.IGNORECASE):
            continue
        if target_kind == "absolute-filesystem":
            inside = False
            exists = None
        else:
            try:
                candidate = (
                    (root / target.lstrip("/")).resolve()
                    if target.startswith("/")
                    else (root / relative.parent / target).resolve()
                )
            except (OSError, ValueError):
                inside = False
                exists = None
                display_target = "<invalid-filesystem-path>"
                target_sha256 = hashlib.sha256(target.encode("utf-8")).hexdigest()
                target_kind = "invalid-filesystem"
            else:
                try:
                    candidate.relative_to(root.resolve())
                except (OSError, ValueError):
                    inside = False
                    exists = None
                else:
                    inside = True
                    try:
                        exists = candidate.exists()
                    except (OSError, ValueError):
                        exists = None
        reference = {
            "target": display_target,
            "target_kind": target_kind,
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
    paths, skipped = walk_candidates(root, fallback_names, frozenset(excluded_roots))
    selected_codex: set[str] = set()
    by_directory: dict[PurePosixPath, dict[str, Path]] = defaultdict(dict)
    read_results: dict[Path, tuple[str | None, str | None, int | None, str | None]] = {}
    for path in paths:
        relative = PurePosixPath(path.relative_to(root).as_posix())
        result = read_text(path)
        read_results[path] = result
        if result[2] is not None and result[2] > 0:
            by_directory[relative.parent][relative.name] = path
    for directory, names in by_directory.items():
        for candidate_name in ("AGENTS.override.md", "AGENTS.md", *fallback_sequence):
            if candidate_name in names:
                selected = PurePosixPath(directory / candidate_name).as_posix()
                selected_codex.add(selected)
                break
    selected_codex_paths = frozenset(selected_codex)
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
            refs = local_references(text, relative, root)
            lines = len(text.splitlines())
            all_blocks.extend(paragraph_blocks(text, relative.as_posix()))
        if metadata_error:
            warnings.append({"path": relative.as_posix(), "message": metadata_error})
        entry = {
            "path": relative.as_posix(),
            "bytes": byte_count,
            "lines": lines,
            "sha256": digest,
            "metadata": metadata,
            "references": refs,
            **classify(relative, metadata, fallback_names, selected_codex_paths),
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

    return {
        "schema_version": INVENTORY_VERSION,
        "root": ".",
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
                            f"broken-reference:{item['path']}:{ref['line']}:"
                            f"{ref['column']}:{ref['target']}"
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
    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION!r}")
    if data.get("mode") != "read-only":
        errors.append("mode must be 'read-only'")
    for key in ("inventory", "findings", "judgment_queue", "limitations"):
        if key not in data:
            errors.append(f"report missing {key}")
    for key in ("judgment_queue", "limitations"):
        value = data.get(key)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            errors.append(f"{key} must be an array of strings")
    inventory = data.get("inventory")
    if not isinstance(inventory, dict):
        errors.append("inventory must be an object")
    else:
        if inventory.get("schema_version") != INVENTORY_VERSION:
            errors.append(f"inventory.schema_version must be {INVENTORY_VERSION!r}")
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
            for index, entry in enumerate(files):
                if not isinstance(entry, dict):
                    errors.append(f"inventory.files[{index}] must be an object")
                    continue
                missing = sorted(required_file_keys - entry.keys())
                for key in missing:
                    errors.append(f"inventory.files[{index}] missing {key}")
                if not isinstance(entry.get("path"), str):
                    errors.append(f"inventory.files[{index}].path must be a string")
                if not isinstance(entry.get("references"), list):
                    errors.append(f"inventory.files[{index}].references must be an array")
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
            if not isinstance(finding.get("locations"), list):
                errors.append(f"findings[{index}].locations must be an array")
            if finding.get("severity") not in {"critical", "high", "medium", "low", "informational"}:
                errors.append(f"findings[{index}] has invalid severity")
            if finding.get("evidence_type") not in {"deterministic", "model-judgment", "user-decision"}:
                errors.append(f"findings[{index}] has invalid evidence_type")
    return errors


def dump_json(data: Any, pretty: bool = False) -> str:
    return json.dumps(data, indent=2 if pretty else None, sort_keys=True, ensure_ascii=False) + "\n"
