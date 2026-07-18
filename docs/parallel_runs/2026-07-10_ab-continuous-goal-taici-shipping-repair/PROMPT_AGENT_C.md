PROMPT_AGENT_C

Read first

- `AGENTS.md`
- `docs/00_START_HERE.md`
- `docs/parallel_runs/2026-07-10_ab-continuous-goal-taici-shipping-repair/PLAN.md`
- `docs/PARALLEL_EXECUTION_PROTOCOL.md`

Shared handoff folder

- `~/Docs/Autonomous_business_agent_handoffs/2026-07-10_ab-continuous-goal-taici-shipping-repair`

Your role

- read-only analyst
- focus: READY retry identity, carry-forward age, physical handover
  classification, safe name resolution, WhatsApp fallback, returns-pickup
  Telegram side effect, and deferred-date exclusion

Rules

- do not modify repo files
- do not mutate the DB
- do not write Sheets, Telegram, WhatsApp, schedulers, Kaspi, or any external
  state
- do not read Agent B's report before publishing your own first-pass findings

Output

- write findings to `agent_c_report.md`
- keep findings concise, source-backed, and actionable for Agent A
