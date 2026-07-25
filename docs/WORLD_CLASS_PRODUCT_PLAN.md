---
status: code-side-implemented
owner: agent-docs-doctor
last_updated: 2026-07-24
implementation_authority: granted-2026-07-24
---

# World-class product plan

## Decision

Agent Docs Doctor should become the easiest trustworthy way to answer:

> Which repository instructions are quietly steering my coding agents, which ones are stale or
> conflicting, and what—if anything—should I change?

The engine and safety model are already credible. The next leap is not a larger framework. It is a
clean first run, more complete authority discovery, a stronger machine contract, visible proof, and
a launch loop built around real user decisions.

The proposed positioning is:

> Map the repository instructions steering your coding agents, then decide what is stale,
> conflicting, or intentionally repeated—before any cleanup is approved.

The operator authorized the code-side implementation on 2026-07-24. That authority covers this
repository's package, CLI, installer, engine, schemas, tests, CI, safety documentation, and public
developer documentation. It does not authorize PyPI publication, a tag or GitHub release, launch
posts, social assets, or changes to any audited repository.

## Implementation record

The code-side release candidate implements:

- WCD-00's package, client-path, version-sync, preview, update, reversible uninstall, and separate
  publication boundaries;
- WCD-01's typed automatic imports, safe imported-target inventory, complete v2 validation,
  versioned schemas, deterministic provenance, and coverage state;
- WCD-02's installed CLI, environment doctor, text/JSON audit formats, legacy validator path,
  stable greater-than-seven decision pagination, and simple first-run documentation;
- WCD-03's resource bounds, Windows reparse handling, cross-platform CI, wheel build, no-write
  proof, deterministic testing, and public-safety scan; and
- the repository-owned portions of WCD-05: security policy, issue forms, pull-request template,
  changelog, and contribution gates.

Still intentionally outside this code-side closeout: WCD-04 media, live-user comprehension and
maintainer pilots from WCD-06, PyPI publication, a tag or GitHub release, repository social
metadata, and launch messaging.

## Product contract to preserve

Every release must retain these invariants:

- The default audit is read-only and does not modify the target repository.
- A user sees a short decision review before technical evidence.
- `preview` does not authorize writes.
- Only a later, explicit approval of an exact preview authorizes path-scoped changes.
- No automatic delete, archive, rewrite, or “fix all” command exists.
- Deterministic facts, semantic judgment, uncertainty, and user decisions remain separate.
- The evidence engine remains local-first, inspectable, privacy-minimized, and usable without a
  hosted service, API key, database, or required model API.
- The product does not assign a numeric health score or call every signal a defect.
- Public product language stays provider-neutral: it may name supported clients and formats
  factually, but it endorses no provider and does not use model-review provenance as a product
  claim.

## Why the 0.3.0 hardening release is needed

The release closes the code-side correctness and safety gaps that remained in 0.2.0:

- source checkout and built wheel/source-archive invocation paths now share an installable console
  command and byte-matched bundled public resources;
- recognized automatic imports are typed, bounded, and inventoried only through the same
  ignore/secret/root/regular-file protections as direct candidates;
- generated reports have complete nested validation, a bounded regular-file input contract, and
  explicit `complete` or `partial` coverage;
- audit traversal, ignore matching, reference extraction, Markdown/frontmatter processing, and
  public-file scanning have deterministic resource ceilings;
- the no-write proof pins traversal and reads to verified filesystem identities and reports its
  metadata-only boundaries;
- skill installer apply is separated from audit, bound to the current preview state, restricted to
  secure descriptor-relative Darwin/Linux operation, interruption-recoverable, and
  backup-preserving; and
- the repository has a pinned, locked six-platform CI workflow, public-safety scan, package parity
  check, and isolated wheel/source smoke tests.

The remaining gaps are release and adoption evidence, not hidden implementation promises:

1. PyPI publication, a tag, and a GitHub release require separate operator authorization.
2. Live-user first-run comprehension and maintainer pilots remain unperformed.
3. Public media, repository social metadata, and launch messaging remain separate work.
4. Installer apply intentionally does not support Windows until equivalent race-resistant
   descriptor-relative semantics and adversarial acceptance evidence exist.

## North-star experience

A first-time user should be able to:

1. install or invoke the doctor without changing the repository being audited;
2. start an audit with one command or one plain-language request;
3. receive no more than seven plain-English decisions;
4. understand that nothing changed and that `preview` is still read-only;
5. inspect evidence only when wanted; and
6. uninstall or update the tool cleanly.

Target: an unfamiliar user reaches the first useful decision review in under three minutes.

## Release sequence

### WCD-00 — Freeze the distribution and safety contract

Before code changes:

- choose one primary no-worktree install path and one documented fallback;
- verify the intended distribution name immediately before freezing commands or media;
- obtain a separate operator decision for PyPI publication and another for any public release;
- define the supported operating-system tier, with Windows treated as supported only if its
  platform-specific acceptance cases pass;
