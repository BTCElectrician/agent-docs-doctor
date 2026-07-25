# Agent Docs Doctor

<p align="center">
  <img src="docs/assets/agent-docs-doctor-hero.webp" alt="Agent Docs Doctor by Ohmni Oracle — audit the rules before they steer the agent" width="100%">
</p>

<p align="center">
  <a href="https://github.com/BTCElectrician/agent-docs-doctor/actions/workflows/ci.yml"><img src="https://github.com/BTCElectrician/agent-docs-doctor/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://opensource.org/licenses/Apache-2.0"><img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg" alt="License: Apache 2.0"></a>
  <img src="https://img.shields.io/badge/Python-3.10--3.13-3776AB.svg" alt="Python 3.10 through 3.13">
  <img src="https://img.shields.io/badge/audit-read--only-16a34a.svg" alt="Read-only audit">
</p>

<p align="center"><strong>Find the stale, conflicting, duplicated, and competing instructions steering your coding agents.</strong></p>

Agent Docs Doctor maps the instruction system around Codex, Claude Code, Cursor, and compatible
agent workflows. It produces deterministic evidence first, then helps a human decide what to keep,
fix, clarify, combine, or archive later.

The audit runs locally, requires no API key, and does not change the repository.

```bash
uvx --from git+https://github.com/BTCElectrician/agent-docs-doctor.git \
  agent-docs-doctor audit . --format text
```

> **Safety promise:** auditing never deletes, rewrites, moves, archives, or “fixes” files.
> Every audit ends by stating `Nothing was changed.`

## TL;DR

**The problem:** Coding agents increasingly read repository instructions carefully. When an old
plan, forgotten adapter, duplicated rule, or competing status file remains discoverable, that
extra context can steer the agent away from current reality.

**The solution:** Agent Docs Doctor reconstructs the instruction surfaces first. It reports what
exists, how it may load, what overlaps, which references are broken, and where current-state claims
compete—without pretending it can infer organizational intent from a filename.

### Why use Agent Docs Doctor?

| Capability | What you get |
| --- | --- |
| **Evidence before opinion** | Relative paths, hashes, byte counts, loading classifications, references, and exact overlap |
| **Human-sized decisions** | Stable choices such as **Keep**, **Fix**, **Clarify**, **Combine**, **Archive later**, or **Ask an owner** |
| **Read-only by default** | The audit does not mutate the repository; even `preview` only proposes a diff |
| **Platform-aware discovery** | Recognizes Codex, Claude Code, Cursor, Agent Skills, and common status/handoff surfaces |
| **Privacy-minimized output** | Avoids paragraph bodies, timestamps, absolute local paths, and secret-like files |
| **Deterministic CLI** | Zero runtime dependencies, JSON schemas, stable validator exits, and repeatable output |

## See it work

Audit one of the included synthetic repositories:

```bash
git clone https://github.com/BTCElectrician/agent-docs-doctor.git
cd agent-docs-doctor

python3 -B scripts/agent_docs_doctor.py audit fixtures/stale-history --format text
```

```text
Agent Docs Doctor
Scanned 3 agent-facing surfaces (complete coverage).
Nothing was changed.

1 deterministic signal(s) found:

E1 [HIGH] Retired metadata appears outside an archive-like path.
   Evidence: CURRENT_PLAN.md
   Caution: Repository policy may intentionally retain a redirect stub here.
```

## What a user gets

That is evidence, not an automatic deletion recommendation. The matching Agent Skill adds
repository-aware judgment and turns findings into a short review:

```text
Agent Docs Doctor found 3 items worth reviewing.
Nothing was changed.

D1 — Old plan is still being referenced
What I found: The plan says it is retired, but AGENTS.md still points to it.
Recommendation: Fix the reference, then archive the old plan.
Safe default: Keep it unchanged until an owner confirms the current plan.

D2 — Repeated deployment rule
Recommendation: Keep both copies because they protect different agent clients.

Reply with: D1 preview, D2 keep — or say “show evidence.”
```

If there are more than seven decisions, the review shows seven at a time. Reply `next` for the next
page. Decision IDs remain stable.

## How it works

