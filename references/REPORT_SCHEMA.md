# Report schema

Produce a concise Markdown report backed by the deterministic JSON ledger.

## Required sections

1. **Scope and mode** — repository root, exclusions, read-only status, client versions if known.
2. **Executive diagnosis** — top safety and authority findings; avoid a numeric health score.
3. **Architecture map** — path, consumer, scope, loading, role, confidence.
4. **Evidence ledger** — findings ordered by severity, each following the audit rubric.
5. **Preservation register** — rules that must survive any redesign.
6. **Recommendations** — keep, tighten, consolidate, pointer, scoped rule, skill, executable control, current state, reference, archive, human decision, or no change.
7. **Challenger** — proposed tree and authority hierarchy; never overwrite the incumbent by default.
8. **Traceability** — every incumbent rule mapped to challenger, retained incumbent, or owner decision.
9. **Evaluation plan** — frozen tasks, measures, contamination controls, and adoption gate.
10. **Limitations and approval boundary** — skipped files, inference, unresolved ownership, and actions requiring approval.

## Finding template

```markdown
### [HIGH] authority-001 — Retired plan still claims current authority

- Evidence class: deterministic + model judgment
- Locations: `CURRENT_PLAN.md:2`, `AGENTS.md:18`
- Observed: `CURRENT_PLAN.md` declares `status: retired`; `AGENTS.md` links to it as current.
- Interpretation: the instruction chain may route work through superseded guidance.
- Platform/scope: Codex root instruction; manual Markdown reference.
- Confidence: high. Alternative: the file may be an intentional redirect stub, but it contains no redirect.
- Preserve: migration and rollback invariants inside the retired plan until an owner reviews them.
- Recommendation: replace the inbound link with the current authority; move the full plan to history after approval.
- Validation: rerun the deterministic audit and a stale-influence task.
```

## Deterministic JSON

`scripts/agent_docs_doctor.py audit` emits `agent-docs-doctor.audit.v1` with:

- `mode: "read-only"`;
- an `agent-docs-doctor.inventory.v1` inventory;
- deterministic `findings` with stable IDs;
- a semantic `judgment_queue`;
- explicit `limitations`.

Validate it with `scripts/validate_report.py`. The JSON is evidence input, not a complete semantic audit.
