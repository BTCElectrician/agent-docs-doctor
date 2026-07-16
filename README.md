# Agent Docs Doctor

Agent instructions rarely live in one file. A repository may load `AGENTS.md`, import it through `CLAUDE.md`, add path rules for Cursor and Claude Code, expose several skills, and still point agents at three different "current" plans.

Agent Docs Doctor audits that system. It combines a deterministic, read-only evidence collector with an Agent Skill that explains platform scope, protects safety rules, and proposes an evaluated challenger architecture without silently rewriting the repository.

## What it does

- inventories recognized agent instructions, scoped rules, skills, state files, startup manifests, archive surfaces, and relevant configuration;
- labels each surface by likely consumer, loading mode, role, scope, and classification basis;
- detects exact substantive overlap, broken local references, retired metadata outside archive paths, and multiple current-state candidates;
- queues semantic work—contradictions, staleness, near-duplication, and architecture decisions—for explicit model judgment;
- records preservation requirements before recommending consolidation;
- produces an incumbent-to-challenger traceability plan and a frozen evaluation protocol.

It deliberately does not generate an `AGENTS.md` from scratch, treat prompt text as enforcement, inspect secret-like files, assign a scientific-sounding health score, claim that shorter is automatically better, or edit governance without approval.

## Why a skill and a deterministic engine

File discovery, hashes, byte counts, exact overlap, frontmatter, and local links should be reproducible. Whether two differently worded safety rules conflict—or whether repeated text is load-bearing—requires repository-aware judgment. This project keeps those evidence classes separate.

The skill is the reasoning workflow. The zero-dependency Python scripts are the evidence engine. See [the research and architecture decision](docs/RESEARCH.md).

## Supported surfaces

| Consumer | Recognized surfaces | Important caveat |
|---|---|---|
| OpenAI Codex | `AGENTS.md`, `AGENTS.override.md`, configured fallback surfaces, `.agents/skills/**/SKILL.md` | one instruction file is selected per directory; trusted-project config may add fallbacks |
| Claude Code | `CLAUDE.md`, `CLAUDE.local.md`, `.claude/rules/**/*.md`, compatible skills | imports organize ownership but still consume context |
| Cursor | nested `AGENTS.md`, `.cursor/rules/*.mdc`, compatible skills | plain `.md` in `.cursor/rules` is not an MDC project rule |
| Agent Skills consumers | any discovered `SKILL.md` | consumer extensions are not automatically portable |
| Repository state | status, handoff, work queue, startup, authority, governance, context, and plan surfaces | filename classification is inference until repository evidence confirms it |

Platform behavior changes. The dated, source-linked contract lives in [references/PLATFORM_BEHAVIOR.md](references/PLATFORM_BEHAVIOR.md).

## Install

Python 3.10 or newer is required for the deterministic scripts. There are no runtime dependencies.

For Codex and consumers that support the shared project skill directory:

```bash
git clone https://github.com/BTCElectrician/agent-docs-doctor.git \
  .agents/skills/agent-docs-doctor
```

For Claude Code, place the same folder at `.claude/skills/agent-docs-doctor`. Cursor also discovers compatible shared and platform-specific skill locations; `.agents/skills/agent-docs-doctor` is the simplest cross-client project location.

## Quick start

Ask the agent client to use the installed Agent Docs Doctor skill:

```text
Audit this repository's agent instructions with Agent Docs Doctor. Give me a short decision review
with safe defaults, and do not change any files.
```

Named-skill syntax varies by client; use the client's normal skill invocation when explicit
selection is needed.

## What a user gets

The default response is a short review, not a wall of audit data:

```text
Agent Docs Doctor found 3 items worth reviewing.
Nothing was changed.

D1 — Old plan is still being referenced
Recommendation: Fix the reference, then archive the old plan.
Safe default: Keep it unchanged until an owner confirms the current plan.

D2 — Repeated deployment rule
Recommendation: Keep both copies because they protect different agent clients.

Reply with: D1 preview, D2 keep — or say “show evidence.”
```

Choosing `preview` does not edit the repository. It only shows the proposed changes. A separate
instruction to apply that preview is required before any file changes.

When the review finds nothing actionable, it says so and recommends no change. Technical evidence,
architecture maps, and the raw deterministic ledger remain available through `show evidence`.

## Advanced: inspect the raw evidence

Run and validate the evidence engine directly when you want the underlying JSON ledger. Use a unique
temporary file:

```bash
audit_report="$(mktemp)"
python3 -B .agents/skills/agent-docs-doctor/scripts/agent_docs_doctor.py audit . --pretty > "$audit_report"
python3 -B .agents/skills/agent-docs-doctor/scripts/validate_report.py "$audit_report"
rm -f "$audit_report"
```

