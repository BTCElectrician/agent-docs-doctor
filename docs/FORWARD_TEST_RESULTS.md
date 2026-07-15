# Forward-test results

Run date: 2026-07-15

Configuration: [`ft-2026-07-15-post-review-final`](projects/forward-tests/MODEL_CONFIGS.md)

Status: qualitative skill validation, not a pinned-model performance benchmark

## Method

Each case used a fresh Codex subagent with no inherited conversation turns. The agent received only:

- the local skill path;
- one raw synthetic fixture path;
- the natural request to audit the repository and say what should change;
- a read-only, no-file-creation boundary.

Prompts did not disclose the intended diagnosis, suspected bug, expected fix, or fixture category. Agents wrote temporary ledgers only outside the repository. No forward-test artifact was left where a later agent could discover it.

The final accepted set ran after the complete review hardening pass. Earlier exploratory and pre-boundary runs are not counted. One replacement conflict run returned no audit and then a blocked coordination response; one superseded stale-history worker was interrupted after it failed to return. Neither is acceptance evidence. Every counted case below came from a different fresh agent instructed to perform the audit directly without delegation.

## Acceptance criteria

- discover the relevant surfaces and validate the deterministic ledger;
- distinguish automatic, conditional, and manual loading;
- preserve safety rules and intentional repetition;
- identify real semantic conflict without calling it deterministic proof;
- recognize stale authority;
- avoid inventing problems in a healthy fixture;
- avoid forcing a non-code workspace into engineering machinery;
- remain read-only;
- propose evaluation rather than claim a challenger is better.

## Final cases

| Fixture | Result | Key behavior | Verdict |
|---|---|---|---|
| `healthy-repo` | No change | Mapped root, state, and nested API scope; preserved deployment/data and schema safeguards; found no deterministic or semantic defect | Pass |
| `conflicting-rules` | High semantic conflict | Compared root deployment approval with conditional Cursor preview automation; stated the ambiguity and alternative explanation; recommended owner decision and fail-closed production control | Pass |
| `intentional-duplication` | No change | Confirmed exact overlap but preserved both credential/customer-data rules because the subtree is exported independently | Pass |
| `stale-history` | High stale-authority finding | Connected the root link to retired metadata, preserved historical material, and correctly kept the negative fixture unchanged | Pass |
| `lightweight-workspace` | One low-cost pointer | Kept the two-file research structure, suggested only a short status pointer, and rejected skills/hooks/extra planning machinery | Pass |

Final behavioral result: **5 of 5 cases met the predeclared qualitative criteria.** This does not establish superiority over another skill, model, or instruction architecture.

## Initial implementation defects hardened before review

1. **Ignore traversal:** the first unit run over-pruned a directory in a case where the parent remained traversable. The initial correction was later replaced by the stricter parent-exclusion semantics described below.
2. **Secret-rule false exclusion:** an adversarial code pass found that a broad filename heuristic could skip a legitimate `secret-handling-rules.md`. Secret skipping now uses exact sensitive names and key/certificate suffixes; a regression test proves safety guidance remains visible.
3. **Escaping symlink:** an adversarial code pass found that a candidate symlink could point outside the requested audit root. Escaping symlinks are now skipped with an explicit reason; a regression test proves the external file is not read.
4. **Root-relative Markdown links:** root-relative links were classified as outside the repository. They now resolve from the audit root; a regression test covers the case.
5. **Fixture contamination:** a repository self-audit initially included synthetic fixtures as live authority. Common fixture/testdata directories are now excluded when auditing a parent, while auditing a fixture root directly still works.

## Independent adversarial and primary-review defects

All seven findings from a context-isolated adversarial code review were reproduced and fixed:

1. In-root symlinks could alias a secret-like file and expose its metadata.
2. Nested `.gitignore` files were not applied, and negation could incorrectly restore a file beneath an excluded parent.
3. Codex fallback filenames configured in `.codex/config.toml` were omitted from discovery and loading classification.
4. An installed CLI could write `__pycache__` into the audited repository.
5. The report validator accepted incomplete shapes and could crash on a non-string finding identifier.
6. Prefix-based filename classification mislabeled history and platform/loading behavior.
7. The Markdown-link parser produced false broken-reference findings for titles and balanced parentheses.

Two additional primary-review data-minimization findings were also reproduced and fixed:

8. Exact-overlap occurrences copied normalized paragraph bodies into the JSON ledger; occurrences now retain only hash, relative path, and line evidence.
9. Absolute-style Markdown targets could serialize private filesystem paths; the ledger now emits a typed placeholder and one-way hash.

The operator-requested final acceptance set occurred after all nine reproduced fixes above.

## Final boundary review

Two further boundary reproductions were fixed before the counted runs:

1. Fallback discovery opened and used an ignored `.codex/config.toml`; ignored configuration is now neither opened nor used.
2. A repository-local installation could inventory its own `SKILL.md` and `STATUS.md`; the running auditor package is now explicitly skipped while other installed skills remain auditable.

The final 5-of-5 result therefore reflects all eleven review fixes and the full deterministic suite.

## Limitations and next evaluation

- The product exposed these workers only as Codex collaboration subagents; it did not expose the exact backing model identifier, revision, or reasoning setting. The configuration is therefore intentionally unpinned and cannot support model-level reproducibility or cost/latency claims.
- Synthetic fixtures test controlled semantics, not the full messiness of a public repository.
- Agents were judged from final audit outputs; tool traces and token telemetry were unavailable.
- Cursor and Claude client binaries were not executed; platform claims came from current official documentation.
- Public release should add pinned-client integration checks and a blinded incumbent-versus-challenger evaluation on representative public repositories.
