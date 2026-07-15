# Forward-test results

Run date: 2026-07-15

Configuration: [`ft-2026-07-15-final`](projects/forward-tests/MODEL_CONFIGS.md)

Status: qualitative skill validation, not a pinned-model performance benchmark

## Method

Each case used a fresh Codex subagent with no inherited conversation turns. The agent received only:

- the local skill path;
- one raw synthetic fixture path;
- the natural request to audit the repository and say what should change;
- a read-only, no-file-creation boundary.

Prompts did not disclose the intended diagnosis, suspected bug, expected fix, or fixture category. Agents wrote temporary ledgers only outside the repository. No forward-test artifact was left where a later agent could discover it.

The final accepted set used the same hardened code. Earlier exploratory runs are excluded from the acceptance set because privacy-boundary code changed while that wave was active.

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
| `healthy-repo` | No change | Mapped root, state, and nested API scope; preserved deployment/data and schema safeguards; noted a conditional Codex cwd nuance | Pass |
| `conflicting-rules` | High semantic conflict | Compared root deployment approval with conditional Cursor preview automation; stated the ambiguity and alternative explanation; recommended owner decision and fail-closed production control | Pass |
| `intentional-duplication` | No change | Confirmed exact overlap but preserved both credential/customer-data rules because the subtree is exported independently | Pass |
| `stale-history` | High stale-authority finding | Connected the root link to retired metadata, preserved historical material, and correctly kept the negative fixture unchanged | Pass |
| `lightweight-workspace` | One low-cost pointer | Kept the two-file research structure, suggested only a short status pointer, and rejected skills/hooks/extra planning machinery | Pass |

Final behavioral result: **5 of 5 cases met the predeclared qualitative criteria.** This does not establish superiority over another skill, model, or instruction architecture.

## Failures found and hardened before acceptance

1. **Ignore negation traversal:** the first unit run pruned an ignored directory before a later negation could restore a specific instruction file. Directory pruning now checks whether a negation may re-include a descendant; a regression test covers it.
2. **Secret-rule false exclusion:** an adversarial code pass found that a broad filename heuristic could skip a legitimate `secret-handling-rules.md`. Secret skipping now uses exact sensitive names and key/certificate suffixes; a regression test proves safety guidance remains visible.
3. **Escaping symlink:** an adversarial code pass found that a candidate symlink could point outside the requested audit root. Escaping symlinks are now skipped with an explicit reason; a regression test proves the external file is not read.
4. **Root-relative Markdown links:** root-relative links were classified as outside the repository. They now resolve from the audit root; a regression test covers the case.
5. **Fixture contamination:** a repository self-audit initially included synthetic fixtures as live authority. Common fixture/testdata directories are now excluded when auditing a parent, while auditing a fixture root directly still works.

The accepted five-case run occurred after these changes and the full deterministic suite passed.

## Limitations and next evaluation

- The product did not expose the exact backing model identifier or reasoning setting, so these runs cannot support model-level reproducibility or cost/latency claims.
- Synthetic fixtures test controlled semantics, not the full messiness of a public repository.
- Agents were judged from final audit outputs; tool traces and token telemetry were unavailable.
- Cursor and Claude client binaries were not executed; platform claims came from current official documentation.
- Public release should add pinned-client integration checks and a blinded incumbent-versus-challenger evaluation on representative public repositories.
