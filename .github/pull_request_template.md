## What changed

Describe the user-visible behavior and why this is the smallest correct change.

## Safety boundary

- [ ] Audits remain read-only by default.
- [ ] No private repository text, paths, identities, or secrets were added.
- [ ] New discovery reads have ignore, secret-name, size, symlink/reparse, and root-boundary tests.
- [ ] Deterministic evidence is not presented as semantic judgment.
- [ ] Any schema change is versioned and compatibility-tested.

## Verification

- [ ] Unit and fixture suite
- [ ] Ruff check and format
- [ ] Pyright
- [ ] Cache-free syntax check
- [ ] Wheel build and installed CLI smoke
- [ ] Official Agent Skill validator
- [ ] No-write proof
- [ ] Public-safety scan
