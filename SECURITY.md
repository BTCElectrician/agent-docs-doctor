# Security policy

## Supported version

Security fixes are applied to the current `main` branch until tagged releases begin.

## Reporting a vulnerability

Do not open a public issue for a vulnerability that could expose private repository contents,
bypass ignore or secret-name boundaries, follow an out-of-root filesystem target, or modify an
audited repository.

Use GitHub’s private vulnerability reporting for this repository. Include:

- the affected command and version or commit;
- a minimal synthetic reproduction;
- the expected safety boundary;
- the observed behavior; and
- whether any real private data was exposed.

Never attach real credentials, private governance documents, personal filesystem paths, or customer
repositories. Replace them with synthetic fixtures.

## Safety boundary

The audit engine is designed to be local, read-only, and privacy-minimized. Skill installation is a
separate, explicitly applied user-level operation. A report or recommendation is not authorization
to modify an audited repository.
