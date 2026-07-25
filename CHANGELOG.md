# Changelog

## Unreleased (0.3.0)

### Added

- Installable `agent-docs-doctor` console command with text and JSON audit output.
- Token-bound, preview-first user-level skill install, update, and backup-preserving uninstall for
  Codex, Claude Code, and Cursor.
- Environment `doctor`, complete v2 JSON Schema, engine/configuration provenance, and explicit
  complete-or-partial coverage.
- Safe recursive inventory of recognized `CLAUDE.md` imports.
- Linux, macOS, and Windows CI across Python 3.10 and 3.13.
- Bounded, regular-file-only report input shared by the console and standalone validators.

### Changed

- First-run documentation now starts with one read-only command and a plain-language result.
- Human decision reviews support stable pagination when more than seven decisions exist.
- Source onboarding now requires a visible checkout and commit verification instead of directly
  executing a mutable remote branch.
- The no-write proof now compares file identity, type, content, symlink or reparse target, mode,
  ownership, timestamps, platform attributes, and extended-attribute hashes where supported.
- No-write traversal and hashing now use pinned directory/file descriptors with identity checks
  before and after each read, preventing a replaced path from redirecting proof reads outside the
  approved root.
- No-write extended-attribute capture uses bounded descriptor size queries with per-name,
  per-value, per-entry, count, and aggregate budgets before allocation.
- Six-platform CI now reproduces the checked-in lock, builds distributions without build
  isolation, compares bundled skill/schema bytes, installs both wheel and source archive without
  runtime dependencies in fresh environments, and smokes both installed packages.
- The public-safety gate now scans every tracked public path plus text-like unignored pending files
  with bounded discovery, reads, matching, diagnostics, and output.

### Security

- Imported targets retain typed missing, ignored, secret-like, non-regular, invalid, depth-limited,
  and out-of-root dispositions without being opened.
- Traversal entries, candidate count, aggregate and file bytes, import depth, ignore controls,
  references, paragraph blocks, findings, finding locations, skip records, and report input are
  bounded.
- Ignore-rule limits are enforced across all loaded controls, and adversarial globstar patterns use
  bounded iterative matching.
- User-level updates and uninstall preserve the entire previous managed destination in a
  collision-resistant, tool-reserved backup container. Preserved extras may remain user-owned;
  backups are never deleted automatically and manual recovery is documented.
- Dangling or newly appeared user-level skill paths are treated as unmanaged and are never
  replaced after a clean preview.
- Apply requires the deterministic current-plan fingerprint emitted by preview and revalidates the
  desired payload, resolved target, ancestor identities, expected target state, and backup
  destination before mutation. The fingerprint proves state equality, not prior human review.
- Supported Darwin/Linux apply uses held directory descriptors and descriptor-relative exclusive
  rename; unsupported platforms fail closed while preview remains portable and no-write.
- Existing symlink, junction, and reparse-point ancestors are rejected. Descriptor anchoring blocks
  replacement-link traversal; operators must still exclude a hostile same-user process from the
  final POSIX visibility-check-to-rename interval.
- Tool-managed payload bytes are hash-bound. User-owned extra bytes are never opened; their path,
  identity, type, size, mode, link count, and change/modify metadata bind the preserved tree.
- Backup containers are reserved without replacement; a post-preview collision fails closed
  instead of overwriting another backup.
- Partial installer creation failures and Python-level interruptions remove only
  identity-verified, tool-created empty directories. An interruption before identity capture
  produces an explicit unconfirmed-private-residue diagnostic; a concurrently substituted path is
  preserved and reported rather than mistaken for tool-owned residue. Once anchors exist,
  activation interruptions inspect descriptor-anchored target/backup state.
- Managed install manifests reject unsafe version labels before any backup path is created.
- Managed destination files with multiple hard links are rejected without reading their bytes.
- Bundled installer resources must belong to the currently executing source checkout or installed
  distribution; unrelated installed data cannot override the code being run.
- File reads use one bounded, nonblocking descriptor with regular-file and identity checks, so a
  candidate replaced by a FIFO or other non-regular object cannot block the audit.
- POSIX reads and directory enumeration require descriptor-path resolution, exact intended-path
  equality, and requested-root containment before consuming bytes or entries.
- Secret-like path components and multiply-linked candidates are excluded from reads.
- Non-printing Unicode paths are replaced by one-way hash markers in report and public-scan
  displays, preventing bidi and zero-width terminal spoofing.
- Automatic-import expansion uses a releasing queue, deduplicates repeated source/target edges,
  and stops at the aggregate reference cap with partial coverage instead of retaining millions of
  duplicate work items.
- Report metadata is reduced to a fixed safe summary, and out-of-root relative reference targets
  are replaced with typed placeholders and one-way hashes.
- Custom-ignored candidates or directories, unreadable traversal points, concurrent disappearance,
  and exhausted caps make coverage explicitly partial.
- Escaped leading `#` and `!` Git-ignore patterns retain their literal meaning, preventing ignored
  agent-document names from entering the read set.
- Windows drive, UNC, home-style, and current-drive-rooted references are privacy-minimized.
- Invalid filesystem references are privacy-minimized before platform path resolution.
- Standalone validation now matches the published positive-integer contract for additive engine
  configuration and coverage-limit fields.
- Both validator entry points reject duplicate JSON keys, non-standard numeric constants,
  unhashable discriminator values, non-finite or underflowing floats, excessive numeric tokens,
  and over-deep or over-large input without tracebacks.
- Validator diagnostics do not echo arbitrary report keys or finding IDs; control characters,
  individual messages, total diagnostic bytes, and error counts are bounded.
