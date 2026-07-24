# Forward-test results

## Pre-final packaged 0.2.0 snapshot

Run date: 2026-07-24

Configuration:
[`ft-2026-07-24-packaged-0.2.0-c4b49a8`](projects/forward-tests/MODEL_CONFIGS.md)

Two fresh context-isolated evaluation agents independently used the committed skill and CLI against
all eight public fixtures at
`c4b49a80c29a01cdba9644135304a299eb696353`. Each received four raw fixture paths, no expected
diagnosis, no prior-result access, no mutation authority, and no delegation authority.

| Fixture | Observed behavior | Safe default | Verdict |
|---|---|---|---|
| `healthy-repo` | Found no defect across root authority, current state, and API scope | Keep unchanged | Pass |
| `stale-history` | Connected an automatically referenced plan to retired metadata and asked for an owner-designated successor | Keep files until authority is confirmed | Pass |
| `conflicting-rules` | Identified the semantic deployment-approval conflict without mislabeling it deterministic | Require approval until an owner resolves scope | Pass |
| `bloated-repo` | Quantified two exact-overlap groups while preserving release and production-data safeguards | Keep copies until cross-client loading is verified | Pass |
| `competing-status` | Presented one plain ownership decision for three possibly scoped current-state surfaces | Keep all three until scopes are confirmed | Pass |
| `intentional-duplication` | Recognized independently exported safety repetition and recommended no change | Keep both copies | Pass |
| `lightweight-workspace` | Avoided inventing skills, hooks, consolidation, or other work | Keep unchanged | Pass |
| `thin-adapters` | Correctly mapped the Claude import and conditional Cursor rule and recommended no change | Keep unchanged | Pass |

Result: **8 of 8 cases passed.** Both agents reported an unchanged commit and clean worktree, and
neither attempted a write or recommended destructive action. The bare console command was not
globally installed in their fresh shell, which is expected before following the documented `uvx`
or `uv tool install` path; the repository environment's installed `0.2.0` entry point passed
`doctor` and all fixture audits.

This run is retained as pre-final evidence. It is superseded for release acceptance because the
subsequent independent code review changed ignore-marker handling, installer path-state checks,
validator strictness, and the declared build-backend floor. A new post-fix set is required before
release.

## Historical acceptance records

Run date: 2026-07-15

Configuration: [`ft-2026-07-15-final-hardened-03e9d44`](projects/forward-tests/MODEL_CONFIGS.md)

Status: qualitative skill validation, not a pinned-model performance benchmark

## Simple decision-review UX validation

Run date: 2026-07-16

Configuration: [`ft-2026-07-16-simple-review-6243003`](projects/forward-tests/MODEL_CONFIGS.md)

Two fresh isolated evaluation agents used the ordinary new-user prompt against commit
`624300385609272fc195065f825bfa51da5500bb`. Neither received the expected diagnosis or output
format, inspected prior evaluation artifacts, delegated, or changed repository files.

| Fixture | Required behavior | Observed behavior | Verdict |
|---|---|---|---|
| `healthy-repo` | Avoid inventing work | Reported 0 items, said nothing changed, and told the user no decision was needed | Pass |
| `stale-history` | Make one real issue easy to decide | Reported one `D1` item, used an owner-confirmed safe default, and offered one `D1 preview` response without authorizing writes | Pass |

Result: **2 of 2 simple-review cases passed.** An earlier committed candidate run showed two
conflicting reply choices for the same decision ID. That run is superseded, the wording was fixed,
and both final cases above ran against the corrected commit.

## Method

Each of the eight public fixtures was audited by a different fresh isolated evaluation agent against
the frozen hardened engine commit `03e9d44ddbad59d25e43eda6de802751e1667ce4`. Each agent received
only:

- the instruction to read the committed `SKILL.md` completely;
- one raw fixture path;
- a natural request to audit it and say what should change;
- a read-only, no-delegation, no-repository-artifact boundary; and
- an explicit prohibition on prior outputs, test expectations, review artifacts, external fixture
  descriptions, and this results document.

No prompt disclosed the intended diagnosis, suspected defect, expected recommendation, or fixture
category. Temporary ledgers were unique, outside the repository, validated, and removed. All eight
agents reported that the worktree remained clean.

