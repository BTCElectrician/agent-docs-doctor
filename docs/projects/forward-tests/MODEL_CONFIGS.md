# Forward-test model configurations

## `ft-2026-07-15-post-fable-03e9d44`

- Profile: [`codex-fresh-agent-unpinned`](../../models/profiles/codex-fresh-agent-unpinned.md)
- Engine commit: `03e9d44ddbad59d25e43eda6de802751e1667ce4`
- Fixtures: all eight public fixture roots, one fresh agent per fixture
- Prompt shape: `At repository commit 03e9d44, read SKILL.md completely, then perform the Agent Docs Doctor audit yourself on <fixture>. Use a fresh, read-only assessment. Do not inspect prior output or expected diagnoses. Do not delegate. Tell the user what should change, if anything, with evidence and an evaluation boundary.`
- Context fork: none
- Expected answer disclosed: no
- Artifact supplied: one raw synthetic fixture
- Output location: agent response plus optional unique temporary ledger outside the repository
- Mutation authority: none
- Paid service: none
- Model provenance: Codex collaboration agent; exact model identifier, revision, and reasoning setting were not exposed

This is the final accepted post-Fable qualitative set. All eight agents returned substantive audits;
no blocked, interrupted, or superseded output is counted.

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

This five-case configuration is retained for historical traceability but was superseded when the
engine changed after Fable review. Its outputs are not final acceptance evidence.

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