```text
Repository root
      │
      ▼
┌───────────────────────────┐
│ Conservative discovery    │
│ rules · skills · status   │
│ plans · imports · ignores │
└─────────────┬─────────────┘
              │ safe, bounded reads
              ▼
┌───────────────────────────┐
│ Deterministic evidence    │
│ inventory · references    │
│ overlap · coverage        │
└─────────────┬─────────────┘
              │ validated v2 report
              ├──────────────────────────┐
              ▼                          ▼
┌───────────────────────────┐  ┌───────────────────────────┐
│ Text or JSON output       │  │ Optional Agent Skill      │
│ reproducible, pipeable    │  │ human decision review     │
└───────────────────────────┘  └─────────────┬─────────────┘
                                             │ explicit approval only
                                             ▼
                                  Previewed, path-scoped changes
```

The deterministic engine finds facts. The skill helps interpret them. Neither treats “old,”
“large,” or “repeated” as synonymous with “wrong.”

## What it audits

- `AGENTS.md`, `AGENTS.override.md`, and configured Codex fallback names;
- `CLAUDE.md` imports and `.claude/rules`;
- `.cursor/rules`;
- project and user Agent Skills;
- status, handoff, work-queue, authority, and planning documents;
- configuration that changes instruction selection;
- exact substantive overlap without copying paragraph bodies into the report;
- broken, excluded, invalid, and out-of-root local references;
- retired metadata outside archive-like paths; and
- multiple files presenting themselves as current operational truth.

Platform loading behavior is version-sensitive. The dated official sources and exact boundaries are
documented in [`references/PLATFORM_BEHAVIOR.md`](references/PLATFORM_BEHAVIOR.md).

## How it compares

| Capability | Agent Docs Doctor | Manual review | Markdown/link lint | LLM-only review |
| --- | --- | --- | --- | --- |
| Reproducible inventory | **Yes** | Inconsistent | File-by-file | Prompt-dependent |
| Platform loading context | **Codex, Claude Code, Cursor** | Reviewer-dependent | No | Model-dependent |
| Exact-overlap evidence | **Hashed and location-based** | Time-consuming | No | Often paraphrased |
| Human judgment | **Separate decision layer** | Yes | No | Yes |
| Read-only default | **Enforced audit path** | Depends | Usually | Depends on tools |
| Privacy-minimized JSON | **Versioned schema** | No | No | No |
| Works without an API key | **Yes** | Yes | Yes | Usually no |

Use a plain Markdown linter when you only need formatting or link syntax. Use manual review when the
repository is tiny and its ownership is obvious. Use Agent Docs Doctor when you need a repeatable
map before deciding which instructions should survive.

## Installation

Python 3.10 or newer is required. The runtime has no third-party dependencies.

### Run without installing

```bash
uvx --from git+https://github.com/BTCElectrician/agent-docs-doctor.git \
  agent-docs-doctor doctor
```

### Install the CLI with `uv`

```bash
uv tool install git+https://github.com/BTCElectrician/agent-docs-doctor.git
agent-docs-doctor doctor
```

### Install from source

```bash
git clone https://github.com/BTCElectrician/agent-docs-doctor.git
cd agent-docs-doctor
python3 -m pip install .
agent-docs-doctor doctor
```

If you do not want to install anything, every CLI command can also be run from a clone:

```bash
python3 -B scripts/agent_docs_doctor.py doctor
```

## Install the Agent Skill

The CLI alone produces deterministic evidence. Install the skill when you also want the short,
repository-aware human decision review.

```bash
agent-docs-doctor install-skill --client codex
```

That command is preview-only. Review the destination, then explicitly apply it:

```bash
agent-docs-doctor install-skill --client codex --apply
```

Use `claude` or `cursor` instead of `codex` for those clients.

| Client | User-level skill location |
| --- | --- |
| Codex | `~/.agents/skills/agent-docs-doctor` |
| Claude Code | `~/.claude/skills/agent-docs-doctor` |
| Cursor | `~/.cursor/skills/agent-docs-doctor` |

Installation writes only to the selected user-level skill folder, never to the repository being
audited. Updates and uninstalls preserve the managed version in a reversible backup.

Now ask your agent:

```text
Audit this repository's agent instructions with Agent Docs Doctor. Give me the short decision
review with safe defaults, and do not change any files.
```

Named-skill syntax varies by client. Select Agent Docs Doctor from the client’s skill picker when
needed.

## Quick start

1. Open a terminal in the repository you want to inspect.
2. Run the text audit:

   ```bash
   agent-docs-doctor audit . --format text
   ```

3. Read each `E#` evidence item. Nothing has been changed.
4. For a machine-readable ledger, save and validate JSON:

   ```bash
   agent-docs-doctor audit . --format json --pretty > agent-docs-audit.json
   agent-docs-doctor validate-report agent-docs-audit.json
   ```

