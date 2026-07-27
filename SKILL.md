---
name: agent-docs-doctor
description: Audit and improve agent-facing repository documentation across Codex, Claude Code, Cursor, and compatible Agent Skills consumers. Use when asked to inspect AGENTS.md, CLAUDE.md, .claude/rules, .cursor/rules, skills, status or handoff files, startup manifests, instruction conflicts, duplicated rules, stale plans, context bloat, authority ambiguity, or an incumbent-versus-challenger documentation redesign. Default to read-only evidence collection and require explicit approval before rewriting or migrating repository governance.
---

# Agent Docs Doctor

Audit the instruction system around a repository, not just one file. First explain what was found in ordinary language, then keep the supporting technical record available when requested. Never equate shorter documentation with safer documentation.

## Operating contract

- Treat the repository as read-only unless the user explicitly approves a proposed rewrite or migration.
- Inspect recognized agent-facing surfaces only. Do not open secret-like files, credential stores, private keys, or ignored paths.
- Treat a secret-like name in any relative path component as a never-read boundary.
- Treat `inventory`, `audit`, `doctor`, and `validate-report` as distinct from user-level skill
  installation. Never imply that an audit approval authorizes `install-skill` or `uninstall-skill`,
  or that an installer plan authorizes repository edits.
- Distinguish platform-verified loading behavior from filename-based inference. Read [references/PLATFORM_BEHAVIOR.md](references/PLATFORM_BEHAVIOR.md) when platform loading or precedence affects a finding.
- Preserve production, deployment, destructive-operation, privacy, authentication, financial, legal, health, data-integrity, ownership, rollback, and incident-derived safeguards.
- Keep deterministic evidence, model judgment, uncertainty, and user decisions separate in the technical record.
- Make the default response a short, plain-language diagnosis. Keep technical detail available only on request instead of leading with it.
- Do not assign a scientific-sounding health score. Use the evidence and severity rubric in [references/AUDIT_RUBRIC.md](references/AUDIT_RUBRIC.md).

## Workflow

### 1. Establish scope

Confirm the repository root and requested output. Note any user-declared private paths or additional exclusions. Do not broaden the audit to sibling repositories without permission.

### 2. Gather the facts

Run:

```bash
agent-docs-doctor doctor
agent-docs-doctor audit <repo> --format json --pretty
```

The audit command validates its generated report before emitting it. If the console command is not
available, stop and tell the user to repair or install the package; do not improvise a different
scanner. Keep any explicitly requested saved report outside the audited repository unless the user
chooses a path inside it.

Review skipped files, warnings, discovered surfaces, exact-overlap groups, local references, archive
classification, and findings. The technical record omits overlap paragraph bodies, emits only
a fixed privacy-safe frontmatter summary, and masks absolute and out-of-root reference targets.
Secret-like names and multiply-linked candidate files are not opened.

Default-pruned directories are reported in `skipped`; only `.agent-docs-doctorignore` can restore
one with an explicit negation such as `!fixtures/`. Oversized ignore controls fail closed before
the walk. Traversal entries, read bytes, candidates, ignore rules, imports, references, paragraph
blocks, findings, finding locations, and skip evidence are bounded. The active values are in
`engine.configuration` and `coverage.limits`.

Interpret `coverage.status: complete` only within the engine's declared discovery scope. A custom
ignored candidate or directory, unreadable traversal point, concurrent disappearance, non-regular
candidate, or exhausted cap makes coverage partial. A partial or skipped audit is a limitation,
not proof that omitted material is irrelevant or safe. Do not give a clean bill of health from an
incomplete scan.

Recognized `CLAUDE.md` imports are typed automatic-import edges. The engine inventories safe,
in-root imported files even when their filenames would not otherwise match discovery heuristics.
Missing, ignored, secret-like, non-regular, invalid, depth-limited, and out-of-root imports remain
visible as typed dispositions and are not opened.

Treat a repository that changes during collection as a potentially mixed snapshot. If warnings or
external evidence suggest concurrent mutation, rerun against a stable checkout before relying on
the ledger for a consequential decision.

On POSIX, reads and directory enumeration fail closed unless the opened descriptor resolves to the
exact intended path under the requested root. Non-printing Unicode paths are represented only by
one-way hash markers in evidence displays. Automatic-import expansion is deduplicated and bounded
by the aggregate reference cap; exhaustion makes coverage partial.

The supported installer keeps this skill outside the repository being audited. Its preview is
portable, no-write, and emits a deterministic current-plan fingerprint. Applying an install,
update, or uninstall is an explicit user-level mutation and requires
`--apply PLAN_TOKEN_FROM_PREVIEW`; it is not part of the audit. The fingerprint binds the payload,
action, client, resolved destination, ancestor identities, expected state, and backup reservation,
and proves current state equality rather than prior human review. Apply uses descriptor-relative
operations on supported Darwin/Linux runtimes and fails closed elsewhere. The installer rejects
unmanaged or aliased destinations and preserves managed updates or uninstalls in tool-reserved
backup containers that it never automatically deletes. Preserved extra contents may remain
user-owned.

Do not clone the full project into a repository-level skill folder, because the project's own
documentation would then become legitimate audit evidence. Other installed repository skills
remain in scope.

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

### 7. Give the simple diagnosis

Read [references/REPORT_SCHEMA.md](references/REPORT_SCHEMA.md). Make its simple review the default
response. Start with what was found and the sentence **Nothing was changed.**

Show no more than seven items at once. Give each one a plain title, where it was found, why it
matters, one recommendation, and the safe thing to do when intent is unknown. Lead with a critical
safety or authority item when one exists. Do not lead with an architecture map, raw JSON, evidence
classes, decision IDs, or terms such as incumbent and challenger.

If more than seven decisions exist, say how many total decisions exist and that the current page
shows `D1` through `D7`. End with `Reply next to see D8 onward.` When the user replies `next`, show
the next unseen decisions in the same audit session without renumbering, repeating, or silently
changing earlier recommendations.

End with one easy approval question:

```text
Nothing has changed yet. Do you want me to prepare a no-change preview for the recommended fixes?
```

Offer `show details` when technical evidence would help. Add `or “next”` only when unseen items
remain.

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
