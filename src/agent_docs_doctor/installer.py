"""Safe, user-level Agent Skill installation with bound previews and backups."""

from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import os
import re
import secrets
import stat
import sys
from contextlib import suppress
from dataclasses import dataclass, replace
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
PREVIEW_FORMAT = "agent-docs-doctor.skill-preview.v1"
MAX_MANIFEST_BYTES = 1_000_000
MAX_SOURCE_FILE_BYTES = 16 * 1024 * 1024
MAX_SOURCE_TOTAL_BYTES = 64 * 1024 * 1024
MAX_TARGET_FILE_BYTES = 64 * 1024 * 1024
MAX_TARGET_TOTAL_BYTES = 256 * 1024 * 1024
MAX_TARGET_ENTRIES = 10_000
MAX_TARGET_DEPTH = 128
MAX_STATE_PATH_CHARS = 512
MAX_BACKUP_COLLISIONS = 1_000
BACKUP_PAYLOAD_NAME = "payload"
SOURCE_RELATIVE_PATHS = (
    "SKILL.md",
    "agents/openai.yaml",
    "references/AUDIT_RUBRIC.md",
    "references/EVALUATION_PROTOCOL.md",
    "references/MIGRATION_GUIDE.md",
    "references/PLATFORM_BEHAVIOR.md",
    "references/REPORT_SCHEMA.md",
)


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
    home: Path | None = None
    desired_manifest_json: str | None = None
    desired_manifest_sha256: str | None = None
    expected_target_sha256: str | None = None
    expected_target_move_sha256: str | None = None
    expected_path_sha256: str | None = None
    backup_reservation: Path | None = None
    plan_token: str | None = None


def _secure_mutation_supported() -> bool:
    """Return whether this runtime can mutate relative to held directory descriptors."""
    return (
        os.name == "posix"
        and os.open in os.supports_dir_fd
        and os.mkdir in os.supports_dir_fd
        and os.stat in os.supports_dir_fd
        and os.readlink in os.supports_dir_fd
        and sys.platform in {"darwin", "linux"}
    )


def _directory_open_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )


def _open_absolute_directory(path: Path) -> int:
    """Open an absolute directory one component at a time without following links."""
    if os.name != "posix":
        raise OSError("secure directory anchoring is unavailable on this platform")
    absolute = Path(os.path.abspath(os.fspath(path)))
    anchor = Path(absolute.anchor)
    if not anchor:
        raise OSError("secure directory anchoring requires an absolute path")
    descriptor = os.open(anchor, _directory_open_flags())
    try:
        for part in absolute.parts[1:]:
            child = os.open(part, _directory_open_flags(), dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        value = os.fstat(descriptor)
        if not stat.S_ISDIR(value.st_mode):
            raise OSError("anchored path is not a directory")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _remove_created_directory_by_identity(
    parent_fd: int,
    name: str,
    identity: tuple[int, int],
) -> bool:
    """Best-effort cleanup without removing a replacement entry."""

    try:
        visible = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return True
    except OSError:
        return False
    if not stat.S_ISDIR(visible.st_mode) or (visible.st_dev, visible.st_ino) != identity:
        return False
    try:
        os.rmdir(name, dir_fd=parent_fd)
    except OSError:
        return False
    return True


def _create_and_open_directory_at(
    parent_fd: int,
    name: str,
) -> int:
    """Create and anchor one directory, cleaning only its captured identity."""

    mkdir_returned = False
    created_identity: tuple[int, int] | None = None
    descriptor: int | None = None
    try:
        os.mkdir(name, mode=0o700, dir_fd=parent_fd)
        mkdir_returned = True
        created = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISDIR(created.st_mode):
            raise OSError("tool-created path is not a directory")
        created_identity = (created.st_dev, created.st_ino)
        descriptor = os.open(name, _directory_open_flags(), dir_fd=parent_fd)
        opened = os.fstat(descriptor)
        if not stat.S_ISDIR(opened.st_mode) or (opened.st_dev, opened.st_ino) != created_identity:
            raise OSError("tool-created directory changed while it was being anchored")
        return descriptor
    except BaseException as exc:
        if descriptor is not None:
            with suppress(OSError):
                os.close(descriptor)
        if isinstance(exc, OSError) and not mkdir_returned:
            raise
        if created_identity is None:
            raise OSError(
                "tool-created directory creation was interrupted before its identity "
                "could be captured; one or more unconfirmed private directory paths may remain"
            ) from exc
        try:
            cleaned = _remove_created_directory_by_identity(
                parent_fd,
                name,
                created_identity,
            )
        except BaseException as cleanup_exc:
            raise OSError(
                "tool-created directory could not be safely anchored or cleaned; "
                "one or more private directory paths may remain"
            ) from cleanup_exc
        if not cleaned:
            raise OSError(
                "tool-created directory could not be safely anchored or cleaned; "
                "one or more private directory paths may remain"
            ) from exc
        raise


def _remove_owned_empty_directory_at(
    parent_fd: int,
    name: str,
    directory_fd: int,
) -> None:
    """Remove only the still-visible empty directory held by ``directory_fd``."""

    visible = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    opened = os.fstat(directory_fd)
    if (
        not stat.S_ISDIR(visible.st_mode)
        or not stat.S_ISDIR(opened.st_mode)
        or visible.st_dev != opened.st_dev
        or visible.st_ino != opened.st_ino
    ):
        raise OSError("tool-created directory changed; refusing cleanup")
    os.rmdir(name, dir_fd=parent_fd)


@dataclass
class _AnchoredUserDirectory:
    """A user directory reached from a held, non-link home descriptor."""

    home: Path
    directory: Path
    descriptors: list[int]
    created: list[tuple[int, str, int]]

    @property
    def fd(self) -> int:
        return self.descriptors[-1]

    def cleanup_created(self) -> bool:
        cleaned = True
        for parent_fd, name, directory_fd in reversed(self.created):
            try:
                _remove_owned_empty_directory_at(parent_fd, name, directory_fd)
            except BaseException:
                cleaned = False
        return cleaned

    def assert_visible(self) -> None:
        """Fail if any held component is no longer at its supplied-home name."""
        visible_home = _open_absolute_directory(self.home)
        try:
            expected_home = os.fstat(self.descriptors[0])
            actual_home = os.fstat(visible_home)
            if expected_home.st_dev != actual_home.st_dev or expected_home.st_ino != actual_home.st_ino:
                raise OSError("supplied home changed during installer apply")
        finally:
            os.close(visible_home)
        relative = _relative_to_home(self.home, self.directory)
        for index, part in enumerate(relative.parts):
            try:
                visible = os.open(
                    part,
                    _directory_open_flags(),
                    dir_fd=self.descriptors[index],
                )
            except OSError as exc:
                raise OSError("skill path ancestor changed during installer apply") from exc
            try:
                expected = os.fstat(self.descriptors[index + 1])
                actual = os.fstat(visible)
                if expected.st_dev != actual.st_dev or expected.st_ino != actual.st_ino:
                    raise OSError("skill path ancestor changed during installer apply")
            finally:
                os.close(visible)

    def close(self) -> None:
        for descriptor in reversed(self.descriptors):
            with suppress(OSError):
                os.close(descriptor)

    def __enter__(self) -> _AnchoredUserDirectory:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def _anchor_user_directory(
    home: Path,
    directory: Path,
    *,
    create: bool,
) -> _AnchoredUserDirectory | None:
    if not _secure_mutation_supported():
        raise OSError("secure ancestor-relative mutation is unavailable on this platform")
    relative = _relative_to_home(home, directory)
    home_fd = _open_absolute_directory(home)
    descriptors = [home_fd]
    created: list[tuple[int, str, int]] = []
    try:
        for part in relative.parts:
            parent_fd = descriptors[-1]
            did_create = False
            try:
                child_fd = os.open(part, _directory_open_flags(), dir_fd=parent_fd)
            except FileNotFoundError:
                if not create:
                    for descriptor in reversed(descriptors):
                        os.close(descriptor)
                    return None
                try:
                    child_fd = _create_and_open_directory_at(parent_fd, part)
                    did_create = True
                except FileExistsError:
                    child_fd = os.open(part, _directory_open_flags(), dir_fd=parent_fd)
            child_stat = os.fstat(child_fd)
            if not stat.S_ISDIR(child_stat.st_mode):
                os.close(child_fd)
                raise OSError("skill path ancestor is not a directory")
            descriptors.append(child_fd)
            if did_create:
                created.append((parent_fd, part, child_fd))
        return _AnchoredUserDirectory(home, directory, descriptors, created)
    except BaseException as exc:
        cleanup_failed = False
        for parent_fd, name, directory_fd in reversed(created):
            try:
                _remove_owned_empty_directory_at(parent_fd, name, directory_fd)
            except BaseException:
                cleanup_failed = True
        for descriptor in reversed(descriptors):
            with suppress(OSError):
                os.close(descriptor)
        if cleanup_failed:
            raise OSError(
                "tool-created ancestor cleanup could not be confirmed; "
                "one or more private directory paths may remain"
            ) from exc
        raise


def _stat_binding(value: os.stat_result) -> dict[str, int]:
    return {
        "mode": value.st_mode,
        "device": value.st_dev,
        "inode": value.st_ino,
        "size": value.st_size,
        "mtime_ns": getattr(value, "st_mtime_ns", 0),
        "ctime_ns": getattr(value, "st_ctime_ns", 0),
        "nlink": value.st_nlink,
    }


def _directory_identity_binding(value: os.stat_result) -> dict[str, int]:
    return {
        "mode": value.st_mode,
        "device": value.st_dev,
        "inode": value.st_ino,
    }


def _user_path_binding_sha256(home: Path, directory: Path) -> str:
    """Bind the existing user-path prefix; missing suffixes remain explicit."""
    if not _secure_mutation_supported():
        # Preview remains portable. Apply refuses platforms without atomic anchoring.
        relative = _relative_to_home(home, directory)
        values: list[dict[str, Any]] = []
        cursor = home
        for part in ("<home>", *relative.parts):
            if part != "<home>":
                cursor /= part
            try:
                value = cursor.lstat()
            except FileNotFoundError:
                values.append({"path": part, "state": "missing"})
                break
            if _is_link_like(cursor, value):
                raise OSError("skill path contains a symlink, junction, or reparse point")
            values.append({"path": part, **_directory_identity_binding(value)})
        return _json_sha256(values)

    relative = _relative_to_home(home, directory)
    home_fd = _open_absolute_directory(home)
    descriptors = [home_fd]
    values = [{"path": "<home>", **_directory_identity_binding(os.fstat(home_fd))}]
    try:
        for part in relative.parts:
            try:
                child_fd = os.open(part, _directory_open_flags(), dir_fd=descriptors[-1])
            except FileNotFoundError:
                values.append({"path": part, "state": "missing"})
                break
            descriptors.append(child_fd)
            values.append({"path": part, **_directory_identity_binding(os.fstat(child_fd))})
        return _json_sha256(values)
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _is_link_like(path: Path, path_stat: os.stat_result | Any | None = None) -> bool:
    try:
        value = path_stat if path_stat is not None else path.lstat()
    except OSError:
        return False
    if stat.S_ISLNK(value.st_mode):
        return True
    attributes = getattr(value, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    if attributes and attributes & reparse_flag:
        return True
    is_junction = getattr(path, "is_junction", None)
    if callable(is_junction):
        try:
            return bool(is_junction())
        except OSError:
            return True
    return False


def _normalized_home(home: Path | None) -> Path:
    raw = home if home is not None else Path.home()
    lexical = Path(os.path.abspath(os.fspath(raw)))
    try:
        home_stat = lexical.lstat()
    except OSError as exc:
        raise OSError("skill home is unavailable") from exc
    if _is_link_like(lexical, home_stat):
        raise OSError("skill home must not be a symlink, junction, or reparse point")
    if not stat.S_ISDIR(home_stat.st_mode):
        raise OSError("skill home is not a directory")
    return lexical.resolve(strict=True)


def _display_user_path(home: Path, candidate: Path) -> str:
    try:
        relative = candidate.relative_to(home)
    except ValueError:
        return "<outside-user-home>"
    if not relative.parts:
        return "~"
    return f"~/{relative.as_posix()}"


def _relative_to_home(home: Path, candidate: Path) -> Path:
    lexical = Path(os.path.abspath(os.fspath(candidate)))
    try:
        relative = lexical.relative_to(home)
    except ValueError as exc:
        raise OSError("skill path escapes the supplied home") from exc
    return relative


def _validate_user_path(home: Path, candidate: Path, *, leaf_may_be_file: bool = False) -> None:
    relative = _relative_to_home(home, candidate)
    cursor = home
    for index, part in enumerate(relative.parts):
        cursor = cursor / part
        try:
            cursor_stat = cursor.lstat()
        except FileNotFoundError:
            break
        except OSError as exc:
            raise OSError(
                f"skill path cannot be safely inspected: {_display_user_path(home, cursor)}"
            ) from exc
        if _is_link_like(cursor, cursor_stat):
            raise OSError(
                "skill path contains a symlink, junction, or reparse point: "
                f"{_display_user_path(home, cursor)}"
            )
        is_leaf = index == len(relative.parts) - 1
        if not stat.S_ISDIR(cursor_stat.st_mode) and not (is_leaf and leaf_may_be_file):
            raise OSError(f"skill path ancestor is not a directory: {_display_user_path(home, cursor)}")
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(home)
    except ValueError as exc:
        raise OSError("resolved skill path escapes the supplied home") from exc


def _descriptor_resolved_path(descriptor: int) -> Path | None:
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
    if os.name == "nt":  # pragma: no cover - exercised by hosted Windows
        try:
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


def _read_regular_bytes(path: Path, *, limit: int) -> bytes:
    try:
        before = path.lstat()
    except OSError as exc:
        raise OSError("installer file is unavailable") from exc
    if _is_link_like(path, before) or not stat.S_ISREG(before.st_mode):
        raise OSError("refusing a non-regular installer file")
    if before.st_nlink > 1:
        raise OSError("refusing a hard-linked installer file")
    if before.st_size > limit:
        raise OSError("installer file exceeds its safety limit")
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise OSError("installer file could not be safely opened") from exc
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_size > limit:
            raise OSError("refusing a changed or oversized installer file")
        descriptor_path = _descriptor_resolved_path(descriptor)
        if descriptor_path is None:
            raise OSError("installer file location could not be safely verified")
        expected_path = Path(os.path.abspath(os.fspath(path)))
        actual_path = Path(os.path.abspath(os.fspath(descriptor_path)))
        if os.path.normcase(os.fspath(actual_path)) != os.path.normcase(os.fspath(expected_path)):
            raise OSError("installer file path changed while it was being opened")
        if opened.st_nlink > 1:
            raise OSError("refusing a hard-linked installer file")
        if (
            before.st_dev != opened.st_dev
            or before.st_ino != opened.st_ino
            or before.st_size != opened.st_size
            or getattr(before, "st_mtime_ns", None) != getattr(opened, "st_mtime_ns", None)
            or getattr(before, "st_ctime_ns", None) != getattr(opened, "st_ctime_ns", None)
        ):
            raise OSError("installer file changed while it was being opened")
        chunks: list[bytes] = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        value = b"".join(chunks)
        if len(value) > limit:
            raise OSError("installer file exceeds its safety limit")
        after = os.fstat(descriptor)
        if (
            opened.st_dev != after.st_dev
            or opened.st_ino != after.st_ino
            or opened.st_size != after.st_size
            or getattr(opened, "st_mtime_ns", None) != getattr(after, "st_mtime_ns", None)
            or getattr(opened, "st_ctime_ns", None) != getattr(after, "st_ctime_ns", None)
        ):
            raise OSError("installer file changed while it was being read")
        return value
    finally:
        os.close(descriptor)


def _sha256(path: Path, *, limit: int) -> str:
    return hashlib.sha256(_read_regular_bytes(path, limit=limit)).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _json_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def bundled_skill_root() -> Path:
    executing_module = Path(__file__).resolve()
    source_checkout = executing_module.parents[2]
    source_module = source_checkout / "src" / "agent_docs_doctor" / "installer.py"
    try:
        is_source_checkout = source_module.resolve(strict=True) == executing_module
    except OSError:
        is_source_checkout = False
    if is_source_checkout and (source_checkout / "SKILL.md").is_file():
        return source_checkout

    try:
        distribution = metadata.distribution("agent-docs-doctor")
    except metadata.PackageNotFoundError:
        distribution = None
    if distribution is not None:
        files = tuple(distribution.files or ())
        code_matches = False
        for item in files:
            if not item.as_posix().endswith("agent_docs_doctor/installer.py"):
                continue
            try:
                located = Path(str(distribution.locate_file(item))).resolve(strict=True)
            except OSError:
                continue
            if located == executing_module:
                code_matches = True
                break
        if code_matches:
            for item in files:
                if item.as_posix().endswith("share/agent-docs-doctor/skill/SKILL.md"):
                    candidate = Path(str(distribution.locate_file(item))).parent
                    if (candidate / "SKILL.md").is_file():
                        return candidate
    raise FileNotFoundError("bundled Agent Skill resources are unavailable")


def _resolved_skill_root() -> Path:
    try:
        root = bundled_skill_root()
        root_stat = root.lstat()
    except OSError as exc:
        raise OSError("bundled skill root is unavailable") from exc
    if _is_link_like(root, root_stat) or not stat.S_ISDIR(root_stat.st_mode):
        raise OSError("bundled skill root must be a regular directory")
    return root.resolve(strict=True)


def _bounded_child_names(directory: Path, expected_count: int) -> set[str]:
    names: set[str] = set()
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                if len(names) >= expected_count + 1:
                    raise OSError("bundled skill directory exceeds the static public allowlist")
                names.add(entry.name)
    except OSError:
        raise
    return names


def _bounded_child_names_fd(directory_fd: int, expected_count: int) -> set[str]:
    names: set[str] = set()
    try:
        with os.scandir(directory_fd) as entries:
            for entry in entries:
                if len(names) >= expected_count + 1:
                    raise OSError("bundled skill directory exceeds the static public allowlist")
                names.add(entry.name)
    except OSError:
        raise
    return names


def _read_open_regular_bytes(
    descriptor: int,
    *,
    limit: int,
    reject_hardlinks: bool,
) -> bytes:
    opened = os.fstat(descriptor)
    if not stat.S_ISREG(opened.st_mode) or opened.st_size > limit:
        raise OSError("refusing a changed or oversized installer file")
    if reject_hardlinks and opened.st_nlink > 1:
        raise OSError("refusing a hard-linked installer file")
    chunks: list[bytes] = []
    remaining = limit + 1
    while remaining:
        chunk = os.read(descriptor, min(1024 * 1024, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    value = b"".join(chunks)
    if len(value) > limit:
        raise OSError("installer file exceeds its safety limit")
    after = os.fstat(descriptor)
    if (
        opened.st_dev != after.st_dev
        or opened.st_ino != after.st_ino
        or opened.st_size != after.st_size
        or getattr(opened, "st_mtime_ns", None) != getattr(after, "st_mtime_ns", None)
        or getattr(opened, "st_ctime_ns", None) != getattr(after, "st_ctime_ns", None)
    ):
        raise OSError("installer file changed while it was being read")
    return value


def _read_relative_regular_bytes(
    root_fd: int,
    relative: str,
    *,
    limit: int,
    reject_hardlinks: bool,
) -> bytes:
    parts = PurePosixPath(relative).parts
    if not parts or ".." in parts:
        raise OSError("invalid installer relative path")
    descriptor = os.dup(root_fd)
    try:
        for part in parts[:-1]:
            child = os.open(part, _directory_open_flags(), dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
        flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        file_fd = os.open(parts[-1], flags, dir_fd=descriptor)
        try:
            return _read_open_regular_bytes(
                file_fd,
                limit=limit,
                reject_hardlinks=reject_hardlinks,
            )
        finally:
            os.close(file_fd)
    finally:
        os.close(descriptor)


def _source_payload_snapshot(root: Path | None = None) -> dict[str, bytes]:
    root = root if root is not None else _resolved_skill_root()
    if not _secure_mutation_supported():
        return {
            path.relative_to(root).as_posix(): _read_regular_bytes(
                path,
                limit=MAX_SOURCE_FILE_BYTES,
            )
            for path in _source_files(root)
        }

    root_fd = _open_absolute_directory(root)
    try:
        directory_expectations = {
            "agents": {"openai.yaml"},
            "references": {
                PurePosixPath(relative).name
                for relative in SOURCE_RELATIVE_PATHS
                if relative.startswith("references/")
            },
        }
        for relative, expected_names in directory_expectations.items():
            directory_fd = os.open(relative, _directory_open_flags(), dir_fd=root_fd)
            try:
                if _bounded_child_names_fd(directory_fd, len(expected_names)) != expected_names:
                    raise OSError("bundled skill directory does not match the static public allowlist")
            finally:
                os.close(directory_fd)

        payloads: dict[str, bytes] = {}
        total = 0
        for relative in SOURCE_RELATIVE_PATHS:
            payload = _read_relative_regular_bytes(
                root_fd,
                relative,
                limit=MAX_SOURCE_FILE_BYTES,
                reject_hardlinks=True,
            )
            total += len(payload)
            if total > MAX_SOURCE_TOTAL_BYTES:
                raise OSError("bundled skill exceeds the aggregate installer safety limit")
            payloads[relative] = payload

        # The held descriptors make replacement unable to redirect reads. Recheck the
        # inventories so concurrent additions also fail the snapshot.
        for relative, expected_names in directory_expectations.items():
            directory_fd = os.open(relative, _directory_open_flags(), dir_fd=root_fd)
            try:
                if _bounded_child_names_fd(directory_fd, len(expected_names)) != expected_names:
                    raise OSError("bundled skill directory changed during inventory")
            finally:
                os.close(directory_fd)
        return payloads
    finally:
        os.close(root_fd)


def _source_files(root: Path | None = None) -> tuple[Path, ...]:
    root = root if root is not None else _resolved_skill_root()
    files: list[Path] = []
    for relative in SOURCE_RELATIVE_PATHS:
        path = root / PurePosixPath(relative)
        try:
            path_stat = path.lstat()
        except OSError as exc:
            raise OSError("a required bundled skill file is unavailable") from exc
        if _is_link_like(path, path_stat) or not stat.S_ISREG(path_stat.st_mode):
            raise OSError("a required bundled skill file is not a regular file")
        if path_stat.st_nlink > 1:
            raise OSError("a required bundled skill file is hard-linked")
        files.append(path)

    agents = root / "agents"
    try:
        agent_stat = agents.lstat()
    except OSError as exc:
        raise OSError("bundled skill agent metadata is unavailable") from exc
    if _is_link_like(agents, agent_stat) or not stat.S_ISDIR(agent_stat.st_mode):
        raise OSError("bundled skill agent metadata must be a regular directory")
    try:
        agent_names = _bounded_child_names(agents, 1)
    except OSError as exc:
        raise OSError("bundled skill agent metadata changed during inventory") from exc
    if agent_names != {"openai.yaml"}:
        raise OSError("bundled skill agent metadata does not match the static public allowlist")

    references = root / "references"
    try:
        reference_stat = references.lstat()
    except OSError as exc:
        raise OSError("bundled skill references are unavailable") from exc
    if _is_link_like(references, reference_stat) or not stat.S_ISDIR(reference_stat.st_mode):
        raise OSError("bundled skill references must be a regular directory")
    expected_reference_names = {
        PurePosixPath(relative).name
        for relative in SOURCE_RELATIVE_PATHS
        if relative.startswith("references/")
    }
    try:
        actual_reference_names = _bounded_child_names(
            references,
            len(expected_reference_names),
        )
    except OSError as exc:
        raise OSError("bundled skill references changed during inventory") from exc
    if actual_reference_names != expected_reference_names:
        raise OSError("bundled skill references do not match the static public allowlist")
    return tuple(files)


def _manifest_from_payloads(client: str, payloads: dict[str, bytes]) -> dict[str, Any]:
    digests = {relative: hashlib.sha256(payload).hexdigest() for relative, payload in payloads.items()}
    return {
        "format": "agent-docs-doctor.skill-install.v1",
        "owner": "agent-docs-doctor",
        "version": __version__,
        "client": client,
        "files": digests,
    }


def _desired_manifest(client: str) -> dict[str, Any]:
    root = _resolved_skill_root()
    return _manifest_from_payloads(client, _source_payload_snapshot(root))


def _unique_manifest_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate manifest key")
        value[key] = item
    return value


def _reject_manifest_constant(_value: str) -> Any:
    raise ValueError("unsupported manifest numeric constant")


def _parse_manifest_bytes(raw: bytes, expected_client: str | None = None) -> dict[str, Any] | None:
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_manifest_object,
            parse_constant=_reject_manifest_constant,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        RecursionError,
        MemoryError,
        ValueError,
    ):
        return None
    if (
        not isinstance(value, dict)
        or set(value) != {"format", "owner", "version", "client", "files"}
        or value.get("format") != "agent-docs-doctor.skill-install.v1"
        or value.get("owner") != "agent-docs-doctor"
        or not isinstance(value.get("version"), str)
        or SAFE_VERSION.fullmatch(value["version"]) is None
        or value.get("client") not in tuple(CLIENT_PATHS)
        or (expected_client is not None and value["client"] != expected_client)
    ):
        return None
    files = value.get("files")
    if (
        not isinstance(files, dict)
        or set(files) != set(SOURCE_RELATIVE_PATHS)
        or len(files) > MAX_TARGET_ENTRIES
    ):
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


def _read_manifest(target: Path, expected_client: str | None = None) -> dict[str, Any] | None:
    try:
        raw = _read_regular_bytes(target / MANIFEST_NAME, limit=MAX_MANIFEST_BYTES)
    except OSError:
        return None
    return _parse_manifest_bytes(raw, expected_client)


def _manifest_sha256(target: Path) -> str | None:
    try:
        return _sha256(target / MANIFEST_NAME, limit=MAX_MANIFEST_BYTES)
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
            if _sha256(path, limit=MAX_TARGET_FILE_BYTES) != digest:
                return False
        except OSError:
            return False
    return True


def _target_state_sha256(
    target: Path,
    managed_manifest: dict[str, Any] | None = None,
    *,
    home: Path | None = None,
    ignore_root_times: bool = False,
) -> str:
    managed_paths = frozenset((*SOURCE_RELATIVE_PATHS, MANIFEST_NAME))
    if _secure_mutation_supported():
        try:
            anchor = (
                _anchor_user_directory(home, target.parent, create=False)
                if home is not None
                else _AnchoredUserDirectory(
                    target.parent,
                    target.parent,
                    [_open_absolute_directory(target.parent.resolve(strict=True))],
                    [],
                )
            )
        except FileNotFoundError:
            return hashlib.sha256(b"absent").hexdigest()
        if anchor is None:
            return hashlib.sha256(b"absent").hexdigest()
        with anchor:
            return _target_state_sha256_at(
                anchor.fd,
                target.name,
                managed_manifest,
                ignore_root_times=ignore_root_times,
            )

    # Preview-only fallback for platforms where apply fails closed.
    try:
        root_stat = target.lstat()
    except FileNotFoundError:
        return hashlib.sha256(b"absent").hexdigest()
    except OSError as exc:
        raise OSError("installation target state cannot be inspected") from exc
    if _is_link_like(target, root_stat):
        raise OSError("installation target is a symlink, junction, or reparse point")
    entries: list[dict[str, Any]] = []
    total_bytes = 0

    def state_path(relative: str) -> str:
        if len(relative) <= MAX_STATE_PATH_CHARS:
            return relative
        digest = hashlib.sha256(relative.encode("utf-8", errors="surrogatepass")).hexdigest()
        return f"<long-path:{digest}>"

    def visit(path: Path, relative: str, depth: int) -> None:
        nonlocal total_bytes
        if depth > MAX_TARGET_DEPTH:
            raise OSError("installation target exceeds the directory depth safety limit")
        if len(entries) >= MAX_TARGET_ENTRIES:
            raise OSError("installation target has too many entries to bind safely")
        try:
            path_stat = path.lstat()
        except OSError as exc:
            raise OSError("installation target changed during preview") from exc
        common = {
            "path": state_path(relative),
            "mode": stat.S_IMODE(path_stat.st_mode),
            "device": path_stat.st_dev,
            "inode": path_stat.st_ino,
            "size": path_stat.st_size,
            "mtime_ns": getattr(path_stat, "st_mtime_ns", 0),
            "ctime_ns": getattr(path_stat, "st_ctime_ns", 0),
            "nlink": path_stat.st_nlink,
        }
        if ignore_root_times and depth == 0:
            common.pop("mtime_ns", None)
            common.pop("ctime_ns", None)
        if _is_link_like(path, path_stat):
            try:
                link_digest = hashlib.sha256(os.fsencode(os.readlink(path))).hexdigest()
            except OSError as exc:
                raise OSError("installation target link changed during preview") from exc
            entries.append({**common, "type": "link", "link_sha256": link_digest})
            return
        if stat.S_ISREG(path_stat.st_mode):
            entry = {**common, "type": "file"}
            if relative in managed_paths:
                payload = _read_regular_bytes(path, limit=MAX_TARGET_FILE_BYTES)
                total_bytes += len(payload)
                if total_bytes > MAX_TARGET_TOTAL_BYTES:
                    raise OSError("installation target exceeds the aggregate safety limit")
                entry["sha256"] = hashlib.sha256(payload).hexdigest()
            else:
                entry["content"] = "unread-user-extra"
            entries.append(entry)
            return
        if stat.S_ISDIR(path_stat.st_mode):
            entries.append({**common, "type": "directory"})
            remaining_entries = MAX_TARGET_ENTRIES - len(entries)
            children: list[tuple[str, Path]] = []
            limit_exceeded = False
            try:
                with os.scandir(path) as iterator:
                    for child in iterator:
                        if len(children) >= remaining_entries:
                            limit_exceeded = True
                            break
                        children.append((child.name, Path(child.path)))
            except OSError as exc:
                raise OSError("installation target directory changed during preview") from exc
            if limit_exceeded:
                raise OSError("installation target has too many entries to bind safely")
            for child_name, child_path in sorted(children, key=lambda item: item[0]):
                child_relative = f"{relative}/{child_name}" if relative else child_name
                visit(child_path, child_relative, depth + 1)
            return
        entries.append({**common, "type": "non-regular"})

    visit(target, "", 0)
    return _json_sha256(entries)


def _target_state_sha256_at(
    parent_fd: int,
    target_name: str,
    managed_manifest: dict[str, Any] | None = None,
    *,
    ignore_root_times: bool = False,
) -> str:
    del managed_manifest
    managed_paths = frozenset((*SOURCE_RELATIVE_PATHS, MANIFEST_NAME))
    entries: list[dict[str, Any]] = []
    total_bytes = 0

    def state_path(relative: str) -> str:
        if len(relative) <= MAX_STATE_PATH_CHARS:
            return relative
        digest = hashlib.sha256(relative.encode("utf-8", errors="surrogatepass")).hexdigest()
        return f"<long-path:{digest}>"

    def visit(directory_fd: int, name: str, relative: str, depth: int) -> None:
        nonlocal total_bytes
        if depth > MAX_TARGET_DEPTH:
            raise OSError("installation target exceeds the directory depth safety limit")
        if len(entries) >= MAX_TARGET_ENTRIES:
            raise OSError("installation target has too many entries to bind safely")
        try:
            path_stat = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            if depth == 0:
                raise
            raise OSError("installation target changed during preview") from None
        except OSError as exc:
            raise OSError("installation target changed during preview") from exc
        common = {
            "path": state_path(relative),
            "mode": stat.S_IMODE(path_stat.st_mode),
            "device": path_stat.st_dev,
            "inode": path_stat.st_ino,
            "size": path_stat.st_size,
            "mtime_ns": getattr(path_stat, "st_mtime_ns", 0),
            "ctime_ns": getattr(path_stat, "st_ctime_ns", 0),
            "nlink": path_stat.st_nlink,
        }
        if ignore_root_times and depth == 0:
            common.pop("mtime_ns", None)
            common.pop("ctime_ns", None)
        if stat.S_ISLNK(path_stat.st_mode):
            try:
                link_digest = hashlib.sha256(os.fsencode(os.readlink(name, dir_fd=directory_fd))).hexdigest()
            except OSError as exc:
                raise OSError("installation target link changed during preview") from exc
            entries.append({**common, "type": "link", "link_sha256": link_digest})
            return
        if stat.S_ISREG(path_stat.st_mode):
            if relative not in managed_paths:
                entries.append(
                    {
                        **common,
                        "type": "file",
                        "content": "unread-user-extra",
                    }
                )
                return
            flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
            flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
            try:
                file_fd = os.open(name, flags, dir_fd=directory_fd)
            except OSError as exc:
                raise OSError("installation target file changed during preview") from exc
            try:
                opened = os.fstat(file_fd)
                if (
                    opened.st_dev != path_stat.st_dev
                    or opened.st_ino != path_stat.st_ino
                    or not stat.S_ISREG(opened.st_mode)
                    or opened.st_size != path_stat.st_size
                    or getattr(opened, "st_mtime_ns", 0) != getattr(path_stat, "st_mtime_ns", 0)
                    or getattr(opened, "st_ctime_ns", 0) != getattr(path_stat, "st_ctime_ns", 0)
                ):
                    raise OSError("installation target file changed during preview")
                payload = _read_open_regular_bytes(
                    file_fd,
                    limit=MAX_TARGET_FILE_BYTES,
                    reject_hardlinks=True,
                )
            finally:
                os.close(file_fd)
            total_bytes += len(payload)
            if total_bytes > MAX_TARGET_TOTAL_BYTES:
                raise OSError("installation target exceeds the aggregate safety limit")
            entries.append(
                {
                    **common,
                    "type": "file",
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            )
            return
        if stat.S_ISDIR(path_stat.st_mode):
            try:
                child_fd = os.open(name, _directory_open_flags(), dir_fd=directory_fd)
            except OSError as exc:
                raise OSError("installation target directory changed during preview") from exc
            try:
                opened = os.fstat(child_fd)
                if opened.st_dev != path_stat.st_dev or opened.st_ino != path_stat.st_ino:
                    raise OSError("installation target directory changed during preview")
                entries.append({**common, "type": "directory"})
                children: list[str] = []
                with os.scandir(child_fd) as iterator:
                    for child in iterator:
                        if len(entries) + len(children) >= MAX_TARGET_ENTRIES:
                            raise OSError("installation target has too many entries to bind safely")
                        children.append(child.name)
                for child_name in sorted(children):
                    child_relative = f"{relative}/{child_name}" if relative else child_name
                    visit(child_fd, child_name, child_relative, depth + 1)
                after = os.fstat(child_fd)
                if (
                    opened.st_dev != after.st_dev
                    or opened.st_ino != after.st_ino
                    or getattr(opened, "st_mtime_ns", 0) != getattr(after, "st_mtime_ns", 0)
                    or getattr(opened, "st_ctime_ns", 0) != getattr(after, "st_ctime_ns", 0)
                ):
                    raise OSError("installation target directory changed during preview")
            except OSError:
                raise
            finally:
                os.close(child_fd)
            return
        entries.append({**common, "type": "non-regular"})

    try:
        visit(parent_fd, target_name, "", 0)
    except FileNotFoundError:
        return hashlib.sha256(b"absent").hexdigest()
    return _json_sha256(entries)


def _backup_plan(
    home: Path,
    client: str,
    target_state_sha256: str,
    version: str,
) -> tuple[Path, Path]:
    safe_version = re.sub(r"[^A-Za-z0-9._+-]", "-", version)[:128].strip(".") or "unknown"
    parent = home / ".agent-docs-doctor" / "backups" / client
    _validate_user_path(home, parent)
    base = parent / f"{SKILL_NAME}-{safe_version}-{target_state_sha256[:16]}"
    for index in range(MAX_BACKUP_COLLISIONS):
        reservation = base if index == 0 else parent / f"{base.name}-{index + 1}"
        if not _path_entry_exists(reservation):
            _validate_user_path(home, reservation)
            return reservation / BACKUP_PAYLOAD_NAME, reservation
    raise OSError("too many backup collisions; existing backups must be reviewed first")


def target_for(client: str, home: Path | None = None) -> Path:
    if client not in CLIENT_PATHS:
        raise ValueError(f"unsupported client: {client}")
    actual_home = _normalized_home(home)
    target = actual_home / CLIENT_PATHS[client]
    _validate_user_path(actual_home, target.parent)
    return target


def _token_payload(plan: InstallPlan) -> dict[str, Any]:
    return {
        "format": PREVIEW_FORMAT,
        "action": plan.action,
        "client": plan.client,
        "home": str(plan.home) if plan.home else None,
        "target": str(plan.target),
        "state": plan.state,
        "files": list(plan.files),
        "backup": str(plan.backup) if plan.backup else None,
        "backup_reservation": (str(plan.backup_reservation) if plan.backup_reservation else None),
        "desired_manifest_sha256": plan.desired_manifest_sha256,
        "expected_manifest_sha256": plan.expected_manifest_sha256,
        "expected_target_sha256": plan.expected_target_sha256,
        "expected_target_move_sha256": plan.expected_target_move_sha256,
        "expected_path_sha256": plan.expected_path_sha256,
    }


def _bind_ready_plan(plan: InstallPlan) -> InstallPlan:
    if plan.state != "ready":
        return plan
    if plan.home is None:
        raise OSError("preview does not contain its supplied home")
    plan = replace(
        plan,
        expected_path_sha256=_user_path_binding_sha256(plan.home, plan.target.parent),
        expected_target_move_sha256=_target_state_sha256(
            plan.target,
            home=plan.home,
            ignore_root_times=True,
        ),
    )
    return replace(plan, plan_token=_json_sha256(_token_payload(plan)))


def plan_install(
    client: str,
    *,
    home: Path | None = None,
    update: bool = False,
) -> InstallPlan:
    actual_home = _normalized_home(home)
    target = target_for(client, actual_home)
    desired = _desired_manifest(client)
    desired_json = _canonical_json(desired)
    desired_sha256 = hashlib.sha256(desired_json.encode("utf-8")).hexdigest()
    files = tuple(desired["files"])
    if not _path_entry_exists(target):
        return _bind_ready_plan(
            InstallPlan(
                action="install",
                client=client,
                target=target,
                state="ready",
                files=files,
                home=actual_home,
                desired_manifest_json=desired_json,
                desired_manifest_sha256=desired_sha256,
                expected_target_sha256=_target_state_sha256(
                    target,
                    home=actual_home,
                ),
            )
        )
    try:
        target_stat = target.lstat()
    except OSError as exc:
        raise OSError("installation target cannot be safely inspected") from exc
    if _is_link_like(target, target_stat):
        return InstallPlan(
            action="install",
            client=client,
            target=target,
            state="blocked-unmanaged",
            files=files,
            message=("The target is a symlink, junction, or reparse point and will not be followed."),
            home=actual_home,
            desired_manifest_json=desired_json,
            desired_manifest_sha256=desired_sha256,
        )
    current = _read_manifest(target, client)
    if current is None:
        return InstallPlan(
            action="install",
            client=client,
            target=target,
            state="blocked-unmanaged",
            files=files,
            message="The target exists but is not owned by Agent Docs Doctor.",
            home=actual_home,
            desired_manifest_json=desired_json,
            desired_manifest_sha256=desired_sha256,
        )
    target_state = _target_state_sha256(target, current, home=actual_home)
    manifest_sha = _manifest_sha256(target)
    if current == desired and _installed_files_match(target, current):
        return InstallPlan(
            action="install",
            client=client,
            target=target,
            state="already-installed",
            files=files,
            expected_manifest_sha256=manifest_sha,
            home=actual_home,
            desired_manifest_json=desired_json,
            desired_manifest_sha256=desired_sha256,
            expected_target_sha256=target_state,
        )
    if not update:
        return InstallPlan(
            action="install",
            client=client,
            target=target,
            state="update-required",
            files=files,
            message="A different managed version exists. Preview again with --update.",
            expected_manifest_sha256=manifest_sha,
            home=actual_home,
            desired_manifest_json=desired_json,
            desired_manifest_sha256=desired_sha256,
            expected_target_sha256=target_state,
        )
    raw_version = str(current.get("version", "unknown"))
    backup, reservation = _backup_plan(actual_home, client, target_state, raw_version)
    return _bind_ready_plan(
        InstallPlan(
            action="update",
            client=client,
            target=target,
            state="ready",
            files=files,
            backup=backup,
            expected_manifest_sha256=manifest_sha,
            home=actual_home,
            desired_manifest_json=desired_json,
            desired_manifest_sha256=desired_sha256,
            expected_target_sha256=target_state,
            backup_reservation=reservation,
        )
    )


def _write_all(descriptor: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("installer staging write made no progress")
        view = view[written:]


def _write_relative_file(root_fd: int, relative: str, payload: bytes) -> None:
    parts = PurePosixPath(relative).parts
    if not parts or ".." in parts:
        raise OSError("invalid staged installer path")
    descriptor = os.dup(root_fd)
    try:
        for part in parts[:-1]:
            try:
                child = os.open(part, _directory_open_flags(), dir_fd=descriptor)
            except FileNotFoundError:
                os.mkdir(part, mode=0o700, dir_fd=descriptor)
                child = os.open(part, _directory_open_flags(), dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        file_fd = os.open(parts[-1], flags, 0o600, dir_fd=descriptor)
        try:
            _write_all(file_fd, payload)
            os.fsync(file_fd)
        finally:
            os.close(file_fd)
    finally:
        os.close(descriptor)


def _write_staged_skill_fd(stage_fd: int, plan: InstallPlan) -> None:
    if plan.desired_manifest_json is None or plan.desired_manifest_sha256 is None:
        raise OSError("preview does not contain a desired payload")
    if hashlib.sha256(plan.desired_manifest_json.encode("utf-8")).hexdigest() != plan.desired_manifest_sha256:
        raise OSError("preview desired payload binding is invalid")
    try:
        manifest = json.loads(plan.desired_manifest_json)
    except (json.JSONDecodeError, RecursionError) as exc:
        raise OSError("preview desired manifest is invalid") from exc
    if _parse_manifest_bytes(plan.desired_manifest_json.encode("utf-8"), plan.client) != manifest:
        raise OSError("preview desired manifest failed validation")

    source_payloads = _source_payload_snapshot()
    current = _manifest_from_payloads(plan.client, source_payloads)
    if _canonical_json(current) != plan.desired_manifest_json:
        raise OSError("bundled skill source changed after preview; preview again")
    if set(source_payloads) != set(manifest["files"]):
        raise OSError("bundled skill source set changed after preview; preview again")

    for relative, digest in manifest["files"].items():
        payload = source_payloads[relative]
        if hashlib.sha256(payload).hexdigest() != digest:
            raise OSError(f"bundled skill source changed after preview: {relative}")
        try:
            _write_relative_file(stage_fd, relative, payload)
        except OSError as exc:
            raise OSError(f"could not stage allowlisted skill file: {relative}") from exc
    manifest_payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    try:
        _write_relative_file(stage_fd, MANIFEST_NAME, manifest_payload)
    except OSError as exc:
        raise OSError("could not stage the managed install manifest") from exc
    for relative, digest in manifest["files"].items():
        if (
            hashlib.sha256(
                _read_relative_regular_bytes(
                    stage_fd,
                    relative,
                    limit=MAX_SOURCE_FILE_BYTES,
                    reject_hardlinks=True,
                )
            ).hexdigest()
            != digest
        ):
            raise OSError(f"staged skill verification failed for {relative}")
    final_payloads = _source_payload_snapshot()
    if _canonical_json(_manifest_from_payloads(plan.client, final_payloads)) != plan.desired_manifest_json:
        raise OSError("bundled skill source changed while staging; preview again")


def _rename_noreplace_at(
    source_parent_fd: int,
    source_name: str,
    destination_parent_fd: int,
    destination_name: str,
) -> None:
    if not _secure_mutation_supported():
        raise OSError("secure ancestor-relative activation is unavailable on this platform")
    if any("/" in name or name in {"", ".", ".."} for name in (source_name, destination_name)):
        raise OSError("exclusive installer move received an unsafe entry name")
    try:
        libc = ctypes.CDLL(None, use_errno=True)
    except OSError as exc:
        raise OSError("exclusive installer move support is unavailable") from exc
    source_bytes = os.fsencode(source_name)
    destination_bytes = os.fsencode(destination_name)
    if sys.platform == "darwin":
        rename_exclusive = 0x00000004
        renameatx = getattr(libc, "renameatx_np", None)
        if renameatx is None:
            raise OSError(errno.ENOTSUP, "exclusive rename is unavailable on this platform")
        renameatx.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameatx.restype = ctypes.c_int
        result = renameatx(
            source_parent_fd,
            source_bytes,
            destination_parent_fd,
            destination_bytes,
            rename_exclusive,
        )
    else:
        renameat2 = getattr(libc, "renameat2", None)
        if renameat2 is None:
            raise OSError(errno.ENOTSUP, "exclusive rename is unavailable on this platform")
        rename_noreplace = 1
        renameat2.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameat2.restype = ctypes.c_int
        result = renameat2(
            source_parent_fd,
            source_bytes,
            destination_parent_fd,
            destination_bytes,
            rename_noreplace,
        )
    if result != 0:
        error = ctypes.get_errno()
        raise OSError(error, f"exclusive installer move failed: {os.strerror(error)}")


def _create_private_directory_at(parent_fd: int, prefix: str) -> tuple[str, int, tuple[int, int]]:
    for _attempt in range(128):
        name = f"{prefix}{secrets.token_hex(16)}"
        try:
            descriptor = _create_and_open_directory_at(parent_fd, name)
        except FileExistsError:
            continue
        value = os.fstat(descriptor)
        return name, descriptor, (value.st_dev, value.st_ino)
    raise OSError("private skill staging directory name collisions exceeded the safety limit")


def _remove_private_tree_contents(directory_fd: int) -> None:
    names: list[str] = []
    with os.scandir(directory_fd) as entries:
        for entry in entries:
            if len(names) >= MAX_TARGET_ENTRIES:
                raise OSError("private staging directory exceeds the cleanup safety limit")
            names.append(entry.name)
    for name in names:
        value = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if stat.S_ISDIR(value.st_mode):
            child_fd = os.open(name, _directory_open_flags(), dir_fd=directory_fd)
            try:
                opened = os.fstat(child_fd)
                if opened.st_dev != value.st_dev or opened.st_ino != value.st_ino:
                    raise OSError("private staging directory changed during cleanup")
                _remove_private_tree_contents(child_fd)
            finally:
                os.close(child_fd)
            os.rmdir(name, dir_fd=directory_fd)
        else:
            os.unlink(name, dir_fd=directory_fd)


def _cleanup_private_directory_at(
    parent_fd: int,
    name: str,
    directory_fd: int,
    identity: tuple[int, int],
) -> None:
    try:
        visible = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if (
        not stat.S_ISDIR(visible.st_mode)
        or (visible.st_dev, visible.st_ino) != identity
        or (os.fstat(directory_fd).st_dev, os.fstat(directory_fd).st_ino) != identity
    ):
        raise OSError("private staging path changed; refusing unsafe cleanup")
    _remove_private_tree_contents(directory_fd)
    os.rmdir(name, dir_fd=parent_fd)


def _assert_entry_identity(
    parent_fd: int,
    name: str,
    descriptor: int,
    *,
    message: str,
) -> None:
    try:
        visible = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise OSError(message) from exc
    opened = os.fstat(descriptor)
    if (
        visible.st_dev != opened.st_dev
        or visible.st_ino != opened.st_ino
        or stat.S_IFMT(visible.st_mode) != stat.S_IFMT(opened.st_mode)
    ):
        raise OSError(message)


def _read_target_manifest_at(
    parent_fd: int,
    target_name: str,
    expected_client: str,
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        target_fd = os.open(target_name, _directory_open_flags(), dir_fd=parent_fd)
    except OSError:
        return None, None
    try:
        try:
            raw = _read_relative_regular_bytes(
                target_fd,
                MANIFEST_NAME,
                limit=MAX_MANIFEST_BYTES,
                reject_hardlinks=True,
            )
        except OSError:
            return None, None
        return (
            _parse_manifest_bytes(raw, expected_client),
            hashlib.sha256(raw).hexdigest(),
        )
    finally:
        os.close(target_fd)


def _installed_files_match_at(
    parent_fd: int,
    target_name: str,
    manifest: dict[str, Any],
) -> bool:
    try:
        target_fd = os.open(target_name, _directory_open_flags(), dir_fd=parent_fd)
    except OSError:
        return False
    try:
        for relative, digest in manifest["files"].items():
            try:
                payload = _read_relative_regular_bytes(
                    target_fd,
                    relative,
                    limit=MAX_TARGET_FILE_BYTES,
                    reject_hardlinks=True,
                )
            except OSError:
                return False
            if hashlib.sha256(payload).hexdigest() != digest:
                return False
        return True
    finally:
        os.close(target_fd)


def _fresh_plan(plan: InstallPlan) -> InstallPlan:
    if plan.home is None:
        raise OSError("preview does not contain its supplied home")
    if plan.action in {"install", "update"}:
        return plan_install(plan.client, home=plan.home, update=plan.action == "update")
    if plan.action == "uninstall":
        return plan_uninstall(plan.client, home=plan.home)
    raise OSError("unsupported installer action")


def _verified_fresh_plan(plan: InstallPlan, plan_token: str) -> InstallPlan:
    if not plan_token or plan.plan_token is None:
        raise OSError("a current-plan fingerprint is required; run preview again")
    recomputed = _json_sha256(_token_payload(plan))
    if not secrets.compare_digest(recomputed, plan.plan_token):
        raise OSError("preview plan binding is invalid; preview again")
    if not secrets.compare_digest(plan.plan_token, plan_token):
        raise OSError("current-plan fingerprint does not match this operation; preview again")
    fresh = _fresh_plan(plan)
    if (
        fresh.state != "ready"
        or fresh.plan_token is None
        or not secrets.compare_digest(fresh.plan_token, plan_token)
    ):
        raise OSError("installation state or source changed after preview; preview again")
    return fresh


def _assert_target_state_at(plan: InstallPlan, target_parent_fd: int) -> None:
    if plan.expected_target_sha256 is None:
        raise OSError("preview does not contain a target-state binding")
    if _target_state_sha256_at(target_parent_fd, plan.target.name) != plan.expected_target_sha256:
        raise OSError("installation target changed after preview; preview again")


def apply_install(plan: InstallPlan, plan_token: str) -> InstallPlan:
    if plan.action not in {"install", "update"} or plan.state != "ready":
        return plan
    if not _secure_mutation_supported():
        raise OSError(
            "apply is unavailable because this platform cannot guarantee ancestor-relative atomic activation"
        )
    fresh = _verified_fresh_plan(plan, plan_token)
    if fresh.home is None:
        raise OSError("preview does not contain its supplied home")
    target_anchor: _AnchoredUserDirectory | None = None
    stage_name: str | None = None
    stage_fd: int | None = None
    stage_identity: tuple[int, int] | None = None
    stage_move_state: str | None = None
    backup_anchor: _AnchoredUserDirectory | None = None
    reservation_fd: int | None = None
    reservation_created = False
    try:
        target_anchor = _anchor_user_directory(fresh.home, fresh.target.parent, create=True)
        if target_anchor is None:
            raise OSError("skill target parent could not be anchored")
        try:
            stage_name, stage_fd, stage_identity = _create_private_directory_at(
                target_anchor.fd,
                f".{SKILL_NAME}-install-",
            )
        except OSError as exc:
            raise OSError("private skill staging directory could not be created") from exc
        _write_staged_skill_fd(stage_fd, fresh)
        stage_move_state = _target_state_sha256_at(
            target_anchor.fd,
            stage_name,
            ignore_root_times=True,
        )
        target_anchor.assert_visible()
        _assert_target_state_at(fresh, target_anchor.fd)
        if fresh.action == "update":
            if fresh.backup is None or fresh.backup_reservation is None:
                raise OSError("operation has no safe backup reservation")
            backup_anchor = _anchor_user_directory(
                fresh.home,
                fresh.backup_reservation.parent,
                create=True,
            )
            if backup_anchor is None:
                raise OSError("backup parent could not be anchored")
            try:
                reservation_fd = _create_and_open_directory_at(
                    backup_anchor.fd,
                    fresh.backup_reservation.name,
                )
                reservation_created = True
            except FileExistsError as exc:
                raise OSError("backup reservation changed after preview; preview again") from exc
            _assert_target_state_at(fresh, target_anchor.fd)
            target_anchor.assert_visible()
            backup_anchor.assert_visible()
            _assert_entry_identity(
                backup_anchor.fd,
                fresh.backup_reservation.name,
                reservation_fd,
                message="backup reservation changed after preview; preview again",
            )
            pre_move_state = _target_state_sha256_at(
                target_anchor.fd,
                fresh.target.name,
                ignore_root_times=True,
            )
            if pre_move_state != fresh.expected_target_move_sha256:
                raise OSError("installation target changed after preview; preview again")
            _rename_noreplace_at(
                target_anchor.fd,
                fresh.target.name,
                reservation_fd,
                BACKUP_PAYLOAD_NAME,
            )
            if (
                _target_state_sha256_at(
                    reservation_fd,
                    BACKUP_PAYLOAD_NAME,
                    ignore_root_times=True,
                )
                != fresh.expected_target_move_sha256
            ):
                raise OSError("backup payload verification failed before activation")
        target_anchor.assert_visible()
        _assert_entry_identity(
            target_anchor.fd,
            stage_name,
            stage_fd,
            message="private staging directory changed before activation",
        )
        _rename_noreplace_at(
            # The final visibility check closes pathname-swap windows before the
            # descriptor-relative atomic move.
            target_anchor.fd,
            stage_name,
            target_anchor.fd,
            fresh.target.name,
        )
    except BaseException:
        if target_anchor is None:
            raise
        absent_state = hashlib.sha256(b"absent").hexdigest()
        recovery_error: BaseException | None = None
        target_state: str | None = None
        backup_state: str | None = None
        try:
            target_state = _target_state_sha256_at(
                target_anchor.fd,
                fresh.target.name,
                ignore_root_times=True,
            )
        except Exception as inspect_exc:
            recovery_error = inspect_exc
        if reservation_fd is not None:
            try:
                backup_state = _target_state_sha256_at(
                    reservation_fd,
                    BACKUP_PAYLOAD_NAME,
                    ignore_root_times=True,
                )
            except Exception as inspect_exc:
                recovery_error = recovery_error or inspect_exc

        # The Python exception may have arrived immediately after either atomic
        # rename and before its adjacent state flag. Determine commit/rollback
        # state from the descriptor-anchored filesystem, never from that flag.
        activation_committed = stage_move_state is not None and target_state == stage_move_state
        prior_in_target = (
            fresh.action == "update"
            and fresh.expected_target_move_sha256 is not None
            and target_state == fresh.expected_target_move_sha256
        )
        prior_in_backup = (
            fresh.action == "update"
            and fresh.expected_target_move_sha256 is not None
            and backup_state == fresh.expected_target_move_sha256
        )

        if fresh.action == "update" and not activation_committed and target_state == absent_state:
            if prior_in_backup and reservation_fd is not None:
                restore_error: BaseException | None = None
                try:
                    _rename_noreplace_at(
                        reservation_fd,
                        BACKUP_PAYLOAD_NAME,
                        target_anchor.fd,
                        fresh.target.name,
                    )
                except BaseException as restore_exc:
                    restore_error = restore_exc
                try:
                    target_state = _target_state_sha256_at(
                        target_anchor.fd,
                        fresh.target.name,
                        ignore_root_times=True,
                    )
                    backup_state = _target_state_sha256_at(
                        reservation_fd,
                        BACKUP_PAYLOAD_NAME,
                        ignore_root_times=True,
                    )
                except Exception as inspect_exc:
                    recovery_error = recovery_error or restore_error or inspect_exc
                prior_in_target = target_state == fresh.expected_target_move_sha256
                prior_in_backup = backup_state == fresh.expected_target_move_sha256
                if not prior_in_target or prior_in_backup:
                    recovery_error = (
                        recovery_error
                        or restore_error
                        or OSError("prior installation could not be restored from its previewed backup")
                    )
            else:
                recovery_error = recovery_error or OSError(
                    "prior installation could not be located at the target or previewed backup"
                )
        elif fresh.action == "update" and not activation_committed and not prior_in_target:
            recovery_error = recovery_error or OSError(
                "installation target state could not be restored safely"
            )
        elif fresh.action == "install" and not activation_committed and target_state != absent_state:
            recovery_error = recovery_error or OSError(
                "new installation target state could not be classified safely"
            )

        if (
            not activation_committed
            and stage_name is not None
            and stage_fd is not None
            and stage_identity is not None
        ):
            try:
                _cleanup_private_directory_at(
                    target_anchor.fd,
                    stage_name,
                    stage_fd,
                    stage_identity,
                )
            except OSError as cleanup_exc:
                recovery_error = recovery_error or cleanup_exc
            except BaseException as cleanup_exc:
                recovery_error = recovery_error or cleanup_exc

        # Remove only an identity-verified empty reservation. A committed
        # update or failed rollback retains the prior tree at the previewed
        # backup and therefore deliberately keeps the reservation.
        if (
            reservation_created
            and backup_anchor is not None
            and fresh.backup_reservation is not None
            and reservation_fd is not None
            and not prior_in_backup
        ):
            try:
                _remove_owned_empty_directory_at(
                    backup_anchor.fd,
                    fresh.backup_reservation.name,
                    reservation_fd,
                )
            except OSError as cleanup_exc:
                recovery_error = recovery_error or cleanup_exc
            except BaseException as cleanup_exc:
                recovery_error = recovery_error or cleanup_exc
        if backup_anchor is not None and not prior_in_backup and not backup_anchor.cleanup_created():
            recovery_error = recovery_error or OSError(
                "tool-created backup ancestors could not be cleaned safely"
            )
        if not activation_committed and not target_anchor.cleanup_created():
            recovery_error = recovery_error or OSError(
                "tool-created target ancestors could not be cleaned safely"
            )
        target_anchor.close()
        if recovery_error is not None and not activation_committed:
            state_is_safe = (
                target_state == absent_state
                if fresh.action == "install"
                else prior_in_target and not prior_in_backup
            )
            if state_is_safe:
                raise OSError(
                    "skill activation failed; the skill target state was preserved, "
                    "but private failure cleanup could not be confirmed"
                ) from recovery_error
            raise OSError(
                "skill activation failed and automatic rollback could not restore the prior "
                "installation; it remains recoverable at the previewed backup"
            ) from recovery_error
        if recovery_error is not None:
            raise OSError(
                "skill activation committed, but private failure cleanup could not be confirmed"
            ) from recovery_error
        raise
    finally:
        if stage_fd is not None:
            os.close(stage_fd)
        if reservation_fd is not None:
            os.close(reservation_fd)
        if backup_anchor is not None:
            backup_anchor.close()

    if target_anchor is None:
        raise OSError("skill target parent anchor was lost after activation")
    try:
        target_anchor.assert_visible()
        installed_manifest, installed_manifest_sha256 = _read_target_manifest_at(
            target_anchor.fd,
            fresh.target.name,
            fresh.client,
        )
        desired_manifest = (
            json.loads(fresh.desired_manifest_json) if fresh.desired_manifest_json is not None else None
        )
        if (
            installed_manifest is None
            or installed_manifest != desired_manifest
            or not _installed_files_match_at(
                target_anchor.fd,
                fresh.target.name,
                installed_manifest,
            )
        ):
            raise OSError("installed payload does not match the previewed payload")
        installed_state = _target_state_sha256_at(target_anchor.fd, fresh.target.name)
    except Exception:
        target_anchor.close()
        return replace(
            fresh,
            state="applied-verification-failed",
            message=(
                "Activation committed, but post-activation verification failed. "
                "Inspect the installed target; an update's prior tree remains in its backup."
            ),
        )
    target_anchor.close()
    return replace(
        fresh,
        state="applied",
        message="Installed files were verified and preview-bound before activation.",
        expected_manifest_sha256=installed_manifest_sha256,
        expected_target_sha256=installed_state,
    )


def plan_uninstall(client: str, *, home: Path | None = None) -> InstallPlan:
    actual_home = _normalized_home(home)
    target = target_for(client, actual_home)
    if not _path_entry_exists(target):
        return InstallPlan(
            action="uninstall",
            client=client,
            target=target,
            state="not-installed",
            files=(),
            home=actual_home,
            expected_target_sha256=_target_state_sha256(
                target,
                home=actual_home,
            ),
        )
    try:
        target_stat = target.lstat()
    except OSError as exc:
        raise OSError("installation target cannot be safely inspected") from exc
    if _is_link_like(target, target_stat):
        return InstallPlan(
            action="uninstall",
            client=client,
            target=target,
            state="blocked-unmanaged",
            files=(),
            message=("The target is a symlink, junction, or reparse point and will not be followed."),
            home=actual_home,
        )
    manifest = _read_manifest(target, client)
    if manifest is None:
        return InstallPlan(
            action="uninstall",
            client=client,
            target=target,
            state="blocked-unmanaged",
            files=(),
            message="The target is not a managed Agent Docs Doctor installation.",
            home=actual_home,
        )
    for relative in manifest["files"]:
        # A managed hard link aliases content outside the install tree. Refuse it
        # before proposing a whole-tree move.
        try:
            value = (target / relative).lstat()
        except OSError as exc:
            raise OSError("managed installer file cannot be safely inspected") from exc
        if value.st_nlink > 1:
            raise OSError("refusing a hard-linked installer file")
    files = tuple(sorted(str(path) for path in manifest.get("files", {})))
    target_state = _target_state_sha256(target, manifest, home=actual_home)
    backup, reservation = _backup_plan(
        actual_home,
        client,
        target_state,
        str(manifest.get("version", "unknown")),
    )
    return _bind_ready_plan(
        InstallPlan(
            action="uninstall",
            client=client,
            target=target,
            state="ready",
            files=files,
            backup=backup,
            expected_manifest_sha256=_manifest_sha256(target),
            home=actual_home,
            expected_target_sha256=target_state,
            backup_reservation=reservation,
        )
    )


def apply_uninstall(plan: InstallPlan, plan_token: str) -> InstallPlan:
    if plan.action != "uninstall" or plan.state != "ready":
        return plan
    if not _secure_mutation_supported():
        raise OSError(
            "apply is unavailable because this platform cannot guarantee ancestor-relative atomic activation"
        )
    fresh = _verified_fresh_plan(plan, plan_token)
    if fresh.home is None or fresh.backup is None or fresh.backup_reservation is None:
        raise OSError("operation has no safe backup reservation")
    target_anchor: _AnchoredUserDirectory | None = None
    backup_anchor: _AnchoredUserDirectory | None = None
    reservation_fd: int | None = None
    reservation_created = False
    verification_failed = False
    try:
        target_anchor = _anchor_user_directory(fresh.home, fresh.target.parent, create=False)
        if target_anchor is None:
            raise OSError("installation target changed after preview; preview again")
        backup_anchor = _anchor_user_directory(
            fresh.home,
            fresh.backup_reservation.parent,
            create=True,
        )
        if backup_anchor is None:
            raise OSError("backup parent could not be anchored")
        try:
            reservation_fd = _create_and_open_directory_at(
                backup_anchor.fd,
                fresh.backup_reservation.name,
            )
            reservation_created = True
        except FileExistsError as exc:
            raise OSError("backup reservation changed after preview; preview again") from exc
        _assert_target_state_at(fresh, target_anchor.fd)
        pre_move_state = _target_state_sha256_at(
            target_anchor.fd,
            fresh.target.name,
            ignore_root_times=True,
        )
        if pre_move_state != fresh.expected_target_move_sha256:
            raise OSError("installation target changed after preview; preview again")
        target_anchor.assert_visible()
        backup_anchor.assert_visible()
        _assert_entry_identity(
            backup_anchor.fd,
            fresh.backup_reservation.name,
            reservation_fd,
            message="backup reservation changed after preview; preview again",
        )
        _rename_noreplace_at(
            target_anchor.fd,
            fresh.target.name,
            reservation_fd,
            BACKUP_PAYLOAD_NAME,
        )
    except BaseException as exc:
        if target_anchor is None or backup_anchor is None:
            if target_anchor is not None:
                target_anchor.close()
            if backup_anchor is not None:
                if not backup_anchor.cleanup_created():
                    backup_anchor.close()
                    raise OSError(
                        "uninstall setup failed and tool-created backup ancestor cleanup "
                        "could not be confirmed"
                    ) from exc
                backup_anchor.close()
            raise
        absent_state = hashlib.sha256(b"absent").hexdigest()
        recovery_error: BaseException | None = None
        target_state: str | None = None
        backup_state: str | None = None
        try:
            target_state = _target_state_sha256_at(
                target_anchor.fd,
                fresh.target.name,
                ignore_root_times=True,
            )
        except Exception as inspect_exc:
            recovery_error = inspect_exc
        if reservation_fd is not None:
            try:
                backup_state = _target_state_sha256_at(
                    reservation_fd,
                    BACKUP_PAYLOAD_NAME,
                    ignore_root_times=True,
                )
            except Exception as inspect_exc:
                recovery_error = recovery_error or inspect_exc
        uninstall_committed = (
            target_state == absent_state
            and fresh.expected_target_move_sha256 is not None
            and backup_state == fresh.expected_target_move_sha256
        )
        target_preserved = (
            fresh.expected_target_move_sha256 is not None
            and target_state == fresh.expected_target_move_sha256
            and (reservation_fd is None or backup_state == absent_state)
        )
        if not uninstall_committed and not target_preserved:
            recovery_error = recovery_error or OSError(
                "uninstall target and previewed backup state could not be classified safely"
            )
        if target_preserved and reservation_created and reservation_fd is not None:
            try:
                _remove_owned_empty_directory_at(
                    backup_anchor.fd,
                    fresh.backup_reservation.name,
                    reservation_fd,
                )
            except OSError as cleanup_exc:
                recovery_error = recovery_error or cleanup_exc
            except BaseException as cleanup_exc:
                recovery_error = recovery_error or cleanup_exc
        if target_preserved and not backup_anchor.cleanup_created():
            recovery_error = recovery_error or OSError(
                "tool-created backup ancestors could not be cleaned safely"
            )
        if reservation_fd is not None:
            os.close(reservation_fd)
        target_anchor.close()
        backup_anchor.close()
        if recovery_error is not None:
            raise OSError(
                "uninstall apply failed and its target, backup, or private cleanup "
                "state could not be confirmed"
            ) from recovery_error
        raise
    if target_anchor is None or backup_anchor is None or reservation_fd is None:
        if reservation_fd is not None:
            os.close(reservation_fd)
        if target_anchor is not None:
            target_anchor.close()
        if backup_anchor is not None:
            backup_anchor.close()
        raise OSError("uninstall anchors were lost after the committed move")
    try:
        target_anchor.assert_visible()
        backup_anchor.assert_visible()
        _assert_entry_identity(
            backup_anchor.fd,
            fresh.backup_reservation.name,
            reservation_fd,
            message="backup reservation changed after committed uninstall",
        )
        if (
            _target_state_sha256_at(
                reservation_fd,
                BACKUP_PAYLOAD_NAME,
                ignore_root_times=True,
            )
            != fresh.expected_target_move_sha256
            or _target_state_sha256_at(target_anchor.fd, fresh.target.name)
            != hashlib.sha256(b"absent").hexdigest()
        ):
            verification_failed = True
    except Exception:
        verification_failed = True
    os.close(reservation_fd)
    target_anchor.close()
    backup_anchor.close()
    return replace(
        fresh,
        state="applied-verification-failed" if verification_failed else "applied",
        message=(
            "The move committed, but post-move verification failed. Inspect the previewed backup."
            if verification_failed
            else "The skill was moved intact to its reversible backup; no files were deleted."
        ),
    )


def plan_as_dict(plan: InstallPlan) -> dict[str, Any]:
    home = plan.home

    def display(path: Path | None) -> str | None:
        if path is None:
            return None
        return _display_user_path(home, path) if home is not None else "<user-home-path>"

    recovery = None
    if plan.backup is not None:
        recovery = {
            "from": display(plan.backup),
            "to": display(plan.target),
            "condition": "restore only when the target is absent",
        }
    return {
        "action": plan.action,
        "client": plan.client,
        "target": display(plan.target),
        "state": plan.state,
        "files": list(plan.files),
        "backup": display(plan.backup),
        "backup_reservation": display(plan.backup_reservation),
        "recovery": recovery,
        "message": plan.message,
        "plan_token": plan.plan_token,
        "desired_payload_sha256": plan.desired_manifest_sha256,
        "managed_state_sha256": plan.expected_manifest_sha256,
        "target_state_sha256": plan.expected_target_sha256,
        "target_move_state_sha256": plan.expected_target_move_sha256,
        "path_state_sha256": plan.expected_path_sha256,
    }