5. If the skill is installed, ask for the short decision review.
6. Request `D1 preview` for any change you want to examine. A preview is still read-only.
7. Apply a preview only after checking the exact paths, preservation notes, validation, and
   rollback plan.

## Command reference

### `doctor`

Check the package, bundled skill, Python runtime, and audit contract:

```bash
agent-docs-doctor doctor
agent-docs-doctor doctor --format json
```

### `inventory`

Emit the deterministic repository inventory as JSON:

```bash
agent-docs-doctor inventory .
agent-docs-doctor inventory /path/to/repository --pretty
```

### `audit`

Run the read-only audit:

```bash
agent-docs-doctor audit .
agent-docs-doctor audit . --format text
agent-docs-doctor audit . --format json --pretty
```

JSON is the default output format.

### `validate-report`

Validate a saved report or standard input:

```bash
agent-docs-doctor validate-report agent-docs-audit.json
agent-docs-doctor audit . --format json | agent-docs-doctor validate-report -
```

Stable exits:

- `0`: valid report or help;
- `1`: well-formed JSON rejected by the report contract;
- `2`: usage, file I/O, or JSON parsing failure.

### `install-skill`

Preview, install, or update the managed skill:

```bash
agent-docs-doctor install-skill --client codex
agent-docs-doctor install-skill --client codex --apply
agent-docs-doctor install-skill --client codex --update
agent-docs-doctor install-skill --client codex --update --apply
```

Clients: `codex`, `claude`, and `cursor`.

### `uninstall-skill`

Preview or move the managed skill to a reversible backup:

```bash
agent-docs-doctor uninstall-skill --client codex
agent-docs-doctor uninstall-skill --client codex --apply
```

### Global options

```bash
agent-docs-doctor --version
agent-docs-doctor --help
agent-docs-doctor <command> --help
```

## Configuration and output contracts

The auditor intentionally has no required config file. It reads a bounded subset of relevant
repository control files, including ignore rules and recognized platform configuration.

New reports use:

- `agent-docs-doctor.audit.v2`;
- `agent-docs-doctor.inventory.v2`; and
- [`schemas/audit-v2.schema.json`](schemas/audit-v2.schema.json).

The validator continues to accept legacy v1 reports. Additive v2 fields may appear in future 0.2.x
releases; incompatible changes require a new schema version.

## Safety and privacy

The audit:

- walks only the requested root;
- never writes into that root;
- never opens secret-like filenames;
- ignores default VCS, dependency, build, fixture, cache, and test-data directories;
- honors a conservative subset of root and nested ignore rules;
- does not descend into an ignored directory or read control files inside it;
- follows only auditable, in-root, regular-file symlinks;
- records out-of-root, missing, excluded, invalid, and resource-limited imports without opening
  them;
- caps individual files, aggregate bytes, candidate count, import depth, and ignore-rule count;
- reports `complete` or `partial` coverage explicitly;
- emits relative paths rather than private absolute paths;
- emits no timestamps; and
- validates every generated report before output.

Ignore files reduce exposure; they are not security sandboxes. Filesystem permissions remain the
correct enforcement boundary for secrets.

## Design philosophy

1. **Evidence ledger, not scorecard.** A large document is not automatically bad, and a high score
   cannot resolve ownership.
2. **Read first, change later.** Discovery and diagnosis are safe defaults. Rewrites require a
   separate preview and explicit approval.
3. **Preserve unknown safeguards.** Repetition may protect different clients or scopes. When
   operational history is unclear, keep the rule and ask an owner.
4. **Make uncertainty visible.** Partial coverage, unsupported ignore semantics, and judgment calls
   are reported rather than hidden.
5. **Keep machines and humans in their lanes.** Deterministic code establishes facts; people decide
   what should become authoritative.

## Troubleshooting

### `uvx: command not found`

