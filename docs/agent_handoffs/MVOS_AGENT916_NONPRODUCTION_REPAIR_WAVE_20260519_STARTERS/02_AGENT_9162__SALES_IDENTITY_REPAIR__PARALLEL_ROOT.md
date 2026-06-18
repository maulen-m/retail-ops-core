# Agent9162 Starter - Sales Identity Repair Matrix

You are Agent9162. Your lane is read-only/evidence-only.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/.claude/OPERATING.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-19_mvos_agent916_nonproduction_repair_wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT916_NONPRODUCTION_REPAIR_WAVE_20260519_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT916_NONPRODUCTION_REPAIR_WAVE_20260519_STARTERS/02_AGENT_9162__SALES_IDENTITY_REPAIR__PARALLEL_ROOT.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent915_copied_temp_proof_wave/agent915_copied_temp_mvos_proof_closeout.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent914_readonly_source_acquisition_wave/agent9142_sales_live_readonly_source_acquisition_closeout.md`
9. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-19_mvos_agent914_readonly_source_acquisition_wave/OWNER_CONFIRMED_STOREB_OFFER_116515378_626543467_MAPPING.md`

## Scope

Write only under:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent916_nonproduction_repair_wave/agent9162_sales_identity_repair_evidence/`

Do not edit repo files, DB, workbooks, config, source pointers, schedulers, Web_automation, external systems, or ad platforms.

## Task

Resolve or explicitly retain the strict `sales_fact_v2` blockers without weakening evidence rules.

Targets:

- Universal offer `132822924_328581041`, orders `913421682` and `921067176`;
- STOREB orders `914238753`, `914286181`, `914319851`, `914340762`, `914363937`;
- four Agent915 order-entry quarantine rows.

Acceptable outcomes per row:

- source-backed mapping;
- owner decision required;
- retained quarantine;
- not eligible with evidence.

Required outputs:

- `SALES_IDENTITY_REPAIR_MATRIX.tsv`
- `ORDER_ENTRY_QUARANTINE_CLASSIFICATION.tsv`
- `SALES_STRICT_REBUILD_DECISION.md`
- `COMMANDS_RUN.tsv`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent916_nonproduction_repair_wave/agent9162_sales_identity_repair_closeout.md`

The closeout must include:

`Gate: GREEN`

Use `GREEN` only if every target row has source-backed mapping or explicit retained quarantine. Use `YELLOW` if owner source decision is needed. Use `RED` for boundary violation or false-green risk.
