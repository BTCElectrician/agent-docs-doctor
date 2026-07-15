# Claude Fable 5

- Status: Active review profile
- Consumer: Claude Code CLI 2.1.170 direct print mode
- First used: 2026-07-15
- Exact model ID: `claude-fable-5`, positively reported in CLI `modelUsage`
- Effort: high
- Tools and web: disabled
- Session persistence: disabled
- Repository mutation: forbidden by prompt
- Reviewed revision: `9467190`
- Review shape: fresh bounded source slices followed by a findings-only synthesis
- Actual total cost: $3.2546650, including the successful model probe

Use this profile for evidence-backed peer review of a fixed snapshot. The 2026-07-15 run produced
findings that Codex independently reproduced and reconciled. It did not review or approve the later
fix commit, so the artifact must not be represented as a final-head Fable sign-off.
