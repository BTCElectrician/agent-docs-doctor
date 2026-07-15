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
- Do not assign a scientific-sounding health score. Use the evidence and severity rubric in [references/AUDIT_RUBRIC.md](references/AUDIT_RUBRIC.md).

## Workflow

### 1. Establish scope

Confirm the repository root and requested output. Note any user-declared private paths or additional exclusions. Do not broaden the audit to sibling repositories without permission.

### 2. Produce the deterministic ledger

Run:

```bash
python3 scripts/agent_docs_doctor.py audit <repo> --pretty > /tmp/agent-docs-audit.json
python3 scripts/validate_report.py /tmp/agent-docs-audit.json
```

If the skill is installed outside the target repository, resolve `scripts/` relative to this `SKILL.md`. Keep temporary output outside the audited repository unless the user requests an artifact there.

Review skipped files, warnings, discovered surfaces, exact-overlap groups, local references, archive classification, and deterministic findings. A skipped or unreadable file is an audit limitation, not proof that it is irrelevant.

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

When a redesign is useful, propose a challenger tree and an incumbent-to-challenger traceability table. Do not create or overwrite the challenger unless the user explicitly approves implementation.

### 6. Define evaluation before claiming improvement

Read [references/EVALUATION_PROTOCOL.md](references/EVALUATION_PROTOCOL.md) before recommending adoption. Freeze representative tasks, the incumbent, the challenger, model settings, and judge rubric. Include safety adherence, correctness, unnecessary reads or approvals, verification quality, latency, and token use when observable. Do not claim the challenger is better before the evaluation supports it.

### 7. Report

Use the structure in [references/REPORT_SCHEMA.md](references/REPORT_SCHEMA.md). Lead with safety- or authority-critical findings, then the architecture map, evidence ledger, recommendations, challenger, evaluation plan, limitations, and approval boundary.

## Approved migration only

After explicit approval, read [references/MIGRATION_GUIDE.md](references/MIGRATION_GUIDE.md). Preserve the incumbent for rollback, make path-scoped edits, update references, validate platform syntax, show the diff, and rerun the audit. Stop if a proposed change would weaken a safeguard whose operational history is unknown.
