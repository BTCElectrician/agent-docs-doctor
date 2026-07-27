"""Plain-language, read-only audit summaries for people."""

from __future__ import annotations

from typing import Any

SEVERITY_ORDER = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "informational": 4,
}

NUMBER_WORDS = {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six", 7: "Seven"}


def _paths(finding: dict[str, Any]) -> str:
    paths = [location["path"] for location in finding["locations"][:3]]
    if len(finding["locations"]) > 3:
        paths.append(f"{len(finding['locations']) - 3} more")
    return ", ".join(paths) or "this repository"


def _plain_finding(finding: dict[str, Any]) -> tuple[str, str, str]:
    """Translate observable finding types without adding semantic certainty."""

    category = finding["category"]
    count = len(finding["locations"])
    if category == "broken-reference":
        target = finding.get("evidence", {}).get("target", "a local file")
        return (
            "An instruction points to a file that is not there.",
            (
                f"The link points to `{target}`, so a person or agent following it cannot reach "
                "the intended guidance."
            ),
            "Fix the link after confirming where it should lead.",
        )
    if category == "exact-duplication":
        copies = "two documents" if count == 2 else f"{count} documents"
        paths = [location["path"].lower() for location in finding["locations"]]
        if any("safety" in path for path in paths):
            return (
                f"The same safety rule appears in {copies}.",
                ("This can be intentional when separate agent surfaces each need the same protection."),
                "Leave it alone unless an owner confirms that both copies cover the same scope.",
            )
        return (
            f"The same instruction appears in {copies}.",
            (
                "Repeated guidance can drift later, but it may be intentional when different tools "
                "or folders need it."
            ),
            "Keep one only if the copies cover the same job; otherwise leave both in place.",
        )
    if category == "competing-current-truth":
        documents = "documents" if count != 1 else "document"
        subject = "Both documents" if count == 2 else f"{NUMBER_WORDS.get(count, str(count))} {documents}"
        return (
            f"{subject} look like they describe the current state.",
            "People and agents may not know which one is the source of truth.",
            "Choose the main document, then clearly label or archive confirmed outdated copies.",
        )
    if category == "archive-boundary":
        return (
            "A document says it is retired but is still outside the history area.",
            "It could be mistaken for current guidance unless it is clearly kept as a redirect.",
            "Confirm its replacement, then move it to history or make the redirect explicit.",
        )
    return (
        finding["summary"],
        "This may affect how people or agents follow the repository's guidance.",
        "Review it before changing anything.",
    )


def audit_text(report: dict[str, Any], limit: int = 7) -> str:
    inventory = report["inventory"]
    findings = sorted(
        report["findings"],
        key=lambda item: (SEVERITY_ORDER.get(item["severity"], 99), item["id"]),
    )
    lines = [
        "Agent Docs Doctor",
        f"Checked {len(inventory['files'])} instruction and status documents.",
        "Nothing was changed.",
        "",
    ]
    if not findings:
        if inventory["coverage"]["status"] == "partial":
            lines.extend(
                [
                    "I did not find anything to recommend within the part I could check.",
                    "",
                    "Some files could not be checked, so open the details before relying on this result.",
                ]
            )
            return "\n".join(lines) + "\n"
        lines.extend(
            [
                "Everything I checked looks okay. No changes are recommended.",
                "",
                "Ask for details if you want to see what was checked.",
            ]
        )
        return "\n".join(lines) + "\n"
    shown = findings[:limit]
    noun = "thing" if len(findings) == 1 else "things"
    lines.append(f"We found {len(findings)} {noun} worth reviewing:")
    for index, finding in enumerate(shown, start=1):
        title, why_it_matters, recommendation = _plain_finding(finding)
        lines.extend(
            [
                "",
                f"{index}. {title}",
                f"   Where: {_paths(finding)}",
                f"   Why it matters: {why_it_matters}",
                f"   Recommendation: {recommendation}",
            ]
        )
    remaining = len(findings) - len(shown)
    if remaining:
        lines.extend(["", f"{remaining} more item(s) are available in the details."])
    lines.extend(
        [
            "",
            (
                "Nothing has changed yet. Do you want me to prepare a no-change preview for the "
                "recommended fixes?"
            ),
            "Say “show details” to see the technical evidence.",
        ]
    )
    return "\n".join(lines) + "\n"
