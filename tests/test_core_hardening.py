from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import agent_docs_doctor.core as core  # noqa: E402
from agent_docs_doctor.presentation import audit_text  # noqa: E402


def write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_secret_named_hardlink_alias_is_never_read_or_emitted() -> None:
    with tempfile.TemporaryDirectory() as value:
        root = Path(value)
        secret = write(
            root,
            ".env",
            "---\nprivate-token: hardlink-secret-sentinel\n---\nprivate body\n",
        )
        alias = root / "AGENTS.md"
        try:
            os.link(secret, alias)
        except OSError as exc:
            pytest.skip(f"hard links unavailable: {exc.__class__.__name__}")

        report = core.build_audit(root)

    rendered = core.dump_json(report)
    assert report["inventory"]["files"] == []
    assert report["inventory"]["coverage"]["status"] == "partial"
    assert "hardlink-secret-sentinel" not in rendered
    assert any("hard-linked" in item["reason"] for item in report["inventory"]["skipped"])


def test_emitted_metadata_contains_signals_not_arbitrary_values() -> None:
    with tempfile.TemporaryDirectory() as value:
        root = Path(value)
        write(
            root,
            ".cursor/rules/safe.mdc",
            "\n".join(
                (
                    "---",
                    "alwaysApply: true",
                    "description: metadata-private-sentinel",
                    "role: metadata-private-role",
                    "privateKey: metadata-private-value",
                    "---",
                    "# Safe body",
                    "",
                )
            ),
        )
        report = core.build_audit(root)

    entry = report["inventory"]["files"][0]
    assert entry["metadata"] == {"alwaysApply": True, "has_description": True}
    assert entry["role"] == "procedure"
    rendered = core.dump_json(report)
    assert "metadata-private-sentinel" not in rendered
    assert "metadata-private-role" not in rendered
    assert "metadata-private-value" not in rendered


def test_relative_reference_outside_root_is_hash_only() -> None:
    with tempfile.TemporaryDirectory() as value:
        root = Path(value)
        private_target = "../../Clients/private-customer/contract.md"
        write(root, "AGENTS.md", f"# Rules\n\n[private]({private_target})\n")
        with patch.object(Path, "exists", side_effect=AssertionError("out-of-root existence probe")):
            report = core.build_audit(root)

    reference = report["inventory"]["files"][0]["references"][0]
    assert reference["target"] == "<out-of-root-path>"
    assert reference["target_kind"] == "out-of-root"
    assert len(reference["target_sha256"]) == 64
    assert private_target not in core.dump_json(report)


def test_file_urls_are_retained_as_sanitized_private_references() -> None:
    private_targets = (
        f"file:///{'Users'}/private/customer.md",
        "file://private-host/share/customer.md",
    )
    with tempfile.TemporaryDirectory() as value:
        root = Path(value)
        links = " ".join(f"[private]({target})" for target in private_targets)
        write(root, "AGENTS.md", f"# Rules\n\n{links}\n")
        report = core.build_audit(root)

    references = report["inventory"]["files"][0]["references"]
    assert len(references) == 2
    assert all(item["target"] == "<absolute-filesystem-path>" for item in references)
    assert all(item["target_kind"] == "absolute-filesystem" for item in references)
    assert all(item["resolution"] == "out-of-scope" for item in references)
    rendered = core.dump_json(report)
    assert all(target not in rendered for target in private_targets)


def test_unc_and_secret_like_references_are_privacy_minimized_without_existence_probes() -> None:
    with tempfile.TemporaryDirectory() as value:
        root = Path(value)
        write(root, ".env", "reference-private-sentinel\n")
        alias = root / "secret-alias.md"
        try:
            alias.symlink_to(root / ".env")
        except OSError as exc:
            pytest.skip(f"symlinks unavailable: {exc.__class__.__name__}")
        write(
            root,
            "AGENTS.md",
            "# Rules\n\n[direct](.env) [alias](secret-alias.md) [unc](//private-host/share/file.md)\n",
        )
        original_exists = Path.exists

        def guarded_exists(path: Path) -> bool:
            if path.name in {".env", "secret-alias.md"}:
                raise AssertionError("secret-like reference existence was probed")
            return original_exists(path)

        with patch.object(Path, "exists", guarded_exists):
            report = core.build_audit(root)

    references = report["inventory"]["files"][0]["references"]
    secret_references = references[:2]
    assert all(item["target"] == "<secret-like-path>" for item in secret_references)
    assert all(item["target_kind"] == "secret-like" for item in secret_references)
    assert all(item["resolution"] == "excluded-secret" for item in secret_references)
    assert all(item["exists"] is None for item in secret_references)
    assert references[2]["target"] == "<absolute-filesystem-path>"
    assert references[2]["target_kind"] == "absolute-filesystem"
    rendered = core.dump_json(report)
    assert "reference-private-sentinel" not in rendered
    assert "private-host" not in rendered


