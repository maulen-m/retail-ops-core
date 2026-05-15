PROMPT_AGENT_C

Read first

- `AGENTS.md`
- `docs/00_START_HERE.md`
- `docs/parallel_runs/2026-05-14_codecaptain-storeb-readiness-packet-patch/PLAN.md`
- `docs/PARALLEL_EXECUTION_PROTOCOL.md`

Shared handoff folder

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-14_codecaptain-storeb-readiness-packet-patch`

Your role

- read-only analyst
- focus: read-only preflight command, stop-condition, backup/rollback, and non-authorization review

Rules

- do not modify repo files
- do not mutate the DB
- do not read Agent B's report before publishing your own first-pass findings

Output

- write findings to `agent_c_report.md`
- keep findings concise, source-backed, and actionable for Agent A
