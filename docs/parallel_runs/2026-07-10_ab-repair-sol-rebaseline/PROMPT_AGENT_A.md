PROMPT_AGENT_A

Read first

- `AGENTS.md`
- `docs/00_START_HERE.md`
- `docs/parallel_runs/2026-07-10_ab-repair-sol-rebaseline/PLAN.md`
- `docs/PARALLEL_EXECUTION_PROTOCOL.md`

Shared handoff folder

- `~/Docs/Autonomous_business_agent_handoffs/2026-07-10_ab-repair-sol-rebaseline`

Your role

- only write-capable execution agent
- only agent allowed to write shared repo state
- production `db/app.db` mutation is NOT authorized; shadow/copy data only

Your job

- read the analyst reports
- execute the plan in causal order
- log actions and results to `agent_a_execution_log.md`

Rules

- do not loosen validators
- do not hide provenance
- do not mutate production DB, workbook-source truth, schedulers, live commerce/customer/platform state, or external systems
- do not use historical approvals or staged tmux text as current authority
- run uncertain validators only in an isolated shadow checkout

Success

- task is completed or narrowed honestly to a smaller explicit stopline