def test_auditor_source_tree_is_not_silently_excluded_from_coverage() -> None:
    with tempfile.TemporaryDirectory() as value:
        root = Path(value)
        write(root, "AGENTS.md", "# Root rules\n")
        write(root, "src/AGENTS.md", "# Nested source rules\n")

        report = core.build_audit(root)

    paths = {item["path"] for item in report["inventory"]["files"]}
    assert paths == {"AGENTS.md", "src/AGENTS.md"}
    assert not any(
        item["reason"] == "auditor's installed package excluded" for item in report["inventory"]["skipped"]
    )


def test_custom_ignored_authority_and_directory_make_coverage_partial() -> None:
    with tempfile.TemporaryDirectory() as value:
        root = Path(value)
        write(root, ".gitignore", "private/\nHIDDEN_STATUS.md\n")
        write(root, "private/AGENTS.md", "ignored-directory-private-sentinel\n")
        write(root, "HIDDEN_STATUS.md", "ignored-file-private-sentinel\n")
        report = core.build_audit(root)

    inventory = report["inventory"]
    rendered = core.dump_json(report)
    assert inventory["coverage"]["status"] == "partial"
    assert "ignored-directory-private-sentinel" not in rendered
    assert "ignored-file-private-sentinel" not in rendered
    reasons = {item["reason"] for item in inventory["skipped"]}
    assert "ignored directory not inspected" in reasons
    assert "ignored candidate not inspected" in reasons


def test_exact_ignored_codex_control_makes_coverage_partial() -> None:
    with tempfile.TemporaryDirectory() as value:
        root = Path(value)
        write(root, ".gitignore", ".codex/config.toml\n")
        write(
            root,
            ".codex/config.toml",
            'project_doc_fallback_filenames = ["ignored-control-private-sentinel.md"]\n',
        )
        report = core.build_audit(root)

    rendered = core.dump_json(report)
    assert report["inventory"]["coverage"]["status"] == "partial"
    assert "ignored-control-private-sentinel" not in rendered
    assert any(
        item["path"] == ".codex/config.toml" and "ignored" in item["reason"]
        for item in report["inventory"]["skipped"]
    )


def test_root_control_ignored_by_primary_rules_is_not_read() -> None:
    with tempfile.TemporaryDirectory() as value:
        root = Path(value)
        write(root, ".gitignore", ".ignore\n")
        write(root, ".ignore", "ignored-control-body-private-sentinel\n")
        write(root, "AGENTS.md", "# Rules\n")
        report = core.build_audit(root)

    rendered = core.dump_json(report)
    assert "ignored-control-body-private-sentinel" not in rendered
    assert report["inventory"]["coverage"]["status"] == "partial"
    assert (
        "custom ignored discovery control not inspected" in report["inventory"]["coverage"]["partial_reasons"]
    )


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFOs unavailable")
def test_bounded_input_rejects_fifo_without_blocking() -> None:
    with tempfile.TemporaryDirectory() as value:
        fifo = Path(value) / "report.json"
        os.mkfifo(fifo)
        with pytest.raises(ValueError, match="regular file"):
            core.read_bounded_input(fifo, 1024)


def test_bounded_input_rejects_in_place_change_during_read() -> None:
    with tempfile.TemporaryDirectory() as value:
        path = Path(value) / "AGENTS.md"
        path.write_bytes(b"A" * 70_000)
        original_read = core.os.read
        changed = False

        def racing_read(descriptor: int, size: int) -> bytes:
            nonlocal changed
            chunk = original_read(descriptor, size)
            if chunk and not changed:
                changed = True
                path.write_bytes(b"B" * 70_000)
            return chunk

        expected_error = OSError if os.name == "nt" else ValueError
        expected_message = "unable to read input" if os.name == "nt" else "changed while it was being read"
        with (
            patch.object(core.os, "read", side_effect=racing_read),
            pytest.raises(expected_error, match=expected_message),
        ):
            core.read_bounded_input(path, core.MAX_READ_BYTES)
        if os.name == "nt":
            assert path.read_bytes() == b"A" * 70_000


