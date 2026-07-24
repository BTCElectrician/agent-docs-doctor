# Forward-test model configurations

## `ft-2026-07-24-final-0.2.0-0ebdf21`

- Profile: [`fresh-agent-unpinned`](../../models/profiles/fresh-agent-unpinned.md)
- Skill and engine commit: `0ebdf21aa3f34a97cab0e4c544156532168d4bb3`
- Fixtures: all eight public fixture roots, split across two new context-isolated agents
- Prompt shape: read the committed skill, perform each audit directly, report a short new-user
  decision review and safe default, and verify no write or destructive recommendation
- Context fork: none
- Expected diagnosis or response format disclosed: no
- Prior evaluation output available: no
- Mutation and delegation authority: none
- Paid service: none
- Invocation: repository environment's installed `agent-docs-doctor 0.2.0` console entry point
- Model provenance: provider, model identifier, revision, and reasoning setting are not published
- Result: 8 of 8 fixtures passed; both agents reported unchanged HEAD and tracked code state, and
  neither read nor changed the coordinating session's three in-progress evidence documents

This is the final accepted packaged 0.2.0 qualitative set. Fresh 8-of-8 sets at `9f599c1`,
`08b9d30`, and `d35f94f` are excluded because later review or hosted Windows evidence changed
engine, installer, or validator semantics before this run.

## `ft-2026-07-24-packaged-0.2.0-c4b49a8`

- Profile: [`fresh-agent-unpinned`](../../models/profiles/fresh-agent-unpinned.md)
- Skill and engine commit: `c4b49a80c29a01cdba9644135304a299eb696353`
- Fixtures: all eight public fixture roots, split across two fresh context-isolated agents
- Prompt shape: read the committed skill, perform each audit directly, report a short new-user
  decision review and safe default, and verify no write or destructive recommendation
- Context fork: none
- Expected diagnosis or response format disclosed: no
- Prior evaluation output available: no
- Mutation and delegation authority: none
- Paid service: none
- Invocation: repository environment's installed `agent-docs-doctor 0.2.0` console entry point
- Model provenance: provider, model identifier, revision, and reasoning setting are not published
- Result: 8 of 8 fixtures passed; both agents reported unchanged HEAD and a clean worktree

This packaged snapshot passed all eight cases but is superseded for release acceptance because
post-review fixes changed ignore, installer, validator, and build behavior. Earlier configurations
below are also retained only for historical traceability.

## `ft-2026-07-16-simple-review-6243003`

- Profile: [`fresh-agent-unpinned`](../../models/profiles/fresh-agent-unpinned.md)
- Skill commit: `624300385609272fc195065f825bfa51da5500bb`
- Fixtures: `healthy-repo` and `stale-history`, one fresh agent per fixture
- Prompt shape: `At commit 6243003, use the Agent Docs Doctor skill in the repository root to audit <fixture>. I am a new user. Tell me what I need to decide. Keep the audit read-only, do not change or create repository files, do not inspect prior evaluation output, and do not delegate.`
- Context fork: none
- Expected diagnosis or response format disclosed: no
- Mutation authority: none
- Paid service: none
- Model provenance: provider, model identifier, revision, and reasoning setting are not published
- Result: 2 of 2 passed the simple no-change/actionable decision-review paths

Preliminary uncommitted runs and the superseded `1ee6307` stale-case output are excluded from the
final count.

## `ft-2026-07-15-final-hardened-03e9d44`

- Profile: [`fresh-agent-unpinned`](../../models/profiles/fresh-agent-unpinned.md)
- Engine commit: `03e9d44ddbad59d25e43eda6de802751e1667ce4`
- Fixtures: all eight public fixture roots, one fresh agent per fixture
- Prompt shape: `At repository commit 03e9d44, read SKILL.md completely, then perform the Agent Docs Doctor audit yourself on <fixture>. Use a fresh, read-only assessment. Do not inspect prior output or expected diagnoses. Do not delegate. Tell the user what should change, if anything, with evidence and an evaluation boundary.`
- Context fork: none
- Expected answer disclosed: no
- Artifact supplied: one raw synthetic fixture
- Output location: agent response plus optional unique temporary ledger outside the repository
- Mutation authority: none
- Paid service: none
- Model provenance: provider, model identifier, revision, and reasoning setting are not published

This is the final accepted hardened qualitative set. All eight agents returned substantive audits;
no blocked, interrupted, or superseded output is counted.

## `ft-2026-07-15-post-review-final`

- Profile: [`fresh-agent-unpinned`](../../models/profiles/fresh-agent-unpinned.md)
- Skill path: repository root with all eleven reproduced review fixes applied
- Prompt shape: `Read <skill-path>/SKILL.md completely. Perform the audit yourself without delegation. Audit <fixture-path> read-only and tell me what should change with supporting evidence. Do not inspect prior run output.`
- Context fork: none
- Expected answer disclosed: no
- Artifact supplied: one raw synthetic fixture
- Output location: agent response plus optional unique temporary ledger outside the repository
- Mutation authority: none
- Paid service: none
- Model provenance: provider, model identifier, revision, and reasoning setting are not published

This five-case configuration is retained for historical traceability but was superseded when the
engine changed during hardening. Its outputs are not final acceptance evidence.

## `ft-2026-07-15-final`

- Profile: [`fresh-agent-unpinned`](../../models/profiles/fresh-agent-unpinned.md)
- Skill path: repository root at the tested local revision
- Prompt shape: `Use $agent-docs-doctor at <skill-path> to audit <fixture-path> and tell me what should change. Keep the audit read-only. Do not edit or create files.`
- Context fork: none
- Expected answer disclosed: no
- Artifact supplied: one raw synthetic fixture
- Output location: agent response only; no run artifact placed inside the repository
- Mutation authority: none
- Paid service: none

This earlier configuration is retained for historical traceability and is not the final accepted post-review set. Both configurations are qualitative rather than pinned-model benchmarks. See [`FORWARD_TEST_RESULTS.md`](../../FORWARD_TEST_RESULTS.md) for case-level results and limitations.
