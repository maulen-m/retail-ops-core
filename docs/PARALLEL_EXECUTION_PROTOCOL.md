PARALLEL_EXECUTION_PROTOCOL

Purpose

Define the default multi-agent operating model for `~/Docs/Autonomous_business` so parallel work can be scaffolded automatically, with explicit provenance, minimal merge friction, and no hidden state handoffs.

Default topology

- one write-capable execution agent
- zero or more read-only analyst agents
- one worktree per agent when work is truly parallel
- one shared out-of-repo handoff folder per run

Default roles

Execution agent

- the only agent allowed to write shared repo state
- the only agent allowed to rerun shared pipelines in the operating checkout
- the only agent allowed to mutate `db/app.db`
- the scribe for `.claude/*` when those files must be updated

Analyst agents

- read-only with respect to repo state
- inspect repo files, DB, workbooks, artifacts, and sibling worktrees as needed
- publish findings to the run handoff folder
- do not edit `.claude/*`

Why this default exists

- keeps repo truth changes serialized
- preserves independent first-pass diagnosis
- reduces merge conflicts
- keeps provenance visible
- lets the human owner bootstrap a run with one short prompt

When to use this protocol

Use this protocol when the task:

- has one clear execution path but multiple analysis threads
- needs artifact review, chronology review, or source-provenance review in parallel
- risks DB or shared export conflicts if multiple agents write concurrently
- would benefit from analyst reports before execution starts

Do not use this protocol when:

- multiple agents must perform concurrent writes to the same repo state
- the task is trivial and faster as a single-agent run
- the task is mostly external-system interaction where separate agent coordination adds more friction than value

Shared surfaces

Safe shared surface

- the out-of-repo handoff folder for the current run

Unsafe shared surfaces for parallel writers

- `db/app.db`
- `exports/validation/...`
- `config/*.yaml` used by validators or operational pipelines
- `.claude/*`

DB rule

- only one DB-writing agent at a time
- if a future task absolutely requires parallel DB work, isolate `AB_DATA_DIR` per worktree
- backup first before any apply path

First-pass independence rule

- analyst agents should not read each other's reports before publishing their own first-pass findings
- the execution agent consumes both reports
- only if needed, the execution agent may request a second-pass cross-review

Why this matters

- prevents anchoring bias
- keeps findings independently falsifiable
- still allows transparent collaboration when needed

Scaffolding command

Use the repo scaffold:

- `python3 scripts/init_parallel_rollout.py --slug <slug> --purpose "<purpose>"`

Optional:

- `--as-of YYYY-MM-DD`
- `--focus-b "<read-only focus for Agent B>"`
- `--focus-c "<read-only focus for Agent C>"`
- `--dry-run`
- `--force`

Generated structure

The scaffold creates:

- run docs under:
  - `docs/parallel_runs/<date>_<slug>/`
- shared handoff folder under:
  - `~/Docs/<repo_name>_agent_handoffs/<date>_<slug>/`

Generated run docs

- `PLAN.md`
- `PROMPT_AGENT_A.md`
- `PROMPT_AGENT_B.md`
- `PROMPT_AGENT_C.md`
- `LAUNCH_ORDER.md`

Generated handoff files

- `README.md`
- `status_board.md`
- `agent_b_report.md`
- `agent_c_report.md`
- `agent_a_execution_log.md`

Launch order

Default launch order:

1. Agent B
2. Agent C
3. Agent A after B and C publish first-pass reports

One-agent fallback

If the task is too sensitive or too small for parallel execution:

- launch Agent A only
- execute sequentially

Execution rules

- analysts do not modify repo files
- analysts do not rerun write paths
- execution agent does not begin mutating shared state until upstream analyst findings are available, unless single-agent mode is intentional
- all provenance-sensitive source decisions must be logged in the execution log or final run doc

Closeout expectations

Every run should leave:

- a readable handoff trail in the shared handoff folder
- commands actually run
- before/after gate results
- DB backup path if DB was touched
- rollback steps if repo or DB state changed

Skill hook

Canonical skill name:

- `autonomous-business-parallel-rollout`

That skill should:

1. read repo rules
2. call the scaffold script
3. verify the generated run pack
4. provide the short launch prompts in order