def test_bounded_input_fails_before_read_when_descriptor_location_is_unavailable() -> None:
    with tempfile.TemporaryDirectory() as value:
        root = Path(value).resolve()
        path = write(root, "AGENTS.md", "# safe\n")
        with (
            patch.object(core, "_descriptor_resolved_path", return_value=None),
            patch.object(core.os, "read") as read_mock,
            pytest.raises(ValueError, match="location could not be verified"),
        ):
            core.read_bounded_input(path, core.MAX_READ_BYTES, allowed_root=root)

    read_mock.assert_not_called()


def test_bounded_input_rejects_existing_ancestor_alias_to_in_root_secret() -> None:
    with tempfile.TemporaryDirectory() as value:
        root = Path(value).resolve()
        write(root, ".secret/AGENTS.md", "# in-root-private-sentinel\n")
        try:
            (root / "docs").symlink_to(root / ".secret", target_is_directory=True)
        except OSError as exc:
            pytest.skip(f"symlinks unavailable: {exc.__class__.__name__}")
        with (
            patch.object(core.os, "read") as read_mock,
            pytest.raises(ValueError, match="path changed"),
        ):
            core.read_bounded_input(
                root / "docs" / "AGENTS.md",
                core.MAX_READ_BYTES,
                allowed_root=root,
            )

    read_mock.assert_not_called()


def test_bounded_input_rejects_existing_ancestor_alias_outside_root() -> None:
    with tempfile.TemporaryDirectory() as value, tempfile.TemporaryDirectory() as outside_value:
        root = Path(value).resolve()
        outside = Path(outside_value).resolve()
        write(outside, "AGENTS.md", "# outside-private-sentinel\n")
        try:
            (root / "docs").symlink_to(outside, target_is_directory=True)
        except OSError as exc:
            pytest.skip(f"symlinks unavailable: {exc.__class__.__name__}")
        with (
            patch.object(core.os, "read") as read_mock,
            pytest.raises(ValueError, match="escapes the allowed root"),
        ):
            core.read_bounded_input(
                root / "docs" / "AGENTS.md",
                core.MAX_READ_BYTES,
                allowed_root=root,
            )

    read_mock.assert_not_called()


def test_bounded_input_rejects_post_discovery_ancestor_replacement() -> None:
    with tempfile.TemporaryDirectory() as value:
        root = Path(value).resolve()
        write(root, "docs/AGENTS.md", "# discovered-safe\n")
        write(root, ".secret/AGENTS.md", "# replacement-private-sentinel\n")
        inventory = core.build_inventory(root)
        assert [item["path"] for item in inventory["files"]] == ["docs/AGENTS.md"]
        (root / "docs").rename(root / "original-docs")
        try:
            (root / "docs").symlink_to(root / ".secret", target_is_directory=True)
        except OSError as exc:
            pytest.skip(f"symlinks unavailable: {exc.__class__.__name__}")

        with (
            patch.object(core.os, "read") as read_mock,
            pytest.raises(ValueError, match="path changed"),
        ):
            core.read_bounded_input(
                root / "docs" / "AGENTS.md",
                core.MAX_READ_BYTES,
                allowed_root=root,
            )

    read_mock.assert_not_called()


def test_walk_fails_closed_when_pinned_directory_location_is_unavailable() -> None:
    with tempfile.TemporaryDirectory() as value:
        root = Path(value).resolve()
        write(root, "AGENTS.md", "# safe\n")
        location_probe = "_windows_handle_resolved_path" if os.name == "nt" else "_descriptor_resolved_path"
        with (
            patch.object(core, location_probe, return_value=None),
            patch.object(
                core.os,
                "scandir",
                side_effect=AssertionError("directory contents must not be enumerated"),
            ) as scandir_mock,
        ):
            inventory = core.build_inventory(root)

    scandir_mock.assert_not_called()
    assert inventory["files"] == []
    assert inventory["coverage"]["status"] == "partial"
    assert "filesystem traversal error" in inventory["coverage"]["partial_reasons"]


