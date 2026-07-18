PROMPT_AGENT_B

Read first

- `AGENTS.md`
- `docs/00_START_HERE.md`
- `docs/parallel_runs/2026-07-10_ab-continuous-goal-taici-shipping-repair/PLAN.md`
- `docs/PARALLEL_EXECUTION_PROTOCOL.md`

Shared handoff folder

- `~/Docs/Autonomous_business_agent_handoffs/2026-07-10_ab-continuous-goal-taici-shipping-repair`

Your role

- read-only analyst
- focus: rebaseline current final acceptance, P0 on-delivery/COGS, cashfloor,
  statement coverage, returns, freshness, and owner-signoff evidence

Rules

- do not modify repo files
- do not mutate the DB
- do not call an external write path
- distinguish copied-DB/local work from production-write approvals
- do not read Agent C's report before publishing your own first-pass findings

Output

- write findings to `agent_b_report.md`
- keep findings concise, source-backed, and actionable for Agent A
