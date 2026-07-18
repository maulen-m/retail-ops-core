PROMPT_AGENT_C

Read first

- `AGENTS.md`
- `docs/00_START_HERE.md`
- `docs/parallel_runs/2026-07-10_ab-repair-sol-rebaseline/PLAN.md`
- `docs/PARALLEL_EXECUTION_PROTOCOL.md`

Shared handoff folder

- `~/Docs/Autonomous_business_agent_handoffs/2026-07-10_ab-repair-sol-rebaseline`

Your role

- read-only analyst
- focus: Read-only cross-repo audit of LINE51 ads scale-up, Web_automation marketing/offer truth, shipping no-send readiness, direct CRM, Sourcing, and relevant M5 handoffs. No API or repo writes.

Rules

- do not modify repo files
- do not mutate the DB
- do not call live APIs, browser sessions, schedulers, or external services; inspect file-backed evidence only
- do not send tmux keys or submit pane input
- do not read Agent B's report before publishing your own first-pass findings

Output

- write findings to `agent_c_report.md`
- keep findings concise, source-backed, and actionable for Agent A
