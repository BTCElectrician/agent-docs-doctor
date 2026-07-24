# Agent Docs Doctor status

Last updated: 2026-07-24

## Current state

The `0.2.0` code-side release candidate is implemented on local `main`. Four evidence-backed
post-review fixes have been applied after the initial packaging commit and are awaiting the final
commit and fresh behavioral acceptance.

It now provides:

- an installable Python CLI and a user-level Agent Skill installer for Codex, Claude Code, and
  Cursor;
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

## Safety boundary

Repository auditing is read-only. The product has no command that deletes, rewrites, archives, or
automatically fixes audited repository content. Skill installation is a separate, explicit
operation; replacement and uninstall preserve the prior managed installation as a user-level
backup.

## Release boundary

The public repository is <https://github.com/BTCElectrician/agent-docs-doctor>. This code-side
closeout does not create a tag or GitHub release, publish to PyPI, change social metadata, or
publish launch messaging or media.

## Acceptance evidence

- 86 unit and fixture tests pass; one Windows-only junction test is skipped on macOS and is covered
  by the hosted Windows matrix.
- Ruff, Pyright, cache-free syntax checks, both report-validator paths, the official skill
  validator, JSON Schema validation, cross-hash-seed determinism, no-write comparison, UBS, public
  safety scanning, package build, and isolated wheel installation pass.
- A fresh read-only review reproduced and fixed one hosted-CI configuration defect before the
  snapshot was frozen.
- Fresh contamination-free behavior checks passed all eight public fixtures at `c4b49a8`; no
  evaluator attempted a write or recommended destructive action. That set is recorded as
  superseded because the later fixes changed engine and installer behavior.

Remaining code-side closeout is to commit the reproduced fixes, run a new fresh eight-fixture set
against that commit, record the final evidence, rerun release gates, push clean `main`, and verify
the hosted CI matrix.

The detailed scope and deferred launch work are tracked in
[`docs/WORLD_CLASS_PRODUCT_PLAN.md`](docs/WORLD_CLASS_PRODUCT_PLAN.md).
