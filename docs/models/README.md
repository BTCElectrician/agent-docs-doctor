# Model registry

This project does not require a model API at runtime. The registry records model-bearing evaluation surfaces only.

## Active evaluation profiles

| Profile | Status | Purpose | Reproducibility limit |
|---|---|---|---|
| [Claude Fable 5](profiles/claude-fable-5.md) | Active review profile | bounded independent code, test, and documentation review | slice-based review of a fixed commit; not a final-head approval |
| [Codex fresh agent, unpinned](profiles/codex-fresh-agent-unpinned.md) | Experimental | contamination-free skill forward tests | product did not expose the exact backing model identifier |

Do not interpret an unpinned profile as a stable benchmark configuration. Add a pinned profile before public comparative performance claims.
