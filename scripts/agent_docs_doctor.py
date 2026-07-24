#!/usr/bin/env python3
"""Compatibility entry point for running from a source checkout."""

from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent_docs_doctor.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
