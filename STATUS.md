# Project status

Post-Fable engine hardening is complete and the focused 66-test, Ruff, Pyright, syntax, and official
skill-validation gates are being frozen into a release-candidate commit.

Current gate: run fresh diagnosis-blind audits over all eight public fixtures against that exact
engine commit, record the results, then rerun the full release and no-write gates.

The independent Fable review used the positively identified `claude-fable-5` model and cost
$3.2546650 in total. Its findings and Codex reconciliation are recorded in
`docs/reviews/FABLE_REVIEW.md`; the review held the pre-fix commit and is not represented as a
post-fix Fable approval.

Publication target after every gate passes: https://github.com/BTCElectrician/agent-docs-doctor.
No tag or packaged release is planned for this closeout.
