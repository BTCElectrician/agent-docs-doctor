# Contributing

Agent Docs Doctor is intentionally conservative: deterministic code reports observable facts; the skill labels semantic judgment and preserves user authority.

## Before opening a change

- Keep runtime code within the Python standard library unless a dependency has clear, documented value.
- Keep audits read-only by default.
- Do not add private repositories, paths, incidents, names, credentials, or source documents to tests or fixtures.
- Use synthetic fixtures or publicly licensed sources.
- Cite current official documentation for platform-loading claims.
- Treat size thresholds as guidance unless a client enforces them.
- Do not turn a heuristic into a scientific-sounding score.

## Development loop

```bash
python3 -B -m unittest discover -s tests -v
python3 -B scripts/check_python_syntax.py src scripts tests
python3 -B scripts/agent_docs_doctor.py audit fixtures/healthy-repo --format json --pretty
ruff check src scripts tests
ruff format --check src scripts tests
pyright
uv build
```

Run the current official skill validator against the repository root.

New discovery behavior needs tests for ignored paths, secret-like names, relative output, deterministic ordering, and read-only operation. New platform classifications need a dated official source in `references/PLATFORM_BEHAVIOR.md`.

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
