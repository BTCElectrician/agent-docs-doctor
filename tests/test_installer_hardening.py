from __future__ import annotations

import base64
import hashlib
import json
import os
import stat
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
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

    @staticmethod
    def _patch_bundled_source(source: Path):
        source_stat = source.lstat()
        return mock.patch.object(
            installer,
            "_bundled_source",
            return_value=installer._BundledSource(
                source,
                root_identity=(source_stat.st_dev, source_stat.st_ino),
            ),
        )

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
            with self._patch_bundled_source(source):
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
            site_packages = root / "other" / "site-packages"
            other_code = site_packages / "agent_docs_doctor" / "installer.py"
            other_code.parent.mkdir(parents=True)
            other_code.write_text("# unrelated code\n", encoding="utf-8")
            stale_skill = self._synthetic_source(root / "other" / "share" / "agent-docs-doctor" / "skill")
            dist_info = site_packages / "agent_docs_doctor-0.3.0.dist-info"
            dist_info.mkdir()
            rows = [
                self._record_row("agent_docs_doctor/installer.py", other_code),
                *[
                    self._record_row(
                        f"../share/agent-docs-doctor/skill/{relative}",
                        stale_skill / relative,
                    )
                    for relative in installer.SOURCE_RELATIVE_PATHS
                ],
            ]
            (dist_info / "RECORD").write_text("".join(rows), encoding="utf-8")

            class MismatchedDistribution:
                _path = dist_info

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

    @staticmethod
    def _record_row(archive_path: str, located: Path, *, digest: str | None = None) -> str:
        raw = located.read_bytes()
        record_digest = digest or (
            "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b"=").decode("ascii")
        )
        return f"{archive_path},{record_digest},{len(raw)}\n"

    def test_distribution_record_binds_copied_resources_and_rejects_hardlinks(self) -> None:
        with (
            tempfile.TemporaryDirectory() as root_value,
            tempfile.TemporaryDirectory() as home_value,
        ):
            root = Path(root_value)
            home = Path(home_value)
            source = self._synthetic_source(root / "share" / "agent-docs-doctor" / "skill")
            site_packages = root / "site-packages"
            executing = site_packages / "agent_docs_doctor" / "installer.py"
            executing.parent.mkdir(parents=True)
            executing.write_text("# active code\n", encoding="utf-8")
            dist_info = site_packages / "agent_docs_doctor-0.3.0.dist-info"
            dist_info.mkdir()

            def record_rows(
                *,
                code_digest: str | None = None,
                first_digest: str | None = None,
            ) -> list[str]:
                return [
                    self._record_row(
                        "agent_docs_doctor/installer.py",
                        executing,
                        digest=code_digest,
                    ),
                    *[
                        self._record_row(
                            f"../share/agent-docs-doctor/skill/{relative}",
                            source / relative,
                            digest=first_digest if index == 0 else None,
                        )
                        for index, relative in enumerate(installer.SOURCE_RELATIVE_PATHS)
                    ],
                ]

            record_path = dist_info / "RECORD"
            original_rows = record_rows()
            record_path.write_text("".join(original_rows), encoding="utf-8")

            class FakeDistribution:
                _path = dist_info

            distribution = FakeDistribution()
            distribution_lookup = mock.Mock(return_value=distribution)
            with (
                mock.patch.object(installer, "__file__", os.fspath(executing)),
                mock.patch.object(
                    installer.metadata,
                    "distribution",
                    distribution_lookup,
                ),
            ):
                preview = plan_install("codex", home=home)
                self.assertEqual(preview.state, "ready")
                self.assertIsNotNone(preview.plan_token)
                distribution_lookup.assert_called_once_with("agent-docs-doctor")

                invalid_code_rows = original_rows.copy()
                invalid_code_rows[0] = "agent_docs_doctor/installer.py,,\n"
                record_path.write_text("".join(invalid_code_rows), encoding="utf-8")
                with self.assertRaisesRegex(OSError, "invalid executing-module record"):
                    plan_install("codex", home=home)

                record_path.write_text(
                    "".join(record_rows(code_digest=f"sha256={'A' * 43}")),
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(OSError, "executing installer"):
                    plan_install("codex", home=home)

                record_path.write_text(
                    "".join(record_rows(first_digest=f"sha256={'A' * 43}")),
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(OSError, "distribution record"):
                    plan_install("codex", home=home)

                record_path.write_text("".join(original_rows[:-1]), encoding="utf-8")
                with self.assertRaisesRegex(OSError, "records are incomplete"):
                    plan_install("codex", home=home)

                record_path.write_text(
                    "".join(
                        [
                            *original_rows,
                            self._record_row(
                                "../share/agent-docs-doctor/skill/not-allowlisted.txt",
                                source / "not-allowlisted.txt",
                            ),
                        ]
                    ),
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(OSError, "unexpected bundled skill record"):
                    plan_install("codex", home=home)

                record_path.write_text("".join(original_rows), encoding="utf-8")
                alias = root / "private-hardlink-alias"
                os.link(source / "SKILL.md", alias)
                real_read = installer.os.read

                def reject_payload_read(descriptor: int, size: int) -> bytes:
                    descriptor_path = installer._descriptor_resolved_path(descriptor)
                    if (
                        descriptor_path is not None
                        and descriptor_path.resolve() == (source / "SKILL.md").resolve()
                    ):
                        raise AssertionError("hard-linked skill bytes were read")
                    return real_read(descriptor, size)

                with (
                    mock.patch.object(installer.os, "read", side_effect=reject_payload_read),
                    self.assertRaisesRegex(OSError, "hard-linked"),
                ):
                    plan_install("codex", home=home)

    def test_distribution_record_limits_fail_closed_before_resource_reads(self) -> None:
        with (
            tempfile.TemporaryDirectory() as root_value,
            tempfile.TemporaryDirectory() as home_value,
        ):
            root = Path(root_value)
            home = Path(home_value)
            site_packages = root / "site-packages"
            executing = site_packages / "agent_docs_doctor" / "installer.py"
            executing.parent.mkdir(parents=True)
            executing.write_text("# active code\n", encoding="utf-8")
            dist_info = site_packages / "agent_docs_doctor-0.3.0.dist-info"
            dist_info.mkdir()
            record_path = dist_info / "RECORD"
            record_path.write_text(
                "".join(self._record_row(f"entry-{index}.txt", executing) for index in range(3)),
                encoding="utf-8",
            )

            class FakeDistribution:
                _path = dist_info

            with (
                mock.patch.object(installer, "__file__", os.fspath(executing)),
                mock.patch.object(
                    installer.metadata,
                    "distribution",
                    return_value=FakeDistribution(),
                ),
                mock.patch.object(installer, "MAX_DISTRIBUTION_RECORDS", 2),
                self.assertRaisesRegex(OSError, "row limit"),
            ):
                plan_install("codex", home=home)

            with (
                mock.patch.object(installer, "__file__", os.fspath(executing)),
                mock.patch.object(
                    installer.metadata,
                    "distribution",
                    return_value=FakeDistribution(),
                ),
                mock.patch.object(installer, "MAX_DISTRIBUTION_RECORD_BYTES", 16),
                self.assertRaisesRegex(OSError, "oversized|safety limit"),
            ):
                plan_install("codex", home=home)

    def test_distribution_metadata_replacement_cannot_redirect_record_read(self) -> None:
        with (
            tempfile.TemporaryDirectory() as root_value,
            tempfile.TemporaryDirectory() as home_value,
        ):
            root = Path(root_value)
            home = Path(home_value)
            site_packages = root / "site-packages"
            executing = site_packages / "agent_docs_doctor" / "installer.py"
            executing.parent.mkdir(parents=True)
            executing.write_text("# active code\n", encoding="utf-8")
            dist_info = site_packages / "agent_docs_doctor-0.3.0.dist-info"
            dist_info.mkdir()
            (dist_info / "RECORD").write_text(
                self._record_row("agent_docs_doctor/installer.py", executing),
                encoding="utf-8",
            )

            class FakeDistribution:
                _path = dist_info

            original_dist_info = site_packages / "original.dist-info"
            resolved_dist_info = dist_info.resolve()
            pin_name = "_open_windows_directory_handle" if os.name == "nt" else "_open_absolute_directory"
            real_open_directory = getattr(installer, pin_name)
            swapped = False

            def replace_before_open(path: Path, *args: object) -> int:
                nonlocal swapped
                if path == resolved_dist_info and not swapped:
                    swapped = True
                    dist_info.rename(original_dist_info)
                    dist_info.mkdir()
                    (dist_info / "RECORD").write_text(
                        "synthetic-private-record-data\n",
                        encoding="utf-8",
                    )
                return real_open_directory(path, *args)

            with (
                mock.patch.object(installer, "__file__", os.fspath(executing)),
                mock.patch.object(
                    installer.metadata,
                    "distribution",
                    return_value=FakeDistribution(),
                ),
                mock.patch.object(
                    installer,
                    pin_name,
                    side_effect=replace_before_open,
                ),
                self.assertRaisesRegex(OSError, "metadata changed before|pinned safely"),
            ):
                plan_install("codex", home=home)
            self.assertTrue(swapped)

    def test_source_root_replacement_is_rejected_before_replacement_bytes_are_read(self) -> None:
        with (
            tempfile.TemporaryDirectory() as root_value,
            tempfile.TemporaryDirectory() as home_value,
        ):
            root = Path(root_value)
            home = Path(home_value)
            source = self._synthetic_source(root / "source")
            original_source = root / "source-original"
            resolved_source = source.resolve()
            pin_name = "_open_windows_directory_handle" if os.name == "nt" else "_open_absolute_directory"
            real_open_directory = getattr(installer, pin_name)
            real_read = installer.os.read
            swapped = False

            def replace_before_open(path: Path, *args: object) -> int:
                nonlocal swapped
                if path == resolved_source and not swapped:
                    swapped = True
                    source.rename(original_source)
                    replacement = self._synthetic_source(source)
                    (replacement / "SKILL.md").write_text(
                        "synthetic private replacement\n",
                        encoding="utf-8",
                    )
                return real_open_directory(path, *args)

            def reject_replacement_read(descriptor: int, size: int) -> bytes:
                descriptor_path = installer._descriptor_resolved_path(descriptor)
                if (
                    descriptor_path is not None
                    and descriptor_path.resolve() == (source / "SKILL.md").resolve()
                ):
                    raise AssertionError("replacement skill bytes were read")
                return real_read(descriptor, size)

            with (
                self._patch_bundled_source(source),
                mock.patch.object(
                    installer,
                    pin_name,
                    side_effect=replace_before_open,
                ),
                mock.patch.object(installer.os, "read", side_effect=reject_replacement_read),
                self.assertRaisesRegex(OSError, "root changed|pinned safely"),
            ):
                plan_install("codex", home=home)
            self.assertTrue(swapped)

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
            with self._patch_bundled_source(source):
                preview = plan_install("cursor", home=home)
                real_inventory = installer._bounded_child_names_fd
                inventory_calls = 0

                def swap_after_reference_inventory(fd: int, expected_count: int) -> set[str]:
                    nonlocal inventory_calls
                    names = real_inventory(fd, expected_count)
                    inventory_calls += 1
                    if inventory_calls == 2:
                        (source / "references").rename(source / "references-original")
                        (external / "references").rename(source / "references")
                    return names

                real_read = installer.os.read

                def reject_external_read(descriptor: int, size: int) -> bytes:
                    descriptor_path = installer._descriptor_resolved_path(descriptor)
                    if (
                        descriptor_path is not None
                        and descriptor_path.resolve() == (source / "references" / "AUDIT_RUBRIC.md").resolve()
                    ):
                        raise AssertionError("replacement directory bytes were read")
                    return real_read(descriptor, size)

                with (
                    mock.patch.object(
                        installer,
                        "_bounded_child_names_fd",
                        side_effect=swap_after_reference_inventory,
                    ),
                    mock.patch.object(installer.os, "read", side_effect=reject_external_read),
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
            with self._patch_bundled_source(source):
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

            def guarded_reader(
                path: Path,
                *,
                limit: int,
                reject_hardlinks: bool = True,
            ) -> bytes:
                opened.append(path)
                if path == unexpected:
                    raise AssertionError("unexpected reference content was read")
                return real_reader(
                    path,
                    limit=limit,
                    reject_hardlinks=reject_hardlinks,
                )

            with (
                self._patch_bundled_source(source),
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
                self._patch_bundled_source(source),
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

            def guarded_reader(
                path: Path,
                *,
                limit: int,
                reject_hardlinks: bool = True,
            ) -> bytes:
                opened.append(path)
                if path == unmanaged_extra:
                    raise AssertionError("unmanaged content was read")
                return real_reader(
                    path,
                    limit=limit,
                    reject_hardlinks=reject_hardlinks,
                )

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

            def guarded_managed_reader(
                path: Path,
                *,
                limit: int,
                reject_hardlinks: bool = True,
            ) -> bytes:
                opened.append(path)
                if path == managed_extra:
                    raise AssertionError("managed extra content was read")
                return real_reader(
                    path,
                    limit=limit,
                    reject_hardlinks=reject_hardlinks,
                )

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


@unittest.skipUnless(os.name == "nt", "Windows native pinning test")
class WindowsInstallerPreviewTests(unittest.TestCase):
    def test_native_handle_abi_and_root_replacement_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as root_value:
            root = Path(root_value)
            pinned = root / "pinned"
            pinned.mkdir()
            pinned_stat = pinned.lstat()
            handle = installer._open_windows_directory_handle(
                pinned,
                (pinned_stat.st_dev, pinned_stat.st_ino),
            )
            renamed = root / "renamed"
            renamed_while_open = False
            try:
                resolved = installer._windows_handle_resolved_path(handle)
                self.assertIsNotNone(resolved)
                if resolved is None:
                    self.fail("pinned Windows directory path was unavailable")
                self.assertTrue(os.path.samefile(resolved, pinned))
                self.assertTrue(
                    installer._windows_directory_handle_unchanged(
                        handle,
                        pinned,
                        (pinned_stat.st_dev, pinned_stat.st_ino),
                    )
                )
                try:
                    pinned.rename(renamed)
                except OSError:
                    pass
                else:
                    renamed_while_open = True
                    pinned.mkdir()
                    self.assertFalse(
                        installer._windows_directory_handle_unchanged(
                            handle,
                            pinned,
                            (pinned_stat.st_dev, pinned_stat.st_ino),
                        )
                    )
            finally:
                installer._close_windows_handle(handle)
            if renamed_while_open:
                pinned.rmdir()
                renamed.rename(pinned)
            else:
                pinned.rename(renamed)
                renamed.rename(pinned)

            pinned_file = pinned / "payload.txt"
            pinned_file.write_text("public payload\n", encoding="utf-8")
            file_descriptor = installer._open_windows_file_descriptor(
                pinned_file,
                pinned_file.lstat(),
            )
            try:
                self.assertFalse(os.get_inheritable(file_descriptor))
                with self.assertRaises(OSError):
                    pinned_file.write_text("changed\n", encoding="utf-8")
                self.assertEqual(os.read(file_descriptor, 1024), b"public payload\n")
            finally:
                os.close(file_descriptor)

        with (
            tempfile.TemporaryDirectory() as root_value,
            tempfile.TemporaryDirectory() as home_value,
        ):
            root = Path(root_value)
            home = Path(home_value)
            source = InstallerHardeningTests._synthetic_source(root / "source")
            original_source = root / "source-original"
            resolved_source = source.resolve()
            real_pin = installer._open_windows_directory_handle
            real_read = installer.os.read
            swapped = False

            def replace_before_pin(
                path: Path,
                identity: tuple[int, int],
            ) -> int:
                nonlocal swapped
                if path == resolved_source and not swapped:
                    swapped = True
                    source.rename(original_source)
                    replacement = InstallerHardeningTests._synthetic_source(source)
                    (replacement / "SKILL.md").write_text(
                        "synthetic private replacement\n",
                        encoding="utf-8",
                    )
                return real_pin(path, identity)

            def reject_replacement_read(descriptor: int, size: int) -> bytes:
                descriptor_path = installer._descriptor_resolved_path(descriptor)
                if (
                    descriptor_path is not None
                    and descriptor_path.resolve() == (source / "SKILL.md").resolve()
                ):
                    raise AssertionError("replacement skill bytes were read")
                return real_read(descriptor, size)

            with (
                InstallerHardeningTests._patch_bundled_source(source),
                mock.patch.object(
                    installer,
                    "_open_windows_directory_handle",
                    side_effect=replace_before_pin,
                ),
                mock.patch.object(installer.os, "read", side_effect=reject_replacement_read),
                self.assertRaisesRegex(OSError, "pinned safely"),
            ):
                plan_install("codex", home=home)
            self.assertTrue(swapped)


if __name__ == "__main__":
    unittest.main()
