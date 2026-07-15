# Product thesis and competitive landscape

Research snapshot: 2026-07-15. Stars, releases, and maintenance status are point-in-time evidence, not enduring quality claims.

## Thesis

The strongest product is not another instruction generator or universal readiness score. It is a local-first **evidence doctor**:

> Inventory the complete agent-document system, explain what each consumer actually loads, separate reproducible facts from semantic judgment, protect safety and incident knowledge, and require evaluation plus approval before migration.

Three observations support that position:

1. Official platform behavior differs materially. Codex chooses one instruction file per directory; Claude has imports, ancestor memory, path rules, skills, and event hooks; Cursor distinguishes MDC rule modes, nested `AGENTS.md`, skills, surface-specific hooks, and incomplete ignore boundaries.
2. Existing products specialize. Readiness suites, generators, migration tools, conflict vocabularies, context-size audits, and enforcement mappers each cover part of the problem.
3. The dangerous gap is between measured syntax and operational meaning. Exact overlap is easy to prove; whether it is a harmful duplicate, a cross-client adapter, or a deliberately repeated safety rule requires traceable judgment.

Therefore Agent Docs Doctor uses a deterministic evidence ledger without a numeric health score, then asks an agent to produce evidence-linked findings, a preservation register, a challenger traceability map, and a frozen evaluation.

## Competitive landscape

| Project | Category and verified snapshot | What it proves | Remaining opening |
|---|---|---|---|
| [Microsoft AgentRC](https://github.com/microsoft/agentrc) | readiness/generation/eval suite; 960 stars; MIT; active 2026-07-15; v2.1.0 tag | broad readiness and instruction evaluation are real products | narrower deterministic doc semantics and platform loading without an LLM dependency |
| [github/awesome-copilot](https://github.com/github/awesome-copilot) | catalog; 36,609 stars; MIT; active 2026-07-14 | distribution and reusable skills have large demand | not a scanner; its `create-agentsmd` and AgentRC skills are generative wrappers |
| [Microsoft Skills: wiki-agents-md](https://github.com/microsoft/skills/tree/main/.github/plugins/deep-wiki/skills/wiki-agents-md) | nested instruction generator; parent 2,747 stars; MIT; active 2026-07-14 | conservative no-overwrite generation is a useful guardrail | intentionally skips auditing incumbent documentation |
| [obra/superpowers](https://github.com/obra/superpowers) | skills methodology and behavior evals; 255,198 stars; MIT; v6.1.1 on 2026-07-02 | fresh-agent behavior tests are essential for skills | adjacent methodology, not an agent-doc diagnosis product |
| [0xmariowu/AgentLint](https://github.com/0xmariowu/AgentLint) | readiness/context linter; 45 stars; MIT; v1.1.13 | deterministic checks plus optional AI and SARIF are credible | deeper precedence, evidence provenance, and score skepticism differentiate this project |
| [samilozturk/agentlint](https://github.com/samilozturk/agentlint) | multi-artifact context CLI/MCP; 29 stars; MIT; active 2026-04-08 | users want stale/conflict/weak-instruction diagnosis | this project avoids required MCP/client setup and keeps deterministic claims inspectable |
| [ruleprobe](https://github.com/moonrunnerkc/ruleprobe) | prose-to-enforcement/drift mapping; 2 stars; MIT; v4.5.0 | some rules should map to executable controls | broader authority/current-state/platform semantics remain outside its scope |
| [agentchecker](https://github.com/moisesvalero/agentchecker) | cross-agent contradiction detector; 0 stars; MIT; v0.1.8 | package/linter/test decision conflicts can be modeled deterministically | vocabulary is narrow and the project is new |
| [context-audit-openclaw-skill](https://github.com/kesslerio/context-audit-openclaw-skill) | OpenClaw context-bloat audit; 0 stars; Apache-2.0; active 2026-07-14 | read-only size and exact-overlap audits are useful | OpenClaw-specific, with no cross-platform authority map |
| [ccode-to-codex](https://github.com/zuharz/ccode-to-codex) | Claude-to-Codex migration/audit; 59 stars; MIT; active 2026-06-10 | dry-run risk classification is a strong migration pattern | one-time migration rather than ongoing governance health |
| [rulesentry](https://github.com/mohamedzhioua/rulesentry) | Unicode/instruction-smuggling scanner; 2 stars; MIT; v0.2.0 | agent config has a supply-chain security surface | intentionally narrow; complementary rather than competing |
| [agent-standard-oss](https://github.com/anmoln7/agent-standard-oss) | canonicalization/drift convention; 13 stars; MIT; v0.10.0 | cross-client canonicalization can be automated | a doctor should diagnose before prescribing one convention |
| [agents.md](https://github.com/agentsmd/agents.md) | flexible format/ecosystem; 23,036 stars; MIT | `AGENTS.md` is established infrastructure | flexibility is not a semantic validation schema |

Requested names that are not standalone products:

- `create-agentsmd`, `acreadiness-assess`, and `acreadiness-generate-instructions` are skills inside `github/awesome-copilot`.
- `wiki-agents-md` is a skill inside Microsoft's `deep-wiki` plugin.
- the closest verified “OpenClaw context-audit” match is a third-party skill, not an official OpenClaw project.

## Positioning decision

Keep the name **Agent Docs Doctor**. “Linter” implies deterministic pass/fail rules; “readiness” implies a broad maturity score; “generator” centers new files instead of incumbent truth. “Doctor” supports the intended sequence—observe, explain, diagnose, preserve, recommend, challenge, evaluate—while the subtitle makes the scope searchable: *evidence-first audits for agent-facing repository documentation*.

## Architecture decision

Build one public repository that is itself an installable Agent Skill and includes a zero-dependency Python evidence engine. Keep detailed platform, rubric, schema, evaluation, and migration guidance in directly linked references. Keep tests, synthetic fixtures, research, and contributor docs at repository level.

### Rejected alternatives

- **Model-only audit:** flexible but irreproducible for discovery, exact overlap, and references.
- **Deterministic-only linter:** cannot safely decide semantic conflict, staleness, or operational necessity.
- **Numeric health score:** compresses incomparable risks and invites false precision.
- **Automatic rewrite/generator:** creates governance risk before authority and safety are understood.
- **Plugin first:** a plugin is justified when distribution needs multiple skills, hooks, apps, or MCP configuration. One focused local skill is the current product.
- **Framework or database:** no demonstrated value for a read-only local audit; standard-library Python is portable and inspectable.
- **One canonical architecture for every repository:** platform compatibility is not proof that one ownership model fits every organization.

## Source-report critique applied to the design

The motivating research correctly emphasized duplication, stale authority, startup context, safety preservation, and evaluation. Live verification rejected or narrowed several stronger claims:

- 200 Claude lines and 500 Cursor lines are guidance, not enforced ceilings.
- a Codex fallback filename is an alternative, not an additive adapter when `AGENTS.md` exists in the same directory;
- Codex's instruction byte budget should not be conflated with files an agent manually reads later;
- prompt instructions and ignore files are not deterministic enforcement or complete privacy fences;
- Claude rule `paths` and Cursor MDC `globs` are different fields;
- a cross-vendor canonical-plus-adapters pattern is reasonable architecture, not a uniform official standard;
- platform repository and distribution guidance can change quickly, so dated official sources belong in the product.

These corrections are encoded in [the platform reference](../references/PLATFORM_BEHAVIOR.md).
