# Approved migration guide

Use only after explicit user approval identifies the accepted challenger and write scope.

## Preconditions

- Freeze the incumbent in version control or an immutable review artifact.
- Confirm repository root, branch, dirty state, and deployment behavior.
- Identify every preservation-register item and owner decision.
- Keep cross-repository edits out of scope unless separately approved.

## Migration sequence

1. Create the smallest path-scoped diff that establishes the approved authority hierarchy.
2. Keep platform adapters thin, but retain consumer-specific behavior that cannot be shared.
3. Convert deterministic gates only to controls whose event, blocking behavior, and failure mode are verified.
4. Move history only after replacing inbound links and leaving an appropriate redirect when repository policy requires one.
5. Keep secrets and private source material outside generated artifacts.
6. Validate syntax for each consumer, run repository tests, and rerun the doctor audit.
7. Inspect the diff for lost safeguards and unrelated changes.
8. Execute the frozen incumbent-versus-challenger evaluation before adoption claims.
9. Document rollback and residual risk.

## Stop conditions

Stop and return to the owner when:

- a safeguard's origin or continued need is unclear;
- two authorities cannot be reconciled from repository evidence;
- a deterministic control fails open when the requirement needs fail-closed behavior;
- a platform assumption cannot be verified;
- the migration would cross a repository, production, privacy, or destructive-operation boundary not already approved.
