# Audit rubric

Use a nonnumeric evidence matrix. Severity communicates review urgency, not a scientifically validated health score.

## Contents

- [Evidence classes](#evidence-classes)
- [Severity](#severity)
- [Finding requirements](#finding-requirements)
- [Coverage gate](#coverage-gate)
- [Diagnosis prompts](#diagnosis-prompts)
- [Preservation gate](#preservation-gate)

## Evidence classes

| Class | Meaning | Examples |
|---|---|---|
| Deterministic | Reproducible from bytes, paths, or parsed metadata | exact block overlap, broken local link, retired metadata outside archive |
| Platform-verified | Supported by a cited current official source | Codex selects at most one instruction file per directory |
| Model judgment | Semantic interpretation with confidence and alternatives | likely contradiction, stale authority, procedure better suited to a skill |
| User decision | Depends on local risk, history, or ownership | whether repeated safety text is load-bearing |

## Severity

| Level | Use when | Required response |
|---|---|---|
| Critical | Evidence indicates an immediate conflict or omission around secrets, production, destructive actions, legal/health/financial risk, authentication, privacy, or data integrity | Stop migration; surface first; require owner decision |
| High | Stale authority, wrong platform assumption, broken rollback/release gate, or ambiguity could plausibly cause harmful action | Resolve before adopting a challenger |
| Medium | Duplication, competing current-state surfaces, excess automatic context, unclear ownership, or broken reference degrades reliability | Address in planned redesign or document why retained |
| Low | Organization, wording, discoverability, or maintainability issue with limited behavioral risk | Fix opportunistically |
| Informational | Measured inventory or neutral architecture fact | No action required |

Severity must trace to concrete evidence and impact. A large file alone is informational until platform loading and likely impact are established.

## Finding requirements

Every finding must contain:

1. stable identifier and category;
2. severity and evidence class;
3. exact paths and line ranges;
4. observed fact, separate from interpretation;
5. platform scope and loading state;
6. impact hypothesis;
7. confidence and plausible alternative explanation;
8. preservation concern;
9. recommended action or explicit no-change decision;
10. validation or evaluation needed before adoption.

Reject findings that merely say a file is "too long," "duplicated," or "confusing" without loading scope, impact, and evidence.

## Coverage gate

Read `coverage.status`, bounded skip records, and warnings before interpreting absence. `complete`
means complete only within the declared candidate and default-exclusion scope; it is not a
whole-repository content scan. Custom-ignored candidates or directories, unreadable traversal
points, non-regular candidates, concurrent disappearance, and exhausted traversal, read,
reference, paragraph, finding, location, or skip caps make coverage partial.

When coverage is partial:

- identify the exact omitted scope or exhausted evidence class;
- treat claims about that area as unknown;
- do not say there are no conflicts, stale authorities, leaks, or other issues across the whole
  repository;
- stabilize the checkout, narrow the input, or obtain owner-approved access before rerunning; and
- keep the limitation adjacent to every conclusion that depends on missing evidence.

Schema-valid JSON proves conformance, not coverage completeness or documentation health.

## Diagnosis prompts

### Authority and current truth

- Which file claims authority, and what consumes it?
- Does another non-archived file make the same claim?
- Is a status file global or scoped to one component?
- Does a retired document retain unqualified inbound links?

### Duplication and contradiction

- Is overlap exact, near, or only thematic?
- Does repetition bridge consumers that cannot share a canonical source?
- Does it intentionally repeat a safety invariant at an exported subtree boundary?
- Are the rules mutually exclusive under the same task and scope?
- Does documented platform precedence actually resolve the difference?

### Context and procedure

- Is the content automatic, conditional, manual, or merely discoverable?
- Is a long passage a stable invariant or a task procedure?
- Would a script, validator, schema, test, or synchronous hook provide deterministic enforcement?
- Would moving the rule make it less likely to load when needed?

### Evidence quality

- Does the rule cite a current command, path, owner, incident class, or validation?
- Can its stated command run from the documented working directory?
- Is the platform claim current and official, or inferred from behavior?

## Preservation gate

Before recommending consolidation, archiving, or deletion, identify whether the text protects:

- credentials or private data;
- production, release, destructive operations, or rollback;
- authentication, authorization, billing, finance, legal, or health decisions;
- repository ownership or cross-repository scope;
- migrations, schemas, backups, or data integrity;
- incident-derived knowledge;
- current implementation authority.

If history or operational necessity is unknown, recommend owner review and preserve the incumbent text in the challenger traceability map.