- define install, verify, update, and uninstall behavior;
- define exact, officially verified user-level skill locations for every supported client;
- define how the skill and evidence-engine versions stay synchronized;
- freeze the current audit, preview, and apply authority boundary; and
- define schema compatibility and deprecation rules.

Recommended distribution shape:

- a standard Python package with a `src/agent_docs_doctor` module;
- a console command named `agent-docs-doctor`;
- a wheel containing the deterministic engine and the complete skill resources;
- `uvx` and `pipx` as clean CLI entry paths after package publication;
- a first-party `install-skill` command that previews its exact user-level write, uses the
  officially verified path for the selected client, installs only the wheel-bundled skill
  resources, records the matching version, refuses an unreviewed overwrite, and supports explicit
  update and uninstall operations;
- no skill-install write inside the repository being audited; and
- manual installation only as a documented fallback.

Initial user-level targets, to be confirmed against the current client binaries during WCD-00:

| Client | Initial target | Verification requirement |
| --- | --- | --- |
| Codex | `~/.agents/skills/agent-docs-doctor` | appears in the skill catalog and invokes bundled resources |
| Claude Code | `~/.claude/skills/agent-docs-doctor` | appears in `/skills` and survives update/uninstall |
| Cursor | `~/.cursor/skills/agent-docs-doctor` | works in both the editor and CLI; do not rely on compatibility-path parity |

The `agent-docs-doctor` project name returned no current PyPI project on 2026-07-24. That is
point-in-time evidence, not a reservation; recheck immediately before command freeze and again
before any approved upload.

Exit gate: the chosen design has an exact client/path support matrix, synchronized engine/skill
versions, install/update/uninstall/rollback tests, a reverified distribution name, and an explicit
publication authority gate before implementation starts. Local wheels and install tests do not
authorize uploading a package.

### WCD-01 — Close correctness and privacy gaps

Implement the smallest evidence-engine changes required for the product promise:

- represent recognized automatic imports as typed edges;
- safely inventory their in-root targets with existing ignore, secret, size, cycle, symlink, and
  non-regular-file protections;
- represent out-of-root, missing, invalid, and otherwise unresolvable automatic imports as typed
  skipped or out-of-scope edges with privacy-minimized targets; never drop them silently;
- keep ordinary Markdown links as references rather than automatically reading every linked file;
- match the relevant Git traversal rule: never descend into an ignored directory or read control
  files inside it; within a traversed directory, treat `.gitignore` as an explicit control-plane
  input even when its own pathname matches an inherited file rule, and document that exception;
- publish a versioned JSON Schema for the complete report;
- validate every emitted nested field and reject malformed integrations;
- include deterministic engine/configuration provenance without timestamps or private paths; and
- add golden compatibility and negative-mutation tests.

Exit gate: imported load-bearing policy cannot disappear silently from the evidence corpus;
out-of-root or unresolvable imports remain visible without being opened; ignored directories and
secret-like targets are never opened; the ignore-control exception is documented and tested; and
every documented report field is validated.

### WCD-02 — Make first use effortless

Build the installable CLI and keep its surfaces honest:

- `agent-docs-doctor --version`;
- `agent-docs-doctor doctor` for environment, resource, root, and read-only self-checks;
- `agent-docs-doctor audit . --format text` for a concise deterministic evidence brief;
- `agent-docs-doctor audit . --format json` for the stable ledger; and
- `agent-docs-doctor validate-report <path|->`.

The text format must not claim semantic contradiction or staleness beyond deterministic evidence.
It should explain how to request the agent-driven decision review.

Improve the human contract:

- lead with the problem, one install action, one request, and one realistic result;
- distinguish clearly between the deterministic CLI and the agent-driven decision review;
- when more than seven decisions exist, show the highest-priority seven, state how many remain, and
  support `next`;
- keep decision IDs stable for the audit session;
- give every displayed item a visible safe default; and
- allow an optional durable Markdown review only after an explicit save request.

Exit gate: isolated package and client-install tests can install, invoke, update, and uninstall the
tool without changing the target repository; the existing behavioral fixtures and the
greater-than-seven decision flow pass. Human comprehension is measured in WCD-06 before launch.

### WCD-03 — Automate trust

Add repository-owned release gates:

- Linux, macOS, and Windows;
- supported Python versions;
- Windows-specific cases for CRLF and UTF-8 output, drive and UNC paths, case-insensitive
  collisions, junctions/reparse points, symlink capability differences, and deterministic
  relative-path output;
- unit and fixture tests;
- Ruff, Pyright, and cache-free syntax checks;
- wheel build and isolated install smoke tests;
- CLI help, version, exit-code, and validator compatibility tests;
- deterministic repeats across hash seeds;
- no-write filesystem comparisons; and
- private-path, secret, Unicode, and generated-cache scans.

Add scale safeguards after measuring them:

- one newline-offset index per file instead of repeated prefix scans;
- a generated monorepo fixture;
- aggregate candidate and byte budgets;
- explicit `complete` or `partial` coverage state; and
- predeclared runtime and memory ceilings.

Exit gate: the packaged release passes the full matrix and a stable large fixture without losing
truth about incomplete coverage.

