# Agent Docs Doctor status

Last updated: 2026-07-24

## Current state

The `0.2.0` code-side release candidate is implemented locally on `main`.

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

## Remaining acceptance work

- Run the complete local release gate on the final source state.
- Complete fresh read-only adversarial and eight-fixture behavioral checks.
- Record those results, commit the final evidence, push clean `main`, and verify the hosted CI run.

The detailed scope and deferred launch work are tracked in
[`docs/WORLD_CLASS_PRODUCT_PLAN.md`](docs/WORLD_CLASS_PRODUCT_PLAN.md).
