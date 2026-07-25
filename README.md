# Agent Docs Doctor

<p align="center">
  <img src="docs/assets/agent-docs-doctor-hero.webp" alt="Agent Docs Doctor by Ohmni Oracle — audit the rules before they steer the agent" width="100%">
</p>

Your coding agent may be following more repository instructions than you realize—and some may be
stale, duplicated, or competing for authority.

Agent Docs Doctor maps those instruction surfaces, shows the evidence, and gives you a short list
of human decisions. The audit is local and read-only. It never deletes, rewrites, archives, or
“fixes” repository files on its own.

## Try it in one command

From the repository you want to inspect:

```bash
uvx --from git+https://github.com/BTCElectrician/agent-docs-doctor.git \
  agent-docs-doctor audit . --format text
```

Python 3.10 or newer is required. There are no runtime dependencies or API keys.

You will see a concise evidence brief ending with:

```text
Nothing was changed.
```

The command reports only deterministic signals. It does not pretend that repeated text is
automatically bad or that an old-looking document is definitely stale.

## Get the human decision review

The Agent Skill adds repository-aware judgment and turns the evidence into simple choices such as
**Keep**, **Fix**, **Clarify**, **Combine**, **Archive later**, or **Ask an owner**.

Install the command once:

```bash
uv tool install git+https://github.com/BTCElectrician/agent-docs-doctor.git
```

Then install the skill for your client:

```bash
agent-docs-doctor install-skill --client codex --apply
```

Use `claude` or `cursor` instead of `codex` for those clients. Installation writes only to the
selected user-level skill folder, never to the repository being audited.

| Client | User-level skill location |
| --- | --- |
| Codex | `~/.agents/skills/agent-docs-doctor` |
| Claude Code | `~/.claude/skills/agent-docs-doctor` |
| Cursor | `~/.cursor/skills/agent-docs-doctor` |

Now ask in normal language:

```text
Audit this repository's agent instructions with Agent Docs Doctor. Give me the short decision
review with safe defaults, and do not change any files.
```

Named-skill syntax varies by client. Explicitly select Agent Docs Doctor from the client’s skill
picker when needed.

## What a user gets

The default response is designed for a maintainer, not a schema author:

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

If there are more than seven decisions, the review shows the first seven, tells you how many remain,
and lets you reply `next`. Decision IDs never change between pages.

`preview` still does not edit anything. It produces an exact proposed diff with preservation,
validation, and rollback notes. Only a later, explicit instruction to apply that preview authorizes
repository changes.

## Why this exists

As coding agents became more careful, they also became more willing to read every instruction and
status document available to them. That can make a stale plan or forgotten adapter more influential,
not less.

The problem is rarely one bad file. A repository may combine:

- `AGENTS.md` and `AGENTS.override.md`;
- `CLAUDE.md` imports and `.claude/rules`;
- `.cursor/rules`;
- user and project Agent Skills;
- status, handoff, work-queue, authority, and archived planning documents; and
- configuration that changes which instruction files are selected.

Agent Docs Doctor reconstructs that system before recommending cleanup.

## Deterministic evidence versus judgment

The zero-dependency engine can reproduce:

- recognized surfaces and automatic imports;
- path, raw-byte hash, byte count, and conservative metadata;
- consumer, loading mode, role, and classification basis;
- exact substantive overlap without copying paragraph bodies into the ledger;
- broken local references;
- retired metadata outside archive-like paths;
- multiple current-state candidates;
- ignored, excluded, unreadable, and resource-limited coverage; and
- a versioned, privacy-minimized JSON report.

Judgment remains separate:

- whether two instructions actually conflict;
- whether repetition protects different loading boundaries;
- whether a plan is operationally stale;
- which source should be authoritative; and
- whether any change is worth making.

That separation is the product’s central safety boundary.

## Command reference

```text
agent-docs-doctor --version
agent-docs-doctor doctor
agent-docs-doctor inventory [ROOT] [--pretty]
agent-docs-doctor audit [ROOT] [--format text|json] [--pretty]
agent-docs-doctor validate-report <PATH|->
agent-docs-doctor install-skill --client codex|claude|cursor [--update] [--apply]
agent-docs-doctor uninstall-skill --client codex|claude|cursor [--apply]
```

`doctor` verifies the package, bundled skill, runtime, and read-only audit contract, and reports the
active schema versions.

Skill installation is preview-first when `--apply` is omitted. Updates move the previous managed
version to a private user-level backup before activating the replacement. Uninstall also moves the
managed skill to a reversible backup; it does not delete it.

The JSON path is pipe-friendly:

```bash
agent-docs-doctor audit . --format json |
  agent-docs-doctor validate-report -
```

The engine validates every generated report before emitting it. The standalone validator remains
useful for stored reports and integrations.

## Read-only and privacy guarantees

The audit:

- walks only the requested root;
- never writes into that root;
- ignores default dependency, build, VCS, fixture, cache, and test-data directories;
- honors a documented, conservative subset of root and nested ignore rules;
- never descends into an ignored directory or reads control files inside it;
- treats `.gitignore` in an already-traversed directory as a control-plane input, matching Git’s
  observed traversal behavior even if an inherited file rule matches that `.gitignore`;
- never opens secret-like names;
- follows only auditable in-root regular-file symlinks;
- inventories recognized in-root `CLAUDE.md` imports, including otherwise-unusual filenames;
- records missing, excluded, invalid, and out-of-root imports without opening them;
- caps each file, aggregate bytes, candidate count, import depth, and ignore-rule count;
- reports `complete` or `partial` coverage explicitly;
- emits relative paths and no timestamps; and
- sanitizes absolute filesystem-style references.

Ignore files reduce exposure; they are not security sandboxes. Filesystem permissions remain the
appropriate enforcement boundary for secrets.

## Schemas and compatibility

New reports use `agent-docs-doctor.audit.v2` and
`agent-docs-doctor.inventory.v2`. The complete machine contract is published at
[`schemas/audit-v2.schema.json`](schemas/audit-v2.schema.json).

The validator continues to accept legacy v1 reports. Additive v2 fields may appear in future
0.2.x releases; incompatible changes require a new schema version.

Validator exits are stable:

- `0`: valid output or help;
- `1`: well-formed JSON rejected by the report contract;
- `2`: usage, file I/O, or JSON parsing failure.

## Platform support

The package and CI support Python 3.10–3.13 on Linux, macOS, and Windows. Platform-specific loading
behavior and the dated official sources behind it are documented in
[`references/PLATFORM_BEHAVIOR.md`](references/PLATFORM_BEHAVIOR.md).

The engine deliberately implements a useful subset of Git ignore semantics rather than claiming
perfect parity with every Git edge case. Frontmatter parsing is conservative and dependency-free.
Multiline or malformed Markdown links remain judgment evidence.

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

## Maturity and license

Status: **public beta**. Package publication and a tagged release are intentionally separate launch
decisions.

Licensed under the [Apache License 2.0](LICENSE).