Install [`uv`](https://docs.astral.sh/uv/getting-started/installation/) or use the source path:

```bash
git clone https://github.com/BTCElectrician/agent-docs-doctor.git
cd agent-docs-doctor
python3 -B scripts/agent_docs_doctor.py doctor
```

### `Python 3.10 or newer is required`

Check the active interpreter:

```bash
python3 --version
```

Then run the command with a Python 3.10–3.13 interpreter.

### The audit reports `partial` coverage

Read the emitted coverage warnings. A file may have been ignored, excluded, unreadable, unsafe,
invalid, or beyond a resource limit. Treat missing evidence as unknown rather than clean.

### A known document was not inventoried

Check whether it lives in a default-excluded directory, matches repository ignore rules, exceeds a
resource bound, or uses an unrecognized filename. Agent Docs Doctor deliberately favors
conservative discovery over reading every Markdown file.

### The skill is installed but does not appear

Verify the client and destination:

```bash
agent-docs-doctor doctor
agent-docs-doctor install-skill --client codex
```

The second command previews the resolved destination without changing it. Restart or refresh the
client’s skill catalog after installation.

### A finding looks wrong

Ask for the evidence and loading basis. Exact overlap is deterministic; semantic conflict and
authority remain judgment calls. Open an issue with a minimal synthetic fixture if the inventory
itself is incorrect.

## Limitations

- **Not a Git implementation:** ignore handling is a documented, useful subset rather than perfect
  parity with every Git edge case.
- **Not a security boundary:** it minimizes reads and output, but filesystem permissions must
  protect secrets.
- **Not an automatic truth detector:** age, size, repetition, and filenames cannot prove that
  content is stale or wrong.
- **Not an autonomous cleanup tool:** it does not delete or rewrite repository documentation during
  audit.
- **Conservative parsing:** frontmatter and Markdown references are parsed without third-party
  dependencies; malformed or complex constructs may remain judgment evidence.
- **Platform behavior changes:** official loading and precedence rules are dated and must be
  reverified as clients evolve.

## FAQ

### Is Agent Docs Doctor limited to Claude?

No. The deterministic CLI is model-agnostic. Discovery currently includes Codex, Claude Code,
Cursor, Agent Skills, and common repository status and planning surfaces. Any human or tool capable
of reading the text or JSON report can use its evidence.

### Does the audit modify or delete anything?

No. `inventory`, `audit`, `doctor`, and `validate-report` do not modify the target repository.
Skill installation changes only the explicitly selected user-level skill directory and is
preview-first.

### Does it upload my repository?

No. The CLI runs locally and has no runtime dependency, API key, telemetry, or network requirement
after installation. Your chosen coding-agent client may have its own data policy.

### Does every finding mean I should remove a file?

No. A duplicate may protect another client, an archive-like plan may remain a useful redirect, and
competing current-state files may reflect a deliberate ownership boundary. The safe default is to
keep uncertain material until an owner confirms the change.

### Can I use only the CLI?

Yes. The CLI gives you a deterministic text or JSON audit. The Agent Skill is optional and adds the
human decision-review workflow.

### Can I automate it in CI?

Yes. Use JSON output, validate it, and decide which repository-specific findings should fail your
pipeline:

```bash
agent-docs-doctor audit . --format json |
  agent-docs-doctor validate-report -
```

The validator proves report conformance; it does not impose your organization’s severity policy.

### How do I propose a change safely?

Ask the installed skill for a specific decision preview, such as `D1 preview`. Review the exact
diff and rollback notes. Only a later explicit instruction authorizes application.

## Development

```bash
python3 -B -m unittest discover -s tests -v
python3 -B scripts/check_python_syntax.py src scripts tests
ruff check src scripts tests
ruff format --check src scripts tests
pyright
uv build
```

Run the current official Agent Skill validator against the repository root before release. See
[`CONTRIBUTING.md`](CONTRIBUTING.md) for discovery, fixture, schema, and safety rules.

## About contributions

*About Contributions:* Please don't take this the wrong way, but I do not accept outside contributions for any of my projects. I simply don't have the mental bandwidth to review anything, and it's my name on the thing, so I'm responsible for any problems it causes; thus, the risk-reward is highly asymmetric from my perspective. I'd also have to worry about other "stakeholders," which seems unwise for tools I mostly make for myself for free. Feel free to submit issues, and even PRs if you want to illustrate a proposed fix, but know I won't merge them directly. Instead, I'll have Claude or Codex review submissions via `gh` and independently decide whether and how to address them. Bug reports in particular are welcome. Sorry if this offends, but I want to avoid wasted time and hurt feelings. I understand this isn't in sync with the prevailing open-source ethos that seeks community contributions, but it's the only way I can move at this velocity and keep my sanity.

## Maturity and license

Status: **public beta**. Package publication and a tagged release are intentionally separate launch
decisions.

Licensed under the [Apache License 2.0](LICENSE).