@pytest.mark.skipif(os.name != "nt", reason="Windows native directory pinning test")
def test_windows_native_directory_pin_detects_replacement_and_closes() -> None:
    with tempfile.TemporaryDirectory() as value:
        root = Path(value).resolve()
        renamed = root.with_name(f"{root.name}-renamed")
        scan_target, close_pinned = core._open_pinned_directory(root, root)
        renamed_while_open = False
        try:
            assert not isinstance(scan_target, int)
            assert os.path.samefile(os.fspath(scan_target), root)
            assert core._pinned_directory_unchanged(scan_target, root)
            try:
                root.rename(renamed)
            except OSError:
                pass
            else:
                renamed_while_open = True
                root.mkdir()
                assert not core._pinned_directory_unchanged(scan_target, root)
        finally:
            close_pinned()
        if renamed_while_open:
            root.rmdir()
            renamed.rename(root)
        else:
            root.rename(renamed)
            renamed.rename(root)


def test_nonprinting_unicode_path_is_hash_only_in_json_and_text() -> None:
    with tempfile.TemporaryDirectory() as value:
        root = Path(value).resolve()
        hostile = "STATUS\u202egpj.md"
        write(
            root,
            hostile,
            "---\nstatus: retired\n---\n# Hostile display path\n",
        )
        report = core.build_audit(root)
        rendered_json = core.dump_json(report)
        rendered_text = audit_text(report)

    assert "\u202e" not in rendered_json
    assert "\u202e" not in rendered_text
    assert report["inventory"]["files"][0]["path"].startswith("<long-relative-path:")


def test_excluded_candidate_and_directory_symlinks_make_coverage_partial() -> None:
    with tempfile.TemporaryDirectory() as value, tempfile.TemporaryDirectory() as outside_value:
        root = Path(value)
        outside = Path(outside_value)
        write(outside, "target.md", "# outside\n")
        write(outside, "directory/AGENTS.md", "# outside directory\n")
        try:
            (root / "AGENTS.md").symlink_to(outside / "target.md")
            (root / "linked-docs").symlink_to(outside / "directory", target_is_directory=True)
        except OSError as exc:
            pytest.skip(f"symlinks unavailable: {exc.__class__.__name__}")
        inventory = core.build_inventory(root)

    assert inventory["coverage"]["status"] == "partial"
    reasons = inventory["coverage"]["partial_reasons"]
    assert "linked candidate not inspected" in reasons
    assert "linked filesystem entry not inspected" in reasons


def test_directory_replacement_during_walk_cannot_escape_root() -> None:
    with tempfile.TemporaryDirectory() as value, tempfile.TemporaryDirectory() as outside_value:
        root = Path(value)
        outside = Path(outside_value)
        (root / "docs").mkdir()
        write(outside, "AGENTS.md", "# outside-private-sentinel\n")
        original_add_control = core.IgnoreMatcher.add_nested_gitignore
        replaced = False

        def replace_after_pin(
            matcher: core.IgnoreMatcher,
            directory: Path,
            relative: core.PurePosixPath,
        ) -> bool:
            nonlocal replaced
            if relative.as_posix() == "docs" and not replaced:
                replaced = True
                directory.rename(root / "original-docs")
                try:
                    directory.symlink_to(outside, target_is_directory=True)
                except OSError as exc:
                    pytest.skip(f"symlinks unavailable: {exc.__class__.__name__}")
            return original_add_control(matcher, directory, relative)

        with patch.object(core.IgnoreMatcher, "add_nested_gitignore", replace_after_pin):
            inventory = core.build_inventory(root)

    assert inventory["files"] == []
    assert inventory["coverage"]["status"] == "partial"
    assert "directory changed during traversal" in inventory["coverage"]["partial_reasons"]
    assert "outside-private-sentinel" not in core.dump_json(inventory)


def test_scandir_enumeration_stops_at_walk_entry_cap() -> None:
    with tempfile.TemporaryDirectory() as value:
        root = Path(value)
        for index in range(8):
            write(root, f"STATUS-{index}.md", "# status\n")
        original_scandir = os.scandir
        yielded = 0

        class CountingScandir:
            def __init__(self, path: Path) -> None:
                self._iterator = original_scandir(path)

            def __enter__(self) -> CountingScandir:
                self._iterator.__enter__()
                return self

            def __exit__(self, *args: object) -> None:
                self._iterator.__exit__(*args)

            def __iter__(self) -> CountingScandir:
                return self

            def __next__(self) -> os.DirEntry[str]:
                nonlocal yielded
                yielded += 1
                return next(self._iterator)

        with (
            patch.object(core, "MAX_WALK_ENTRIES", 2),
            patch.object(core.os, "scandir", CountingScandir),
        ):
            inventory = core.build_inventory(root)

    assert yielded == 3
    assert inventory["files"] == []
    assert inventory["coverage"]["status"] == "partial"
    assert "filesystem entry budget exceeded" in inventory["coverage"]["partial_reasons"]


