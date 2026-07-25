# Security policy

## Supported version

Security fixes are applied to the current `main` branch until tagged releases begin.

## Reporting a vulnerability

Do not open a public issue for a vulnerability that could expose private repository contents,
bypass ignore or secret-name boundaries, follow an out-of-root filesystem target, or modify an
audited repository.

Also report a vulnerability privately if it can:

- disclose frontmatter, paragraph text, ignored content, environment values, or private absolute or
  out-of-root paths in reports or errors;
- reach secret bytes through a hard link or path alias;
- hang on a FIFO, device, reparse point, deeply nested report, or unbounded evidence class;
- apply a skill plan whose payload, target, manifest, ancestor, or backup state changed after
  preview; or
- replace an unmanaged destination or lose a user-owned file during install, update, uninstall, or
  rollback.

Use GitHub’s private vulnerability reporting for this repository. Include:

- the affected command and version or commit;
- a minimal synthetic reproduction;
- the expected safety boundary;
- the observed behavior; and
- whether any real private data was exposed.

Never attach real credentials, private governance documents, personal filesystem paths, or customer
repositories. Replace them with synthetic fixtures.

## Safety boundary

The audit engine is designed to be local, read-only, bounded, and privacy-minimized. `complete`
coverage applies only to the documented discovery scope; `partial` coverage must not be presented
as proof that omitted areas are safe.

Skill installation is a separate, explicitly applied user-level operation. In 0.3.0, apply requires
the deterministic current-plan fingerprint emitted by preview and rechecks the packaged payload,
resolved destination, ancestor identities, managed state, and backup reservation before mutation.
The fingerprint proves state equality, not prior human review or authorization. Apply uses
descriptor-relative operations on supported Darwin/Linux runtimes and fails closed elsewhere. It
refuses unmanaged destinations and existing link, junction, or reparse-point ancestors. Managed
backups are retained for manual recovery and are never automatically deleted.

Tool-managed bytes are hash-bound. User-owned extra file bytes are preserved but never opened;
their path, identity, type, size, mode, link count, and change/modify metadata are bound instead.
Multiply-linked managed files are rejected without reading their contents. Bundled skill resources
must come from the currently executing source checkout or installed distribution.

Creation, rollback, interruption recovery, and cleanup are identity-bound. If a tool-created
private directory cannot be proved still visible, empty, and identical, the operation fails and
reports that residue may remain rather than removing an unknown replacement. Backup-name
collisions after preview fail closed and do not remove the colliding path. A catchable interruption
after directory creation but before its identity is captured produces an explicit
unconfirmed-private-residue diagnostic; the installer will not guess that the visible path is
tool-owned. Once anchor identities are captured, Python-level interruptions around activation are
state-classified: install/update either restores the prior target or retains the committed new
target plus its reversible backup, while a committed uninstall retains the complete prior tree in
its previewed backup. Uncatchable process termination or machine failure may still require manual
recovery from that backup.

Audit reads and POSIX directory enumeration require the opened descriptor to resolve to the exact
intended path under the requested root. Missing descriptor-path verification, an ancestor alias,
or a path replacement fails closed before candidate bytes or directory entries are consumed.
Secret-like matching applies to every relative path component, not only the final filename.
Non-printing Unicode path displays are replaced with one-way hash markers in JSON and text output
to prevent terminal directionality or zero-width spoofing. Automatic-import expansion deduplicates
source/target edges, releases consumed queue entries, and shares the aggregate reference cap;
exhaustion makes coverage partial.

Descriptor anchoring prevents replacement-link traversal, but POSIX provides no mandatory rename
lock against another hostile process running as the same user in the final
visibility-check-to-rename interval. Run apply only while the selected skill and backup directories
are under the operator's exclusive control.

A report, recommendation, repository-edit preview, or installer preview is not authorization to
modify an audited repository. Likewise, authorization to edit a repository is not authorization to
install or uninstall a user-level skill.
