# Agent Docs Doctor status

Last updated: 2026-10-02

## Current state

Version `0.3.0` is unreleased: there is no tag, GitHub release, or package-index upload. `main` is
the current code. Every push to `main` runs the hosted six-job matrix (Linux, macOS, and Windows on
Python 3.10 and 3.14).

It now provides:

- an installable Python CLI and a user-level Agent Skill installer for Codex, Claude Code, and
  Cursor;
- discovery and loading labels for Codex, Claude Code, Cursor, GitHub Copilot, Gemini CLI, and
  Agent Skills surfaces, checked against official documentation on 2026-10-02;
- deterministic JSON and concise human-readable audits;
- typed, bounded handling of recognized Claude instruction imports;
- a complete v2 report contract with a deep standalone validator and published JSON Schema;
- preview-first, explicitly applied skill installation, managed updates, and reversible uninstall;
- resource limits, ignore and secret-path boundaries, symlink and reparse-point protections, and
  privacy-minimized evidence;
- cross-platform continuous integration, package-build checks, no-write verification, and
  public-safety scanning; and
- a stable one-decision-at-a-time review flow, including `next` pagination after the first seven
  decisions.

The default `audit` output is now a human-first, plain-language diagnosis: what was found, where it
was found, why it matters, and what to do next. It says nothing changed and asks one approval
question. Technical evidence remains in explicit `--format json` output or on request; the report
schema, read-only audit, preview, and explicit-approval boundaries are unchanged.

## Safety boundary

Repository auditing is read-only. The product has no command that deletes, rewrites, archives, or
automatically fixes audited repository content. Skill installation is a separate, explicit
Darwin/Linux operation. It requires a fingerprint-bound preview, refuses unmanaged or aliased
destinations, and preserves a prior managed installation as a user-level backup. Preview remains
no-write on all supported CLI platforms; apply fails closed where the required descriptor-relative
filesystem operations are unavailable.

## Release boundary

The public repository is <https://github.com/BTCElectrician/agent-docs-doctor>. This code-side
closeout does not create a tag or GitHub release, publish to PyPI, change social metadata, or
publish launch messaging or media.

## Acceptance evidence

- 190 unit, fixture, resource-bound, validator, traversal, privacy, no-write, public-safety, and
  installer-race tests pass locally on Python 3.10, 3.12, and 3.14; three Windows-only
  junction/audit-pinning/installer-pinning tests are skipped on macOS and exercised by the hosted
  Windows matrix.
- Ruff, Pyright, cache-free syntax checks, both report-validator paths, the official skill
  validator, JSON Schema validation, cross-hash-seed determinism, no-write comparison, UBS, public
  safety scanning, package build and archive parity, and isolated wheel/source installation are
  required release gates.
- Targeted adversarial probes cover ignored control files, secret aliases, secret-like path
  components, hostile references and Unicode display paths, unavailable descriptor resolution,
  FIFOs and non-regular files, symlink and directory-replacement races, managed hardlinks,
  bounded distribution-`RECORD` provenance, never-read bundled hardlinks, Windows binary reads and
  cross-provider metadata comparisons, identity-pinned source replacements, pre-identity and
  post-rename interruption recovery, installer preview/apply changes, backup collisions, rollback
  cleanup, deduplicated aggregate-capped import expansion, malformed reports, and bounded
  repeated-pattern scans.
- Local passing gates are evidence, not proof of all host or filesystem behavior. The exact pushed
  commit must also pass all Linux, macOS, and Windows jobs on Python 3.10 and 3.14.

### 2026-10-02 platform currency refresh

- Claude Code now reads `AGENTS.md` when no `CLAUDE.md` is present; the engine labels and follows
  imports for those files. GitHub Copilot, Gemini CLI, and legacy `.cursorrules` surfaces are
  inventoried. Imports beyond Claude Code's four-hop limit are no longer called automatic.
- `references/PLATFORM_BEHAVIOR.md` was re-verified against official sources on 2026-10-02.
- Build pins moved to setuptools 83.0.0 and wheel 0.47.0, with pytest 9 and refreshed dev tools.

The detailed local commands, evaluation provenance, and limitations are recorded in the linked
repository documents. The forward tests in `docs/FORWARD_TEST_RESULTS.md` predate this refresh.

The detailed scope and deferred launch work are tracked in
[`docs/WORLD_CLASS_PRODUCT_PLAN.md`](docs/WORLD_CLASS_PRODUCT_PLAN.md).