def test_reference_finding_and_record_caps_mark_partial() -> None:
    with tempfile.TemporaryDirectory() as value:
        root = Path(value)
        links = " ".join(f"[missing-{index}](missing-{index}.md)" for index in range(20))
        write(root, "AGENTS.md", f"# Rules\n\n{links}\n")
        with (
            patch.object(core, "MAX_REFERENCES", 4),
            patch.object(core, "MAX_REFERENCES_PER_FILE", 4),
            patch.object(core, "MAX_FINDINGS", 2),
        ):
            report = core.build_audit(root)

    assert len(report["inventory"]["files"][0]["references"]) == 4
    assert len(report["findings"]) == 2
    assert report["inventory"]["coverage"]["status"] == "partial"
    reasons = report["inventory"]["coverage"]["partial_reasons"]
    assert "reference record budget exceeded" in reasons
    assert "finding record budget exceeded" in reasons


def test_automatic_import_expansion_deduplicates_and_obeys_aggregate_cap() -> None:
    with tempfile.TemporaryDirectory() as value:
        root = Path(value).resolve()
        imports: list[str] = []
        for index in range(20):
            relative = f"docs/import-{index}.txt"
            write(root, relative, "@leaf.txt\n" * 20)
            imports.extend([f"@{relative}"] * 20)
        write(root, "docs/leaf.txt", "# leaf\n")
        write(root, "CLAUDE.md", "\n".join(imports) + "\n")
        real_reference_candidate = core._reference_candidate
        resolution_calls = 0

        def counted_reference_candidate(
            target: str,
            relative: core.PurePosixPath,
            audit_root: Path,
        ) -> tuple[Path | None, core.PurePosixPath | None, bool | None, bool | None]:
            nonlocal resolution_calls
            resolution_calls += 1
            return real_reference_candidate(target, relative, audit_root)

        with (
            patch.object(core, "MAX_REFERENCES", 8),
            patch.object(core, "_reference_candidate", counted_reference_candidate),
            patch.object(core, "local_references", return_value=[]),
        ):
            inventory = core.build_inventory(root)

    assert resolution_calls == 8
    assert len(inventory["files"]) <= 9
    assert inventory["coverage"]["status"] == "partial"
    assert "automatic import reference budget exceeded" in inventory["coverage"]["partial_reasons"]
    assert "reference record budget exceeded" in inventory["coverage"]["partial_reasons"]


def test_ignore_evaluation_budget_fails_closed_and_marks_partial() -> None:
    with tempfile.TemporaryDirectory() as value:
        root = Path(value)
        write(root, ".gitignore", "never-matches\n")
        write(root, "AGENTS.md", "# Rules\n")
        write(root, "STATUS.md", "# Status\n")
        with patch.object(core, "MAX_IGNORE_EVALUATIONS", 1):
            inventory = core.build_inventory(root)

    assert inventory["coverage"]["status"] == "partial"
    assert "ignore rule evaluation budget exceeded" in inventory["coverage"]["partial_reasons"]


def test_warning_and_skipped_output_caps_preserve_partial_reason() -> None:
    with tempfile.TemporaryDirectory() as value:
        root = Path(value)
        write(root, ".gitignore", "one/\ntwo/\nthree/\n")
        for name in ("one", "two", "three"):
            write(root, f"{name}/AGENTS.md", "# ignored\n")
        for index in range(4):
            write(root, f"STATUS-{index}.md", "---\nbroken\n---\n")
        with (
            patch.object(core, "MAX_SKIPPED_RECORDS", 2),
            patch.object(core, "MAX_WARNING_RECORDS", 2),
        ):
            inventory = core.build_inventory(root)

    assert len(inventory["skipped"]) == 2
    assert len(inventory["warnings"]) == 2
    assert inventory["coverage"]["status"] == "partial"
    reasons = inventory["coverage"]["partial_reasons"]
    assert "skipped record output cap exceeded" in reasons
    assert "warning record output cap exceeded" in reasons


