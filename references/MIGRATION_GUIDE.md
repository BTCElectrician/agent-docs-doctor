# Approved migration guide

Use only after the user has reviewed an exact change preview and explicitly authorized applying it.
Requesting `preview` in the decision review does not authorize writes.

This guide governs approved edits to repository documentation. The built-in `install-skill` and
`uninstall-skill` commands are a different user-level mutation path: they require their own plan
preview and `--apply PLAN_TOKEN_FROM_PREVIEW`. An installer fingerprint never authorizes repository edits,
and approval of this migration never authorizes skill installation or uninstall.

## Preconditions

- Freeze the incumbent in version control or an immutable review artifact.
- Confirm the user said **Apply this preview** or gave equally unambiguous approval after seeing the
  exact paths and operations.
- Confirm repository root, branch, dirty state, and deployment behavior.
- Identify every preservation-register item and owner decision.
- Keep cross-repository edits out of scope unless separately approved.
- Require a complete audit for every conclusion that depends on absence. If coverage is partial,
  list the custom-ignored, unreadable, non-regular, concurrently changed, or resource-limited scope
  and resolve it or obtain an owner decision before migration.

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

## Installer backup recovery

Repository migration rollback and Agent Docs Doctor's managed-skill backups are separate. The
installer never automatically restores or deletes a backup.

For a managed-skill recovery, use only the `Reversible backup` path emitted by the applied plan.
Verify the backup manifest, client, version, file allowlist, and hashes. Confirm that the exact
user-level destination is absent and that no path component is a symlink, junction, or reparse
point. Then use a same-filesystem move that fails if the destination appears concurrently; never
use an overwrite-capable copy or move. Preview `install-skill --client CLIENT`; an
`already-installed` result confirms the manifest. Stop if the destination exists or any identity
differs. Never replace an unmanaged destination to complete a restore.

## Stop conditions

Stop and return to the owner when:

- a safeguard's origin or continued need is unclear;
- two authorities cannot be reconciled from repository evidence;
- a deterministic control fails open when the requirement needs fail-closed behavior;
- a platform assumption cannot be verified;
- the migration would cross a repository, production, privacy, or destructive-operation boundary not already approved.
