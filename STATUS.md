# Project status

The public initial release is complete. The post-Fable engine is frozen at `03e9d44`, and all eight
public fixtures passed fresh, diagnosis-blind qualitative audits against that exact engine commit.

Release evidence includes the full 67-test suite, Ruff lint and format checks, Pyright, cache-free
syntax checks, the official skill validator, both report-validator paths, deterministic repeats,
self-audit, UBS, no-write comparison, and public-safety scans.

The independent Fable review used the positively identified `claude-fable-5` model and cost
$3.2546650 in total. Its findings and Codex reconciliation are recorded in
`docs/reviews/FABLE_REVIEW.md`; the review held the pre-fix commit and is not represented as a
post-fix Fable approval.

Public repository: https://github.com/BTCElectrician/agent-docs-doctor. `main` is the published
branch. No tag or packaged release was created for this closeout.
