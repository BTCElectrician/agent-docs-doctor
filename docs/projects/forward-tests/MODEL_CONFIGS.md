# Forward-test model configurations

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

This is a qualitative forward-test configuration, not a pinned model benchmark. See [`FORWARD_TEST_RESULTS.md`](../../FORWARD_TEST_RESULTS.md) for case-level results and limitations.