### WCD-04 — Show the product, not the architecture

Create three public-safe assets:

1. a 20–45 second recording showing install, one audit request, `Nothing was changed`, `D1
   preview`, and the exact no-write preview;
2. a sanitized dogfood case study showing what was found, what was intentional, what an owner kept,
   and what was later fixed; and
3. one readable before/after image suitable for the README, GitHub social card, and a launch post.

The proof must not expose private paths or governance prose, describe every signal as a bug, or
claim superiority from synthetic fixtures.

Exit gate: a stranger can understand the problem, result, and safety boundary from the recording
without reading the architecture documentation.

### WCD-05 — Complete the public storefront

After WCD-00 through WCD-04 pass:

- rewrite the README above the fold around the user problem and three-minute path to value;
- add the repository description, relevant topics, and social preview;
- add CI and package badges only after those surfaces exist;
- add `SECURITY.md`, focused issue forms, and a pull-request template;
- publish a changelog and the first verified tagged release;
- document a tested client/install support matrix; and
- open contribution lanes for platform discovery, synthetic fixtures, and packaging.

Exit gate: the repository page explains what the product does, shows it working, and gives a
verified install command without requiring architecture knowledge.

### WCD-06 — Run the adoption experiment

Before a broad launch:

- observe ten consenting maintainers with documentation-heavy repositories;
- require the first five unfamiliar users to install, invoke, interpret `preview`, and explain the
  later apply boundary without coaching before recruiting the remainder;
- measure install time, time to first useful review, confusion points, false positives, false
  negatives, decisions, and any safety concerns;
- fix repeated onboarding failures;
- freeze the quick start; and
- publish one permissioned user result.

Then launch in a short sequence:

1. founder story and demo;
2. technical explanation of deterministic evidence plus human judgment;
3. relevant agent-tool communities where self-promotion is allowed; and
4. a second real case study after feedback.

The founder story is the authentic hook:

> The smarter models got, the more carefully they read my repository—and that exposed a new
> problem: they were carefully reading stale instructions.

Exit gate: real users can complete the journey unaided. Stars are a lagging outcome, not the
acceptance metric.

## Next product moat

Only after the first launch works:

- formalize the inventory as a versioned evidence graph of instruction, state, skill,
  configuration, archive, and imported-authority nodes;
- represent automatic import, local reference, scope inheritance, and platform-selection edges;
- add baseline comparison so teams can review newly introduced deterministic risks;
- add a GitHub Action and SARIF for deterministic findings only;
- make incomplete scans fail closed when a team explicitly opts into CI enforcement; and
- add platform contract packs only when a real supported consumer requires one.

This evidence graph is the defensible core. It can support human review, agent reasoning, CI, and
future integrations without merging facts and judgment.

## Deliberate non-goals

Do not build these without repeated user evidence:

- hosted service;
- dashboard or TUI;
- database;
- required model API;
- MCP server;
- editor extension;
- automatic migration;
- automatic deletion or archival;
- universal instruction generator;
- numeric health score;
- complete Git-ignore reimplementation; or
- broad framework split performed only for aesthetics.

## Acceptance scorecard

The world-class release is ready only when:

- a clean machine can install and run the built wheel on Linux, macOS, and Windows;
- installation and audit leave every recorded target-repository filesystem entry and attribute
  unchanged; this before/after proof is not a system-call trace;
- time to first useful decision review is under three minutes;
- five of five fresh users understand that `preview` is read-only and later approval is required;
- the eight public behavioral fixtures still pass;
- a greater-than-seven decision case proves stable IDs and `next`;
- automatic imports are inventoried safely and cyclic or excluded targets are never opened;
- the published schema rejects malformed nested report data;
- deterministic output remains identical across hash seeds;
- one scale fixture meets its declared resource budget;
- one real, sanitized case study is published without exaggeration; and
- no destructive incident is observed.

## Dependency-ordered delivery sequence

Calendar targets begin only after implementation is explicitly activated. Stop gates take
precedence over dates:

1. **Freeze:** complete WCD-00, including the client/path matrix, Windows tier, distribution-name
   check, and publication gates.
2. **Correctness:** complete WCD-01 and freeze the evidence/schema compatibility contract.
3. **Product:** complete WCD-02 and WCD-03; build local artifacts and pass the full platform matrix.
4. **Comprehension:** run the first five unfamiliar-user cases from WCD-06 and harden every repeated
   failure.
5. **Proof:** complete WCD-04 and WCD-05 with local or draft assets; do not publish yet.
6. **Pilot:** complete the ten-maintainer cohort and obtain one permissioned result.
7. **Publication decision:** present the final artifacts, package-name recheck, costs, rollback, and
   validation evidence to the operator for explicit PyPI, release, and launch decisions.
8. **Launch:** only after those approvals, run the founder-led launch and an evidence-based
   follow-up release.

The plan should pause if installation cannot remain clean, imported authority cannot be followed
without weakening exposure controls, the schema requires an unbounded compatibility break, or a
real user misunderstands the write boundary.
