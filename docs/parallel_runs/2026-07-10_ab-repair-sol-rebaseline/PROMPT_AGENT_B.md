PROMPT_AGENT_B

Read first

- `AGENTS.md`
- `docs/00_START_HERE.md`
- `docs/parallel_runs/2026-07-10_ab-repair-sol-rebaseline/PLAN.md`
- `docs/PARALLEL_EXECUTION_PROTOCOL.md`

Shared handoff folder

- `~/Docs/Autonomous_business_agent_handoffs/2026-07-10_ab-repair-sol-rebaseline`

Your role

- read-only analyst
- focus: Read-only audit of current 71-gate, acceptance, blocker, cash/OPEX, validator-safety, and stale-run-state evidence. No repo, DB, scheduler, workbook, or external writes.

Rules

- do not modify repo files
- do not mutate the DB
- do not run reporters or validators that may write, refresh views, acquire locks, or contact external services; inspect existing evidence and code statically instead
- do not send tmux keys or submit pane input
- do not read Agent C's report before publishing your own first-pass findings

Output

- write findings to `agent_b_report.md`
- keep findings concise, source-backed, and actionable for Agent A
