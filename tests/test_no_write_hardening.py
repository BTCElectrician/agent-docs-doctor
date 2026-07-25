from __future__ import annotations

import ctypes
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_no_write  # noqa: E402


def _synthetic_xattr_api(
    names_payload: bytes,
    value_size: int,
):
    def list_xattrs(_descriptor: int, buffer, _size: int) -> int:
        if buffer is None:
            return len(names_payload)
        ctypes.memmove(buffer, names_payload, len(names_payload))
        return len(names_payload)

    def get_xattr(_descriptor: int, _name: bytes, buffer, _size: int) -> int:
        if buffer is None:
            return value_size
        raise AssertionError("oversized xattr value must not be allocated or read")

    return list_xattrs, get_xattr


def test_snapshot_parent_swap_fails_before_out_of_root_content_read() -> None:
    with (
        tempfile.TemporaryDirectory() as root_value,
        tempfile.TemporaryDirectory() as outside_value,
    ):
        root = Path(root_value)
        outside = Path(outside_value)
        nested = root / "docs"
        nested.mkdir()
        (nested / "AGENTS.md").write_text("# original\n", encoding="utf-8")
        outside_file = outside / "AGENTS.md"
        outside_file.write_text("outside-private-sentinel\n", encoding="utf-8")
        real_walk = check_no_write._walk_without_links
        real_hash = check_no_write._hash_regular
        hashed: list[Path] = []

        def swap_after_walk(captured_root: Path):
            paths = real_walk(captured_root)
            nested.rename(root / "docs-original")
            try:
                nested.symlink_to(outside, target_is_directory=True)
            except OSError as exc:
                pytest.skip(f"symlinks unavailable: {exc.__class__.__name__}")
            return paths

        def record_hash(
            captured_root: Path,
            path: Path,
            expected,
            byte_limit: int,
        ) -> str:
            hashed.append(path)
            return real_hash(captured_root, path, expected, byte_limit)

        with (
            patch.object(
                check_no_write,
                "_walk_without_links",
                side_effect=swap_after_walk,
            ),
            patch.object(check_no_write, "_hash_regular", side_effect=record_hash),
            pytest.raises(
                check_no_write.SnapshotLimitError,
                match="entry changed before capture",
            ),
        ):
            check_no_write.snapshot(root)

    assert root / "docs" / "AGENTS.md" not in hashed


def test_xattr_count_limit_fails_before_value_reads() -> None:
    names = b"".join(f"user.synthetic-{index}".encode() + b"\0" for index in range(129))
    with tempfile.TemporaryDirectory() as value:
        root = Path(value).resolve()
        path = root / "AGENTS.md"
        path.write_text("# synthetic\n", encoding="utf-8")
        with (
            patch.object(
                check_no_write,
                "_xattr_api",
                return_value=_synthetic_xattr_api(names, 0),
            ),
            pytest.raises(
                check_no_write.SnapshotLimitError,
                match="too many extended attributes",
            ),
        ):
            check_no_write._xattrs(
                root,
                path,
                path.stat(),
                kind="regular",
                hash_values=True,
                remaining_bytes=check_no_write.MAX_XATTR_BYTES,
            )


def test_single_xattr_value_limit_fails_before_allocation() -> None:
    names = b"user.synthetic\0"
    with tempfile.TemporaryDirectory() as value:
        root = Path(value).resolve()
        path = root / "AGENTS.md"
        path.write_text("# synthetic\n", encoding="utf-8")
        with (
            patch.object(
                check_no_write,
                "_xattr_api",
                return_value=_synthetic_xattr_api(
                    names,
                    check_no_write.MAX_XATTR_VALUE_BYTES + 1,
                ),
            ),
            pytest.raises(
                check_no_write.SnapshotLimitError,
                match="values exceed the snapshot safety limit",
            ),
        ):
            check_no_write._xattrs(
                root,
                path,
                path.stat(),
                kind="regular",
                hash_values=True,
                remaining_bytes=check_no_write.MAX_XATTR_BYTES,
            )


def test_aggregate_xattr_budget_fails_before_value_allocation() -> None:
    names = b"user.synthetic\0"
    with tempfile.TemporaryDirectory() as value:
        root = Path(value).resolve()
        path = root / "AGENTS.md"
        path.write_text("# synthetic\n", encoding="utf-8")
        with (
            patch.object(
                check_no_write,
                "_xattr_api",
                return_value=_synthetic_xattr_api(names, 128),
            ),
            pytest.raises(
                check_no_write.SnapshotLimitError,
                match="values exceed the snapshot safety limit",
            ),
        ):
            check_no_write._xattrs(
                root,
                path,
                path.stat(),
                kind="regular",
                hash_values=True,
                remaining_bytes=len(names) + 64,
            )
