# Agent Docs Doctor status

Last updated: 2026-07-24

## Current state

The `0.2.0` code-side release candidate is implemented and locally accepted on `main`. Three
independent code-review passes produced ten evidence-backed release findings after the initial
packaging commit; every confirmed issue was reproduced, fixed, and covered by regression tests.

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

- 88 unit and fixture tests pass; one Windows-only junction test is skipped on macOS and is covered
  by the hosted Windows matrix.
- Ruff, Pyright, cache-free syntax checks, both report-validator paths, the official skill
  validator, JSON Schema validation, cross-hash-seed determinism, no-write comparison, UBS, public
  safety scanning, package build, and isolated wheel installation pass.
- The first hosted Windows run exposed one platform-specific invalid-path privacy defect; it was
  reproduced, fixed before resolution, and added to the final cross-platform rerun.
- The final fresh contamination-free behavior set passed all eight public fixtures at
  `0ebdf21aa3f34a97cab0e4c544156532168d4bb3`; no evaluator wrote repository files, recommended
  deletion, authorized a deployment, or proposed automatic remediation.
- Earlier successful sets at `c4b49a8`, `9f599c1`, `08b9d30`, and `d35f94f` are retained only as
  superseded evidence because later fixes changed engine, installer, validator, or cross-platform
  privacy behavior.

Every push to `main` runs the hosted Linux, macOS, and Windows matrix. The detailed local commands,
evaluation provenance, and limitations are recorded in the linked repository documents.

The detailed scope and deferred launch work are tracked in
[`docs/WORLD_CLASS_PRODUCT_PLAN.md`](docs/WORLD_CLASS_PRODUCT_PLAN.md).