In PowerShell 7 or newer, capture output with `Set-Content -Encoding utf8`; legacy Windows
PowerShell 5.1 redirection may emit UTF-16LE, which is not valid input for this validator:

```powershell
$auditReport = [System.IO.Path]::GetTempFileName()
$auditJson = python3 -B .agents/skills/agent-docs-doctor/scripts/agent_docs_doctor.py audit . --pretty
$auditJson | Set-Content -Path $auditReport -Encoding utf8
python3 -B .agents/skills/agent-docs-doctor/scripts/validate_report.py $auditReport
Remove-Item $auditReport
```

When developing this repository itself, shorten the script paths to `scripts/...`. The entry
points disable bytecode writes, and `-B` adds an explicit interpreter-level guard. The scripts
write only to standard output unless your shell redirects it.

Exact evidence does not settle intent. The review separates what was observed, what was inferred,
and what still needs an owner decision.

## Read-only and safety model

The default audit:

- walks only the requested root;
- honors a documented subset of root and nested `.gitignore` files plus root `.ignore` and `.agent-docs-doctorignore`, including slash-aware `*`, `?`, `**`, negation, and the rule that a file cannot be re-included while its parent directory remains excluded;
- does not follow symlinked ignore-control files and records that limitation in `skipped`;
- prunes `.git`, `.hg`, `.svn`, `node_modules`, `.venv`, `venv`, `dist`, `build`, `.next`, `coverage`, `fixtures`, `.fixtures`, `testdata`, and `__pycache__` by default, recording each pruned directory in `skipped`; only an explicit rule such as `!fixtures/` in `.agent-docs-doctorignore` restores a needed default;
- fails closed before walking when an ignore-control file exceeds the 2 MB read limit or 10,000 active rules;
- skips secret- or credential-like filenames;
- follows only in-root symlinks whose targets are auditable, non-ignored, non-secret-like regular files;
- excludes its own installed package from a parent-repository audit while continuing to inventory other installed skills;
- refuses to read candidate files above a fixed safety limit while reporting the limitation;
- emits relative paths, raw-byte file hashes, and no timestamps, making output reproducible and less likely to leak local paths;
- omits duplicated paragraph bodies and sanitizes absolute-style reference targets in JSON evidence;
- never writes into the target repository.

Ignore files are exposure controls, not security sandboxes. Shell tools may bypass platform-specific ignore behavior. Use filesystem permissions and verified fail-closed controls for actual enforcement.

## Evaluation philosophy

Do not promote a challenger because it looks cleaner. Freeze representative tasks, both documentation conditions, client/model settings, and a task-specific judge rubric. Compare correctness and safety first; count irrelevant reads, stale influence, unnecessary questions or approvals, verification quality, latency, and tokens when observable. Resource reductions count only if quality still passes.

See [the full evaluation protocol](references/EVALUATION_PROTOCOL.md) and [forward-test results](docs/FORWARD_TEST_RESULTS.md).

## Limitations

- The ignore matcher intentionally implements a useful subset of Git ignore semantics, not every escaping or repository-boundary edge case in Git's specification.
- Frontmatter parsing is conservative and dependency-free; complex nested YAML remains raw evidence for model review.
- The local-link parser handles ordinary single-line Markdown destinations; malformed or multiline inline-link constructs remain model-review evidence.
- A repository changed concurrently with an audit can produce warnings or a mixed snapshot; rerun
  against a stable checkout when evidence will support a consequential decision.
- Filename-based consumer and role classifications are labeled inference.
- Exact overlap is deterministic; semantic equivalence and contradiction are not.
- The tool does not inspect global user/team rules outside the requested repository.
- A report cannot determine whether undocumented incident history remains operationally necessary.
- Platform documentation and client behavior can drift after the verification date.

## Development

```bash
python3 -B -m unittest discover -s tests -v
python3 -B scripts/check_python_syntax.py scripts tests
```

Release maintainers also run the skill validator bundled with their current client. That optional
validator is not a source dependency and its installation path is client-managed.

Validator exits are stable across both entry points: `0` means valid output or help, `1` means a
well-formed report failed schema validation, and `2` means usage, file I/O, or JSON parsing failed.

Synthetic fixtures cover healthy, bloated, conflicting, stale, competing-state, thin-adapter, intentionally duplicated, and lightweight non-code repositories. They contain no private source documents.

Read [CONTRIBUTING.md](CONTRIBUTING.md) before changing discovery rules or report semantics.

## Maturity and license

Status: **public initial release**. The deterministic core, synthetic fixture suite, independent
Fable review reconciliation, and fresh eight-case behavioral acceptance record are complete.

Licensed under [Apache License 2.0](LICENSE).
