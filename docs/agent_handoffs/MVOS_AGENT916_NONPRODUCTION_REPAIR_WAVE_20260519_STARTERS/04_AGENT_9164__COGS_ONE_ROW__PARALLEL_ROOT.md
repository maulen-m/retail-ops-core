# Agent9164 Starter - COGS One-Row Resolver Route

You are Agent9164. Your lane is read-only/evidence-only.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/.claude/OPERATING.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-19_mvos_agent916_nonproduction_repair_wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT916_NONPRODUCTION_REPAIR_WAVE_20260519_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT916_NONPRODUCTION_REPAIR_WAVE_20260519_STARTERS/04_AGENT_9164__COGS_ONE_ROW__PARALLEL_ROOT.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent915_copied_temp_proof_wave/agent915_copied_temp_mvos_proof_closeout.md`

## Scope

Write only under:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent916_nonproduction_repair_wave/agent9164_cogs_one_row_evidence/`

Do not edit repo files, DB, workbooks, config, source pointers, schedulers, Web_automation, external systems, or ad platforms.

## Task

Identify the single unresolved COGS row/SKU from Agent915 evidence and propose a source-backed cost route or retained-blocker decision.

Do not treat missing COGS as zero cost.

Required outputs:

- `COGS_SINGLE_UNRESOLVED_ROW_REPAIR.tsv`
- `COGS_SOURCE_DECISION.md`
- `COMMANDS_RUN.tsv`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent916_nonproduction_repair_wave/agent9164_cogs_one_row_closeout.md`

The closeout must include:

`Gate: GREEN`

Use `GREEN` only if the row has source-backed COGS or explicit retained blocker. Use `YELLOW` if source truth is still missing. Use `RED` for boundary violation or false-green risk.
