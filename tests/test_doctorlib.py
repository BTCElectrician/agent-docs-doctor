from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from doctorlib import MAX_READ_BYTES, build_audit, build_inventory, dump_json, validate_audit  # noqa: E402


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
            paths = [item["path"] for item in build_inventory(root)["files"]]
        self.assertEqual(paths, ["AGENTS.md"])

    def test_discovers_nested_instructions_and_scoped_rules(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self.write(root, "AGENTS.md", "# Root\n")
            self.write(root, "services/api/AGENTS.override.md", "# API\n")
            self.write(root, ".claude/rules/python.md", "# Python\n")
            self.write(root, ".cursor/rules/web.mdc", "---\nalwaysApply: false\n---\n# Web\n")
            paths = [item["path"] for item in build_inventory(root)["files"]]
        self.assertEqual(
            paths,
            [
                ".claude/rules/python.md",
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
        self.assertEqual(paths, ["STATUS.md", "ignored/AGENTS.md"])

    def test_secret_like_files_are_never_read(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            secret = self.write(root, "agent.key", "do-not-read")
            secret.chmod(0)
            try:
                result = build_inventory(root)
            finally:
                secret.chmod(0o600)
        self.assertEqual(result["files"], [])
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

    def test_malformed_frontmatter_is_a_warning(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self.write(root, "AGENTS.md", "---\nname without colon\n---\n# Rules\n")
            result = build_inventory(root)
        self.assertIn("malformed frontmatter", result["warnings"][0]["message"])

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
        self.assertEqual(len(broken), 1)
        self.assertEqual(broken[0]["evidence"]["target"], "docs/missing.md")

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

    def test_output_is_deterministic_and_uses_relative_root(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self.write(root, "AGENTS.md", "# Rules\n")
            first = dump_json(build_audit(root), pretty=True)
            second = dump_json(build_audit(root), pretty=True)
        self.assertEqual(first, second)
        self.assertNotIn(value, first)
        self.assertEqual(json.JSONDecoder().decode(first)["inventory"]["root"], ".")

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


if __name__ == "__main__":
    unittest.main()
