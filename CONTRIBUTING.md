# Contributing

Agent Docs Doctor is intentionally conservative: deterministic code reports observable facts; the skill labels semantic judgment and preserves user authority.

## Before opening a change

- Keep runtime code within the Python standard library unless a dependency has clear, documented value.
- Keep audits read-only by default.
- Keep user-level installer mutation behind a current-plan fingerprint that binds payload, destination, target
  state, and backup state. Never reuse audit approval as installer or repository-edit authority.
- Do not add private repositories, paths, incidents, names, credentials, or source documents to tests or fixtures.
- Use synthetic fixtures or publicly licensed sources.
- Cite current official documentation for platform-loading claims.
- Treat size thresholds as guidance unless a client enforces them.
- Do not turn a heuristic into a scientific-sounding score.

## Development loop

```bash
uv sync --frozen --extra dev
uv run --frozen --no-sync python -B -m pytest -q
uv run --frozen --no-sync python -B scripts/check_python_syntax.py src scripts tests
uv run --frozen --no-sync python -B scripts/check_schema_contract.py
uv run --frozen --no-sync python -B scripts/check_no_write.py fixtures/healthy-repo
uv run --frozen --no-sync python -B scripts/public_safety_scan.py .
uv run --frozen --no-sync python -B scripts/agent_docs_doctor.py audit fixtures/healthy-repo --format json --pretty
uv run --frozen --no-sync ruff check src scripts tests
uv run --frozen --no-sync ruff format --check src scripts tests
uv run --frozen --no-sync pyright
uv run --frozen --no-sync python -m build --no-isolation
```

Run the current official skill validator against the repository root. CI repeats the full gates on
Linux, macOS, and Windows for Python 3.10 and 3.13, compares bundled skill and schema bytes between
the wheel and source archive, then installs each archive without runtime dependencies into a
separate fresh environment and smokes both installed CLIs. If dependencies change, regenerate
`uv.lock`, inspect its source URLs and hashes, and keep build-system dependencies exactly
constrained in both `[build-system]` and the locked development environment.

New discovery behavior needs tests for root and nested ignores, ignored controls, secret-like names
and hard-link aliases, symlinks and platform reparse points, FIFOs and replacement races, private
path minimization, resource caps, deterministic ordering across hash seeds, partial-coverage
semantics, and read-only operation. New installer behavior needs fingerprint mismatch, changed state,
unmanaged destination, ancestor alias, backup collision, failure atomicity, and recovery tests. New
platform classifications need a dated official source in `references/PLATFORM_BEHAVIOR.md`.

## Fixture rules

Fixtures must be synthetic, minimal, and safe to publish. State the intended ambiguity in the fixture content only when it represents real repository evidence; do not encode hidden expected answers that would contaminate forward tests. Hold expected diagnoses in tests or an external evaluator.

## Changes to the audit contract

For a new deterministic finding:

1. define the observable evidence;
2. give it a stable category and identifier;
3. state uncertainty and alternative explanations;
4. add positive and negative tests;
5. update the report reference when the shape changes.

Backward-compatible additions stay within the current schema version. A breaking field or semantic
change requires a new versioned file under `schemas/`, legacy-validator coverage, and an explicit
migration note.

For a new recommendation heuristic, keep it in the skill or rubric rather than disguising it as deterministic code.

For a human-report change, preserve the short decision review, stable decision IDs, safe defaults,
and two-step approval boundary. Keep advanced evidence available without making it the default.

By contributing, you agree that your contribution is licensed under Apache License 2.0.
