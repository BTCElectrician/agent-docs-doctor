#!/usr/bin/env python3
"""Validate the published v2 schema and its generated-report contract."""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from jsonschema import Draft202012Validator  # noqa: E402

from agent_docs_doctor.core import build_audit, build_inventory  # noqa: E402


def main() -> int:
    schema_path = ROOT / "schemas" / "audit-v2.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)

    report = build_audit(ROOT / "fixtures" / "healthy-repo")
    validator.validate(report)
    standalone_inventory_report = deepcopy(report)
    standalone_inventory_report["inventory"] = build_inventory(ROOT / "fixtures" / "healthy-repo")
    validator.validate(standalone_inventory_report)

    invalid = deepcopy(report)
    invalid["findings"] = [
        {
            "id": "synthetic",
            "severity": "low",
            "evidence_type": "deterministic",
            "category": "synthetic",
            "summary": "Synthetic schema-bound probe.",
            "locations": [{"path": "AGENTS.md"}] * 501,
            "uncertainty": "Synthetic.",
        }
    ]
    if not list(validator.iter_errors(invalid)):
        raise RuntimeError("v2 schema did not enforce the finding-location limit")

    print("JSON Schema 2020-12 contract passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
