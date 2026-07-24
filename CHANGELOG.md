# Changelog

## Unreleased

### Added

- Installable `agent-docs-doctor` console command with text and JSON audit output.
- Preview-first user-level skill install, update, and reversible uninstall for Codex, Claude Code,
  and Cursor.
- Environment `doctor`, complete v2 JSON Schema, engine/configuration provenance, and explicit
  complete-or-partial coverage.
- Safe recursive inventory of recognized `CLAUDE.md` imports.
- Linux, macOS, and Windows CI across Python 3.10 and 3.13.

### Changed

- First-run documentation now starts with one read-only command and a plain-language result.
- Human decision reviews support stable pagination when more than seven decisions exist.

### Security

- Imported targets retain typed missing, ignored, secret-like, non-regular, invalid, depth-limited,
  and out-of-root dispositions without being opened.
- Candidate count, aggregate bytes, file bytes, import depth, and ignore controls are bounded.
- User-level updates and uninstall preserve the previous skill in a reversible backup.
- Dangling or newly appeared user-level skill paths are treated as unmanaged and are never
  replaced after a clean preview.
- Escaped leading `#` and `!` Git-ignore patterns retain their literal meaning, preventing ignored
  agent-document names from entering the read set.
