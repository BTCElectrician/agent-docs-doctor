# Platform behavior

Verified against official sources on 2026-10-02. Treat all platform behavior as version-sensitive
and re-check before a migration.

## Contents

- [Shared vocabulary](#shared-vocabulary)
- [OpenAI Codex](#openai-codex)
- [Claude Code](#claude-code)
- [Cursor](#cursor)
- [GitHub Copilot](#github-copilot)
- [Gemini CLI](#gemini-cli)
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

The global file lives in the Codex home directory, `~/.codex` unless `CODEX_HOME` is set.

Sources: [OpenAI, Custom instructions with AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
and [OpenAI, Configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).
The older `developers.openai.com/codex/...` addresses redirect to these pages.

### Skills and plugins

Codex discovers project skills from `.agents/skills` in the working directory and each parent up to
the repository root. User-level skills live under `$HOME/.agents/skills`, administrator skills
under `/etc/codex/skills`, and built-in system skills ship with Codex. Skills use progressive
disclosure: name, description, and path are available for routing; the body loads when selected;
bundled resources load as needed. The initial skill list uses at most 2% of the model's context
window (8,000 characters when the window is unknown), so a precise trigger description matters.
Optional `agents/openai.yaml` metadata controls display (`interface`), implicit invocation
(`policy.allow_implicit_invocation`), and declared tool dependencies.

Use a skill for one repeatable capability or repository workflow. Use a plugin when distribution needs a stable package containing multiple skills, hooks, apps, MCP configuration, or other lifecycle assets. The formerly central `openai/skills` repository now redirects current examples toward plugins, though its system skill-creator remains useful authoring tooling.

Sources: [OpenAI, Build skills](https://learn.chatgpt.com/docs/build-skills), [OpenAI, Build plugins](https://learn.chatgpt.com/docs/build-plugins), [openai/plugins](https://github.com/openai/plugins), and [openai/skills](https://github.com/openai/skills).

### Instruction design and evaluation

OpenAI publishes prompting guidance for its newest model family on a stable "latest model" page;
on 2026-10-02 that page covered the GPT-6 family. It says the newest model follows instructions
more closely and "can be more sensitive to instructions contained in skills and other files, such
as `AGENTS.md`," and it strongly recommends auditing those files. It also advises making the
priority between user instructions and skill instructions explicit, and evaluating each suggested
prompt change against your own model and workload. The previous generation's guidance recommended
trimming repeated rules, obsolete process scaffolding, irrelevant tools, and contradictions while
preserving safety, business, evidence, permission, validation, and stop constraints. Published
gains from leaner prompts are directional and workload-dependent, not a promise for another
repository.

Sources: [OpenAI, Using the latest model](https://developers.openai.com/api/docs/guides/latest-model),
[OpenAI, GPT-5.6 prompt guidance](https://developers.openai.com/api/docs/guides/prompt-guidance-gpt-5p6),
and [OpenAI, Evaluation best practices](https://developers.openai.com/api/docs/guides/evaluation-best-practices).

## Claude Code

### Memory and imports

At launch, Claude Code loads `CLAUDE.md`, `.claude/CLAUDE.md`, and `CLAUDE.local.md` along the
ancestor path from filesystem root to the current working directory, plus user-level
`~/.claude/CLAUDE.md` and any organization-managed `CLAUDE.md`. Files are concatenated rather than
overridden; within a directory, `CLAUDE.local.md` follows `CLAUDE.md`. Files below the working
directory load when Claude reads files in their subtree. `claudeMdExcludes` settings can skip
specific files, except managed ones.

`@path` imports resolve relative to the importing file and recurse to a maximum depth of four hops.
Imports may appear inline ("See @README for ...") as well as on their own line, and import parsing
skips code spans and fenced code blocks. Imports outside the working directory require a one-time
approval in shared projects. An import organizes ownership but does not reduce the imported
content's context cost, because imported files also load at launch.

Claude Code now reads `AGENTS.md` natively (v2.1.277 or later). Under the default
`claude-md-or-agents-md` setting it reads every `AGENTS.md` and `.claude/AGENTS.md` in the working
directory and above it only when no `CLAUDE.md`, `.claude/CLAUDE.md`, or `CLAUDE.local.md` exists
there. User and managed `CLAUDE.md` files and `.claude/rules/` do not count for that check. A
subdirectory's `AGENTS.md` loads on demand when that subdirectory has none of the three Claude
files. `@path` imports inside a natively read `AGENTS.md` are expanded. A user or managed setting
can change the mode to read both files, only `CLAUDE.md`, or only managed instructions; project
settings cannot. Some sessions still cannot read `AGENTS.md` directly, so a `CLAUDE.md` containing
`@AGENTS.md` remains a valid compatibility pattern and is never read twice. A `CLAUDE.md` that only
tells Claude in words to read `AGENTS.md`, or a `SessionStart` hook that prints it, is now an
obsolete workaround: the first depends on the model choosing to open the file and the second adds a
duplicate copy.

Claude Code also ships `/doctor prompt-audit` (v2.1.283 or later), a model-driven audit of
`CLAUDE.md`, `CLAUDE.local.md`, `AGENTS.md`, and `.claude/` surfaces that proposes edits without
applying them.

Source: [Anthropic, How Claude remembers your project](https://code.claude.com/docs/en/memory).

#### How Agent Docs Doctor models this

- An `AGENTS.md` is labeled `claude-code` only when no `CLAUDE.md`, `.claude/CLAUDE.md`, or
  `CLAUDE.local.md` exists in its directory or an ancestor inside the audited root. Files above the
  root and user settings are invisible to the auditor, so the label is a filename inference.
- `@path` lines in such an `AGENTS.md` become automatic-import edges, like those in `CLAUDE.md`.
- The auditor recognizes only imports on a line of their own. Inline imports are not expanded and
  may appear as plain text.
- Files reached by more than four import hops stay in the inventory, but they are not labeled as
  automatically loaded. The engine's own `max_import_depth` resource bound is separate and larger.

### Rules, skills, and hooks

`.claude/rules/**/*.md` files without `paths` load at launch. Rules with `paths` load when matching
files are read. This is file scope, not event scope. User-level rules in `~/.claude/rules/` apply
to every project.

Claude skills progressively disclose their body and resources and support the Agent Skills core
plus Claude-specific extensions such as `when_to_use`, `disable-model-invocation`, `paths`, and
`context: fork`. User-level skills live under `~/.claude/skills`; project skills live under
`.claude/skills` in the working directory and each parent up to the repository root, and nested
`.claude/skills` folders load when Claude works in their subtree. The skills documentation does not
list `.agents/skills` as a Claude Code location. Historical `.claude/commands` still work, but
commands have converged into skills.

Hooks run on lifecycle events. Only a synchronous, block-capable event with valid deny output or the documented blocking exit behavior is enforcement. Async and observational hooks cannot block.

Sources: [Anthropic, Memory](https://code.claude.com/docs/en/memory), [Anthropic, Skills](https://code.claude.com/docs/en/skills), and [Anthropic, Hooks](https://code.claude.com/docs/en/hooks).

Anthropic's target of fewer than 200 lines per `CLAUDE.md` is guidance about context and adherence, not an enforced validity limit.

## Cursor

### Rules and `AGENTS.md`

Cursor project rules use `.cursor/rules/*.mdc`, optionally in subfolders; plain `.md` files in that directory are ignored by the rules system. MDC modes are Always (`alwaysApply: true`), Intelligent (description-selected), Specific Files (`globs`), and Manual. `paths` is not the MDC rule field. Team Rules from the dashboard take precedence over project rules, which take precedence over User Rules.

The legacy root `.cursorrules` file is no longer described in Cursor's rules documentation. Agent
Docs Doctor inventories it as a `legacy-rule-file` with `platform-dependent` loading, because
current official sources neither confirm nor deny that every Cursor surface still reads it.

Cursor IDE supports root and nested `AGENTS.md`. Nested files combine with parents and apply to their directory subtree, with more-specific guidance taking precedence. Cursor CLI has additional root-file compatibility behavior, including root `CLAUDE.md`; do not generalize CLI behavior to every Cursor surface.

Source: [Cursor, Rules](https://cursor.com/docs/rules) and [Cursor, CLI](https://cursor.com/docs/cli/using).

### Skills, hooks, and ignore files

Cursor documents both `.agents/skills` and `.cursor/skills` for project use, plus their matching
user-level locations, and for compatibility also loads `.claude/skills` and `.codex/skills`
locations. Agent Docs Doctor installs to the native `~/.cursor/skills` location because
compatibility-path behavior has not always matched across Cursor surfaces. Skills support
progressive disclosure, `paths` scope, and `disable-model-invocation`. Cursor's `/migrate-to-skills`
command converts eligible dynamic rules and slash commands into skills.

Cursor hooks differ by event and surface. Some fail open unless `failClosed` is configured; some are fire-and-forget; user hooks do not run in cloud agents. Audit the exact event, blocking contract, failure mode, and local/cloud coverage.

`.cursorignore` reduces access by built-in context features, but terminal and MCP tools can bypass it. It is a privacy and exposure-reduction control, not a complete security boundary. Current ignore-file documentation no longer mentions `.cursorindexingignore`; the auditor still inventories it when present.

Sources: [Cursor, Skills](https://cursor.com/docs/skills), [Cursor, Hooks](https://cursor.com/docs/hooks), and [Cursor, Ignore files](https://cursor.com/docs/reference/ignore-file).

Cursor's recommendation to keep rules under 500 lines is focus guidance, not a hard cap.

## GitHub Copilot

Copilot supports three kinds of repository instructions:

- **Repository-wide:** `.github/copilot-instructions.md`.
- **Path-specific:** `.github/instructions/**/NAME.instructions.md`, scoped by an `applyTo` glob in
  frontmatter. An optional `excludeAgent` field can hide a file from code review or the cloud agent.
  VS Code can also select one by its `description`.
- **Agent instructions:** `AGENTS.md` anywhere in the repository, where the nearest file in the
  directory tree takes precedence, or a single `CLAUDE.md` or `GEMINI.md` at the repository root.

Support differs by surface. Repository-wide instructions are the most widely supported. Agent
instructions are supported by the cloud agent, code review on GitHub.com, VS Code chat, and Copilot
CLI, but not by every chat surface. In VS Code, several of these sources sit behind settings such as
`chat.useAgentsMdFile`, `chat.useNestedAgentsMdFiles`, and `chat.useClaudeMdFile`, and the local
agent can also read `.claude/rules`. Personal instructions take priority over repository
instructions, which take priority over organization instructions.

Agent Docs Doctor labels `.github/copilot-instructions.md` as automatic, path-specific files as
conditional when they declare `applyTo` or `description`, and root `CLAUDE.md`, root `GEMINI.md`,
and every `AGENTS.md` as also visible to `github-copilot`. Those labels mean "a Copilot surface may
load this," not "every Copilot surface loads this."

Sources: [GitHub, Adding repository custom instructions](https://docs.github.com/en/copilot/how-tos/configure-custom-instructions/add-repository-instructions),
[GitHub, Support for different types of custom instructions](https://docs.github.com/en/copilot/reference/custom-instructions-support),
and [VS Code, Custom instructions](https://code.visualstudio.com/docs/copilot/customization/custom-instructions).

## Gemini CLI

Gemini CLI loads a global `~/.gemini/GEMINI.md`, then `GEMINI.md` files in the workspace
directories and their parents, then just-in-time `GEMINI.md` files found when a tool accesses a
directory (searching its ancestors up to a trusted root). Context files can import others with
`@file.md`. `GEMINI.md` is the default name; the `context.fileName` setting in `settings.json` can
replace it or add names such as `AGENTS.md`, so Gemini CLI reads `AGENTS.md` only when configured
to.

Agent Docs Doctor inventories `GEMINI.md` as an automatic `gemini-cli` instruction. It does not
parse Gemini settings, so it cannot see a custom `context.fileName`, and it records `@file` lines in
`GEMINI.md` as plain references rather than expanding them.

Source: [Gemini CLI, Provide context with GEMINI.md files](https://geminicli.com/docs/cli/gemini-md/).

## Agent Skills portability

The open Agent Skills specification requires a directory containing `SKILL.md` with YAML frontmatter. `name` is required: 1 to 64 lowercase letters, digits, and single hyphens, matching the parent directory. `description` is required and limited to 1,024 characters. Optional core fields are `license`, `compatibility` (up to 500 characters), `metadata` (a string-to-string map), and the experimental `allowed-tools`. The specification recommends keeping `SKILL.md` under 500 lines, with detail moved to `references/`, `scripts/`, or `assets/`. Consumers may add extensions, so keep portable behavior in the core skill and label consumer-specific metadata.

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
- Do not assume a tool ignores `AGENTS.md` because it has its own filename; Claude Code and GitHub
  Copilot now read it, and Gemini CLI can be configured to.
- Do not prescribe one canonical-file architecture as an official cross-vendor standard.
- Do not claim a challenger is faster, cheaper, or more accurate without frozen comparative evaluation.
