# Human report contract

Produce a plain-language diagnosis backed by the JSON report. The user should be able to understand
what was found, why it matters, what to fix, what to leave alone, and that nothing has changed
without understanding the engine or agent-document architecture.

## Default response

Start with:

```text
We found N things worth reviewing.
Nothing was changed.
```

For no actionable items, say `No changes are recommended. Nothing was changed.` and stop after a
short summary.

Otherwise show at most seven items, ordered by safety and likely impact:

```markdown
### 1. An instruction points to a file that is not there.

`CURRENT_PLAN.md` and `AGENTS.md`

**Where:** `AGENTS.md`
**Why it matters:** Someone following the instruction cannot reach the intended guidance.
**Recommendation:** Fix the link after confirming where it should lead.
**If you are unsure:** Leave the files unchanged until the intended destination is confirmed.
```

Use these user-facing recommendations:

- **Keep** — leave it unchanged.
- **Fix** — repair a link, label, scope, or loading problem.
- **Clarify** — make ownership or intent explicit.
- **Combine** — reduce competing editable copies while preserving every rule.
- **Archive later** — move history only after references and preservation needs are resolved.
- **Ask an owner** — do not guess when history or risk is unknown.

End with one easy approval question:

```text
Nothing has changed yet. Do you want me to prepare a no-change preview for the recommended fixes?
Say “show details” to see the technical evidence. Nothing will be changed until you review a
separate change preview and explicitly approve it.
```

Do not require the user to choose internal IDs or understand report categories to ask for help.

If more than seven decisions exist, state the total and the visible range:

```text
12 decisions need review. Showing D1–D7.
Reply “next” to see D8 onward.
```

Keep IDs stable for the audit session. `next` shows only the next unseen page; it must not
renumber, repeat, reorder, or silently revise earlier decisions.

`preview` asks for an exact no-write change preview. `keep` preserves the current file. `later`
defers the decision. `show evidence` expands the technical report.

## Change preview

After the user chooses items, restate each choice. For every requested preview show:

- exact paths and operations;
- text or safeguards that must survive;
- references that will be repaired;
- validation and rollback steps; and
- unresolved uncertainty.

End the preview with `Nothing has been changed yet.` Only an explicit instruction to **Apply this
preview**, or an equally unambiguous approval after the preview, authorizes writes.

## Advanced evidence

Show this detail only when the user asks for evidence, when a critical item requires immediate
context, or when preparing a change preview:

1. scope and read-only mode;
2. architecture map with path, consumer, scope, loading, role, and confidence;
3. evidence ledger ordered by severity;
4. preservation register;
5. internal recommendation classes;
6. proposed future tree when useful;
7. incumbent-to-future traceability;
8. evaluation plan; and
9. limitations and approval boundary.

Do not hide critical evidence behind the simple view. State the danger plainly in the first decision
item and use **Keep** or **Ask an owner** as the safe default.

## Detailed finding template

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

`agent-docs-doctor audit . --format json` emits `agent-docs-doctor.audit.v2` with:

- `mode: "read-only"`;
- deterministic engine and configuration provenance;
- an `agent-docs-doctor.inventory.v2` inventory with complete-or-partial coverage;
- deterministic `findings` with stable IDs;
- a semantic `judgment_queue`;
- explicit `limitations`.

Exact-overlap occurrences contain hashes plus path and line evidence, not copied paragraph bodies.
File `sha256` values cover raw bytes. Reference evidence includes path, line, and column so stable
finding IDs remain unique when a line contains repeated links. Absolute-style Markdown and import
targets are replaced with typed placeholders and one-way hashes so a shareable ledger does not
reproduce local filesystem paths. References inside Markdown fenced code are not treated as links.

References include `edge_type` and `resolution`. Recognized automatic imports are inventoried
recursively when they remain safe and in scope. Missing, ignored, secret-like, non-regular,
depth-limited, invalid, and out-of-root targets stay visible as typed dispositions without being
opened.

Default-pruned directories are listed in `skipped`; only `.agent-docs-doctorignore` can restore one
with an explicit negation such as `!fixtures/`. Symlinked ignore-control files are not followed and
are reported as a limitation. Ignore controls above 2 MB or 10,000 active rules stop the audit
before the repository walk. An ignored `.codex/config.toml` is not opened or used for fallback
discovery. Non-regular candidates such as named pipes and dangling symlinks are not opened and
receive distinct skip reasons.

The inventory is deterministic for a stable filesystem snapshot. Concurrent mutation can produce
read warnings or a mixed snapshot; rerun against a stable checkout when the evidence is material.

The current machine contract comprises
[`schemas/audit-v2.schema.json`](../schemas/audit-v2.schema.json) and the bounded runtime validator.
The schema encodes the complete emitted v2 shape and every expressible per-container limit. The
runtime validator additionally enforces aggregate budgets across nested references, platforms,
overlap occurrences, and finding locations, plus bounded input bytes, JSON depth, object keys,
diagnostics, and serialized report size. Those cross-container and parser resource constraints are
not fully expressible in JSON Schema. The validator accepts v1 reports for compatibility and
validates all emitted v2 nested references, overlaps, skip/warning records, coverage, provenance,
findings, and locations.

`agent-docs-doctor validate-report` exits `0` for valid output or help, `1` for a well-formed report
rejected by the runtime report contract, and `2` for usage, file I/O, or JSON parsing errors. A
standalone JSON Schema check does not replace the runtime validator. The JSON is evidence input,
not a complete semantic audit.
