# Platform behavior

Verified against official sources on 2026-07-24. Treat all platform behavior as version-sensitive
and re-check before a migration.

## Contents

- [Shared vocabulary](#shared-vocabulary)
- [OpenAI Codex](#openai-codex)
- [Claude Code](#claude-code)
- [Cursor](#cursor)
- [Agent Skills portability](#agent-skills-portability)
- [Claims not safe to generalize](#claims-not-safe-to-generalize)

## Shared vocabulary

- **Automatic**: loaded without task-specific model selection.
- **Conditional**: loaded after a path, description, or skill match.
- **Manual**: loaded only through an explicit mention, command, import, or read.
- **Discoverable**: visible to search or the agent but not documented as instruction context.
- **Enforced**: blocked by a deterministic control. Prompt text alone is not enforcement.

## OpenAI Codex

### `AGENTS.md`

Codex constructs an instruction chain once per run. It first selects a global `AGENTS.override.md` or `AGENTS.md`, then walks from the repository root to the current working directory. In each directory it selects at most one non-empty file in priority order: `AGENTS.override.md`, `AGENTS.md`, then configured fallback filenames. Selected project files concatenate root to leaf, and nearer guidance takes precedence on conflict. Discovery stops at the current working directory.

User configuration normally lives at `~/.codex/config.toml`. Codex can also layer project-scoped
`.codex/config.toml` files from the project root toward the working directory, but only for trusted
projects. This auditor reads only the requested root's non-ignored `.codex/config.toml` to discover
`project_doc_fallback_filenames`. Its `loading: automatic` label means Codex behavior when that
trusted project configuration layer is active; the auditor does not infer or attest trust.

The dedicated guide describes `project_doc_max_bytes` as a combined chain limit with a 32 KiB default. A separate advanced-config page has used per-file wording, so exact byte-limit semantics should be verified against the deployed Codex version. A fallback such as `CLAUDE.md` is an alternative in a directory, not an additional file when `AGENTS.md` already exists there.

Sources: [OpenAI, Custom instructions with AGENTS.md](https://developers.openai.com/codex/guides/agents-md)
and [OpenAI, Configuration reference](https://developers.openai.com/codex/config-reference).

### Skills and plugins

Current Codex project skills are discovered from `.agents/skills` between the working directory and
repository root. User-level skills live under `$HOME/.agents/skills`. Skills use progressive
disclosure: name, description, and path are available for routing; the body loads when selected;
bundled resources load as needed. The initial skill list is budgeted, so a precise trigger
description matters.

Use a skill for one repeatable capability or repository workflow. Use a plugin when distribution needs a stable package containing multiple skills, hooks, apps, MCP configuration, or other lifecycle assets. The formerly central `openai/skills` repository now redirects current examples toward plugins, though its system skill-creator remains useful authoring tooling.

Sources: [OpenAI, Build skills](https://learn.chatgpt.com/docs/build-skills), [OpenAI, Build plugins](https://learn.chatgpt.com/docs/build-plugins), [openai/plugins](https://github.com/openai/plugins), and [openai/skills](https://github.com/openai/skills).

### Instruction design and evaluation

Current GPT-5.6 guidance recommends defining the outcome, constraints, evidence, and completion bar while leaving the execution path to the agent. It recommends trimming repeated rules, obsolete process scaffolding, irrelevant tools, and contradictions while preserving safety, business, evidence, permission, validation, and stop constraints. Its published internal gains from leaner system prompts are directional and workload-dependent, not a promise for another repository.

Sources: [OpenAI, GPT-5.6 prompt guidance](https://developers.openai.com/api/docs/guides/prompt-guidance-gpt-5p6) and [OpenAI, Evaluation best practices](https://developers.openai.com/api/docs/guides/evaluation-best-practices).

## Claude Code

### Memory and imports

At launch, Claude Code loads `CLAUDE.md` and `CLAUDE.local.md` along the ancestor path from filesystem root to the current working directory. Files below the working directory load when Claude reads files in their subtree. `@path` imports resolve relative to the importing file and can recurse up to the documented depth. External-project imports can require first-use approval.

Claude Code does not natively consume `AGENTS.md` through its project-memory system. Its official compatibility pattern is a `CLAUDE.md` containing `@AGENTS.md` or a symlink. An import organizes ownership but does not reduce the imported content's context cost.

Source: [Anthropic, How Claude remembers your project](https://code.claude.com/docs/en/memory).

### Rules, skills, and hooks

`.claude/rules/**/*.md` files without `paths` load at launch. Rules with `paths` load when matching
files are read. This is file scope, not event scope.

Claude skills progressively disclose their body and resources and support the Agent Skills core
plus Claude-specific extensions. User-level skills live under `~/.claude/skills`; project skills
live under `.claude/skills`. Historical `.claude/commands` still work, but commands have converged
into skills.

Hooks run on lifecycle events. Only a synchronous, block-capable event with valid deny output or the documented blocking exit behavior is enforcement. Async and observational hooks cannot block.

Sources: [Anthropic, Memory](https://code.claude.com/docs/en/memory), [Anthropic, Skills](https://code.claude.com/docs/en/skills), and [Anthropic, Hooks](https://code.claude.com/docs/en/hooks).

Anthropic's target of fewer than 200 lines per `CLAUDE.md` is guidance about context and adherence, not an enforced validity limit.

## Cursor

### Rules and `AGENTS.md`

Cursor project rules use `.cursor/rules/*.mdc`; plain `.md` files in that directory are not project rules. MDC modes are Always (`alwaysApply: true`), Intelligent (description-selected), Specific Files (`globs`), and Manual. `paths` is not the MDC rule field.

Cursor IDE supports root and nested `AGENTS.md`. Nested files combine with parents and apply to their directory subtree, with more-specific guidance taking precedence. Cursor CLI has additional root-file compatibility behavior, including root `CLAUDE.md`; do not generalize CLI behavior to every Cursor surface.

Source: [Cursor, Rules](https://cursor.com/docs/rules) and [Cursor, CLI](https://cursor.com/docs/cli/using).

### Skills, hooks, and ignore files

Cursor documents both `.agents/skills` and `.cursor/skills` for project use, plus their matching
user-level locations. Agent Docs Doctor installs to the native `~/.cursor/skills` location because
current Cursor CLI compatibility-path behavior has not always matched the editor. Skills support
progressive disclosure and path scope. Cursor commands are migrating toward manually invoked
skills.

Cursor hooks differ by event and surface. Some fail open unless `failClosed` is configured; some are fire-and-forget; user hooks do not run in cloud agents. Audit the exact event, blocking contract, failure mode, and local/cloud coverage.

`.cursorignore` reduces access by built-in context features, but terminal and MCP tools can bypass it. It is a privacy and exposure-reduction control, not a complete security boundary.

Sources: [Cursor, Skills](https://cursor.com/docs/skills), [Cursor, Hooks](https://cursor.com/docs/hooks), and [Cursor, Ignore files](https://cursor.com/docs/context/ignore-files).

Cursor's recommendation to keep rules under 500 lines is focus guidance, not a hard cap.

## Agent Skills portability

The open Agent Skills specification requires a directory containing `SKILL.md` with a matching lowercase-hyphenated `name` and a meaningful `description`. It permits additional core fields, but consumers may add extensions. Keep portable behavior in the core skill and label consumer-specific metadata.

The public `anthropics/skills` repository is not uniformly permissively licensed; several document skills use restrictive source-available terms. Do not assume a repository-level brand implies every example is reusable.

Sources: [Agent Skills specification](https://agentskills.io/specification), [agentskills/agentskills](https://github.com/agentskills/agentskills), and [anthropics/skills](https://github.com/anthropics/skills).

### Agent Docs Doctor installer boundary

The client paths above describe expected user-level discovery locations, not permission to write
them. Agent Docs Doctor 0.3.0 previews one resolved client destination and emits a deterministic
current-plan fingerprint for apply. The fingerprint proves current state equality, not prior human
review. Preview is portable and no-write; apply uses descriptor-relative operations on supported
Darwin/Linux runtimes and fails closed elsewhere. It rejects unmanaged destinations and existing
symlink, junction, or reparse-point ancestors; updates and uninstalls retain the entire prior
managed destination in a tool-reserved backup container that is never automatically deleted.
Preserved extra contents may remain user-owned. If a catchable interruption lands after private
directory creation but before identity capture, apply fails with an explicit
unconfirmed-private-residue diagnostic rather than removing a pathname whose ownership cannot be
proved.

On POSIX audit platforms, descriptor-path verification is mandatory for candidate reads and
directory enumeration. The descriptor must resolve to the exact intended path under the requested
root; unavailable resolution, ancestor aliases, and concurrent path replacement fail closed before
bytes or directory entries are consumed. Non-printing Unicode path displays are hash-only.

That installer operation is not an audit and does not change the repository being audited. It is
also not a universal platform guarantee: other installers may follow links, overwrite unmanaged
files, or use different locations.

## Claims not safe to generalize

- Do not describe guidance thresholds as hard size ceilings.
- Do not assume concatenation order always defines conflict resolution.
- Do not call prompt rules enforcement.
- Do not assume ignored paths are inaccessible to shell or external tools.
- Do not assume every adapter saves context; an import may still load the full canonical file.
- Do not prescribe one canonical-file architecture as an official cross-vendor standard.
- Do not claim a challenger is faster, cheaper, or more accurate without frozen comparative evaluation.
