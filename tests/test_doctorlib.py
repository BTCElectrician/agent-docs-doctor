from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from doctorlib import (  # noqa: E402
    MAX_IGNORE_RULES,
    MAX_READ_BYTES,
    build_audit,
    build_inventory,
    dump_json,
    read_text,
    validate_audit,
)


class DoctorLibTests(unittest.TestCase):
    def write(self, root: Path, relative: str, text: str) -> Path:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_empty_repository(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            result = build_inventory(value)
        self.assertEqual(result["files"], [])
        self.assertEqual(result["exact_overlap_groups"], [])

    def test_fixture_directories_are_excluded_from_parent_audits(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self.write(root, "AGENTS.md", "# Root\n")
            self.write(root, "fixtures/sample/AGENTS.md", "# Synthetic\n")
            result = build_inventory(root)
            paths = [item["path"] for item in result["files"]]
        self.assertEqual(paths, ["AGENTS.md"])
        self.assertIn(
            {"path": "fixtures", "reason": "default excluded directory"},
            result["skipped"],
        )

    def test_default_exclusion_can_be_explicitly_restored(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self.write(root, ".agent-docs-doctorignore", "!fixtures/\n")
            self.write(root, "fixtures/sample/AGENTS.md", "# Synthetic\n")
            result = build_inventory(root)
        self.assertEqual(
            [item["path"] for item in result["files"]],
            ["fixtures/sample/AGENTS.md"],
        )
        self.assertNotIn(
            {"path": "fixtures", "reason": "default excluded directory"},
            result["skipped"],
        )

    def test_gitignore_negation_cannot_restore_tool_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self.write(root, ".gitignore", "!fixtures/\n")
            self.write(root, "fixtures/sample/AGENTS.md", "# Synthetic\n")
            result = build_inventory(root)
        self.assertEqual(result["files"], [])
        self.assertIn(
            {"path": "fixtures", "reason": "default excluded directory"},
            result["skipped"],
        )

    def test_discovers_nested_instructions_and_scoped_rules(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self.write(root, "AGENTS.md", "# Root\n")
            self.write(root, "services/api/AGENTS.override.md", "# API\n")
            self.write(root, ".claude/rules/python.md", "# Python\n")
            self.write(root, ".claude/rules/python/style.md", "# Python style\n")
            self.write(root, ".cursor/rules/web.mdc", "---\nalwaysApply: false\n---\n# Web\n")
            self.write(root, "other/rules/python/style.md", "# Not a platform rule\n")
            paths = [item["path"] for item in build_inventory(root)["files"]]
        self.assertEqual(
            paths,
            [
                ".claude/rules/python.md",
                ".claude/rules/python/style.md",
                ".cursor/rules/web.mdc",
                "AGENTS.md",
                "services/api/AGENTS.override.md",
            ],
        )

    def test_ignore_behavior_and_negation(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self.write(root, ".gitignore", "ignored/\n!ignored/AGENTS.md\nprivate-*.md\n")
            self.write(root, "ignored/AGENTS.md", "# Restored\n")
            self.write(root, "private-status.md", "# Private\n")
            self.write(root, "STATUS.md", "# Current\n")
            paths = [item["path"] for item in build_inventory(root)["files"]]
        self.assertEqual(paths, ["STATUS.md"])

    def test_negation_can_restore_file_when_parent_directory_is_not_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self.write(root, ".gitignore", "ignored/*\n!ignored/AGENTS.md\n")
            self.write(root, "ignored/AGENTS.md", "# Restored\n")
            self.write(root, "ignored/STATUS.md", "# Still ignored\n")
            paths = [item["path"] for item in build_inventory(root)["files"]]
        self.assertEqual(paths, ["ignored/AGENTS.md"])

    def test_nested_gitignore_is_applied_to_its_subtree(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self.write(root, "docs/.gitignore", "private/\n")
            self.write(root, "docs/private/AGENTS.md", "# Private\n")
            self.write(root, "docs/STATUS.md", "# Public\n")
            paths = [item["path"] for item in build_inventory(root)["files"]]
        self.assertEqual(paths, ["docs/STATUS.md"])

    def test_slash_pattern_star_does_not_cross_directories(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self.write(root, ".gitignore", "docs/*.md\n")
            self.write(root, "docs/STATUS.md", "# Direct status\n")
            self.write(root, "docs/nested/STATUS.md", "# Nested status\n")
            paths = [item["path"] for item in build_inventory(root)["files"]]
        self.assertEqual(paths, ["docs/nested/STATUS.md"])

    def test_trailing_globstar_does_not_prune_parent_before_negation(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self.write(root, ".gitignore", "docs/**\n!docs/AGENTS.md\n")
            self.write(root, "docs/AGENTS.md", "# Restored root doc\n")
            self.write(root, "docs/nested/AGENTS.md", "# Still ignored\n")
            paths = [item["path"] for item in build_inventory(root)["files"]]
        self.assertEqual(paths, ["docs/AGENTS.md"])

    def test_globstar_matching_is_bounded_for_adversarial_patterns(self) -> None:
        code = (
            "import sys; sys.path.insert(0, 'scripts'); "
            "from doctorlib import path_pattern_matches; "
            "n=40; path='/'.join(['x']*n); "
            "pattern='/'.join(['**']*n+['missing']); "
            "assert not path_pattern_matches(path, pattern)"
        )
        completed = subprocess.run(
            [sys.executable, "-B", "-c", code],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_oversized_ignore_control_fails_closed_without_opening(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            control = root / ".gitignore"
            with control.open("wb") as handle:
                handle.truncate(MAX_READ_BYTES + 1)
            self.write(root, "AGENTS.md", "# Rules\n")
            original_read_bytes = Path.read_bytes

            def guarded_read_bytes(path: Path) -> bytes:
                if path == control:
                    raise AssertionError("oversized ignore control was opened")
                return original_read_bytes(path)

            with (
                patch.object(Path, "read_bytes", guarded_read_bytes),
                self.assertRaisesRegex(ValueError, "byte read limit"),
            ):
                build_inventory(root)

    def test_excessive_ignore_rules_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            rules = "".join(f"ignored-{index}\n" for index in range(MAX_IGNORE_RULES + 1))
            self.write(root, ".gitignore", rules)
            with self.assertRaisesRegex(ValueError, "rule limit"):
                build_inventory(root)

    def test_root_ignore_symlink_is_not_opened(self) -> None:
        with tempfile.TemporaryDirectory() as value, tempfile.TemporaryDirectory() as outside_value:
            root = Path(value)
            sentinel = "ignore-target-private-sentinel"
            outside = self.write(Path(outside_value), "ignore-rules", f"AGENTS.md\n{sentinel}\n")
            control = root / ".gitignore"
            control.symlink_to(outside)
            self.write(root, "AGENTS.md", "# Rules\n")
            original_read_text = Path.read_text
            original_read_bytes = Path.read_bytes
            original_open = Path.open
            blocked = {control, outside}

            def guarded_read_text(path: Path, encoding: str | None = None, errors: str | None = None) -> str:
                if path in blocked:
                    raise AssertionError("root ignore symlink was opened")
                return original_read_text(path, encoding=encoding, errors=errors)

            def guarded_read_bytes(path: Path) -> bytes:
                if path in blocked:
                    raise AssertionError("root ignore symlink was opened")
                return original_read_bytes(path)

            def guarded_open(path: Path, *args: Any, **kwargs: Any) -> Any:
                if path in blocked:
                    raise AssertionError("root ignore symlink was opened")
                return original_open(path, *args, **kwargs)

            with (
                patch.object(Path, "read_text", guarded_read_text),
                patch.object(Path, "read_bytes", guarded_read_bytes),
                patch.object(Path, "open", guarded_open),
            ):
                result = build_inventory(root)
                paths = [item["path"] for item in result["files"]]
                serialized = dump_json(result)
        self.assertEqual(paths, ["AGENTS.md"])
        self.assertNotIn(sentinel, serialized)
        self.assertEqual(
            result["skipped"],
            [{"path": ".gitignore", "reason": "ignore control symlink not followed"}],
        )

    def test_secret_like_files_are_never_read(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            sentinel = "private-secret-sentinel"
            secret = self.write(root, "agent.key", sentinel)
            original_read_text = Path.read_text
            original_read_bytes = Path.read_bytes
            original_open = Path.open

            def guarded_read_text(path: Path, encoding: str | None = None, errors: str | None = None) -> str:
                if path == secret:
                    raise AssertionError("secret-like candidate was opened")
                return original_read_text(path, encoding=encoding, errors=errors)

            def guarded_read_bytes(path: Path) -> bytes:
                if path == secret:
                    raise AssertionError("secret-like candidate was opened")
                return original_read_bytes(path)

            def guarded_open(path: Path, *args: Any, **kwargs: Any) -> Any:
                if path == secret:
                    raise AssertionError("secret-like candidate was opened")
                return original_open(path, *args, **kwargs)

            with (
                patch.object(Path, "read_text", guarded_read_text),
                patch.object(Path, "read_bytes", guarded_read_bytes),
                patch.object(Path, "open", guarded_open),
            ):
                result = build_inventory(root)
                serialized = dump_json(result)
        self.assertEqual(result["files"], [])
        self.assertNotIn(sentinel, serialized)
        self.assertEqual(result["skipped"][0]["reason"], "secret-like filename")

    def test_secret_handling_rule_is_not_mistaken_for_a_secret(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self.write(root, "docs/secret-handling-rules.md", "# Secret handling rules\n")
            paths = [item["path"] for item in build_inventory(root)["files"]]
        self.assertEqual(paths, ["docs/secret-handling-rules.md"])

    def test_symlink_outside_root_is_not_read(self) -> None:
        with tempfile.TemporaryDirectory() as value, tempfile.TemporaryDirectory() as outside_value:
            root = Path(value)
            outside = self.write(Path(outside_value), "AGENTS.md", "# Outside\n")
            (root / "AGENTS.md").symlink_to(outside)
            result = build_inventory(root)
        self.assertEqual(result["files"], [])
        self.assertEqual(result["skipped"], [{"path": "AGENTS.md", "reason": "symlink escapes audit root"}])

    def test_symlink_to_in_root_secret_is_not_read(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self.write(root, ".env", "sentinel-do-not-read\n")
            (root / "AGENTS.md").symlink_to(root / ".env")
            result = build_inventory(root)
            serialized = dump_json(result)
        self.assertEqual(result["files"], [])
        self.assertNotIn("sentinel-do-not-read", serialized)
        self.assertEqual(
            result["skipped"],
            [{"path": "AGENTS.md", "reason": "symlink target excluded from audit"}],
        )

    def test_symlink_to_in_root_agent_doc_is_audited(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self.write(root, "AGENTS.md", "# Shared rules\n")
            (root / "CLAUDE.md").symlink_to(root / "AGENTS.md")
            paths = [item["path"] for item in build_inventory(root)["files"]]
        self.assertEqual(paths, ["AGENTS.md", "CLAUDE.md"])

    def test_dangling_symlink_has_truthful_skip_reason(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            (root / "AGENTS.md").symlink_to(root / "missing.md")
            result = build_inventory(root)
        self.assertEqual(result["files"], [])
        self.assertEqual(
            result["skipped"],
            [{"path": "AGENTS.md", "reason": "symlink target does not exist"}],
        )

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX FIFO support required")
    def test_non_regular_candidate_is_skipped_without_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            os.mkfifo(root / "AGENTS.md")
            completed = subprocess.run(
                [sys.executable, str(SCRIPTS / "agent_docs_doctor.py"), "inventory", str(root)],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            result = json.JSONDecoder().decode(completed.stdout)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(result["files"], [])
        self.assertEqual(
            result["skipped"],
            [{"path": "AGENTS.md", "reason": "non-regular filesystem entry"}],
        )

    def test_exact_overlap_across_files(self) -> None:
        block = (
            "Always require explicit approval before deleting production data or changing release controls."
        )
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self.write(root, "AGENTS.md", f"# Rules\n\n{block}\n")
            self.write(root, "CLAUDE.md", f"# Adapter\n\n{block}\n")
            result = build_inventory(root)
        self.assertEqual(len(result["exact_overlap_groups"]), 1)
        occurrences = result["exact_overlap_groups"][0]["occurrences"]
        self.assertEqual([item["path"] for item in occurrences], ["AGENTS.md", "CLAUDE.md"])
        self.assertTrue(all("text" not in item for item in occurrences))
        self.assertNotIn(block, dump_json(result))

    def test_short_or_heading_overlap_is_not_reported(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self.write(root, "AGENTS.md", "# Same\n\nBe safe.\n")
            self.write(root, "CLAUDE.md", "# Same\n\nBe safe.\n")
            result = build_inventory(root)
        self.assertEqual(result["exact_overlap_groups"], [])

    def test_frontmatter_metadata_and_cursor_loading(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self.write(
                root,
                ".cursor/rules/always.mdc",
                "---\nalwaysApply: true\nrole: adapter\n---\n# Rule\n",
            )
            entry = build_inventory(root)["files"][0]
        self.assertEqual(entry["metadata"]["alwaysApply"], True)
        self.assertEqual(entry["loading"], "automatic")
        self.assertEqual(entry["role"], "adapter")

    def test_crlf_frontmatter_remains_parseable_with_raw_byte_hashing(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            raw = b"---\r\nalwaysApply: true\r\n---\r\n# Rule\r\n"
            path = root / ".cursor/rules/always.mdc"
            path.parent.mkdir(parents=True)
            path.write_bytes(raw)
            entry = build_inventory(root)["files"][0]
        self.assertEqual(entry["metadata"]["alwaysApply"], True)
        self.assertEqual(entry["sha256"], hashlib.sha256(raw).hexdigest())

    def test_malformed_frontmatter_is_a_warning(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self.write(root, "AGENTS.md", "---\nname without colon\n---\n# Rules\n")
            result = build_inventory(root)
        self.assertIn("malformed frontmatter", result["warnings"][0]["message"])

    def test_frontmatter_requires_a_bare_closing_delimiter(self) -> None:
        for false_delimiter in ("----", "---:", "--- draft"):
            with self.subTest(false_delimiter=false_delimiter):
                with tempfile.TemporaryDirectory() as value:
                    root = Path(value)
                    self.write(
                        root,
                        "AGENTS.md",
                        f"---\nstatus: retired\n{false_delimiter}\n# Still frontmatter\n",
                    )
                    result = build_inventory(root)
                self.assertEqual(result["files"][0]["metadata"], {})
                self.assertIn("unclosed YAML frontmatter", result["warnings"][0]["message"])

    def test_broken_and_external_references(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self.write(
                root,
                "AGENTS.md",
                "# Rules\n\nRead [missing](docs/missing.md), "
                "[web](https://example.com), and [outside](../outside.md).\n",
            )
            audit = build_audit(root)
        broken = [item for item in audit["findings"] if item["category"] == "broken-reference"]
        references = audit["inventory"]["files"][0]["references"]
        outside = next(item for item in references if item["target"] == "../outside.md")
        self.assertEqual(len(broken), 1)
        self.assertEqual(broken[0]["evidence"]["target"], "docs/missing.md")
        self.assertFalse(outside["inside_root"])
        self.assertIsNone(outside["exists"])
        self.assertFalse(any(item["target"] == "https://example.com" for item in references))

    def test_same_line_broken_references_have_unique_ids(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self.write(
                root,
                "AGENTS.md",
                "Read [first](missing.md), [again](missing.md), "
                "[one](/private/one.md), and [two](/private/two.md).\n",
            )
            report = build_audit(root)
        broken = [item for item in report["findings"] if item["category"] == "broken-reference"]
        identifiers = [item["id"] for item in broken]
        self.assertEqual(len(broken), 4)
        self.assertEqual(len(set(identifiers)), 4)
        self.assertEqual(validate_audit(report), [])
        self.assertTrue(all("column" in item["locations"][0] for item in broken))

    def test_markdown_titles_and_parenthesized_destinations_resolve(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self.write(root, "docs/guide.md", "# Guide\n")
            self.write(root, "docs/spec_(draft).md", "# Draft\n")
            self.write(
                root,
                "AGENTS.md",
                'Read [guide](docs/guide.md "read this") and [draft](docs/spec_(draft).md).\n',
            )
            findings = build_audit(root)["findings"]
        self.assertFalse(any(item["category"] == "broken-reference" for item in findings))

    def test_many_unterminated_markdown_links_are_bounded(self) -> None:
        code = (
            "import sys; sys.path.insert(0, 'scripts'); "
            "from pathlib import PurePosixPath; "
            "from doctorlib import local_references; "
            "text=''.join('[bad](missing' for _ in range(50000)); "
            "assert local_references(text, PurePosixPath('AGENTS.md'), __import__('pathlib').Path('.')) == []"
        )
        completed = subprocess.run(
            [sys.executable, "-B", "-c", code],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_absolute_style_reference_target_is_sanitized(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            private_target = "/private/tmp/private-user/plan.md"
            self.write(root, "AGENTS.md", f"Read [plan]({private_target}).\n")
            result = build_inventory(root)
            serialized = dump_json(result)
            reference = result["files"][0]["references"][0]
        self.assertNotIn(private_target, serialized)
        self.assertEqual(reference["target"], "<root-relative-path>")
        self.assertEqual(reference["target_kind"], "root-relative")
        self.assertIn("target_sha256", reference)

    def test_home_reference_is_sanitized_and_never_resolved_inside_root(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            private_target = "~/.claude/personal.md"
            self.write(root, "AGENTS.md", f"@{private_target}\n")
            report = build_audit(root)
            reference = report["inventory"]["files"][0]["references"][0]
        self.assertEqual(reference["target"], "<absolute-filesystem-path>")
        self.assertEqual(reference["target_kind"], "absolute-filesystem")
        self.assertFalse(reference["inside_root"])
        self.assertIsNone(reference["exists"])
        self.assertFalse(any(item["category"] == "broken-reference" for item in report["findings"]))

    def test_named_home_and_windows_drive_references_are_sanitized(self) -> None:
        private_targets = ("~someone/private/plan.md", "C:/example/private-plan.md")
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self.write(
                root,
                "AGENTS.md",
                "\n".join(f"Read [private]({target})." for target in private_targets),
            )
            result = build_inventory(root)
            serialized = dump_json(result)
            references = result["files"][0]["references"]
        self.assertEqual(len(references), 2)
        self.assertTrue(all(item["target"] == "<absolute-filesystem-path>" for item in references))
        self.assertTrue(all(item["target_kind"] == "absolute-filesystem" for item in references))
        self.assertTrue(all(not item["inside_root"] for item in references))
        self.assertTrue(all(item["exists"] is None for item in references))
        for target in private_targets:
            self.assertNotIn(target, serialized)

    def test_invalid_filesystem_reference_does_not_abort_or_leak(self) -> None:
        invalid_target = "private\x00path.md"
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self.write(root, "AGENTS.md", f"Read [invalid]({invalid_target}).\n")
            result = build_inventory(root)
            reference = result["files"][0]["references"][0]
        self.assertEqual(reference["target"], "<invalid-filesystem-path>")
        self.assertEqual(reference["target_kind"], "invalid-filesystem")
        self.assertFalse(reference["inside_root"])
        self.assertIsNone(reference["exists"])
        self.assertIn("target_sha256", reference)

    def test_references_inside_fenced_code_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self.write(
                root,
                "AGENTS.md",
                "```python\n@dataclass\n[example](docs/example.md)\n```\n\n"
                "~~~text\n@missing/inside-fence.md\n~~~\n\n"
                "Read [real](docs/real-missing.md).\n",
            )
            report = build_audit(root)
        broken = [item for item in report["findings"] if item["category"] == "broken-reference"]
        self.assertEqual(len(broken), 1)
        self.assertEqual(broken[0]["evidence"]["target"], "docs/real-missing.md")

    def test_unterminated_fence_is_masked_to_end_of_file(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self.write(root, "AGENTS.md", "```text\n@missing/inside-fence.md\n")
            findings = build_audit(root)["findings"]
        self.assertFalse(any(item["category"] == "broken-reference" for item in findings))

    def test_crlf_fence_closes_before_real_reference(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            raw = (
                b"```text\r\n[example](docs/example.md)\r\n```\r\n\r\n"
                b"Read [real](docs/real-missing.md).\r\n"
            )
            (root / "AGENTS.md").write_bytes(raw)
            report = build_audit(root)
        broken = [item for item in report["findings"] if item["category"] == "broken-reference"]
        self.assertEqual(len(broken), 1)
        self.assertEqual(broken[0]["evidence"]["target"], "docs/real-missing.md")

    def test_root_relative_reference_resolves_inside_audit_root(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self.write(root, "AGENTS.md", "Read [status](/docs/STATUS.md).\n")
            self.write(root, "docs/STATUS.md", "# Current\n")
            findings = build_audit(root)["findings"]
        self.assertFalse(any(item["category"] == "broken-reference" for item in findings))

    def test_archive_and_retired_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self.write(root, "docs/archive/OLD_PLAN.md", "---\nstatus: retired\n---\n# Old\n")
            self.write(root, "CURRENT_PLAN.md", "---\nstatus: retired\n---\n# Misplaced\n")
            audit = build_audit(root)
        archive = next(
            item for item in audit["inventory"]["files"] if item["path"].startswith("docs/archive")
        )
        self.assertTrue(archive["archive"])
        findings = [item["id"] for item in audit["findings"]]
        self.assertIn("retired-outside-archive:CURRENT_PLAN.md", findings)
        self.assertNotIn("retired-outside-archive:docs/archive/OLD_PLAN.md", findings)

    def test_multiple_status_surfaces_are_evidence_not_a_conclusion(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self.write(root, "STATUS.md", "# Product status\n")
            self.write(root, "docs/API_STATUS.md", "# API status\n")
            findings = build_audit(root)["findings"]
        finding = next(item for item in findings if item["category"] == "competing-current-truth")
        self.assertIn("may have intentionally distinct scopes", finding["uncertainty"])

    def test_unusual_names_and_spaces(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self.write(root, "team docs/Release Authority Rules.md", "# Release authority\n")
            paths = [item["path"] for item in build_inventory(root)["files"]]
        self.assertEqual(paths, ["team docs/Release Authority Rules.md"])

    def test_large_file_is_not_read(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            path = root / "AGENTS.md"
            with path.open("wb") as handle:
                handle.truncate(MAX_READ_BYTES + 1)
            result = build_inventory(root)
        self.assertIsNone(result["files"][0]["sha256"])
        self.assertIn("read limit", result["warnings"][0]["message"])

    def test_file_hash_uses_raw_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            raw = b"# Rules\r\n\r\nUse CRLF safely.\r\n"
            (root / "AGENTS.md").write_bytes(raw)
            entry = build_inventory(root)["files"][0]
        self.assertEqual(entry["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(entry["bytes"], len(raw))

    def test_invalid_utf8_is_hashed_raw_and_decoded_safely(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            raw = b"# Rules\n\xff\n"
            (root / "AGENTS.md").write_bytes(raw)
            entry = build_inventory(root)["files"][0]
        self.assertEqual(entry["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(entry["lines"], 2)

    def test_filename_hints_use_token_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self.write(root, "STATUSBAR_WIDGETS.md", "# UI\n")
            self.write(root, "EXPLANATION.md", "# Explanation\n")
            self.write(root, "API_STATUS.md", "# API status\n")
            self.write(root, "CURRENT_PLAN.md", "# Current plan\n")
            entries = {item["path"]: item for item in build_inventory(root)["files"]}
        self.assertEqual(set(entries), {"API_STATUS.md", "CURRENT_PLAN.md"})
        self.assertEqual(entries["API_STATUS.md"]["role"], "current-state")

    def test_camelcase_filename_hints_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            for name in ("AgentRules.md", "WorkQueue.md", "CurrentState.md", "ModelConfigs.md"):
                self.write(root, name, f"# {name}\n")
            paths = [item["path"] for item in build_inventory(root)["files"]]
        self.assertEqual(
            paths,
            ["AgentRules.md", "CurrentState.md", "ModelConfigs.md", "WorkQueue.md"],
        )

    def test_output_is_deterministic_and_uses_relative_root(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self.write(root, "AGENTS.md", "# Rules\n")
            outputs: list[str] = []
            for hash_seed in ("1", "8675309"):
                environment = os.environ.copy()
                environment["PYTHONHASHSEED"] = hash_seed
                completed = subprocess.run(
                    [
                        sys.executable,
                        "-B",
                        str(SCRIPTS / "agent_docs_doctor.py"),
                        "audit",
                        str(root),
                        "--pretty",
                    ],
                    cwd=ROOT,
                    env=environment,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                outputs.append(completed.stdout)
        first, second = outputs
        self.assertEqual(first, second)
        self.assertNotIn(value, first)
        self.assertEqual(json.JSONDecoder().decode(first)["inventory"]["root"], ".")

    def test_read_text_reports_concurrent_disappearance(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            path = self.write(Path(value), "AGENTS.md", "# Rules\n")
            path.unlink()
            text, digest, byte_count, warning = read_text(path)
        self.assertIsNone(text)
        self.assertIsNone(digest)
        self.assertIsNone(byte_count)
        self.assertIsNotNone(warning)
        self.assertIn("unable to read", warning or "")

    def test_audit_discloses_concurrent_mutation_limit(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            report = build_audit(value)
        self.assertTrue(any("Concurrent repository mutation" in item for item in report["limitations"]))

    def test_read_only_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self.write(root, "AGENTS.md", "# Rules\n")
            before = sorted((p.relative_to(root).as_posix(), p.stat().st_mtime_ns) for p in root.rglob("*"))
            build_audit(root)
            after = sorted((p.relative_to(root).as_posix(), p.stat().st_mtime_ns) for p in root.rglob("*"))
        self.assertEqual(before, after)

    def test_validator_accepts_generated_report_and_rejects_bad_severity(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            report = build_audit(value)
        self.assertEqual(validate_audit(report), [])
        report["findings"] = [
            {
                "id": "x",
                "severity": "urgent",
                "evidence_type": "deterministic",
                "category": "test",
                "summary": "test",
                "locations": [],
                "uncertainty": "none",
            }
        ]
        self.assertIn("findings[0] has invalid severity", validate_audit(report))

    def test_standalone_validator_help_flags(self) -> None:
        for flag in ("-h", "--help"):
            with self.subTest(flag=flag):
                completed = subprocess.run(
                    [sys.executable, str(SCRIPTS / "validate_report.py"), flag],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertIn("usage: validate_report.py <report.json|->", completed.stdout)
                self.assertIn("standard input", completed.stdout)
                self.assertEqual(completed.stderr, "")

    def test_validator_entrypoints_share_exit_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            valid = root / "valid.json"
            invalid = root / "invalid.json"
            malformed = root / "malformed.json"
            valid.write_text(json.dumps(build_audit(root)), encoding="utf-8")
            invalid.write_text("{}", encoding="utf-8")
            malformed.write_text("{", encoding="utf-8")
            entrypoints = (
                [sys.executable, str(SCRIPTS / "validate_report.py")],
                [sys.executable, str(SCRIPTS / "agent_docs_doctor.py"), "validate-report"],
            )
            cases = ((valid, 0), (invalid, 1), (malformed, 2), (root / "missing.json", 2))
            for entrypoint in entrypoints:
                for report, expected in cases:
                    with self.subTest(entrypoint=entrypoint[-1], report=report.name):
                        completed = subprocess.run(
                            [*entrypoint, str(report)],
                            check=False,
                            capture_output=True,
                            text=True,
                        )
                        self.assertEqual(completed.returncode, expected, completed.stderr)

    def test_validator_rejects_incomplete_inventory_and_unhashable_id(self) -> None:
        incomplete = {
            "schema_version": "agent-docs-doctor.audit.v1",
            "mode": "read-only",
            "inventory": {"schema_version": "agent-docs-doctor.inventory.v1"},
            "findings": [
                {
                    "id": ["not", "hashable"],
                    "severity": "medium",
                    "evidence_type": "deterministic",
                    "category": "test",
                    "summary": "test",
                    "locations": [],
                    "uncertainty": "none",
                }
            ],
            "judgment_queue": [],
            "limitations": [],
        }
        errors = validate_audit(incomplete)
        self.assertIn("inventory missing files", errors)
        self.assertIn("findings[0].id must be a non-empty string", errors)
        completed = subprocess.run(
            [sys.executable, str(SCRIPTS / "agent_docs_doctor.py"), "validate-report", "-"],
            input=json.dumps(incomplete),
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 1)
        self.assertIn("id must be a non-empty string", completed.stderr)

    def test_codex_fallback_file_is_discovered_and_selected(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self.write(
                root,
                ".codex/config.toml",
                'project_doc_fallback_filenames = ["GUIDE.md", "SECONDARY.md"]\n',
            )
            self.write(root, "GUIDE.md", "# Fallback authority\n")
            self.write(root, "SECONDARY.md", "# Lower-priority fallback\n")
            entries = {item["path"]: item for item in build_inventory(root)["files"]}
        self.assertEqual(entries["GUIDE.md"]["loading"], "automatic")
        self.assertEqual(entries["SECONDARY.md"]["loading"], "not-loaded")

    def test_ignored_codex_config_is_not_used_for_fallback_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self.write(root, ".gitignore", ".codex/\n")
            self.write(
                root,
                ".codex/config.toml",
                'project_doc_fallback_filenames = ["PRIVATE_GUIDE.md"]\n',
            )
            self.write(root, "PRIVATE_GUIDE.md", "# Ignored fallback\n")
            ignored_config = root / ".codex/config.toml"
            sentinel = 'project_doc_fallback_filenames = ["PRIVATE_GUIDE.md"]'
            original_read_bytes = Path.read_bytes
            original_read_text = Path.read_text
            original_open = Path.open

            def guarded_read_bytes(path: Path) -> bytes:
                if path == ignored_config:
                    raise AssertionError("ignored config was opened")
                return original_read_bytes(path)

            def guarded_read_text(path: Path, encoding: str | None = None, errors: str | None = None) -> str:
                if path == ignored_config:
                    raise AssertionError("ignored config was opened")
                return original_read_text(path, encoding=encoding, errors=errors)

            def guarded_open(path: Path, *args: Any, **kwargs: Any) -> Any:
                if path == ignored_config:
                    raise AssertionError("ignored config was opened")
                return original_open(path, *args, **kwargs)

            with (
                patch.object(Path, "read_bytes", guarded_read_bytes),
                patch.object(Path, "read_text", guarded_read_text),
                patch.object(Path, "open", guarded_open),
            ):
                paths = [item["path"] for item in build_inventory(root)["files"]]
                serialized = dump_json(build_inventory(root))
        self.assertNotIn("PRIVATE_GUIDE.md", paths)
        self.assertNotIn(sentinel, serialized)

    def test_codex_override_selection_and_agent_history_classification(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self.write(root, "AGENTS.override.md", "# Override\n")
            self.write(root, "AGENTS.md", "# Base\n")
            self.write(root, "AGENTS_HISTORY.md", "# History\n")
            entries = {item["path"]: item for item in build_inventory(root)["files"]}
        self.assertEqual(entries["AGENTS.override.md"]["platforms"], ["codex"])
        self.assertEqual(entries["AGENTS.md"]["platforms"], ["cursor"])
        self.assertEqual(entries["AGENTS_HISTORY.md"]["kind"], "reference")
        self.assertEqual(entries["AGENTS_HISTORY.md"]["loading"], "manual")

    def test_cli_from_arbitrary_working_directory(self) -> None:
        with tempfile.TemporaryDirectory() as value, tempfile.TemporaryDirectory() as cwd:
            root = Path(value)
            self.write(root, "AGENTS.md", "# Rules\n")
            completed = subprocess.run(
                [sys.executable, str(SCRIPTS / "agent_docs_doctor.py"), "audit", str(root)],
                cwd=cwd,
                check=True,
                capture_output=True,
                text=True,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.JSONDecoder().decode(completed.stdout)["mode"], "read-only")

    def test_installed_cli_does_not_create_bytecode_in_target(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            installed_scripts = root / ".agents/skills/agent-docs-doctor/scripts"
            shutil.copytree(SCRIPTS, installed_scripts, ignore=shutil.ignore_patterns("__pycache__"))
            self.write(root, ".agents/skills/agent-docs-doctor/SKILL.md", "# Auditor skill\n")
            self.write(root, ".agents/skills/agent-docs-doctor/STATUS.md", "# Auditor status\n")
            self.write(root, ".agents/skills/other-skill/SKILL.md", "# Other skill\n")
            self.write(root, "AGENTS.md", "# Rules\n")
            self.write(root, "STATUS.md", "# Project status\n")
            environment = os.environ.copy()
            environment.pop("PYTHONDONTWRITEBYTECODE", None)
            completed = subprocess.run(
                [sys.executable, str(installed_scripts / "agent_docs_doctor.py"), "audit", str(root)],
                cwd=root,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )
            report = json.JSONDecoder().decode(completed.stdout)
            paths = [item["path"] for item in report["inventory"]["files"]]
            skipped = report["inventory"]["skipped"]
            bytecode = list(root.rglob("__pycache__")) + list(root.rglob("*.pyc"))
        self.assertNotIn(".agents/skills/agent-docs-doctor/SKILL.md", paths)
        self.assertNotIn(".agents/skills/agent-docs-doctor/STATUS.md", paths)
        self.assertIn(".agents/skills/other-skill/SKILL.md", paths)
        self.assertIn("STATUS.md", paths)
        self.assertFalse(any(item["category"] == "competing-current-truth" for item in report["findings"]))
        self.assertIn(
            {
                "path": ".agents/skills/agent-docs-doctor",
                "reason": "auditor's installed package excluded",
            },
            skipped,
        )
        self.assertEqual(bytecode, [])

    def test_cache_free_syntax_checker(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self.write(root, "valid.py", "value = 1\n")
            invalid = self.write(root, "invalid.py", "if True print('no')\n")
            checker = [sys.executable, str(SCRIPTS / "check_python_syntax.py")]
            valid = subprocess.run(
                [*checker, str(root / "valid.py")],
                check=False,
                capture_output=True,
                text=True,
            )
            failed = subprocess.run(
                [*checker, str(invalid)],
                check=False,
                capture_output=True,
                text=True,
            )
            missing = subprocess.run(
                [*checker, str(root / "definitely-missing")],
                check=False,
                capture_output=True,
                text=True,
            )
            caches = list(root.rglob("__pycache__")) + list(root.rglob("*.pyc"))
        self.assertEqual(valid.returncode, 0, valid.stderr)
        self.assertEqual(failed.returncode, 1)
        self.assertIn("invalid syntax", failed.stderr)
        self.assertEqual(missing.returncode, 2)
        self.assertIn("path does not exist", missing.stderr)
        self.assertEqual(caches, [])

    def test_public_commands_do_not_prescribe_shared_temp_or_compileall(self) -> None:
        public_workflow = "\n".join(
            (ROOT / name).read_text(encoding="utf-8") for name in ("README.md", "SKILL.md", "CONTRIBUTING.md")
        )
        self.assertNotIn("/tmp/agent-docs-audit.json", public_workflow)
        self.assertNotIn("-m compileall", public_workflow)

    def test_default_human_review_is_simple_and_requires_preview_approval(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        schema = (ROOT / "references/REPORT_SCHEMA.md").read_text(encoding="utf-8")
        migration = (ROOT / "references/MIGRATION_GUIDE.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        metadata = (ROOT / "agents/openai.yaml").read_text(encoding="utf-8")

        self.assertIn("Nothing was changed.", skill)
        self.assertIn("no more than seven decision items", skill)
        self.assertIn("D1 preview, D2 keep, D3 later", skill)
        self.assertIn("Apply this preview", skill)
        self.assertIn("preview` asks for an exact no-write change preview", skill)

        self.assertLess(schema.index("## Default response"), schema.index("## Advanced evidence"))
        self.assertIn("**Safe default:**", schema)
        self.assertIn("Nothing has been changed yet.", schema)
        self.assertIn("Requesting `preview` in the decision review does not authorize writes", migration)

        self.assertIn("## What a user gets", readme)
        self.assertIn("short decision review with safe defaults", metadata)
        self.assertIn("do not change files", metadata)


if __name__ == "__main__":
    unittest.main()
