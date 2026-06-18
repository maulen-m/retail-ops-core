PROMPT_AGENT_A

Read first

- `AGENTS.md`
- `docs/00_START_HERE.md`
- `docs/parallel_runs/2026-05-21_mvos-phase0-canonical-route/PLAN.md`
- `docs/PARALLEL_EXECUTION_PROTOCOL.md`

Shared handoff folder

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-21_mvos-phase0-canonical-route`

Your role

- only write-capable execution agent
- only agent allowed to write shared repo state
- only agent allowed to mutate `db/app.db`

Your job

- read the analyst reports
- execute the plan in causal order
- log actions and results to `agent_a_execution_log.md`

Rules

- do not loosen validators
- do not hide provenance
- do not start DB writes before upstream analysis unless single-agent mode was explicitly chosen

Success

- task is completed or narrowed honestly to a smaller explicit stopline
