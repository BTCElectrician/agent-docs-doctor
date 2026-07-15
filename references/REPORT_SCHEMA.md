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

Exact-overlap occurrences contain hashes plus path and line evidence, not copied paragraph bodies.
File `sha256` values cover raw bytes. Reference evidence includes path, line, and column so stable
finding IDs remain unique when a line contains repeated links. Absolute-style Markdown and import
targets are replaced with typed placeholders and one-way hashes so a shareable ledger does not
reproduce local filesystem paths. References inside Markdown fenced code are not treated as links.

An installed auditor package nested inside the target is listed in `skipped` and excluded from the inventory; other installed skills remain auditable. Default-pruned directories are also listed in `skipped`; add an explicit negation such as `!fixtures/` to `.agent-docs-doctorignore` when one belongs in scope. Symlinked ignore-control files are not followed and are reported as a limitation. An ignored `.codex/config.toml` is not opened or used for fallback discovery. Non-regular candidates such as named pipes and dangling symlinks are not opened and receive distinct skip reasons.

Validate it with `scripts/validate_report.py`. Both that entry point and `agent_docs_doctor.py
validate-report` exit `0` for valid output or help, `1` for a well-formed report rejected by the
schema, and `2` for usage, file I/O, or JSON parsing errors. The JSON is evidence input, not a
complete semantic audit.
