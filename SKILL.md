---
name: agent-docs-doctor
description: Audit and improve agent-facing repository documentation across Codex, Claude Code, Cursor, and compatible Agent Skills consumers. Use when asked to inspect AGENTS.md, CLAUDE.md, .claude/rules, .cursor/rules, skills, status or handoff files, startup manifests, instruction conflicts, duplicated rules, stale plans, context bloat, authority ambiguity, or an incumbent-versus-challenger documentation redesign. Default to read-only evidence collection and require explicit approval before rewriting or migrating repository governance.
---

# Agent Docs Doctor

Audit the instruction system around a repository, not just one file. Build an evidence ledger first, apply labeled judgment second, and never equate shorter documentation with safer documentation.

## Operating contract

- Treat the repository as read-only unless the user explicitly approves a proposed rewrite or migration.
- Inspect recognized agent-facing surfaces only. Do not open secret-like files, credential stores, private keys, or ignored paths.
- Distinguish platform-verified loading behavior from filename-based inference. Read [references/PLATFORM_BEHAVIOR.md](references/PLATFORM_BEHAVIOR.md) when platform loading or precedence affects a finding.
- Preserve production, deployment, destructive-operation, privacy, authentication, financial, legal, health, data-integrity, ownership, rollback, and incident-derived safeguards.
- Label deterministic evidence, model judgment, uncertainty, and user decisions separately.
- Make the default human response a short decision review. Keep technical detail available on request instead of leading with it.
- Do not assign a scientific-sounding health score. Use the evidence and severity rubric in [references/AUDIT_RUBRIC.md](references/AUDIT_RUBRIC.md).

## Workflow

### 1. Establish scope

Confirm the repository root and requested output. Note any user-declared private paths or additional exclusions. Do not broaden the audit to sibling repositories without permission.

### 2. Produce the deterministic ledger

Run:

```bash
agent-docs-doctor doctor
agent-docs-doctor audit <repo> --format json --pretty
```

The audit command validates its generated report before emitting it. If the console command is not
available, stop and tell the user to repair or install the package; do not improvise a different
scanner. Keep any explicitly requested saved report outside the audited repository unless the user
chooses a path inside it.

Review skipped files, warnings, discovered surfaces, exact-overlap groups, local references, archive classification, and deterministic findings. The ledger omits overlap paragraph bodies and sanitizes absolute-style reference targets. Default-pruned directories are reported in `skipped`; only `.agent-docs-doctorignore` can restore one with an explicit negation such as `!fixtures/`. Oversized ignore controls fail closed before the walk. A skipped or unreadable file is an audit limitation, not proof that it is irrelevant.

Recognized `CLAUDE.md` imports are typed automatic-import edges. The engine inventories safe,
in-root imported files even when their filenames would not otherwise match discovery heuristics.
Missing, ignored, secret-like, non-regular, invalid, depth-limited, and out-of-root imports remain
visible as typed dispositions and are not opened.

Treat a repository that changes during collection as a potentially mixed snapshot. If warnings or
external evidence suggest concurrent mutation, rerun against a stable checkout before relying on
the ledger for a consequential decision.

The supported installer keeps this skill outside the repository being audited. Do not clone the
full project into a repository-level skill folder, because the project's own documentation would
then become legitimate audit evidence. Other installed repository skills remain in scope.

### 3. Reconstruct the instruction architecture

For each surface, explain:

- consumer and scope;
- verified, conditional, manual, or inferred loading;
- authority, current state, procedure, reference, history, or adapter role;
- inbound and outbound references;
- whether another file claims the same source-of-truth role.

Do not infer that a file is automatically loaded merely because its name sounds important.

### 4. Diagnose with evidence

Read [references/AUDIT_RUBRIC.md](references/AUDIT_RUBRIC.md). Cite paths and line ranges for every semantic finding. Treat exact overlap and broken local references as deterministic; treat near-duplication, contradiction, staleness, and suitability for a skill or hook as model judgment.

For apparent conflicts, state both rules, the scopes in which each applies, the likely resolution, and confidence. Do not call intentional safety repetition a defect without explaining the loading boundary it protects.

### 5. Recommend without erasing safeguards

Classify each recommendation as keep, tighten, consolidate, pointer, scoped rule, skill, executable control, current state, reference, archive, human decision, or no change. Pair every consolidation or archive proposal with preservation and traceability notes.

Translate those internal classes into plain user choices: **Keep**, **Fix**, **Clarify**, **Combine**,
**Archive later**, or **Ask an owner**. When evidence or operational history is incomplete, use
**Keep** as the safe default.

When a redesign is useful, propose a challenger tree and an incumbent-to-challenger traceability table. Do not create or overwrite the challenger unless the user explicitly approves implementation.

### 6. Define evaluation before claiming improvement

Read [references/EVALUATION_PROTOCOL.md](references/EVALUATION_PROTOCOL.md) before recommending adoption. Freeze representative tasks, the incumbent, the challenger, model settings, and judge rubric. Include safety adherence, correctness, unnecessary reads or approvals, verification quality, latency, and token use when observable. Do not claim the challenger is better before the evaluation supports it.

### 7. Give the simple decision review

Read [references/REPORT_SCHEMA.md](references/REPORT_SCHEMA.md). Make its simple review the default
response. Start with the number of items worth reviewing and the sentence **Nothing was changed.**

Show no more than seven decision items at once. Give each one a stable ID such as `D1`, a plain
title, the affected path or scope, one short explanation, one recommendation, and a safe default.
Lead with a critical safety or authority item when one exists. Do not lead with the architecture map,
raw JSON, evidence classes, or terms such as incumbent and challenger.

If more than seven decisions exist, say how many total decisions exist and that the current page
shows `D1` through `D7`. End with `Reply next to see D8 onward.` When the user replies `next`, show
the next unseen decisions in the same audit session without renumbering, repeating, or silently
changing earlier recommendations.

End with one easy reply format:

```text
Reply with: D1 preview, D2 keep, D3 later — or say “show evidence.”
```

Show one choice per decision ID; never present conflicting choices for the same ID in the example
reply. Add `or “next”` only when unseen decisions remain.

`preview` asks for an exact no-write change preview. `keep` rejects the recommendation and
preserves the current file. `later` defers it. `show evidence` expands the technical basis.

When the user selects recommendations that would change files, restate the decisions and show an
exact change preview with paths, operations, preservation notes, tests, and rollback. Do not edit
yet. Only a later, explicit instruction to **Apply this preview** or an equally unambiguous approval
after seeing that preview authorizes implementation.

If there are no actionable items, say so plainly, state that nothing changed, and stop. Do not
invent a decision queue.

## Approved migration only

After the user explicitly approves the displayed change preview, read [references/MIGRATION_GUIDE.md](references/MIGRATION_GUIDE.md). Preserve the incumbent for rollback, make path-scoped edits, update references, validate platform syntax, show the diff, and rerun the audit. Stop if a proposed change would weaken a safeguard whose operational history is unknown.
