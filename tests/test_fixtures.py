from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from doctorlib import build_audit  # noqa: E402


class FixtureTests(unittest.TestCase):
    def audit(self, name: str):
        return build_audit(ROOT / "fixtures" / name)

    def test_all_public_fixtures_scan(self) -> None:
        names = sorted(path.name for path in (ROOT / "fixtures").iterdir() if path.is_dir())
        self.assertEqual(
            names,
            [
                "bloated-repo",
                "competing-status",
                "conflicting-rules",
                "healthy-repo",
                "intentional-duplication",
                "lightweight-workspace",
                "stale-history",
                "thin-adapters",
            ],
        )
        for name in names:
            with self.subTest(name=name):
                self.assertEqual(self.audit(name)["mode"], "read-only")

    def test_bloated_fixture_has_exact_overlap(self) -> None:
        self.assertTrue(self.audit("bloated-repo")["inventory"]["exact_overlap_groups"])

    def test_conflict_fixture_is_not_deterministically_called_a_contradiction(self) -> None:
        categories = {item["category"] for item in self.audit("conflicting-rules")["findings"]}
        self.assertNotIn("contradiction", categories)

    def test_stale_fixture_flags_retired_outside_archive(self) -> None:
        ids = {item["id"] for item in self.audit("stale-history")["findings"]}
        self.assertIn("retired-outside-archive:CURRENT_PLAN.md", ids)

    def test_lightweight_workspace_is_discovered_without_engineering_assumptions(self) -> None:
        files = self.audit("lightweight-workspace")["inventory"]["files"]
        self.assertEqual([item["path"] for item in files], ["AGENTS.md", "STATUS.md"])


if __name__ == "__main__":
    unittest.main()
