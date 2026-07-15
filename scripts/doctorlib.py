#!/usr/bin/env python3
"""Deterministic, read-only evidence collection for Agent Docs Doctor."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA_VERSION = "agent-docs-doctor.audit.v1"
INVENTORY_VERSION = "agent-docs-doctor.inventory.v1"
MAX_READ_BYTES = 2_000_000

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

NAME_HINT = re.compile(
    r"(?:agent|instruction|rule|status|handoff|work[-_ ]?queue|startup|context|"
    r"manifest|governance|authority|current[-_ ]?state|model[-_ ]?configs?|plan)",
    re.IGNORECASE,
)

TEXT_SUFFIXES = {".md", ".mdc", ".txt", ".yaml", ".yml", ".json", ".toml"}
ARCHIVE_PARTS = {"archive", "archived", "retired", "deprecated", "history"}
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
IMPORT_LINE = re.compile(r"(?m)^\s*@([^\s#]+)\s*$")


@dataclass(frozen=True)
class IgnoreRule:
    pattern: str
    negate: bool
    directory_only: bool
    anchored: bool


class IgnoreMatcher:
    """Small deterministic gitignore-style matcher for non-git and test repos."""

    def __init__(self, root: Path) -> None:
        self.rules: list[IgnoreRule] = []
        for filename in (".gitignore", ".ignore", ".agent-docs-doctorignore"):
            path = root / filename
            if path.is_file() and not is_secret_path(path):
                self.rules.extend(self._parse(path))

    @staticmethod
    def _parse(path: Path) -> list[IgnoreRule]:
        rules: list[IgnoreRule] = []
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return rules
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
                rules.append(IgnoreRule(line, negate, directory_only, anchored))
        return rules

    def ignored(self, relative: PurePosixPath, is_dir: bool = False) -> bool:
        text = relative.as_posix()
        parts = relative.parts
        ignored = any(part in DEFAULT_IGNORED_DIRS for part in parts)
        for rule in self.rules:
            if rule.directory_only and not (is_dir or any(fnmatch.fnmatch(p, rule.pattern) for p in parts)):
                continue
            if rule.anchored:
                matched = fnmatch.fnmatch(text, rule.pattern) or text.startswith(rule.pattern + "/")
            elif "/" in rule.pattern:
                matched = fnmatch.fnmatch(text, rule.pattern) or fnmatch.fnmatch(text, f"**/{rule.pattern}")
            else:
                matched = any(fnmatch.fnmatch(part, rule.pattern) for part in parts)
            if matched:
                ignored = not rule.negate
        return ignored

    def may_reinclude_below(self, relative: PurePosixPath) -> bool:
        """Return whether a negation rule may restore a path below a directory."""
        prefix = relative.as_posix().rstrip("/") + "/"
        return any(rule.negate and rule.pattern.lstrip("/").startswith(prefix) for rule in self.rules)


def is_secret_path(path: Path | PurePosixPath) -> bool:
    name = path.name.lower()
    if name in SECRET_NAMES or name.startswith(".env."):
        return True
    return name.endswith(SECRET_SUFFIXES)


def is_candidate(relative: PurePosixPath) -> bool:
    if is_secret_path(relative):
        return False
    name = relative.name.lower()
    suffix = relative.suffix.lower()
    parts_lower = tuple(part.lower() for part in relative.parts)
    if name in EXACT_NAMES:
        return True
    if len(parts_lower) >= 2 and parts_lower[-2] == "rules" and (
        ".claude" in parts_lower or ".cursor" in parts_lower
    ):
        return suffix in {".md", ".mdc"}
    if name == "config.toml" and ".codex" in parts_lower:
        return True
    if name in {"settings.json", "settings.local.json"} and ".claude" in parts_lower:
        return True
    if name in {".cursorignore", ".cursorindexingignore"}:
        return True
    return suffix in TEXT_SUFFIXES and bool(NAME_HINT.search(relative.stem))


def walk_candidates(root: Path) -> tuple[list[Path], list[dict[str, str]]]:
    matcher = IgnoreMatcher(root)
    candidates: list[Path] = []
    skipped: list[dict[str, str]] = []
    for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        rel_current = current_path.relative_to(root)
        kept_dirs: list[str] = []
        for dirname in sorted(dirs):
            rel = PurePosixPath((rel_current / dirname).as_posix())
            if matcher.ignored(rel, is_dir=True) and not matcher.may_reinclude_below(rel):
                continue
            kept_dirs.append(dirname)
        dirs[:] = kept_dirs
        for filename in sorted(files):
            path = current_path / filename
            rel = PurePosixPath(path.relative_to(root).as_posix())
            if matcher.ignored(rel):
                continue
            if is_secret_path(rel):
                if NAME_HINT.search(rel.stem) or rel.name.lower() in EXACT_NAMES:
                    skipped.append({"path": rel.as_posix(), "reason": "secret-like filename"})
                continue
            if is_candidate(rel):
                try:
                    path.resolve().relative_to(root.resolve())
                except (OSError, ValueError):
                    skipped.append({"path": rel.as_posix(), "reason": "symlink escapes audit root"})
                    continue
                candidates.append(path)
    candidates.sort(key=lambda p: p.relative_to(root).as_posix())
    skipped.sort(key=lambda item: item["path"])
    return candidates, skipped


def read_text(path: Path) -> tuple[str | None, str | None]:
    try:
        size = path.stat().st_size
        if size > MAX_READ_BYTES:
            return None, f"file exceeds {MAX_READ_BYTES} byte read limit"
        return path.read_text(encoding="utf-8", errors="replace"), None
    except OSError as exc:
        return None, f"unable to read: {exc.__class__.__name__}"


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str | None]:
    if not text.startswith("---\n"):
        return {}, None
    end = text.find("\n---", 4)
    if end < 0:
        return {}, "unclosed YAML frontmatter"
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


def classify(relative: PurePosixPath, metadata: dict[str, Any]) -> dict[str, Any]:
    name = relative.name.lower()
    parts = tuple(part.lower() for part in relative.parts)
    archive = any(part in ARCHIVE_PARTS for part in parts[:-1])
    status_value = str(metadata.get("status", "")).lower()
    retired = status_value in {"retired", "deprecated", "archived", "superseded"} or bool(
        metadata.get("retired")
    )

    if name.startswith("agents"):
        kind, platforms, loading, role = "instruction", ["codex", "cursor"], "automatic", "authority"
    elif name.startswith("claude"):
        kind, platforms, loading, role = "instruction", ["claude-code"], "automatic", "adapter"
    elif ".claude" in parts and "rules" in parts:
        scoped = "paths" in metadata
        kind, platforms, loading, role = (
            "scoped-rule",
            ["claude-code"],
            "conditional" if scoped else "automatic",
            "procedure",
        )
    elif ".cursor" in parts and "rules" in parts:
        if relative.suffix.lower() != ".mdc":
            kind, platforms, loading, role = "rule-like-file", ["cursor"], "not-loaded", "reference"
        else:
            always = str(metadata.get("alwaysApply", "")).lower() == "true"
            conditional = "globs" in metadata or bool(metadata.get("description"))
            load_mode = "automatic" if always else "conditional" if conditional else "manual"
            kind, platforms, loading, role = "scoped-rule", ["cursor"], load_mode, "procedure"
    elif name == "skill.md":
        kind, platforms, loading, role = "skill", ["agent-skills"], "conditional", "procedure"
    elif "status" in name or "handoff" in name or "work_queue" in name or "work-queue" in name:
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


def local_references(text: str, relative: PurePosixPath, root: Path) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    matches = list(MARKDOWN_LINK.finditer(text)) + list(IMPORT_LINE.finditer(text))
    for match in sorted(matches, key=lambda item: item.start()):
        raw = match.group(1).strip().strip("<>")
        target = raw.split("#", 1)[0]
        if not target or re.match(r"^[a-z][a-z0-9+.-]*:", target, re.IGNORECASE) or target.startswith("#"):
            continue
        candidate = (root / target.lstrip("/")).resolve() if target.startswith("/") else (
            root / relative.parent / target
        ).resolve()
        try:
            candidate.relative_to(root.resolve())
            inside = True
        except ValueError:
            inside = False
        refs.append(
            {
                "target": target,
                "line": line_for_offset(text, match.start()),
                "inside_root": inside,
                "exists": candidate.exists() if inside else None,
            }
        )
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
            "text": normalized,
            "sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        }


def build_inventory(root_value: str | Path) -> dict[str, Any]:
    root = Path(root_value).resolve()
    if not root.is_dir():
        raise ValueError(f"not a directory: {root_value}")
    paths, skipped = walk_candidates(root)
    files: list[dict[str, Any]] = []
    warnings: list[dict[str, str]] = []
    all_blocks: list[dict[str, Any]] = []
    for path in paths:
        relative = PurePosixPath(path.relative_to(root).as_posix())
        stat = path.stat()
        text, warning = read_text(path)
        if warning:
            warnings.append({"path": relative.as_posix(), "message": warning})
        metadata: dict[str, Any] = {}
        metadata_error = None
        refs: list[dict[str, Any]] = []
        digest = None
        lines = None
        if text is not None:
            metadata, metadata_error = parse_frontmatter(text)
            refs = local_references(text, relative, root)
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            lines = len(text.splitlines())
            all_blocks.extend(paragraph_blocks(text, relative.as_posix()))
        if metadata_error:
            warnings.append({"path": relative.as_posix(), "message": metadata_error})
        entry = {
            "path": relative.as_posix(),
            "bytes": stat.st_size,
            "lines": lines,
            "sha256": digest,
            "metadata": metadata,
            "references": refs,
            **classify(relative, metadata),
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
                        "id": f"broken-reference:{item['path']}:{ref['line']}:{ref['target']}",
                        "severity": "medium",
                        "evidence_type": "deterministic",
                        "category": "broken-reference",
                        "summary": "A local Markdown reference does not resolve.",
                        "locations": [{"path": item["path"], "line": ref["line"]}],
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
    inventory = data.get("inventory")
    if not isinstance(inventory, dict):
        errors.append("inventory must be an object")
    elif inventory.get("schema_version") != INVENTORY_VERSION:
        errors.append(f"inventory.schema_version must be {INVENTORY_VERSION!r}")
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
            if identifier in seen:
                errors.append(f"duplicate finding id: {identifier}")
            if isinstance(identifier, str):
                seen.add(identifier)
            if finding.get("severity") not in {"critical", "high", "medium", "low", "informational"}:
                errors.append(f"findings[{index}] has invalid severity")
            if finding.get("evidence_type") not in {"deterministic", "model-judgment", "user-decision"}:
                errors.append(f"findings[{index}] has invalid evidence_type")
    return errors


def dump_json(data: Any, pretty: bool = False) -> str:
    return json.dumps(data, indent=2 if pretty else None, sort_keys=True, ensure_ascii=False) + "\n"
