# Model registry

This project does not require a model API at runtime. The registry records model-bearing evaluation surfaces only.

## Active evaluation profiles

| Profile | Status | Purpose | Reproducibility limit |
|---|---|---|---|
| [Fresh evaluation agent, unpinned](profiles/fresh-agent-unpinned.md) | Experimental | contamination-free skill forward tests | provider, model identifier, and reasoning configuration are not published |

Do not interpret an unpinned profile as a stable benchmark configuration. Add a pinned profile before public comparative performance claims.