def test_fallback_parser_ignores_multiline_strings_comments_and_tables() -> None:
    text = "\n".join(
        (
            'message = """',
            'project_doc_fallback_filenames = ["PRIVATE.md"]',
            '"""',
            '# project_doc_fallback_filenames = ["COMMENT.md"]',
            "[other]",
            'project_doc_fallback_filenames = ["TABLE.md"]',
            "",
        )
    )
    with patch.object(core, "tomllib", None):
        assert core._fallback_names_from_toml(text) == ()


def test_python310_fallback_parser_supports_multiline_top_level_array() -> None:
    text = "\n".join(
        (
            "project_doc_fallback_filenames = [",
            '  "FIRST.md",',
            "  'SECOND.md',",
            "]",
            "",
        )
    )
    with patch.object(core, "tomllib", None):
        assert core._fallback_names_from_toml(text) == ("FIRST.md", "SECOND.md")


def test_empty_agents_file_is_still_selected_as_codex_authority() -> None:
    with tempfile.TemporaryDirectory() as value:
        root = Path(value)
        write(root, "AGENTS.md", "")
        inventory = core.build_inventory(root)

    entry = inventory["files"][0]
    assert "codex" in entry["platforms"]
    assert entry["role"] == "authority"


def test_invalid_utf8_and_frontmatter_failures_make_coverage_partial() -> None:
    with tempfile.TemporaryDirectory() as value:
        root = Path(value)
        (root / "AGENTS.md").write_bytes(b"# Rules\n\xff\n")
        write(root, "STATUS.md", "---\nunclosed: true\n")
        inventory = core.build_inventory(root)

    assert inventory["coverage"]["status"] == "partial"
    messages = {item["message"] for item in inventory["warnings"]}
    assert "invalid UTF-8 replaced during decoding" in messages
    assert "unclosed YAML frontmatter" in messages
    reasons = inventory["coverage"]["partial_reasons"]
    assert "candidate read or text decoding was incomplete" in reasons
    assert "frontmatter interpretation was incomplete" in reasons


def test_frontmatter_field_cap_marks_partial_without_emitting_values() -> None:
    with tempfile.TemporaryDirectory() as value:
        root = Path(value)
        write(
            root,
            "AGENTS.md",
            "---\none: private-one\ntwo: private-two\nthree: private-three\n---\n",
        )
        with patch.object(core, "MAX_FRONTMATTER_FIELDS", 2):
            report = core.build_audit(root)

    assert report["inventory"]["coverage"]["status"] == "partial"
    assert report["inventory"]["files"][0]["metadata"] == {}
    rendered = core.dump_json(report)
    assert "private-one" not in rendered
    assert "private-two" not in rendered
    assert "private-three" not in rendered


def test_long_paths_and_targets_are_hash_bounded() -> None:
    with tempfile.TemporaryDirectory() as value:
        root = Path(value)
        segment = "private-path-sentinel-" + ("x" * 180)
        relative = "/".join((segment, segment, segment, "AGENTS.md"))
        long_target = "../" + ("private-target-sentinel-" * 40) + ".md"
        write(root, relative, f"# Rules\n\n[target]({long_target})\n")
        report = core.build_audit(root)

    rendered = core.dump_json(report)
    entry = report["inventory"]["files"][0]
    reference = entry["references"][0]
    assert entry["path"].startswith("<long-relative-path:")
    assert reference["target"] in {"<long-reference-target>", "<out-of-root-path>"}
    assert "private-path-sentinel" not in rendered
    assert "private-target-sentinel" not in rendered
    assert len(rendered.encode("utf-8")) <= core.MAX_REPORT_BYTES


def test_current_report_contract_and_partial_human_output() -> None:
    with tempfile.TemporaryDirectory() as value:
        root = Path(value)
        write(root, ".gitignore", "private/\n")
        write(root, "private/AGENTS.md", "# ignored\n")
        report = core.build_audit(root)

    assert core.validate_audit(report) == []
    json.loads(core.dump_json(report))
    rendered = audit_text(report)
    assert "Coverage is partial" in rendered
    assert "No deterministic signals need review" not in rendered


def test_dump_json_enforces_aggregate_byte_limit() -> None:
    with (
        patch.object(core, "MAX_REPORT_BYTES", 32),
        pytest.raises(ValueError, match="serialized output exceeds"),
    ):
        core.dump_json({"value": "x" * 64})
