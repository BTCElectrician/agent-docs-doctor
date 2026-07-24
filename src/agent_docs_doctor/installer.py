"""Safe, user-level Agent Skill installation with exact previews and backups."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import sysconfig
import tempfile
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path, PurePosixPath
from typing import Any

from .version import __version__

SKILL_NAME = "agent-docs-doctor"
MANIFEST_NAME = ".agent-docs-doctor-install.json"
CLIENT_PATHS = {
    "codex": Path(".agents/skills") / SKILL_NAME,
    "claude": Path(".claude/skills") / SKILL_NAME,
    "cursor": Path(".cursor/skills") / SKILL_NAME,
}
SAFE_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}\Z")


@dataclass(frozen=True)
class InstallPlan:
    action: str
    client: str
    target: Path
    state: str
    files: tuple[str, ...]
    backup: Path | None = None
    message: str = ""
    expected_manifest_sha256: str | None = None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bundled_skill_root() -> Path:
    try:
        distribution = metadata.distribution("agent-docs-doctor")
    except metadata.PackageNotFoundError:
        distribution = None
    if distribution is not None:
        for item in distribution.files or ():
            if item.as_posix().endswith("share/agent-docs-doctor/skill/SKILL.md"):
                candidate = Path(str(distribution.locate_file(item))).resolve().parent
                if (candidate / "SKILL.md").is_file():
                    return candidate
    installed = Path(sysconfig.get_path("data")) / "share" / "agent-docs-doctor" / "skill"
    if (installed / "SKILL.md").is_file():
        return installed
    source_checkout = Path(__file__).resolve().parents[2]
    if (source_checkout / "SKILL.md").is_file():
        return source_checkout
    raise FileNotFoundError("bundled Agent Skill resources are unavailable")


def _source_files() -> tuple[Path, ...]:
    root = bundled_skill_root()
    allowed_roots = (
        root / "SKILL.md",
        root / "agents" / "openai.yaml",
        root / "references",
    )
    files: list[Path] = []
    for item in allowed_roots:
        if item.is_file() and not item.is_symlink():
            files.append(item)
        elif item.is_dir() and not item.is_symlink():
            files.extend(path for path in item.rglob("*") if path.is_file() and not path.is_symlink())
    return tuple(sorted(files, key=lambda path: path.relative_to(root).as_posix()))


def _desired_manifest(client: str) -> dict[str, Any]:
    root = bundled_skill_root()
    return {
        "format": "agent-docs-doctor.skill-install.v1",
        "owner": "agent-docs-doctor",
        "version": __version__,
        "client": client,
        "files": {path.relative_to(root).as_posix(): _sha256(path) for path in _source_files()},
    }


def _read_manifest(target: Path, expected_client: str | None = None) -> dict[str, Any] | None:
    path = target / MANIFEST_NAME
    try:
        file_stat = path.lstat()
        if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_size > 1_000_000:
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if (
        not isinstance(value, dict)
        or value.get("format") != "agent-docs-doctor.skill-install.v1"
        or value.get("owner") != "agent-docs-doctor"
        or not isinstance(value.get("version"), str)
        or SAFE_VERSION.fullmatch(value["version"]) is None
        or value.get("client") not in CLIENT_PATHS
        or (expected_client is not None and value["client"] != expected_client)
    ):
        return None
    files = value.get("files")
    if not isinstance(files, dict) or "SKILL.md" not in files:
        return None
    for relative, digest in files.items():
        relative_path = PurePosixPath(relative) if isinstance(relative, str) else None
        if (
            relative_path is None
            or not relative
            or relative_path.is_absolute()
            or ".." in relative_path.parts
            or "\\" in relative
            or ":" in relative
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            return None
    return value


def _manifest_sha256(target: Path) -> str | None:
    path = target / MANIFEST_NAME
    try:
        file_stat = path.lstat()
        if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_size > 1_000_000:
            return None
        return _sha256(path)
    except OSError:
        return None


def _path_entry_exists(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return True


def _installed_files_match(target: Path, manifest: dict[str, Any]) -> bool:
    for relative, digest in manifest["files"].items():
        path = target / relative
        try:
            file_stat = path.lstat()
            if not stat.S_ISREG(file_stat.st_mode) or _sha256(path) != digest:
                return False
        except OSError:
            return False
    return True


def _backup_path(home: Path, client: str, target: Path) -> Path:
    manifest = _read_manifest(target, client) or {}
    fingerprint = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    raw_version = str(manifest.get("version", "unknown"))
    version = re.sub(r"[^A-Za-z0-9._+-]", "-", raw_version)[:128].strip(".") or "unknown"
    parent = home / ".agent-docs-doctor" / "backups" / client
    base = parent / f"{SKILL_NAME}-{version}-{fingerprint}"
    candidate = base
    suffix = 2
    while _path_entry_exists(candidate):
        candidate = parent / f"{base.name}-{suffix}"
        suffix += 1
    return candidate


def target_for(client: str, home: Path | None = None) -> Path:
    if client not in CLIENT_PATHS:
        raise ValueError(f"unsupported client: {client}")
    return (home or Path.home()) / CLIENT_PATHS[client]


def plan_install(
    client: str,
    *,
    home: Path | None = None,
    update: bool = False,
) -> InstallPlan:
    actual_home = home or Path.home()
    target = target_for(client, actual_home)
    desired = _desired_manifest(client)
    files = tuple(desired["files"])
    if not _path_entry_exists(target):
        return InstallPlan("install", client, target, "ready", files)
    current = _read_manifest(target, client)
    if current is None:
        return InstallPlan(
            "install",
            client,
            target,
            "blocked-unmanaged",
            files,
            message="The target exists but is not owned by Agent Docs Doctor.",
        )
    if current == desired and _installed_files_match(target, current):
        return InstallPlan(
            "install",
            client,
            target,
            "already-installed",
            files,
            expected_manifest_sha256=_manifest_sha256(target),
        )
    if not update:
        return InstallPlan(
            "install",
            client,
            target,
            "update-required",
            files,
            message="A different managed version exists. Preview again with --update.",
            expected_manifest_sha256=_manifest_sha256(target),
        )
    return InstallPlan(
        "update",
        client,
        target,
        "ready",
        files,
        backup=_backup_path(actual_home, client, target),
        expected_manifest_sha256=_manifest_sha256(target),
    )


def _write_staged_skill(stage: Path, client: str) -> None:
    source_root = bundled_skill_root()
    manifest = _desired_manifest(client)
    for source in _source_files():
        relative = source.relative_to(source_root)
        destination = stage / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    (stage / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for relative, digest in manifest["files"].items():
        if _sha256(stage / relative) != digest:
            raise OSError(f"staged skill verification failed for {relative}")


def apply_install(plan: InstallPlan) -> InstallPlan:
    if plan.action not in {"install", "update"} or plan.state != "ready":
        return plan
    target = plan.target
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{SKILL_NAME}-install-", dir=target.parent))
    moved_existing = False
    try:
        _write_staged_skill(stage, plan.client)
        target_exists = _path_entry_exists(target)
        if plan.action == "install" and target_exists:
            raise OSError("installation target changed after preview; preview again")
        if plan.action == "update":
            if not target_exists:
                raise OSError("managed installation changed after preview; preview again")
            if plan.backup is None:
                raise OSError("update has no backup destination")
            if _manifest_sha256(target) != plan.expected_manifest_sha256:
                raise OSError("managed installation changed after preview; preview again")
            plan.backup.parent.mkdir(parents=True, exist_ok=True)
            os.replace(target, plan.backup)
            moved_existing = True
        os.replace(stage, target)
    except Exception:
        if moved_existing and plan.backup is not None and not _path_entry_exists(target):
            os.replace(plan.backup, target)
        if stage.exists():
            shutil.rmtree(stage)
        raise
    return InstallPlan(
        plan.action,
        plan.client,
        plan.target,
        "applied",
        plan.files,
        plan.backup,
        "Installed files were verified before activation.",
        _manifest_sha256(target),
    )


def plan_uninstall(client: str, *, home: Path | None = None) -> InstallPlan:
    actual_home = home or Path.home()
    target = target_for(client, actual_home)
    if not _path_entry_exists(target):
        return InstallPlan("uninstall", client, target, "not-installed", ())
    manifest = _read_manifest(target, client)
    if manifest is None:
        return InstallPlan(
            "uninstall",
            client,
            target,
            "blocked-unmanaged",
            (),
            message="The target is not a managed Agent Docs Doctor installation.",
        )
    files = tuple(sorted(str(path) for path in manifest.get("files", {})))
    return InstallPlan(
        "uninstall",
        client,
        target,
        "ready",
        files,
        backup=_backup_path(actual_home, client, target),
        expected_manifest_sha256=_manifest_sha256(target),
    )


def apply_uninstall(plan: InstallPlan) -> InstallPlan:
    if plan.action != "uninstall" or plan.state != "ready":
        return plan
    if plan.backup is None:
        raise OSError("uninstall has no backup destination")
    if _manifest_sha256(plan.target) != plan.expected_manifest_sha256:
        raise OSError("managed installation changed after preview; preview again")
    plan.backup.parent.mkdir(parents=True, exist_ok=True)
    os.replace(plan.target, plan.backup)
    return InstallPlan(
        plan.action,
        plan.client,
        plan.target,
        "applied",
        plan.files,
        plan.backup,
        "The skill was moved to a reversible backup; no files were deleted.",
        plan.expected_manifest_sha256,
    )


def plan_as_dict(plan: InstallPlan) -> dict[str, Any]:
    return {
        "action": plan.action,
        "client": plan.client,
        "target": str(plan.target),
        "state": plan.state,
        "files": list(plan.files),
        "backup": str(plan.backup) if plan.backup else None,
        "message": plan.message,
        "managed_state_sha256": plan.expected_manifest_sha256,
    }
