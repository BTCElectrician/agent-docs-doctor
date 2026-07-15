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
| OpenAI Codex | `AGENTS.md`, `AGENTS.override.md`, configured-looking surfaces, `.agents/skills/**/SKILL.md` | one instruction file is selected per directory; fallbacks are alternatives |
| Claude Code | `CLAUDE.md`, `CLAUDE.local.md`, `.claude/rules/**/*.md`, compatible skills | imports organize ownership but still consume context |
| Cursor | nested `AGENTS.md`, `.cursor/rules/*.mdc`, compatible skills | plain `.md` in `.cursor/rules` is not an MDC project rule |
| Agent Skills consumers | any discovered `SKILL.md` | consumer extensions are not automatically portable |
| Repository state | status, handoff, work queue, startup, authority, governance, context, and plan surfaces | filename classification is inference until repository evidence confirms it |

Platform behavior changes. The dated, source-linked contract lives in [references/PLATFORM_BEHAVIOR.md](references/PLATFORM_BEHAVIOR.md).

## Install

Python 3.10 or newer is required for the deterministic scripts. There are no runtime dependencies.

For Codex and consumers that support the shared project skill directory:

```bash
git clone <repository-url> .agents/skills/agent-docs-doctor
```

For Claude Code, place the same folder at `.claude/skills/agent-docs-doctor`. Cursor also discovers compatible shared and platform-specific skill locations; `.agents/skills/agent-docs-doctor` is the simplest cross-client project location.

Until this repository has an approved public remote, copy the local folder into the appropriate project skill directory. The project is not yet published.

## Quick start

Invoke the skill:

```text
Use $agent-docs-doctor to audit this repository's agent instructions and tell me what should change.
```

Or run the evidence engine directly:

```bash
python3 scripts/agent_docs_doctor.py audit . --pretty > /tmp/agent-docs-audit.json
python3 scripts/validate_report.py /tmp/agent-docs-audit.json
```

The scripts write only to standard output unless your shell explicitly redirects it.

## Example inventory

```json
{
  "path": ".cursor/rules/frontend.mdc",
  "kind": "scoped-rule",
  "platforms": ["cursor"],
  "loading": "conditional",
  "role": "procedure",
  "classification_basis": "filename-and-metadata inference"
}
```

## Example finding

```text
[HIGH] archive-boundary
Observed: CURRENT_PLAN.md declares status: retired outside an archive-like path.
Uncertainty: it may be an intentional redirect stub.
Next: inspect inbound links and preserve migration or rollback invariants before moving it.
```

Exact evidence does not settle intent. The report must say what is observed, what is inferred, and what needs an owner decision.

## Example challenger

```text
AGENTS.md                         canonical cross-client invariants
CLAUDE.md                         @AGENTS.md plus real Claude-only behavior
.cursor/rules/frontend.mdc        frontend-specific Cursor procedure
.agents/skills/release/SKILL.md   on-demand release workflow
STATUS.md                         one short current-state surface
docs/archive/                     retired history with repaired inbound links
```

That tree is a proposal, not a universal standard. A real audit includes an incumbent-to-challenger traceability table and keeps the incumbent unchanged until approval and evaluation.

## Read-only and safety model

The default audit:

- walks only the requested root;
- honors `.gitignore`, `.ignore`, and `.agent-docs-doctorignore` with common negation behavior;
- skips secret- or credential-like filenames;
- refuses to read candidate files above a fixed safety limit while reporting the limitation;
- emits relative paths and no timestamps, making output reproducible and less likely to leak local paths;
- never writes into the target repository.

Ignore files are exposure controls, not security sandboxes. Shell tools may bypass platform-specific ignore behavior. Use filesystem permissions and verified fail-closed controls for actual enforcement.

## Evaluation philosophy

Do not promote a challenger because it looks cleaner. Freeze representative tasks, both documentation conditions, client/model settings, and a task-specific judge rubric. Compare correctness and safety first; count irrelevant reads, stale influence, unnecessary questions or approvals, verification quality, latency, and tokens when observable. Resource reductions count only if quality still passes.

See [the full evaluation protocol](references/EVALUATION_PROTOCOL.md) and [forward-test results](docs/FORWARD_TEST_RESULTS.md).

## Limitations

- The ignore matcher intentionally implements a useful subset of Git ignore semantics, not every edge case in Git's specification.
- Frontmatter parsing is conservative and dependency-free; complex nested YAML remains raw evidence for model review.
- Filename-based consumer and role classifications are labeled inference.
- Exact overlap is deterministic; semantic equivalence and contradiction are not.
- The tool does not inspect global user/team rules outside the requested repository.
- A report cannot determine whether undocumented incident history remains operationally necessary.
- Platform documentation and client behavior can drift after the verification date.

## Development

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q scripts tests
python3 /path/to/skill-creator/scripts/quick_validate.py .
```

Synthetic fixtures cover healthy, bloated, conflicting, stale, competing-state, thin-adapter, intentionally duplicated, and lightweight non-code repositories. They contain no private source documents.

Read [CONTRIBUTING.md](CONTRIBUTING.md) before changing discovery rules or report semantics.

## Maturity and license

Status: **local pre-release**. The deterministic core and synthetic fixture suite are implemented; broader public-repository evaluation and multi-version client verification remain release gates.

Licensed under [Apache License 2.0](LICENSE).
