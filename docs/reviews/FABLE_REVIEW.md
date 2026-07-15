# Fable review and Codex reconciliation

- Review date: 2026-07-15
- Reviewed commit: `9467190`
- Surface: Claude Code CLI 2.1.170 direct print mode
- Model: `claude-fable-5`, positively reported in `modelUsage`
- Effort: high
- Tools, web, and session persistence: disabled
- Total actual cost: **$3.2546650**, including the successful model probe

The review was assessment-only. Fable received bounded committed slices as direct prompt data and
could not inspect the repository, edit files, use tools, browse, delegate, push, or publish. Failed
authentication or prompt-size attempts made no model call, cost $0, and are excluded. The public
prompt and execution protocol are in [`FABLE_REVIEW_PROMPT.md`](FABLE_REVIEW_PROMPT.md).

## Run record

| Slice | Run ID | Cost | Result |
|---|---|---:|---|
| model identity probe | not retained as a review run | $0.0626070 | exact model accepted |
| `scripts/doctorlib.py` lines 1–220 | `0f2a3b99-d9bc-48d7-bbe2-6b507c05dc4e` | $0.3779185 | findings returned |
| `scripts/doctorlib.py` lines 221–520 | `3b161c79-ece8-4763-ac47-77b133983059` | $0.5041575 | findings returned |
| `scripts/doctorlib.py` lines 521–end | `a53e6307-1460-4366-9787-768f364494ba` | $0.7917785 | findings returned |
| `tests/test_doctorlib.py` lines 1–350 | `e7fa527a-e3b8-44fa-9363-7fe231f66872` | $0.4556810 | findings returned |
| `tests/test_doctorlib.py` lines 351–end | `01096b4f-58dd-49f6-b70b-816915ad2450` | $0.4363825 | findings returned |
| `README.md`, `SKILL.md`, report schema | `5b0629cd-573b-43f2-ad90-4eb54642d4e6` | $0.4307835 | release hold returned |
| findings-only synthesis | `dd2b9b12-7fc5-405d-9882-b5a33ca99b55` | $0.1953565 | release hold returned |

No review call reported permission denials or tool/web use.

## Accepted findings

Codex reproduced these issues before changing them and implemented bounded remedies:

1. Repository ignore negations could restore privacy-oriented default exclusions. Ordinary
   `.gitignore` and `.ignore` negations can no longer override tool defaults; the explicit
   `.agent-docs-doctorignore` control retains opt-in restoration.
2. Recursive globstar matching could exhaust recursion exponentially. The matcher is memoized and
   has an adversarial subprocess regression.
3. Ignore controls had no byte or rule caps. Controls above 2 MB or 10,000 active rules now stop the
   audit before the walk, with size checked before and after the read.
4. Repeated unterminated Markdown link starts could trigger quadratic scanning. The parser now
   advances linearly over ordinary single-line links and has a bounded adversarial regression.
5. Frontmatter accepted delimiter prefixes such as `----` and `--- draft`. Closing delimiters must
   now be bare `---` lines, including CRLF-normalized input.
6. Hostile reference values could raise outside the resolver guard. Resolution, containment, and
   existence checks now catch filesystem and value errors; invalid targets are minimized to a
   typed placeholder and hash.
7. `~user/...` references and Windows drive paths could evade absolute-path minimization. Both are
   now classified before URL schemes and serialized only as typed placeholders plus hashes.
8. Unguarded repeated stats could abort when a candidate disappeared. Each candidate is collected
   once through the guarded reader; disappearance becomes a warning with a regression.
9. No-read tests relied on permissions or guarded only one `Path` API. Secret, ignored-config, and
   symlinked-ignore tests now intercept `open`, `read_text`, and `read_bytes` and assert sentinels do
   not appear in serialized output.
10. The out-of-root relative reference case existed but did not assert its privacy disposition. It
    now explicitly requires `inside_root: false`, `exists: null`, and no broken-link finding.
11. The unit determinism check reused one interpreter. It now compares subprocesses with distinct
    `PYTHONHASHSEED` values; the release gate also performs independent repeat comparisons.
12. The bounded FIFO regression allows a 10-second ceiling to reduce slow-runner flakiness without
    permitting an unbounded hang.
13. Public installation and invocation guidance is client-neutral, names the intended public URL,
    warns about Windows PowerShell 5.1 encoding, and removes an unresolvable validator placeholder.

## Rejected or bounded findings

- Full descriptor-relative traversal was not added. The scanner is a local read-only evidence tool,
  not a security boundary for a repository being actively modified by an adversary. Filesystem
  errors are caught, and the documented contract requires rerunning consequential audits against a
  stable checkout.
- The auditor-specific restore file remains intentional. It is the explicit way to include a
  default-pruned fixture or testdata directory; general repository ignore files cannot do so.
- Auditing both an in-root symlink alias and its target is intentional evidence about two loaded
  names. Secret, ignored, escaping, dangling, and non-regular targets remain excluded.
- The nested `.gitignore` secret-path observation was non-actionable because the control filename
  is fixed and is not a candidate secret surface.
- Paragraph-block worst-case cost and duplicate alias behavior were excerpt limitations without a
  reproduced correctness or safety failure.
- The syntax-check regression already used `check=False`, so the claimed unreachable return-code
  assertion was not present in the reviewed committed test.

## Verdict

Fable's synthesis correctly returned **HOLD** for commit `9467190`. This document records Codex's
subsequent reconciliation; it does not relabel that result as Fable approval of the fix commit.
Release still requires the full deterministic gates and fresh post-fix behavioral acceptance set.
