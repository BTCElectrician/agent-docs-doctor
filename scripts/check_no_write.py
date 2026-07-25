#!/usr/bin/env python3
"""Prove that an audit leaves the requested repository filesystem unchanged."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import os
import stat
import sys
from collections.abc import Callable
from itertools import islice
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent_docs_doctor import build_audit, validate_audit  # noqa: E402
from agent_docs_doctor.core import (  # noqa: E402
    _descriptor_resolved_path,
    _directory_entry_stat,
    _existing_path_within_root,
    _open_pinned_directory,
    _open_windows_file_descriptor,
    _pinned_directory_unchanged,
    _same_existing_path,
    is_secret_path,
)

SnapshotEntry = tuple[str, tuple[tuple[str, Any], ...]]
MAX_SNAPSHOT_ENTRIES = 100_000
MAX_SNAPSHOT_BYTES = 512_000_000
MAX_XATTRS_PER_ENTRY = 128
MAX_XATTR_NAME_BYTES = 1_024
MAX_XATTR_NAMES_BYTES_PER_ENTRY = 64_000
MAX_XATTR_VALUE_BYTES = 1_000_000
MAX_XATTR_BYTES_PER_ENTRY = 4_000_000
MAX_XATTR_BYTES = 64_000_000


class SnapshotLimitError(OSError):
    """Raised when a proof snapshot would exceed its safe local bounds."""


def _is_reparse_point(value: os.stat_result) -> bool:
    attributes = getattr(value, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_flag)


def _kind(value: os.stat_result) -> str:
    if stat.S_ISLNK(value.st_mode):
        return "symlink"
    if _is_reparse_point(value):
        return "reparse-point"
    if stat.S_ISREG(value.st_mode):
        return "regular"
    if stat.S_ISDIR(value.st_mode):
        return "directory"
    if stat.S_ISFIFO(value.st_mode):
        return "fifo"
    if stat.S_ISSOCK(value.st_mode):
        return "socket"
    if stat.S_ISCHR(value.st_mode):
        return "character-device"
    if stat.S_ISBLK(value.st_mode):
        return "block-device"
    return "other"


def _same_file_identity(left: os.stat_result, right: os.stat_result) -> bool:
    left_inode = int(getattr(left, "st_ino", 0))
    right_inode = int(getattr(right, "st_ino", 0))
    if left_inode and right_inode:
        return left.st_dev == right.st_dev and left_inode == right_inode
    return (
        stat.S_IFMT(left.st_mode) == stat.S_IFMT(right.st_mode)
        and left.st_size == right.st_size
        and left.st_ctime_ns == right.st_ctime_ns
    )


def _same_file_snapshot(
    left: os.stat_result,
    right: os.stat_result,
    *,
    compare_change_time: bool = True,
) -> bool:
    return (
        _same_file_identity(left, right)
        and stat.S_IFMT(left.st_mode) == stat.S_IFMT(right.st_mode)
        and left.st_size == right.st_size
        and left.st_nlink == right.st_nlink
        and left.st_mtime_ns == right.st_mtime_ns
        and (not compare_change_time or left.st_ctime_ns == right.st_ctime_ns)
    )


def _same_directory_snapshot(left: os.stat_result, right: os.stat_result) -> bool:
    """Compare stable directory identity fields across Windows metadata providers."""

    if os.name != "nt":
        return _same_file_snapshot(left, right)
    return (
        _same_file_identity(left, right)
        and stat.S_ISDIR(left.st_mode)
        and stat.S_ISDIR(right.st_mode)
        and _is_reparse_point(left) == _is_reparse_point(right)
        and getattr(left, "st_reparse_tag", None) == getattr(right, "st_reparse_tag", None)
    )


def _directory_entries_match(
    left: list[tuple[str, os.stat_result]],
    right: list[tuple[str, os.stat_result]],
) -> bool:
    def stable_fields(record: tuple[str, os.stat_result]) -> tuple[Any, ...]:
        name, info = record
        return (
            name,
            info.st_dev,
            info.st_ino,
            stat.S_IFMT(info.st_mode),
            info.st_size,
            info.st_nlink,
            info.st_mtime_ns,
            _is_reparse_point(info),
            getattr(info, "st_reparse_tag", None),
        )

    return sorted(map(stable_fields, left)) == sorted(map(stable_fields, right))


def _walk_without_links(root: Path) -> list[tuple[Path, os.stat_result]]:
    root_info = root.lstat()
    if not stat.S_ISDIR(root_info.st_mode) or _is_reparse_point(root_info):
        raise SnapshotLimitError("filesystem snapshot root is not a safe directory")
    paths = [(root, root_info)]
    pending = [(root, root_info)]
    while pending:
        directory, expected_directory = pending.pop()
        try:
            visible_before = directory.lstat()
        except OSError as exc:
            raise SnapshotLimitError("filesystem snapshot directory changed before traversal") from exc
        if not _same_directory_snapshot(expected_directory, visible_before):
            raise SnapshotLimitError("filesystem snapshot directory changed before traversal")
        remaining = MAX_SNAPSHOT_ENTRIES - len(paths)
        try:
            scan_target, close_pinned = _open_pinned_directory(directory, root)
        except OSError as exc:
            raise SnapshotLimitError("filesystem snapshot directory could not be pinned") from exc
        entries: list[tuple[str, os.stat_result]] = []
        try:
            if not _pinned_directory_unchanged(scan_target, directory):
                raise SnapshotLimitError("filesystem snapshot directory changed before traversal")
            pinned = os.fstat(scan_target) if isinstance(scan_target, int) else directory.lstat()
            if not _same_directory_snapshot(expected_directory, pinned):
                raise SnapshotLimitError("filesystem snapshot directory changed before traversal")
            with os.scandir(scan_target) as iterator:
                for entry in islice(iterator, remaining + 1):
                    try:
                        entry_info = _directory_entry_stat(directory, entry)
                    except OSError as exc:
                        raise SnapshotLimitError(
                            "filesystem snapshot entry changed during traversal"
                        ) from exc
                    entries.append((entry.name, entry_info))
            if os.name == "nt" and len(entries) <= remaining:
                repeated_entries: list[tuple[str, os.stat_result]] = []
                with os.scandir(scan_target) as iterator:
                    for entry in islice(iterator, remaining + 1):
                        try:
                            entry_info = _directory_entry_stat(directory, entry)
                        except OSError as exc:
                            raise SnapshotLimitError(
                                "filesystem snapshot entry changed during traversal"
                            ) from exc
                        repeated_entries.append((entry.name, entry_info))
                if len(repeated_entries) > remaining or not _directory_entries_match(
                    entries,
                    repeated_entries,
                ):
                    raise SnapshotLimitError("filesystem snapshot directory changed during traversal")
            try:
                visible_after = directory.lstat()
                pinned_after = os.fstat(scan_target) if isinstance(scan_target, int) else visible_after
            except OSError as exc:
                raise SnapshotLimitError("filesystem snapshot directory changed during traversal") from exc
            if (
                not _pinned_directory_unchanged(scan_target, directory)
                or not _same_directory_snapshot(expected_directory, visible_after)
                or not _same_directory_snapshot(pinned, pinned_after)
            ):
                raise SnapshotLimitError("filesystem snapshot directory changed during traversal")
        finally:
            try:
                close_pinned()
            except OSError as exc:
                raise SnapshotLimitError("filesystem snapshot directory pin could not be closed") from exc
        if len(entries) > remaining:
            raise SnapshotLimitError(
                f"filesystem snapshot exceeds the {MAX_SNAPSHOT_ENTRIES} entry safety limit"
            )
        entries.sort(key=lambda item: item[0], reverse=True)
        for name, value in entries:
            path = directory / name
            paths.append((path, value))
            if stat.S_ISDIR(value.st_mode) and not _is_reparse_point(value):
                pending.append((path, value))
    return sorted(paths, key=lambda item: item[0].relative_to(root).as_posix())


def _open_verified_entry(
    root: Path,
    path: Path,
    expected: os.stat_result,
    *,
    directory: bool,
) -> int:
    flags = os.O_RDONLY
    flags |= getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    if directory:
        flags |= getattr(os, "O_DIRECTORY", 0)
    descriptor = (
        _open_windows_file_descriptor(path, expected)
        if os.name == "nt" and not directory
        else os.open(path, flags)
    )
    try:
        opened = os.fstat(descriptor)
        expected_kind = stat.S_ISDIR if directory else stat.S_ISREG
        if not expected_kind(opened.st_mode):
            raise SnapshotLimitError("filesystem snapshot entry changed type")
        if not _same_file_snapshot(
            opened,
            expected,
            compare_change_time=os.name != "nt",
        ):
            raise SnapshotLimitError("filesystem snapshot entry changed while opening")
        descriptor_path = _descriptor_resolved_path(descriptor)
        if descriptor_path is None:
            raise SnapshotLimitError("filesystem snapshot entry location could not be verified")
        if not _existing_path_within_root(descriptor_path, root):
            raise SnapshotLimitError("filesystem snapshot entry escaped its root")
        if not _same_existing_path(descriptor_path, path):
            raise SnapshotLimitError("filesystem snapshot entry path changed while opening")
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _hash_regular(root: Path, path: Path, expected: os.stat_result, byte_limit: int) -> str:
    descriptor = _open_verified_entry(root, path, expected, directory=False)
    try:
        opened = os.fstat(descriptor)
        digest = hashlib.sha256()
        total = 0
        while chunk := os.read(descriptor, min(1024 * 1024, byte_limit + 1 - total)):
            total += len(chunk)
            if total > byte_limit:
                raise SnapshotLimitError(
                    f"filesystem snapshot exceeds the {MAX_SNAPSHOT_BYTES} byte safety limit"
                )
            digest.update(chunk)
        final = os.fstat(descriptor)
        if not _same_file_snapshot(opened, final):
            return "<changed-during-snapshot>"
        return digest.hexdigest()
    finally:
        os.close(descriptor)


def _xattr_api() -> tuple[Callable[[int, Any, int], int], Callable[[int, bytes, Any, int], int]] | None:
    """Return descriptor xattr calls that support bounded size queries."""

    if not (sys.platform.startswith("linux") or sys.platform == "darwin"):
        return None
    try:
        library = ctypes.CDLL(None, use_errno=True)
        list_function = library.flistxattr
        get_function = library.fgetxattr
    except (AttributeError, OSError):
        return None
    list_function.restype = ctypes.c_ssize_t
    get_function.restype = ctypes.c_ssize_t

    if sys.platform == "darwin":

        def list_xattrs(descriptor: int, buffer: Any, size: int) -> int:
            return int(list_function(descriptor, buffer, size, 0))

        def get_xattr(descriptor: int, name: bytes, buffer: Any, size: int) -> int:
            return int(get_function(descriptor, name, buffer, size, 0, 0))

    else:

        def list_xattrs(descriptor: int, buffer: Any, size: int) -> int:
            return int(list_function(descriptor, buffer, size))

        def get_xattr(descriptor: int, name: bytes, buffer: Any, size: int) -> int:
            return int(get_function(descriptor, name, buffer, size))

    return list_xattrs, get_xattr


def _bounded_xattr_names(
    descriptor: int,
    list_xattrs: Callable[[int, Any, int], int],
    remaining_bytes: int,
) -> tuple[list[tuple[str, bytes]], int]:
    ctypes.set_errno(0)
    required = list_xattrs(descriptor, None, 0)
    if required < 0:
        raise SnapshotLimitError("filesystem extended attributes could not be listed safely")
    if required > MAX_XATTR_NAMES_BYTES_PER_ENTRY or required > remaining_bytes or required > MAX_XATTR_BYTES:
        raise SnapshotLimitError("filesystem extended-attribute names exceed the snapshot safety limit")
    if required == 0:
        return [], 0
    buffer = ctypes.create_string_buffer(required)
    ctypes.set_errno(0)
    written = list_xattrs(descriptor, buffer, required)
    if written < 0 or written > required:
        raise SnapshotLimitError("filesystem extended attributes changed while names were captured")
    raw_names = bytes(buffer.raw[:written])
    if raw_names and not raw_names.endswith(b"\0"):
        raise SnapshotLimitError("filesystem extended-attribute names are malformed")
    encoded_names = [value for value in raw_names.split(b"\0") if value]
    if len(encoded_names) > MAX_XATTRS_PER_ENTRY:
        raise SnapshotLimitError("filesystem entry has too many extended attributes")
    names: list[tuple[str, bytes]] = []
    for raw_name in encoded_names:
        if len(raw_name) > MAX_XATTR_NAME_BYTES:
            raise SnapshotLimitError("filesystem extended-attribute name exceeds the safety limit")
        names.append((os.fsdecode(raw_name), raw_name))
    names.sort(key=lambda item: item[1])
    return names, written


def _xattrs(
    root: Path,
    path: Path,
    expected: os.stat_result,
    *,
    kind: str,
    hash_values: bool,
    remaining_bytes: int,
) -> tuple[tuple[tuple[str, str], ...], int]:
    api = _xattr_api()
    if api is None:
        return (("<status>", "unsupported"),), 0
    if kind not in {"regular", "directory"}:
        return (("<status>", "not-read-for-non-regular-entry"),), 0
    list_xattrs, get_xattr = api
    descriptor = _open_verified_entry(
        root,
        path,
        expected,
        directory=kind == "directory",
    )
    try:
        names, consumed_bytes = _bounded_xattr_names(
            descriptor,
            list_xattrs,
            remaining_bytes,
        )
        values: list[tuple[str, str]] = []
        entry_value_bytes = 0
        for name, raw_name in names:
            if not hash_values:
                values.append((name, "<protected-value-not-read>"))
                continue
            ctypes.set_errno(0)
            required = get_xattr(descriptor, raw_name, None, 0)
            if required < 0:
                raise SnapshotLimitError("filesystem extended attribute could not be sized safely")
            if (
                required > MAX_XATTR_VALUE_BYTES
                or entry_value_bytes + required > MAX_XATTR_BYTES_PER_ENTRY
                or consumed_bytes + required > remaining_bytes
            ):
                raise SnapshotLimitError(
                    "filesystem extended-attribute values exceed the snapshot safety limit"
                )
            buffer = ctypes.create_string_buffer(max(required, 1))
            ctypes.set_errno(0)
            written = get_xattr(descriptor, raw_name, buffer, required)
            if written < 0 or written > required:
                raise SnapshotLimitError("filesystem extended attribute changed while it was captured")
            raw = bytes(buffer.raw[:written])
            entry_value_bytes += written
            consumed_bytes += written
            values.append((name, hashlib.sha256(raw).hexdigest()))
        if not _same_file_snapshot(
            expected,
            os.fstat(descriptor),
            compare_change_time=os.name != "nt",
        ):
            raise SnapshotLimitError("filesystem snapshot entry changed during xattr capture")
        return tuple(values), consumed_bytes
    finally:
        os.close(descriptor)


def _snapshot_entry(
    root: Path,
    path: Path,
    expected: os.stat_result,
    protected_identities: set[tuple[int, int]],
    remaining_bytes: int,
    remaining_xattr_bytes: int,
) -> tuple[SnapshotEntry, int]:
    try:
        value = path.lstat()
    except OSError as exc:
        raise SnapshotLimitError("filesystem snapshot entry changed before capture") from exc
    unchanged_before = (
        _same_directory_snapshot(expected, value)
        if stat.S_ISDIR(expected.st_mode)
        else _same_file_snapshot(expected, value, compare_change_time=os.name != "nt")
    )
    if not unchanged_before:
        raise SnapshotLimitError("filesystem snapshot entry changed before capture")
    kind = _kind(value)
    relative = "." if path == root else path.relative_to(root).as_posix()
    target = ""
    content_sha256 = ""
    protected_content = False
    if kind in {"symlink", "reparse-point"}:
        try:
            target = os.readlink(path)
        except OSError as exc:
            target = f"<{type(exc).__name__}>"
    elif kind == "regular":
        if is_secret_path(path) or value.st_nlink > 1 or (value.st_dev, value.st_ino) in protected_identities:
            content_sha256 = "<protected-content-not-read>"
            protected_content = True
        else:
            if value.st_size > remaining_bytes:
                raise SnapshotLimitError(
                    f"filesystem snapshot exceeds the {MAX_SNAPSHOT_BYTES} byte safety limit"
                )
            content_sha256 = _hash_regular(
                root,
                path,
                value,
                min(value.st_size, remaining_bytes),
            )

    xattrs, xattr_bytes = _xattrs(
        root,
        path,
        value,
        kind=kind,
        hash_values=not protected_content,
        remaining_bytes=remaining_xattr_bytes,
    )
    if xattr_bytes > remaining_xattr_bytes:
        raise SnapshotLimitError(
            f"filesystem snapshot exceeds the {MAX_XATTR_BYTES} extended-attribute byte safety limit"
        )
    metadata: tuple[tuple[str, Any], ...] = (
        ("kind", kind),
        ("mode", value.st_mode),
        ("uid", getattr(value, "st_uid", None)),
        ("gid", getattr(value, "st_gid", None)),
        ("size", value.st_size),
        ("device", value.st_dev),
        ("inode", value.st_ino),
        ("links", value.st_nlink),
        ("mtime_ns", value.st_mtime_ns),
        ("ctime_ns", value.st_ctime_ns),
        ("flags", getattr(value, "st_flags", None)),
        ("file_attributes", getattr(value, "st_file_attributes", None)),
        ("reparse_tag", getattr(value, "st_reparse_tag", None)),
        ("target", target),
        ("content_sha256", content_sha256),
        (
            "xattrs",
            xattrs,
        ),
    )
    try:
        final = path.lstat()
    except OSError as exc:
        raise SnapshotLimitError("filesystem snapshot entry changed during capture") from exc
    unchanged = (
        _same_directory_snapshot(value, final)
        if kind == "directory"
        else _same_file_snapshot(value, final, compare_change_time=os.name != "nt")
    )
    if not unchanged:
        raise SnapshotLimitError("filesystem snapshot entry changed during capture")
    return (relative, metadata), xattr_bytes


def snapshot(root: Path) -> tuple[SnapshotEntry, ...]:
    root = root.resolve(strict=True)
    paths = _walk_without_links(root)
    protected_identities = {
        (value.st_dev, value.st_ino)
        for path, value in paths
        if is_secret_path(path) and stat.S_ISREG(value.st_mode) and value.st_ino > 0
    }
    values: list[SnapshotEntry] = []
    read_bytes = 0
    xattr_bytes = 0
    for path, value in paths:
        protected = stat.S_ISREG(value.st_mode) and (
            is_secret_path(path) or value.st_nlink > 1 or (value.st_dev, value.st_ino) in protected_identities
        )
        entry, entry_xattr_bytes = _snapshot_entry(
            root,
            path,
            value,
            protected_identities,
            MAX_SNAPSHOT_BYTES - read_bytes,
            MAX_XATTR_BYTES - xattr_bytes,
        )
        values.append(entry)
        xattr_bytes += entry_xattr_bytes
        if stat.S_ISREG(value.st_mode) and not protected:
            read_bytes += value.st_size
    return tuple(values)


def _contains_protected_content(values: tuple[SnapshotEntry, ...]) -> bool:
    return any(
        field == "content_sha256" and value == "<protected-content-not-read>"
        for _, metadata in values
        for field, value in metadata
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if not root.is_dir():
        print("error: requested root is not a directory", file=sys.stderr)
        return 2
    try:
        before = snapshot(root)
        errors = validate_audit(build_audit(root))
        after = snapshot(root)
    except SnapshotLimitError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        detail = exc.strerror or type(exc).__name__
        print(f"error: unable to complete filesystem snapshot: {detail}", file=sys.stderr)
        return 2
    if errors:
        print(f"error: generated report is invalid: {errors[0]}", file=sys.stderr)
        return 1
    if before != after:
        print("error: repository filesystem changed during audit", file=sys.stderr)
        return 1
    if _contains_protected_content(before):
        print("unchanged metadata; protected file contents were not read")
    else:
        print("unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
