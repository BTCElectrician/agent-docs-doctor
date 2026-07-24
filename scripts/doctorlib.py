#!/usr/bin/env python3
"""Compatibility imports for source-checkout scripts and integrations."""

from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent_docs_doctor.core import *  # noqa: F403,E402
