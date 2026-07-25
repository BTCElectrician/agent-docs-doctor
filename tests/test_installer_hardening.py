from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import agent_docs_doctor.installer as installer  # noqa: E402
from agent_docs_doctor.installer import (  # noqa: E402
    MANIFEST_NAME,
    apply_install,
    apply_uninstall,
    plan_as_dict,
    plan_install,
    plan_uninstall,
    target_for,
)


class InstallerHardeningTests(unittest.TestCase):
    def setUp(self) -> None:
        if not installer._secure_mutation_supported():
            self.skipTest("secure ancestor-relative installer apply is unavailable")

    def _install(self, client: str, home: Path) -> installer.InstallPlan:
        preview = plan_install(client, home=home)
        self.assertIsNotNone(preview.plan_token)
        return apply_install(preview, preview.plan_token or "")

    def _make_update(self, client: str, home: Path) -> installer.InstallPlan:
        installed = self._install(client, home)
        manifest_path = installed.target / MANIFEST_NAME
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["version"] = "0.0.1"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        preview = plan_install(client, home=home, update=True)
        self.assertEqual(preview.state, "ready")
        self.assertIsNotNone(preview.plan_token)
        return preview

    @staticmethod
    def _tree_snapshot(root: Path) -> dict[str, tuple[str, bytes | str]]:
        snapshot: dict[str, tuple[str, bytes | str]] = {}
        for path in sorted(root.rglob("*")):
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                snapshot[relative] = ("link", os.readlink(path))
            elif path.is_file():
                snapshot[relative] = ("file", path.read_bytes())
            elif path.is_dir():
                snapshot[relative] = ("directory", "")
        return snapshot

    @staticmethod
    def _synthetic_source(root: Path) -> Path:
        (root / "agents").mkdir(parents=True)
        (root / "references").mkdir()
        (root / "SKILL.md").write_text("# Synthetic skill\n", encoding="utf-8")
        (root / "agents" / "openai.yaml").write_text("name: synthetic\n", encoding="utf-8")
        for relative in installer.SOURCE_RELATIVE_PATHS:
            if not relative.startswith("references/"):
                continue
            path = root / relative
            path.write_text(f"# {path.stem}\n", encoding="utf-8")
        (root / "not-allowlisted.txt").write_text("must not be installed\n", encoding="utf-8")
        return root

    def test_ancestor_symlink_is_rejected_without_touching_its_destination(self) -> None:
        with (
            tempfile.TemporaryDirectory() as home_value,
            tempfile.TemporaryDirectory() as external_value,
        ):
            home = Path(home_value)
            external = Path(external_value)
            (home / ".agents").symlink_to(external, target_is_directory=True)

            with self.assertRaisesRegex(OSError, "symlink, junction, or reparse"):
                plan_install("codex", home=home)

            self.assertEqual(list(external.iterdir()), [])

    def test_ancestor_alias_appearing_after_preview_is_rejected(self) -> None:
        with (
            tempfile.TemporaryDirectory() as home_value,
            tempfile.TemporaryDirectory() as external_value,
        ):
            home = Path(home_value)
            external = Path(external_value)
            preview = plan_install("codex", home=home)
            (home / ".agents").symlink_to(external, target_is_directory=True)

            with self.assertRaisesRegex(OSError, "symlink, junction, or reparse"):
                apply_install(preview, preview.plan_token or "")

            self.assertEqual(list(external.iterdir()), [])

    def test_reparse_attribute_is_treated_as_an_alias(self) -> None:
        fake = SimpleNamespace(
            st_mode=stat.S_IFDIR | 0o700,
            st_file_attributes=getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400),
        )
        self.assertTrue(installer._is_link_like(Path("synthetic"), fake))

    def test_plan_token_is_required_and_binds_every_mutating_field(self) -> None:
        with tempfile.TemporaryDirectory() as home_value:
            home = Path(home_value)
            preview = plan_install("codex", home=home)

            with self.assertRaisesRegex(OSError, "does not match"):
                apply_install(preview, "0" * 64)

            tampered = replace(preview, target=home / "elsewhere")
            with self.assertRaisesRegex(OSError, "binding is invalid"):
                apply_install(tampered, preview.plan_token or "")

            self.assertFalse(preview.target.exists())
            self.assertFalse((home / "elsewhere").exists())

    def test_target_appearance_and_content_changes_invalidate_preview(self) -> None:
        with tempfile.TemporaryDirectory() as home_value:
            home = Path(home_value)
            install_preview = plan_install("claude", home=home)
            install_preview.target.mkdir(parents=True)
            user_file = install_preview.target / "user-owned.txt"
            user_file.write_text("preserve me\n", encoding="utf-8")

            with self.assertRaisesRegex(OSError, "changed after preview"):
                apply_install(install_preview, install_preview.plan_token or "")
            self.assertEqual(user_file.read_text(encoding="utf-8"), "preserve me\n")

        with tempfile.TemporaryDirectory() as home_value:
            home = Path(home_value)
            installed = self._install("claude", home)
            extra = installed.target / "user-extra.txt"
            extra.write_text("one\n", encoding="utf-8")
            uninstall_preview = plan_uninstall("claude", home=home)
            extra.write_text("two\n", encoding="utf-8")

            with self.assertRaisesRegex(OSError, "changed after preview"):
                apply_uninstall(uninstall_preview, uninstall_preview.plan_token or "")
            self.assertEqual(extra.read_text(encoding="utf-8"), "two\n")

    def test_source_change_after_preview_is_rejected_before_destination_mutation(self) -> None:
        with (
            tempfile.TemporaryDirectory() as home_value,
            tempfile.TemporaryDirectory() as source_value,
        ):
            home = Path(home_value)
            source = self._synthetic_source(Path(source_value))
            with mock.patch.object(installer, "bundled_skill_root", return_value=source):
                preview = plan_install("cursor", home=home)
                (source / "SKILL.md").write_text("# Changed after preview\n", encoding="utf-8")
                with self.assertRaisesRegex(OSError, "source changed after preview"):
                    apply_install(preview, preview.plan_token or "")

            self.assertFalse(preview.target.exists())

    def test_bundled_skill_source_must_match_the_executing_code_distribution(self) -> None:
        with mock.patch.object(
            installer.metadata,
            "distribution",
            side_effect=AssertionError("source checkout must be preferred"),
        ):
            self.assertEqual(installer.bundled_skill_root(), ROOT)

        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            executing = root / "current" / "agent_docs_doctor" / "installer.py"
            executing.parent.mkdir(parents=True)
            executing.write_text("# current code\n", encoding="utf-8")
            other_code = root / "other" / "agent_docs_doctor" / "installer.py"
            other_code.parent.mkdir(parents=True)
            other_code.write_text("# unrelated code\n", encoding="utf-8")
            stale_skill = root / "other" / "share" / "agent-docs-doctor" / "skill"
            stale_skill.mkdir(parents=True)
            (stale_skill / "SKILL.md").write_text("# stale skill\n", encoding="utf-8")
            code_item = PurePosixPath("agent_docs_doctor/installer.py")
            skill_item = PurePosixPath("share/agent-docs-doctor/skill/SKILL.md")

            class MismatchedDistribution:
                files = (code_item, skill_item)

                @staticmethod
                def locate_file(item: PurePosixPath) -> Path:
                    return other_code if item == code_item else stale_skill / "SKILL.md"

            with (
                mock.patch.object(installer, "__file__", os.fspath(executing)),
                mock.patch.object(
                    installer.metadata,
                    "distribution",
                    return_value=MismatchedDistribution(),
                ),
                self.assertRaises(FileNotFoundError),
            ):
                installer.bundled_skill_root()

    def test_source_directory_swap_cannot_redirect_staging_reads(self) -> None:
        with (
            tempfile.TemporaryDirectory() as home_value,
            tempfile.TemporaryDirectory() as source_value,
            tempfile.TemporaryDirectory() as external_value,
        ):
            home = Path(home_value)
            source = self._synthetic_source(Path(source_value))
            external = self._synthetic_source(Path(external_value))
            (external / "references" / "AUDIT_RUBRIC.md").write_text(
                "external payload must not be staged\n",
                encoding="utf-8",
            )
            with mock.patch.object(installer, "bundled_skill_root", return_value=source):
                preview = plan_install("cursor", home=home)
                real_inventory = installer._bounded_child_names_fd
                inventory_calls = 0

                def swap_after_reference_inventory(fd: int, expected_count: int) -> set[str]:
                    nonlocal inventory_calls
                    names = real_inventory(fd, expected_count)
                    inventory_calls += 1
                    if inventory_calls == 2:
                        (source / "references").rename(source / "references-original")
                        (source / "references").symlink_to(
                            external / "references",
                            target_is_directory=True,
                        )
                    return names

                with (
                    mock.patch.object(
                        installer,
                        "_bounded_child_names_fd",
                        side_effect=swap_after_reference_inventory,
                    ),
                    self.assertRaises(OSError),
                ):
                    apply_install(preview, preview.plan_token or "")
            self.assertFalse(preview.target.exists())

    def test_ancestor_swap_after_staging_cannot_redirect_activation(self) -> None:
        with (
            tempfile.TemporaryDirectory() as home_value,
            tempfile.TemporaryDirectory() as external_value,
        ):
            home = Path(home_value)
            external = Path(external_value)
            captured = external / "captured-original"
            redirected = external / "redirected"
            redirected.mkdir()
            preview = plan_install("codex", home=home)
            real_stage = installer._write_staged_skill_fd

            def swap_ancestor(stage_fd: int, plan: installer.InstallPlan) -> None:
                real_stage(stage_fd, plan)
                (home / ".agents").rename(captured)
                (home / ".agents").symlink_to(redirected, target_is_directory=True)

            with (
                mock.patch.object(
                    installer,
                    "_write_staged_skill_fd",
                    side_effect=swap_ancestor,
                ),
                self.assertRaisesRegex(OSError, "private failure cleanup could not be confirmed"),
            ):
                apply_install(preview, preview.plan_token or "")

            self.assertEqual(list(redirected.iterdir()), [])
            self.assertFalse((captured / "skills" / installer.SKILL_NAME).exists())
            self.assertEqual(
                list((captured / "skills").glob(".agent-docs-doctor-install-*")),
                [],
            )

    def test_only_previewed_allowlisted_payload_is_staged(self) -> None:
        with (
            tempfile.TemporaryDirectory() as home_value,
            tempfile.TemporaryDirectory() as source_value,
        ):
            home = Path(home_value)
            source = self._synthetic_source(Path(source_value))
            with mock.patch.object(installer, "bundled_skill_root", return_value=source):
                preview = plan_install("codex", home=home)
                applied = apply_install(preview, preview.plan_token or "")

            self.assertTrue((applied.target / "SKILL.md").is_file())
            self.assertTrue((applied.target / "agents" / "openai.yaml").is_file())
            self.assertTrue((applied.target / "references" / "AUDIT_RUBRIC.md").is_file())
            self.assertFalse((applied.target / "not-allowlisted.txt").exists())
            manifest = json.loads((applied.target / MANIFEST_NAME).read_text(encoding="utf-8"))
            self.assertEqual(set(manifest["files"]), set(preview.files))
            self.assertEqual(
                list(applied.target.parent.glob(".agent-docs-doctor-install-*")),
                [],
            )

    def test_unexpected_reference_is_rejected_without_being_read(self) -> None:
        with (
            tempfile.TemporaryDirectory() as home_value,
            tempfile.TemporaryDirectory() as source_value,
        ):
            home = Path(home_value)
            source = self._synthetic_source(Path(source_value))
            unexpected = source / "references" / "PRIVATE.md"
            unexpected.write_text("synthetic private payload\n", encoding="utf-8")
            real_reader = installer._read_regular_bytes
            opened: list[Path] = []

            def guarded_reader(path: Path, *, limit: int) -> bytes:
                opened.append(path)
                if path == unexpected:
                    raise AssertionError("unexpected reference content was read")
                return real_reader(path, limit=limit)

            with (
                mock.patch.object(installer, "bundled_skill_root", return_value=source),
                mock.patch.object(installer, "_read_regular_bytes", side_effect=guarded_reader),
                self.assertRaisesRegex(OSError, "static public allowlist"),
            ):
                plan_install("codex", home=home)
            self.assertNotIn(unexpected, opened)

    def test_hardlinked_source_manifest_and_managed_file_fail_closed(self) -> None:
        with (
            tempfile.TemporaryDirectory() as home_value,
            tempfile.TemporaryDirectory() as source_value,
        ):
            home = Path(home_value)
            source = self._synthetic_source(Path(source_value))
            os.link(source / "SKILL.md", source / "skill-hardlink-alias")
            with (
                mock.patch.object(installer, "bundled_skill_root", return_value=source),
                self.assertRaisesRegex(OSError, "hard-linked"),
            ):
                plan_install("codex", home=home)

        with tempfile.TemporaryDirectory() as home_value:
            home = Path(home_value)
            installed = self._install("codex", home)
            manifest_alias = home / "manifest-alias"
            os.link(installed.target / MANIFEST_NAME, manifest_alias)
            blocked = plan_uninstall("codex", home=home)
            self.assertEqual(blocked.state, "blocked-unmanaged")
            manifest_alias.unlink()

            skill_alias = home / "skill-alias"
            os.link(installed.target / "SKILL.md", skill_alias)
            with self.assertRaisesRegex(OSError, "hard-linked"):
                plan_uninstall("codex", home=home)

        with tempfile.TemporaryDirectory() as home_value:
            home = Path(home_value)
            installed = self._install("codex", home)
            private_alias_source = home / "synthetic-private-payload"
            private_alias_source.write_text("must never be read\n", encoding="utf-8")
            managed_path = installed.target / "SKILL.md"
            managed_path.unlink()
            os.link(private_alias_source, managed_path)

            with self.assertRaisesRegex(OSError, "hard-linked"):
                plan_install("codex", home=home, update=True)

    def test_manifest_duplicate_keys_and_numeric_constants_are_rejected(self) -> None:
        desired = installer._desired_manifest("codex")
        rendered = json.dumps(desired, sort_keys=True)
        duplicate = rendered[:-1] + ', "owner": "agent-docs-doctor"}'
        constant = rendered.replace('"version": "0.3.0"', '"version": NaN')

        self.assertIsNone(installer._parse_manifest_bytes(duplicate.encode("utf-8"), "codex"))
        self.assertIsNone(installer._parse_manifest_bytes(constant.encode("utf-8"), "codex"))

    def test_backup_collision_never_clobbers_user_data(self) -> None:
        with tempfile.TemporaryDirectory() as home_value:
            home = Path(home_value)
            preview = self._make_update("cursor", home)
            assert preview.backup_reservation is not None
            preview.backup_reservation.mkdir(parents=True)
            collision = preview.backup_reservation / "user-owned.txt"
            collision.write_text("do not overwrite\n", encoding="utf-8")
            target_before = self._tree_snapshot(preview.target)

            with self.assertRaisesRegex(OSError, "changed after preview"):
                apply_install(preview, preview.plan_token or "")

            self.assertEqual(collision.read_text(encoding="utf-8"), "do not overwrite\n")
            self.assertEqual(self._tree_snapshot(preview.target), target_before)

    def test_uninstall_collision_appearing_after_freshness_check_is_not_removed(self) -> None:
        with tempfile.TemporaryDirectory() as home_value:
            home = Path(home_value)
            self._install("codex", home)
            preview = plan_uninstall("codex", home=home)
            assert preview.backup_reservation is not None
            reservation = preview.backup_reservation
            real_anchor = installer._anchor_user_directory
            injected = False

            def inject_collision(
                supplied_home: Path,
                directory: Path,
                *,
                create: bool,
            ) -> installer._AnchoredUserDirectory | None:
                nonlocal injected
                anchor = real_anchor(supplied_home, directory, create=create)
                if directory == reservation.parent and not injected:
                    reservation.mkdir()
                    injected = True
                return anchor

            with (
                mock.patch.object(
                    installer,
                    "_anchor_user_directory",
                    side_effect=inject_collision,
                ),
                self.assertRaisesRegex(OSError, "private cleanup state could not be confirmed"),
            ):
                apply_uninstall(preview, preview.plan_token or "")

            self.assertTrue(reservation.is_dir())
            self.assertTrue(preview.target.is_dir())

    def test_cleanup_never_removes_a_replacement_for_a_created_ancestor(self) -> None:
        with tempfile.TemporaryDirectory() as home_value:
            home = Path(home_value).resolve()
            anchor = installer._anchor_user_directory(
                home,
                home / ".agents" / "skills",
                create=True,
            )
            assert anchor is not None
            original = home / "original-agents"
            (home / ".agents").rename(original)
            replacement = home / ".agents"
            replacement.mkdir()

            try:
                anchor.cleanup_created()
            finally:
                anchor.close()

            self.assertTrue(replacement.is_dir())

    def test_partial_directory_anchor_failure_cleans_only_its_created_entry(self) -> None:
        with tempfile.TemporaryDirectory() as home_value:
            home = Path(home_value).resolve()
            parent_fd = installer._open_absolute_directory(home)
            real_open = installer.os.open

            def fail_created_open(
                path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
                flags: int,
                mode: int = 0o777,
                *,
                dir_fd: int | None = None,
            ) -> int:
                if os.fsdecode(path) == "private-probe" and dir_fd == parent_fd:
                    raise OSError("synthetic open failure")
                return real_open(path, flags, mode, dir_fd=dir_fd)

            try:
                with (
                    mock.patch.object(installer.os, "open", side_effect=fail_created_open),
                    self.assertRaisesRegex(OSError, "synthetic open failure"),
                ):
                    installer._create_and_open_directory_at(parent_fd, "private-probe")
            finally:
                os.close(parent_fd)

            self.assertFalse((home / "private-probe").exists())

    def test_interrupt_after_mkdir_before_identity_reports_unconfirmed_residue(self) -> None:
        with tempfile.TemporaryDirectory() as home_value:
            home = Path(home_value).resolve()
            parent_fd = installer._open_absolute_directory(home)
            real_mkdir = installer.os.mkdir

            def create_then_interrupt(
                path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
                mode: int = 0o777,
                *,
                dir_fd: int | None = None,
            ) -> None:
                real_mkdir(path, mode, dir_fd=dir_fd)
                raise KeyboardInterrupt("synthetic interruption after mkdir")

            try:
                with (
                    mock.patch.object(installer.os, "mkdir", side_effect=create_then_interrupt),
                    self.assertRaisesRegex(
                        OSError,
                        "unconfirmed private directory paths may remain",
                    ),
                ):
                    installer._create_and_open_directory_at(parent_fd, "private-probe")
            finally:
                os.close(parent_fd)

            self.assertTrue((home / "private-probe").is_dir())

    def test_interrupt_after_identity_before_open_cleans_created_directory(self) -> None:
        with tempfile.TemporaryDirectory() as home_value:
            home = Path(home_value).resolve()
            parent_fd = installer._open_absolute_directory(home)
            real_open = installer.os.open

            def interrupt_created_open(
                path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
                flags: int,
                mode: int = 0o777,
                *,
                dir_fd: int | None = None,
            ) -> int:
                if os.fsdecode(path) == "private-probe" and dir_fd == parent_fd:
                    raise KeyboardInterrupt("synthetic interruption before open")
                return real_open(path, flags, mode, dir_fd=dir_fd)

            try:
                with (
                    mock.patch.object(installer.os, "open", side_effect=interrupt_created_open),
                    self.assertRaises(KeyboardInterrupt),
                ):
                    installer._create_and_open_directory_at(parent_fd, "private-probe")
            finally:
                os.close(parent_fd)

            self.assertFalse((home / "private-probe").exists())

    def test_multi_ancestor_interruption_reports_any_unconfirmed_paths(self) -> None:
        with tempfile.TemporaryDirectory() as home_value:
            home = Path(home_value).resolve()
            real_stat = installer.os.stat
            interrupted = False

            def interrupt_second_identity(
                path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
                *,
                dir_fd: int | None = None,
                follow_symlinks: bool = True,
            ) -> os.stat_result:
                nonlocal interrupted
                if os.fsdecode(path) == "skills" and not follow_symlinks and not interrupted:
                    interrupted = True
                    raise KeyboardInterrupt("synthetic interruption before second identity")
                return real_stat(path, dir_fd=dir_fd, follow_symlinks=follow_symlinks)

            with (
                mock.patch.object(installer.os, "stat", side_effect=interrupt_second_identity),
                mock.patch.object(installer, "_secure_mutation_supported", return_value=True),
                self.assertRaisesRegex(
                    OSError,
                    "private directory paths may remain",
                ),
            ):
                installer._anchor_user_directory(
                    home,
                    home / ".agents" / "skills",
                    create=True,
                )

            self.assertTrue((home / ".agents" / "skills").is_dir())

    def test_backup_collision_search_is_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as home_value:
            home = Path(home_value).resolve()
            backup_parent = home / ".agent-docs-doctor" / "backups" / "codex"
            backup_parent.mkdir(parents=True)
            stem = f"{installer.SKILL_NAME}-0.1.0-{'a' * 16}"
            (backup_parent / stem).mkdir()
            (backup_parent / f"{stem}-2").mkdir()
            with (
                mock.patch.object(installer, "MAX_BACKUP_COLLISIONS", 2),
                self.assertRaisesRegex(OSError, "too many backup collisions"),
            ):
                installer._backup_plan(home, "codex", "a" * 64, "0.1.0")

    def test_target_state_entry_and_depth_scans_are_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            target = Path(value) / "target"
            target.mkdir()
            (target / "one").write_text("one\n", encoding="utf-8")
            (target / "two").write_text("two\n", encoding="utf-8")
            with (
                mock.patch.object(installer, "MAX_TARGET_ENTRIES", 2),
                self.assertRaisesRegex(OSError, "too many entries"),
            ):
                installer._target_state_sha256(target)

    def test_same_size_extra_change_with_restored_mtime_invalidates_preview(self) -> None:
        with tempfile.TemporaryDirectory() as home_value:
            home = Path(home_value)
            installed = self._install("codex", home)
            extra = installed.target / "user-extra.txt"
            extra.write_bytes(b"one\n")
            preview = plan_uninstall("codex", home=home)
            before = extra.stat()
            extra.write_bytes(b"two\n")
            os.utime(extra, ns=(before.st_atime_ns, before.st_mtime_ns))

            with self.assertRaisesRegex(OSError, "changed after preview"):
                apply_uninstall(preview, preview.plan_token or "")
            self.assertEqual(extra.read_bytes(), b"two\n")

        with tempfile.TemporaryDirectory() as value:
            target = Path(value) / "target"
            nested = target / "one" / "two"
            nested.mkdir(parents=True)
            with (
                mock.patch.object(installer, "MAX_TARGET_DEPTH", 1),
                self.assertRaisesRegex(OSError, "depth safety limit"),
            ):
                installer._target_state_sha256(target)

    def test_failed_update_rolls_back_and_cleans_staging_and_reservation(self) -> None:
        with tempfile.TemporaryDirectory() as home_value:
            home = Path(home_value)
            preview = self._make_update("codex", home)
            target_before = self._tree_snapshot(preview.target)
            real_rename = installer._rename_noreplace_at
            calls = 0

            def fail_activation(
                source_parent_fd: int,
                source_name: str,
                destination_parent_fd: int,
                destination_name: str,
            ) -> None:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("synthetic activation failure")
                real_rename(
                    source_parent_fd,
                    source_name,
                    destination_parent_fd,
                    destination_name,
                )

            with (
                mock.patch.object(
                    installer,
                    "_rename_noreplace_at",
                    side_effect=fail_activation,
                ),
                self.assertRaisesRegex(OSError, "synthetic activation failure"),
            ):
                apply_install(preview, preview.plan_token or "")

            self.assertEqual(self._tree_snapshot(preview.target), target_before)
            assert preview.backup_reservation is not None
            self.assertFalse(preview.backup_reservation.exists())
            leftovers = list(preview.target.parent.glob(".agent-docs-doctor-install-*"))
            self.assertEqual(leftovers, [])

    def test_keyboard_interrupt_before_existing_move_preserves_prior_install(self) -> None:
        with tempfile.TemporaryDirectory() as home_value:
            home = Path(home_value)
            preview = self._make_update("codex", home)
            target_before = self._tree_snapshot(preview.target)

            with (
                mock.patch.object(
                    installer,
                    "_rename_noreplace_at",
                    side_effect=KeyboardInterrupt("synthetic interruption before move"),
                ),
                self.assertRaises(KeyboardInterrupt),
            ):
                apply_install(preview, preview.plan_token or "")

            self.assertEqual(self._tree_snapshot(preview.target), target_before)
            assert preview.backup_reservation is not None
            self.assertFalse(preview.backup_reservation.exists())
            self.assertEqual(
                list(preview.target.parent.glob(".agent-docs-doctor-install-*")),
                [],
            )

    def test_keyboard_interrupt_after_existing_move_restores_prior_install(self) -> None:
        with tempfile.TemporaryDirectory() as home_value:
            home = Path(home_value)
            preview = self._make_update("claude", home)
            target_before = self._tree_snapshot(preview.target)
            real_rename = installer._rename_noreplace_at
            calls = 0

            def interrupt_after_existing_move(
                source_parent_fd: int,
                source_name: str,
                destination_parent_fd: int,
                destination_name: str,
            ) -> None:
                nonlocal calls
                calls += 1
                real_rename(
                    source_parent_fd,
                    source_name,
                    destination_parent_fd,
                    destination_name,
                )
                if calls == 1:
                    raise KeyboardInterrupt("synthetic interruption after existing move")

            with (
                mock.patch.object(
                    installer,
                    "_rename_noreplace_at",
                    side_effect=interrupt_after_existing_move,
                ),
                self.assertRaises(KeyboardInterrupt),
            ):
                apply_install(preview, preview.plan_token or "")

            self.assertEqual(self._tree_snapshot(preview.target), target_before)
            assert preview.backup_reservation is not None
            self.assertFalse(preview.backup_reservation.exists())
            self.assertEqual(
                list(preview.target.parent.glob(".agent-docs-doctor-install-*")),
                [],
            )

    def test_keyboard_interrupt_after_activation_retains_new_target_and_prior_backup(self) -> None:
        with tempfile.TemporaryDirectory() as home_value:
            home = Path(home_value)
            preview = self._make_update("cursor", home)
            target_before = self._tree_snapshot(preview.target)
            real_rename = installer._rename_noreplace_at
            calls = 0

            def interrupt_after_activation(
                source_parent_fd: int,
                source_name: str,
                destination_parent_fd: int,
                destination_name: str,
            ) -> None:
                nonlocal calls
                calls += 1
                real_rename(
                    source_parent_fd,
                    source_name,
                    destination_parent_fd,
                    destination_name,
                )
                if calls == 2:
                    raise KeyboardInterrupt("synthetic interruption after activation")

            with (
                mock.patch.object(
                    installer,
                    "_rename_noreplace_at",
                    side_effect=interrupt_after_activation,
                ),
                self.assertRaises(KeyboardInterrupt),
            ):
                apply_install(preview, preview.plan_token or "")

            self.assertTrue(preview.target.is_dir())
            installed_manifest = json.loads((preview.target / MANIFEST_NAME).read_text(encoding="utf-8"))
            self.assertEqual(installed_manifest["version"], installer.__version__)
            assert preview.backup is not None
            self.assertEqual(self._tree_snapshot(preview.backup), target_before)
            self.assertEqual(
                list(preview.target.parent.glob(".agent-docs-doctor-install-*")),
                [],
            )

    def test_staging_cleanup_failure_is_reported_after_target_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as home_value:
            home = Path(home_value)
            preview = plan_install("codex", home=home)
            with (
                mock.patch.object(
                    installer,
                    "_write_staged_skill_fd",
                    side_effect=OSError("synthetic staging failure"),
                ),
                mock.patch.object(
                    installer,
                    "_cleanup_private_directory_at",
                    side_effect=OSError("synthetic cleanup failure"),
                ),
                self.assertRaisesRegex(OSError, "private failure cleanup could not be confirmed"),
            ):
                apply_install(preview, preview.plan_token or "")

            self.assertFalse(preview.target.exists())
            self.assertNotEqual(
                list((home / ".agents" / "skills").glob(".agent-docs-doctor-install-*")),
                [],
            )

    def test_failed_initial_staging_cleans_created_directories(self) -> None:
        with tempfile.TemporaryDirectory() as home_value:
            home = Path(home_value)
            preview = plan_install("codex", home=home)
            with (
                mock.patch.object(
                    installer,
                    "_write_staged_skill_fd",
                    side_effect=OSError("synthetic staging failure"),
                ),
                self.assertRaisesRegex(OSError, "synthetic staging failure"),
            ):
                apply_install(preview, preview.plan_token or "")

            self.assertFalse((home / ".agents").exists())
            self.assertEqual(
                list(home.rglob(".agent-docs-doctor-install-*")),
                [],
            )

    def test_rollback_failure_preserves_prior_tree_at_previewed_backup(self) -> None:
        with tempfile.TemporaryDirectory() as home_value:
            home = Path(home_value)
            preview = self._make_update("claude", home)
            target_before = self._tree_snapshot(preview.target)
            real_rename = installer._rename_noreplace_at
            calls = 0

            def fail_activation_and_rollback(
                source_parent_fd: int,
                source_name: str,
                destination_parent_fd: int,
                destination_name: str,
            ) -> None:
                nonlocal calls
                calls += 1
                if calls in {2, 3}:
                    raise OSError("synthetic private move failure")
                real_rename(
                    source_parent_fd,
                    source_name,
                    destination_parent_fd,
                    destination_name,
                )

            with (
                mock.patch.object(
                    installer,
                    "_rename_noreplace_at",
                    side_effect=fail_activation_and_rollback,
                ),
                self.assertRaisesRegex(OSError, "recoverable at the previewed backup") as captured,
            ):
                apply_install(preview, preview.plan_token or "")

            self.assertNotIn(str(home), str(captured.exception))
            self.assertFalse(preview.target.exists())
            assert preview.backup is not None
            self.assertEqual(self._tree_snapshot(preview.backup), target_before)
            self.assertEqual(
                list(preview.target.parent.glob(".agent-docs-doctor-install-*")),
                [],
            )

    def test_uninstall_backup_is_reversible_and_recovery_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as home_value:
            home = Path(home_value)
            installed = self._install("cursor", home)
            extra = installed.target / "user-extra.txt"
            extra.write_text("preserved in backup\n", encoding="utf-8")
            preview = plan_uninstall("cursor", home=home)
            public_plan = plan_as_dict(preview)

            self.assertEqual(public_plan["target"], "~/.cursor/skills/agent-docs-doctor")
            self.assertTrue(str(public_plan["backup"]).startswith("~/.agent-docs-doctor/backups/"))
            self.assertEqual(public_plan["plan_token"], preview.plan_token)
            self.assertNotIn(str(home), json.dumps(public_plan))

            applied = apply_uninstall(preview, preview.plan_token or "")
            assert applied.backup is not None
            self.assertFalse(applied.target.exists())
            self.assertEqual(
                (applied.backup / "user-extra.txt").read_text(encoding="utf-8"),
                "preserved in backup\n",
            )
            recovery = plan_as_dict(applied)["recovery"]
            self.assertEqual(recovery["from"], plan_as_dict(applied)["backup"])
            self.assertEqual(recovery["to"], "~/.cursor/skills/agent-docs-doctor")
            self.assertIn("target is absent", recovery["condition"])

    def test_keyboard_interrupt_before_uninstall_move_preserves_target_and_cleans_reservation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as home_value:
            home = Path(home_value)
            installed = self._install("codex", home)
            target_before = self._tree_snapshot(installed.target)
            preview = plan_uninstall("codex", home=home)

            with (
                mock.patch.object(
                    installer,
                    "_rename_noreplace_at",
                    side_effect=KeyboardInterrupt("synthetic uninstall interruption"),
                ),
                self.assertRaises(KeyboardInterrupt),
            ):
                apply_uninstall(preview, preview.plan_token or "")

            self.assertEqual(self._tree_snapshot(preview.target), target_before)
            assert preview.backup_reservation is not None
            self.assertFalse(preview.backup_reservation.exists())

    def test_keyboard_interrupt_after_uninstall_move_retains_reversible_backup(self) -> None:
        with tempfile.TemporaryDirectory() as home_value:
            home = Path(home_value)
            installed = self._install("claude", home)
            target_before = self._tree_snapshot(installed.target)
            preview = plan_uninstall("claude", home=home)
            real_rename = installer._rename_noreplace_at

            def interrupt_after_uninstall_move(
                source_parent_fd: int,
                source_name: str,
                destination_parent_fd: int,
                destination_name: str,
            ) -> None:
                real_rename(
                    source_parent_fd,
                    source_name,
                    destination_parent_fd,
                    destination_name,
                )
                raise KeyboardInterrupt("synthetic interruption after uninstall move")

            with (
                mock.patch.object(
                    installer,
                    "_rename_noreplace_at",
                    side_effect=interrupt_after_uninstall_move,
                ),
                self.assertRaises(KeyboardInterrupt),
            ):
                apply_uninstall(preview, preview.plan_token or "")

            self.assertFalse(preview.target.exists())
            assert preview.backup is not None
            self.assertEqual(self._tree_snapshot(preview.backup), target_before)

    def test_post_activation_verification_failure_reports_committed_state(self) -> None:
        with tempfile.TemporaryDirectory() as home_value:
            home = Path(home_value)
            preview = plan_install("codex", home=home)
            with mock.patch.object(
                installer,
                "_read_target_manifest_at",
                return_value=(None, None),
            ):
                applied = apply_install(preview, preview.plan_token or "")

            self.assertEqual(applied.state, "applied-verification-failed")
            self.assertIn("Activation committed", applied.message)
            self.assertTrue(applied.target.exists())

    def test_apply_fails_closed_when_secure_relative_mutation_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as home_value:
            home = Path(home_value)
            preview = plan_install("codex", home=home)
            with (
                mock.patch.object(installer, "_secure_mutation_supported", return_value=False),
                self.assertRaisesRegex(OSError, "ancestor-relative atomic activation"),
            ):
                apply_install(preview, preview.plan_token or "")
            self.assertFalse(preview.target.exists())

    def test_target_state_never_opens_unmanaged_or_managed_extra_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as home_value:
            home = Path(home_value)
            unmanaged_target = target_for("codex", home)
            unmanaged_target.mkdir(parents=True)
            unmanaged_extra = unmanaged_target / "synthetic-secret.txt"
            unmanaged_extra.write_text("must not be opened\n", encoding="utf-8")
            (unmanaged_target / MANIFEST_NAME).write_text(
                json.dumps(
                    {
                        "format": "agent-docs-doctor.skill-install.v1",
                        "owner": "agent-docs-doctor",
                        "version": "0.0.1",
                        "client": "codex",
                        "files": {"synthetic-secret.txt": "0" * 64},
                    }
                ),
                encoding="utf-8",
            )
            real_reader = installer._read_regular_bytes
            opened: list[Path] = []

            def guarded_reader(path: Path, *, limit: int) -> bytes:
                opened.append(path)
                if path == unmanaged_extra:
                    raise AssertionError("unmanaged content was read")
                return real_reader(path, limit=limit)

            with mock.patch.object(
                installer,
                "_read_regular_bytes",
                side_effect=guarded_reader,
            ):
                preview = plan_install("codex", home=home)
            self.assertEqual(preview.state, "blocked-unmanaged")
            self.assertNotIn(unmanaged_extra, opened)

        with tempfile.TemporaryDirectory() as home_value:
            home = Path(home_value)
            installed = self._install("codex", home)
            managed_extra = installed.target / "synthetic-secret.txt"
            managed_extra.write_text("must not be opened\n", encoding="utf-8")
            opened = []

            def guarded_managed_reader(path: Path, *, limit: int) -> bytes:
                opened.append(path)
                if path == managed_extra:
                    raise AssertionError("managed extra content was read")
                return real_reader(path, limit=limit)

            real_open = installer.os.open

            def guarded_open(
                path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
                flags: int,
                mode: int = 0o777,
                *,
                dir_fd: int | None = None,
            ) -> int:
                if dir_fd is not None and os.fsdecode(path) == managed_extra.name:
                    raise AssertionError("managed extra content was opened")
                return real_open(path, flags, mode, dir_fd=dir_fd)

            with (
                mock.patch.object(
                    installer,
                    "_read_regular_bytes",
                    side_effect=guarded_managed_reader,
                ),
                mock.patch.object(installer.os, "open", side_effect=guarded_open),
            ):
                preview = plan_uninstall("codex", home=home)
            self.assertEqual(preview.state, "ready")
            self.assertNotIn(managed_extra, opened)

    def test_error_and_plan_output_do_not_disclose_absolute_home(self) -> None:
        with (
            tempfile.TemporaryDirectory() as home_value,
            tempfile.TemporaryDirectory() as external_value,
        ):
            home = Path(home_value)
            target = target_for("codex", home)
            self.assertNotIn(str(home), json.dumps(plan_as_dict(plan_install("codex", home=home))))
            (home / ".agents").symlink_to(
                Path(external_value),
                target_is_directory=True,
            )
            with self.assertRaises(OSError) as captured:
                target_for("codex", home)
            self.assertNotIn(str(home), str(captured.exception))
            self.assertFalse(target.exists())

        with tempfile.TemporaryDirectory() as home_value:
            home = Path(home_value)
            preview = plan_install("codex", home=home)
            with (
                mock.patch.object(
                    installer,
                    "_create_private_directory_at",
                    side_effect=OSError(f"private failure at {home}"),
                ),
                self.assertRaises(OSError) as captured,
            ):
                apply_install(preview, preview.plan_token or "")
            self.assertNotIn(str(home), str(captured.exception))
            self.assertFalse((home / ".agents").exists())


if __name__ == "__main__":
    unittest.main()