Earlier behavioral runs do not count toward this acceptance set. The five-case pre-hardening set, the
three fresh cases run at `9467190`, one blocked replacement conflict attempt, and one interrupted
stale-history worker are retained only as superseded or excluded history. Code and discovery
semantics changed after `9467190`, so reusing those outputs would have overstated provenance.

## Acceptance criteria

- discover the relevant surfaces and validate the deterministic ledger;
- distinguish automatic, conditional, and manual loading;
- preserve safety rules and intentional repetition;
- identify real semantic conflict without presenting it as deterministic proof;
- recognize stale authority and unrouted scoped state;
- avoid inventing problems in healthy, thin-adapter, and lightweight fixtures;
- avoid treating exact duplication as automatically harmful context bloat;
- remain read-only; and
- propose evaluation instead of claiming an untested challenger is better.

## Final cases

| Fixture | Result | Key behavior | Verdict |
|---|---|---|---|
| `healthy-repo` | No change | Mapped root, nested API scope, and status; preserved deployment/data and schema safeguards; found no defect | Pass |
| `bloated-repo` | Exact overlap, no required change | Distinguished cross-client safety repetition from runtime bloat; identified the manual maintenance copy and offered only an evaluated optional challenger | Pass |
| `competing-status` | Medium routing issue | Treated three state files as compatible scoped facts, not contradiction; recommended a root status index without forced consolidation | Pass |
| `conflicting-rules` | Safety-critical semantic conflict | Compared root deployment approval with conditional Cursor preview automation, preserved the stricter gate, stated uncertainty, and required owner resolution | Pass with severity caveat |
| `intentional-duplication` | Keep | Preserved the repeated credential/customer-data safeguard because the subtree is independently exported | Pass |
| `lightweight-workspace` | No change | Kept the two-file research structure and rejected skills, hooks, consolidation, or extra machinery | Pass |
| `stale-history` | High stale-authority finding | Connected the automatic root instruction to retired plan metadata, preserved history, and required a real owner-designated successor | Pass |
| `thin-adapters` | No required change | Validated the Claude import and Cursor scope, preserved the release gate, and surfaced only the owner-intent boundary around cross-client frontend coverage | Pass |

Historical behavioral result: **8 of 8 cases met the predeclared qualitative criteria.** The conflict
agent used `critical` severity while also acknowledging that production impact was not established;
`high` would be a reasonable calibration. The core diagnosis and fail-closed recommendation were
still correct, so this is recorded as a severity limitation rather than hidden or counted as a
behavioral failure.

## Initial implementation hardening

Before independent review, early runs exposed and fixed ignore traversal, an overbroad secret-name
heuristic, escaping candidate symlinks, root-relative link resolution, and synthetic-fixture
contamination. These were implementation-development defects, not findings from the later fresh
peer review.

## Independent adversarial and primary review

The context-isolated adversarial review and primary reproductions fixed eleven boundary defects,
including in-root secret aliases, nested ignore semantics, Codex fallback discovery, bytecode
writes, report-shape validation, filename classification, Markdown destinations, overlap-text data
minimization, absolute-path minimization, ignored Codex config reads, and installed-layout self-audit.

## Additional hardening

Adversarial testing of `9467190` found bounded correctness, resource, privacy, test, and documentation
issues. Accepted fixes include memoized globstars, capped ignore controls, linear
single-line Markdown scanning, bare frontmatter delimiters, guarded hostile references, `~user` and
Windows-drive minimization, guarded candidate reads, stronger no-read tests, cross-process hash-seed
determinism, and public installation/encoding guidance.

The final eight-case set ran only after this hardening was committed.

## Limitations and next evaluation

- Provider, model, revision, and reasoning details for evaluation workers are not published.
- Synthetic fixtures test controlled semantics, not the full messiness of a public repository.
- Agents were judged from final audit outputs; tool traces, token telemetry, and latency were not
  available.
- Cursor and Claude client binaries were not used for behavioral fixture tests; platform claims
  came from the dated official-source reference.
- This result establishes qualitative conformance for the eight fixtures, not superiority over
  another skill, model, or instruction architecture.
