# Agent9172 Starter - Sales Identity Matrix

You are Agent9172. Your lane is read-only/evidence-only with respect to repo state.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/.claude/OPERATING.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-19_mvos_agent917_yellow_to_green_repair_wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT917_YELLOW_TO_GREEN_REPAIR_20260519_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT917_YELLOW_TO_GREEN_REPAIR_20260519_STARTERS/02_AGENT_9172__SALES_IDENTITY_MATRIX__PARALLEL_ROOT.md`
7. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-19_mvos_agent916_nonproduction_repair_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT9167.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent916_nonproduction_repair_wave/agent9167_copied_temp_rerun_closeout.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent916_nonproduction_repair_wave/agent9167_implementation_copied_temp_rerun_evidence/AGENT9167_RETAINED_BLOCKER_COUNTS.tsv`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent916_nonproduction_repair_wave/agent9167_implementation_copied_temp_rerun_evidence/validator_outputs/022_rebuild_sales_fact_v2_from_kaspi_entries.stdout.txt`

## Scope

Write only under:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent917_yellow_to_green_repair_wave/agent9172_sales_identity_matrix_evidence/`

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent917_yellow_to_green_repair_wave/agent9172_sales_identity_matrix_closeout.md`

Do not edit repo files, production DB, workbooks, config, source pointers, schedulers, Web_automation, external systems, or ad platforms.

## Task

Create the exact sales identity repair/retention matrix for Agent9178.

Targets:

- Universal offer `132822924_328581041` for orders `913421682` and `921067176`;
- five STOREB `sku_identity` gaps previously repaired by Agent9162;
- four remaining order-entry recovery quarantine rows.

Rules:

- Do not resolve XL-vs-3XL by assumption.
- Do not insert header-only rows into product truth.
- If evidence is not enough, keep the blocker retained and state the closure condition.
- Separate source-backed mapping, owner-confirmed copied-temp mapping, and retained quarantine.

## Required Outputs

Inside your evidence folder:

- `SALES_IDENTITY_REPAIR_MATRIX.tsv`
- `UNIVERSAL_132822924_328581041_DECISION.md`
- `ORDER_ENTRY_RETAINED_QUARANTINE_MATRIX.tsv`
- `COMMANDS_RUN.tsv`

The closeout must include a standalone line:

`Gate: <GREEN/YELLOW/RED>`

Use `GREEN` only if every target row has either source-backed mapping or explicit retained quarantine with a validator-safe route. Use `YELLOW` if an owner/source decision is still needed. Use `RED` for boundary violation or silent mapping risk.
