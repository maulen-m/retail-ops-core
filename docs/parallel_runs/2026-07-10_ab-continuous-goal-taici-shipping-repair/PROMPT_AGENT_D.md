PROMPT_AGENT_D

Read first

- `AGENTS.md`
- `docs/00_START_HERE.md`
- `docs/parallel_runs/2026-07-10_ab-continuous-goal-taici-shipping-repair/PLAN.md`
- `docs/PARALLEL_EXECUTION_PROTOCOL.md`
- `~/Docs/Web_automation/AGENTS.md`

Shared handoff folder

- `~/Docs/Autonomous_business_agent_handoffs/2026-07-10_ab-continuous-goal-taici-shipping-repair`

Your role

- read-only analyst
- freshly identity-lock exactly the six approved WHITE TAICI rows across
  UNIVERSAL and STORE-B and produce the fail-closed execution checklist

Rules

- do not modify repo files, workbooks, Repricer, Kaspi, DB, Sheets, schedulers,
  or any external state
- read-only APIs/public offer views are allowed
- stop on any store/row/SKU/count mismatch
- do not widen into ACMEWEAR, 11KZ, MELVIS, other SKUs, broad DLRO,
  competitor state, or redflag execution

Output

- write findings to `agent_d_report.md`
- include current six-row identity, current ACTIVE/ARCHIVE baseline counts,
  rollback paths, exact commands, and readback gates
