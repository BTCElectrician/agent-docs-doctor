# Forward-test results

Run date: 2026-07-15

Configuration: [`ft-2026-07-15-post-fable-03e9d44`](projects/forward-tests/MODEL_CONFIGS.md)

Status: qualitative skill validation, not a pinned-model performance benchmark

## Method

Each of the eight public fixtures was audited by a different fresh Codex collaboration agent against
the frozen post-Fable engine commit `03e9d44ddbad59d25e43eda6de802751e1667ce4`. Each agent received
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

Earlier behavioral runs do not count toward this acceptance set. The five-case pre-Fable set, the
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

Final behavioral result: **8 of 8 cases met the predeclared qualitative criteria.** The conflict
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

## Fable review hardening

The real `claude-fable-5` review of `9467190` then found bounded correctness, resource, privacy, test,
and documentation issues. Accepted fixes include memoized globstars, capped ignore controls, linear
single-line Markdown scanning, bare frontmatter delimiters, guarded hostile references, `~user` and
Windows-drive minimization, guarded candidate reads, stronger no-read tests, cross-process hash-seed
determinism, and public installation/encoding guidance. Full provenance, cost, accepted findings,
and bounded rejections are in [`FABLE_REVIEW.md`](reviews/FABLE_REVIEW.md).

The final eight-case set ran only after this post-Fable hardening was committed.

## Limitations and next evaluation

- The product exposed these workers only as Codex collaboration agents; the exact backing model,
  revision, and reasoning setting were not available.
- Synthetic fixtures test controlled semantics, not the full messiness of a public repository.
- Agents were judged from final audit outputs; tool traces, token telemetry, and latency were not
  available.
- Cursor and Claude client binaries were not used for behavioral fixture tests; platform claims
  came from the dated official-source reference.
- This result establishes qualitative conformance for the eight fixtures, not superiority over
  another skill, model, or instruction architecture.
