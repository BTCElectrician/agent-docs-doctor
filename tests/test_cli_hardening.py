from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = [sys.executable, str(ROOT / "scripts" / "agent_docs_doctor.py")]
STANDALONE = [sys.executable, str(ROOT / "scripts" / "validate_report.py")]


class CliHardeningTests(unittest.TestCase):
    @staticmethod
    def isolated_home_environment(home: Path) -> dict[str, str]:
        environment = os.environ.copy()
        environment["HOME"] = str(home)
        environment["USERPROFILE"] = str(home)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        return environment

    def test_doctor_runs_a_real_disposable_no_write_probe(self) -> None:
        completed = subprocess.run(
            [*ENTRYPOINT, "doctor"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("captured filesystem snapshot unchanged", completed.stdout)
        self.assertIn("state-bound plan without applying it", completed.stdout)
        self.assertIn("used only a disposable probe", completed.stdout)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX FIFO support required")
    def test_report_validators_reject_fifo_without_hanging(self) -> None:
        mkfifo = getattr(os, "mk" + "fifo", None)
        if not callable(mkfifo):
            self.skipTest("POSIX FIFO support required")
        with tempfile.TemporaryDirectory() as value:
            fifo = Path(value) / "report.json"
            mkfifo(fifo)
            for command in (ENTRYPOINT + ["validate-report"], STANDALONE):
                with self.subTest(command=command[-1]):
                    completed = subprocess.run(
                        [*command, str(fifo)],
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    self.assertEqual(completed.returncode, 2)
                    self.assertIn("regular file", completed.stderr)

    def test_report_validators_bound_json_depth_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            report = Path(value) / "deep.json"
            report.write_text("[" * 200 + "0" + "]" * 200, encoding="utf-8")
            for command in (ENTRYPOINT + ["validate-report"], STANDALONE):
                with self.subTest(command=command[-1]):
                    completed = subprocess.run(
                        [*command, str(report)],
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    self.assertEqual(completed.returncode, 2)
                    self.assertIn("nesting depth", completed.stderr)
                    self.assertNotIn("Traceback", completed.stderr)

    def test_report_validators_reject_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            report = root / "report.json"
            alias = root / "alias.json"
            report.write_text("{}", encoding="utf-8")
            try:
                alias.symlink_to(report)
            except (NotImplementedError, OSError):
                self.skipTest("symlink creation unavailable")
            for command in (ENTRYPOINT + ["validate-report"], STANDALONE):
                with self.subTest(command=command[-1]):
                    completed = subprocess.run(
                        [*command, str(alias)],
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    self.assertEqual(completed.returncode, 2)
                    self.assertIn("not a link", completed.stderr)

    @unittest.skipUnless(
        os.name == "posix" and sys.platform in {"darwin", "linux"},
        "secure ancestor-relative installer apply is unavailable",
    )
    def test_skill_cli_requires_and_honors_bound_preview_token(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            home = Path(value)
            environment = self.isolated_home_environment(home)
            preview = subprocess.run(
                [*ENTRYPOINT, "install-skill", "--client", "codex", "--format", "json"],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
                timeout=10,
            )
            self.assertEqual(preview.returncode, 0, preview.stderr)
            plan = json.loads(preview.stdout)
            token = plan["plan_token"]
            target = home / ".agents" / "skills" / "agent-docs-doctor"
            self.assertRegex(token, r"^[0-9a-f]{64}$")
            self.assertEqual(plan["target"], "~/.agents/skills/agent-docs-doctor")
            self.assertFalse(target.exists())

            rejected = subprocess.run(
                [
                    *ENTRYPOINT,
                    "install-skill",
                    "--client",
                    "codex",
                    "--apply",
                    "0" * 64,
                ],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
                timeout=10,
            )
            self.assertEqual(rejected.returncode, 2)
            self.assertIn("current-plan fingerprint", rejected.stderr)
            self.assertFalse(target.exists())

            applied = subprocess.run(
                [
                    *ENTRYPOINT,
                    "install-skill",
                    "--client",
                    "codex",
                    "--apply",
                    token,
                    "--format",
                    "json",
                ],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
                timeout=10,
            )
            self.assertEqual(applied.returncode, 0, applied.stderr)
            self.assertEqual(json.loads(applied.stdout)["state"], "applied")
            self.assertTrue((target / "SKILL.md").is_file())

    def test_skill_cli_stale_preview_never_overwrites_new_target(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            home = Path(value)
            environment = self.isolated_home_environment(home)
            preview = subprocess.run(
                [*ENTRYPOINT, "install-skill", "--client", "claude", "--format", "json"],
                check=True,
                capture_output=True,
                text=True,
                env=environment,
                timeout=10,
            )
            token = json.loads(preview.stdout)["plan_token"]
            target = home / ".claude" / "skills" / "agent-docs-doctor"
            target.mkdir(parents=True)
            sentinel = target / "SKILL.md"
            sentinel.write_text("# user-owned\n", encoding="utf-8")
            applied = subprocess.run(
                [
                    *ENTRYPOINT,
                    "install-skill",
                    "--client",
                    "claude",
                    "--apply",
                    token,
                ],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
                timeout=10,
            )
            self.assertNotEqual(applied.returncode, 0)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "# user-owned\n")


if __name__ == "__main__":
    unittest.main()
