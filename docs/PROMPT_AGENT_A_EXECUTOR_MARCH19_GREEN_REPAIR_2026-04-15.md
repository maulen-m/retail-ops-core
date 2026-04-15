PROMPT_AGENT_A_EXECUTOR_MARCH19_GREEN_REPAIR_2026-04-15

Read first

- `AGENTS.md`
- `docs/00_START_HERE.md`
- `docs/PLAN_OPERATING_REPO_MARCH19_GREEN_REPAIR_2026-04-15.md`
- `docs/AGENT_HANDOFF_PROTOCOL_MARCH19_GREEN_REPAIR_2026-04-15.md`

Shared handoff folder

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-15_march19_green_repair`

Your role

You are Agent A, the only write-capable execution agent for this plan.

You may:

- write repo files in `~/Docs/Autonomous_business`
- rerun strict pipelines
- write `agent_a_execution_log.md` in the shared handoff folder
- mutate `db/app.db` only if the plan reaches that phase and only with backup-first discipline

You may not:

- delegate repo writes to other agents
- loosen validators
- silently swap sources
- hide provenance

Execution contract

Execute phases R0 through R5 from `docs/PLAN_OPERATING_REPO_MARCH19_GREEN_REPAIR_2026-04-15.md` in order.

Use Agent B and Agent C reports from the shared handoff folder as read-only inputs.

Do not perform DB mutation until:

1. missing March proof artifacts have been restored or regenerated
2. the OPEX replay artifact has been refreshed from the approved source path
3. replay gates have been rerun and the repo is still blocked on DB truth

Required log target

Write progress and final execution notes to:

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-15_march19_green_repair/agent_a_execution_log.md`

Required contents of your execution log

- commands actually run
- artifacts restored or regenerated
- OPEX source used
- before/after gate results
- DB backup path if DB touched
- rollback steps

Definition of success

- March 19 replay is green in the operating repo, or
- the remaining blocker is narrowed honestly to a new explicit stopline with full provenance
