from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCANNER = [sys.executable, "-B", str(ROOT / "scripts" / "public_safety_scan.py")]


class PublicSafetyScanTests(unittest.TestCase):
    @staticmethod
    def initialize(root: Path) -> None:
        subprocess.run(
            ["git", "init", "--quiet", str(root)],
            check=True,
            capture_output=True,
            timeout=10,
        )

    def test_ignored_local_payload_is_not_discovered_or_read(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self.initialize(root)
            (root / ".gitignore").write_text("ignored/\n", encoding="utf-8")
            (root / "README.md").write_text("# Safe public text\n", encoding="utf-8")
            ignored = root / "ignored"
            ignored.mkdir()
            private = ignored / "private.md"
            mkfifo = getattr(os, "mkfifo", None)
            if mkfifo is not None:
                mkfifo(private)
            else:
                private.write_text("ignored-private-sentinel\n", encoding="utf-8")

            completed = subprocess.run(
                [*SCANNER, str(root)],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("public safety scan passed", completed.stdout)

    def test_public_text_symlink_is_rejected_without_following_it(self) -> None:
        with tempfile.TemporaryDirectory() as value, tempfile.TemporaryDirectory() as outside_value:
            root = Path(value)
            outside = Path(outside_value) / "private.md"
            self.initialize(root)
            outside.write_text("private-sentinel\n", encoding="utf-8")
            alias = root / "public.md"
            try:
                alias.symlink_to(outside)
            except (NotImplementedError, OSError):
                self.skipTest("symlink creation unavailable")

            completed = subprocess.run(
                [*SCANNER, str(root)],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )

        self.assertEqual(completed.returncode, 1)
        self.assertIn("link or reparse point was not followed", completed.stderr)
        self.assertNotIn("private-sentinel", completed.stderr)

    def test_multiply_linked_public_text_is_rejected_without_reading_it(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self.initialize(root)
            source = root / "source.bin"
            candidate = root / "public.md"
            source.write_bytes(b"private-sentinel\n")
            try:
                os.link(source, candidate)
            except (NotImplementedError, OSError):
                self.skipTest("hardlink creation unavailable")

            completed = subprocess.run(
                [*SCANNER, str(root)],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )

        self.assertEqual(completed.returncode, 1)
        self.assertIn("multiply-linked public text was not read", completed.stderr)
        self.assertNotIn("private-sentinel", completed.stderr)

    def test_public_fixture_paths_are_scanned(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self.initialize(root)
            fixture = root / "fixtures" / "public-case.md"
            fixture.parent.mkdir()
            private_prefix = "/" + "Users" + "/"
            fixture.write_text(f"{private_prefix}private-reviewer/project\n", encoding="utf-8")

            completed = subprocess.run(
                [*SCANNER, str(root)],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )

        self.assertEqual(completed.returncode, 1)
        self.assertIn("fixtures/public-case.md:1: private macOS path", completed.stderr)

    def test_all_tracked_file_classes_are_scanned(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self.initialize(root)
            private_prefix = "/" + "Users" + "/"
            cases = {
                ".cursor/rules/public.mdc": f"{private_prefix}private-mdc/project\n",
                ".gitignore": f"{private_prefix}private-ignore/project\n",
                "uv.lock": f"{private_prefix}private-lock/project\n",
                "LICENSE": f"{private_prefix}private-license/project\n",
            }
            for relative, payload in cases.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(payload, encoding="utf-8")
            subprocess.run(
                ["git", "-C", str(root), "add", *cases],
                check=True,
                capture_output=True,
                timeout=10,
            )

            completed = subprocess.run(
                [*SCANNER, str(root)],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )

        self.assertEqual(completed.returncode, 1)
        for relative in cases:
            self.assertIn(f"{relative}:1: private macOS path", completed.stderr)

    def test_repeated_matches_have_bounded_runtime_and_output(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self.initialize(root)
            repeated = root / "repeated.txt"
            synthetic_address = "fake" + "@" + "example.com"
            repeated.write_text((f"{synthetic_address}\n" * 100_000), encoding="utf-8")
            subprocess.run(
                ["git", "-C", str(root), "add", "repeated.txt"],
                check=True,
                capture_output=True,
                timeout=10,
            )

            completed = subprocess.run(
                [*SCANNER, str(root)],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )

        self.assertEqual(completed.returncode, 1)
        self.assertLessEqual(len(completed.stderr.splitlines()), 1_000)
        self.assertEqual(completed.stderr.count("email address"), 1)

    def test_nonprinting_unicode_path_is_hash_only_in_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self.initialize(root)
            hostile_name = "public\u202egpj.md"
            private_prefix = "/" + "Users" + "/"
            (root / hostile_name).write_text(
                f"{private_prefix}synthetic-reviewer/project\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                [*SCANNER, str(root)],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )

        self.assertEqual(completed.returncode, 1)
        self.assertNotIn("\u202e", completed.stderr)
        self.assertIn("<public-path:", completed.stderr)


if __name__ == "__main__":
    unittest.main()
