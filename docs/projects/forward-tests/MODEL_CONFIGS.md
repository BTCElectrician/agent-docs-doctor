# Forward-test model configurations

## `ft-2026-07-15-post-review-final`

- Profile: [`codex-fresh-agent-unpinned`](../../models/profiles/codex-fresh-agent-unpinned.md)
- Skill path: repository root with all eleven reproduced review fixes applied
- Prompt shape: `Read <skill-path>/SKILL.md completely. Perform the audit yourself without delegation. Audit <fixture-path> read-only and tell me what should change with supporting evidence. Do not inspect prior run output.`
- Context fork: none
- Expected answer disclosed: no
- Artifact supplied: one raw synthetic fixture
- Output location: agent response plus optional unique temporary ledger outside the repository
- Mutation authority: none
- Paid service: none
- Model provenance: Codex collaboration subagent; exact model identifier, revision, and reasoning setting were not exposed

This is the final post-review qualitative acceptance configuration. Each counted fixture used a distinct fresh agent. Empty, blocked, interrupted, and pre-boundary attempts were excluded.

## `ft-2026-07-15-final`

- Profile: [`codex-fresh-agent-unpinned`](../../models/profiles/codex-fresh-agent-unpinned.md)
- Skill path: repository root at the tested local revision
- Prompt shape: `Use $agent-docs-doctor at <skill-path> to audit <fixture-path> and tell me what should change. Keep the audit read-only. Do not edit or create files.`
- Context fork: none
- Expected answer disclosed: no
- Artifact supplied: one raw synthetic fixture
- Output location: agent response only; no run artifact placed inside the repository
- Mutation authority: none
- Paid service: none

This earlier configuration is retained for historical traceability and is not the final accepted post-review set. Both configurations are qualitative rather than pinned-model benchmarks. See [`FORWARD_TEST_RESULTS.md`](../../FORWARD_TEST_RESULTS.md) for case-level results and limitations.
