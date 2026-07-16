# Project status

The public release now defaults to a short decision review with stable IDs, safe defaults, and a
separate no-write preview before any implementation approval. The behavior is frozen at `6243003`.

Two fresh new-user checks passed at that exact commit: a healthy repository returned no decisions,
and a stale-authority repository returned one clear `D1 preview` choice. The earlier eight-fixture
diagnostic set remains 8 of 8 against the post-Fable engine commit `03e9d44`.

Release evidence includes the full 68-test suite, Ruff lint and format checks, Pyright, cache-free
syntax checks, the official skill validator, both report-validator paths, deterministic repeats,
self-audit, UBS, no-write comparison, and public-safety scans.

The independent Fable review used the positively identified `claude-fable-5` model and cost
$3.2546650 in total. Its findings and Codex reconciliation are recorded in
`docs/reviews/FABLE_REVIEW.md`; the review held the pre-fix commit and is not represented as a
post-fix Fable approval.

Public repository: https://github.com/BTCElectrician/agent-docs-doctor. `main` is the published
branch. No tag or packaged release was created for this closeout.
