"""Concise, deterministic human-readable CLI output."""

from __future__ import annotations

from typing import Any

SEVERITY_ORDER = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "informational": 4,
}


def audit_text(report: dict[str, Any], limit: int = 7) -> str:
    inventory = report["inventory"]
    findings = sorted(
        report["findings"],
        key=lambda item: (SEVERITY_ORDER.get(item["severity"], 99), item["id"]),
    )
    lines = [
        "Agent Docs Doctor",
        (
            f"Scanned {len(inventory['files'])} agent-facing surfaces "
            f"({inventory['coverage']['status']} coverage)."
        ),
        "Nothing was changed.",
        "",
    ]
    if not findings:
        lines.extend(
            [
                "No deterministic signals need review.",
                "",
                "Semantic conflicts and staleness still require repository-aware judgment.",
            ]
        )
        return "\n".join(lines) + "\n"
    shown = findings[:limit]
    lines.append(f"{len(findings)} deterministic signal(s) found:")
    for index, finding in enumerate(shown, start=1):
        locations = ", ".join(location["path"] for location in finding["locations"][:3])
        if len(finding["locations"]) > 3:
            locations += f" (+{len(finding['locations']) - 3} more)"
        lines.extend(
            [
                "",
                f"E{index} [{finding['severity'].upper()}] {finding['summary']}",
                f"   Evidence: {locations or 'repository-level'}",
                f"   Caution: {finding['uncertainty']}",
            ]
        )
    remaining = len(findings) - len(shown)
    if remaining:
        lines.extend(["", f"{remaining} more signal(s) remain in the JSON ledger."])
    lines.extend(
        [
            "",
            (
                "Next: ask your agent to use Agent Docs Doctor for the short decision review. "
                "It will separate Keep, Fix, Clarify, and Later choices."
            ),
        ]
    )
    return "\n".join(lines) + "\n"
