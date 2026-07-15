# Incumbent-versus-challenger evaluation

Use this protocol before claiming an instruction redesign improves behavior.

## Contents

- [1. Freeze the experiment](#1-freeze-the-experiment)
- [2. Build the task set](#2-build-the-task-set)
- [3. Define measures](#3-define-measures)
- [4. Run without contamination](#4-run-without-contamination)
- [5. Judge and compare](#5-judge-and-compare)
- [6. Adoption gate](#6-adoption-gate)

## 1. Freeze the experiment

Record immutable identifiers for the incumbent and challenger, repository snapshot, model/client version, reasoning setting, tools, permissions, environment, and prompts. Do not edit either condition mid-run. If a defect requires a revision, create a new challenger identifier and restart comparable cases.

## 2. Build the task set

Use representative tasks from the repository's actual work distribution. Include:

- ordinary implementation or content work;
- status and ownership questions;
- a task that triggers each load-bearing safety rule;
- nested-directory work;
- a request where stale history could mislead;
- an ambiguous task where a useful clarifying question is appropriate;
- at least one task outside software engineering when the repository serves broader work.

Keep prompts natural. Do not encode the expected diagnosis. Separate development fixtures from the held-out set.

## 3. Define measures

Prefer task-specific pass/fail rubrics and observable counts:

| Dimension | Example measure |
|---|---|
| Correctness | required outcome and validations satisfied |
| Safety | protected action blocked or approval requested at the correct boundary |
| Instruction adherence | applicable rule followed without importing unrelated rules |
| Evidence quality | claims tied to commands, files, diffs, or current sources |
| Context selectivity | irrelevant instruction files read |
| Stale influence | retired or superseded source affected the answer |
| Friction | unnecessary questions, approvals, or planning turns |
| Communication | commentary and final output meet task needs without omission |
| Efficiency | time to first useful action, wall time, tokens, and cost when observable |
| Cross-platform behavior | same invariant survives each supported consumer |

Resource savings count only when correctness and safety still pass.

## 4. Run without contamination

- Use fresh agents or clean sessions for every condition.
- Provide only the condition's repository snapshot, task prompt, and normal platform context.
- Do not reveal intended findings, prior failures, expected fixes, or judge criteria that a real user would not provide.
- Randomize or blind condition labels where practical.
- Keep run outputs outside later agents' discovery paths.
- Never reuse a session after it has seen both incumbent and challenger.
- Record failures before hardening; do not delete inconvenient runs.

## 5. Judge and compare

Use deterministic graders where the task has objective outputs. Calibrate model or rubric judges against human review. Report per-task outcomes, not only averages. Include regressions, uncertainty, missing telemetry, and sample size.

Do not borrow acceptance percentages from another repository. Define thresholds before runs based on local risk. Safety-critical cases should generally require zero regressions.

## 6. Adoption gate

Adopt only when:

1. safety has no unexplained regression;
2. task correctness meets the predeclared threshold;
3. the challenger improves at least one target measure without material hidden cost;
4. every incumbent safeguard maps to a challenger location or an explicit owner-approved retirement;
5. rollback is tested;
6. residual risk is documented.

If results are mixed, keep the incumbent and design a narrower challenger.
