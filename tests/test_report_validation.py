from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agent_docs_doctor.core import build_audit, validate_audit  # noqa: E402

VALIDATORS = (
    [sys.executable, "-B", str(ROOT / "scripts" / "validate_report.py")],
    [
        sys.executable,
        "-B",
        str(ROOT / "scripts" / "agent_docs_doctor.py"),
        "validate-report",
    ],
)


class ReportValidationSafetyTests(unittest.TestCase):
    def test_multiply_linked_report_alias_is_never_read(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            private = root / ".env"
            alias = root / "report.json"
            private.write_text('{"private": "report-private-sentinel"}', encoding="utf-8")
            try:
                os.link(private, alias)
            except (NotImplementedError, OSError):
                self.skipTest("hardlink creation unavailable")

            for command in VALIDATORS:
                with self.subTest(command=command[-1]):
                    completed = subprocess.run(
                        [*command, str(alias)],
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    self.assertEqual(completed.returncode, 2)
                    self.assertIn("must not be multiply linked", completed.stderr)
                    self.assertNotIn("report-private-sentinel", completed.stderr)

    def test_pathological_numbers_and_duplicate_keys_fail_without_tracebacks(self) -> None:
        payloads = (
            '{"value": ' + ("9" * 5_000) + "}",
            '{"value": NaN}',
            '{"value": 1e100000}',
            '{"value": 1e-100000}',
            '{"value": 1, "value": 2}',
        )
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            for index, payload in enumerate(payloads):
                report = root / f"report-{index}.json"
                report.write_text(payload, encoding="utf-8")
                for command in VALIDATORS:
                    with self.subTest(index=index, command=command[-1]):
                        completed = subprocess.run(
                            [*command, str(report)],
                            check=False,
                            capture_output=True,
                            text=True,
                            timeout=10,
                        )
                        self.assertEqual(completed.returncode, 2)
                        self.assertNotIn("Traceback", completed.stderr)
                        self.assertNotIn("999999", completed.stderr)

    def test_runtime_validation_rejects_non_finite_in_memory_values(self) -> None:
        report_value = build_audit(ROOT / "fixtures" / "healthy-repo")
        report_value["findings"] = [
            {
                "id": "synthetic",
                "severity": "low",
                "evidence_type": "deterministic",
                "category": "synthetic",
                "summary": "Synthetic validation probe.",
                "locations": [{"path": "AGENTS.md"}],
                "evidence": {"score": float("inf")},
                "uncertainty": "Synthetic.",
            }
        ]
        report_value["inventory"]["coverage"]["finding_records"] = 1

        self.assertIn(
            "report cannot be serialized as bounded JSON",
            validate_audit(report_value),
        )

    def test_schema_validation_caps_items_and_error_output(self) -> None:
        report_value = {
            "schema_version": "agent-docs-doctor.audit.v2",
            "mode": "read-only",
            "engine": {},
            "inventory": {
                "schema_version": "agent-docs-doctor.inventory.v2",
                "root": ".",
                "files": [{}] * 20_000,
                "exact_overlap_groups": [],
                "skipped": [],
                "warnings": [],
            },
            "findings": [],
            "judgment_queue": [],
            "limitations": [],
        }
        with tempfile.TemporaryDirectory() as value:
            report = Path(value) / "many-errors.json"
            report.write_text(json.dumps(report_value), encoding="utf-8")
            for command in VALIDATORS:
                with self.subTest(command=command[-1]):
                    completed = subprocess.run(
                        [*command, str(report)],
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    self.assertEqual(completed.returncode, 1)
                    self.assertLessEqual(len(completed.stderr.splitlines()), 200)
                    self.assertIn("inventory.files exceeds", completed.stderr)
                    self.assertIn("additional validation errors omitted", completed.stderr)

    def test_unhashable_schema_values_fail_without_tracebacks(self) -> None:
        base = build_audit(ROOT / "fixtures" / "healthy-repo")
        reference = {
            "target": "missing.md",
            "target_kind": "relative",
            "edge_type": "markdown-link",
            "resolution": "missing",
            "line": 1,
            "column": 1,
            "inside_root": True,
            "exists": False,
        }
        base["inventory"]["files"][0]["references"] = [reference]
        base["findings"] = [
            {
                "id": "synthetic",
                "severity": "low",
                "evidence_type": "deterministic",
                "category": "synthetic",
                "summary": "Synthetic validation probe.",
                "locations": [{"path": "AGENTS.md"}],
                "uncertainty": "Synthetic.",
            }
        ]
        mutations = (
            lambda report: report.__setitem__("schema_version", {}),
            lambda report: report["inventory"]["coverage"].__setitem__("status", {}),
            lambda report: report["inventory"]["files"][0]["metadata"].__setitem__("status", {}),
            lambda report: report["inventory"]["files"][0]["references"][0].__setitem__("edge_type", {}),
            lambda report: report["findings"][0].__setitem__("severity", {}),
        )
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            for index, mutate in enumerate(mutations):
                report_value = deepcopy(base)
                mutate(report_value)
                report = root / f"unhashable-{index}.json"
                report.write_text(json.dumps(report_value), encoding="utf-8")
                for command in VALIDATORS:
                    with self.subTest(index=index, command=command[-1]):
                        completed = subprocess.run(
                            [*command, str(report)],
                            check=False,
                            capture_output=True,
                            text=True,
                            timeout=10,
                        )
                        self.assertEqual(completed.returncode, 1)
                        self.assertNotIn("Traceback", completed.stderr)

    def test_untrusted_labels_cannot_inject_controls_or_unbounded_diagnostics(self) -> None:
        report_value = build_audit(ROOT / "fixtures" / "healthy-repo")
        hostile_label = "\x1b[2JSECRET-LABEL" + ("X" * 100_000)
        report_value["engine"]["configuration"][hostile_label] = 0
        report_value["inventory"]["coverage"]["limits"][hostile_label] = 0
        report_value["inventory"]["files"][0]["metadata"][hostile_label] = True
        report_value["findings"] = [
            {
                "id": hostile_label,
                "severity": "low",
                "evidence_type": "deterministic",
                "category": "synthetic",
                "summary": "Synthetic validation probe.",
                "locations": [{"path": "AGENTS.md"}],
                "uncertainty": "Synthetic.",
            },
            {
                "id": hostile_label,
                "severity": "low",
                "evidence_type": "deterministic",
                "category": "synthetic",
                "summary": "Synthetic validation probe.",
                "locations": [{"path": "AGENTS.md"}],
                "uncertainty": "Synthetic.",
            },
        ]
        with tempfile.TemporaryDirectory() as value:
            report = Path(value) / "hostile-labels.json"
            report.write_text(json.dumps(report_value), encoding="utf-8")
            for command in VALIDATORS:
                with self.subTest(command=command[-1]):
                    completed = subprocess.run(
                        [*command, str(report)],
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    self.assertEqual(completed.returncode, 1)
                    self.assertNotIn("\x1b", completed.stderr)
                    self.assertNotIn("SECRET-LABEL", completed.stderr)
                    self.assertLessEqual(len(completed.stderr.encode("utf-8")), 40_000)


if __name__ == "__main__":
    unittest.main()
