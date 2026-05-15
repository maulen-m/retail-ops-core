# Agent836 - Cashflow Compact SKU + Bank Freshness Source Packet

Gate target: `GREEN` if the exact 8 compact-SKU rows have source-backed economics choices ready for copied-temp proof and bank/manual freshness is classified with evidence. Use `YELLOW` if an owner/source choice is still required.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-15_mvos_source_fact_implementation/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_SOURCE_FACT_IMPLEMENTATION_20260515_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business/exports/validation/mvos_source_decision_wave/20260515_134601/agent835_source_decision_synthesis_packet/MVOS_NEXT_CODECAPTAIN_PACKET.md`
6. `~/Docs/Autonomous_business/exports/validation/mvos_source_decision_wave/20260515_134601/agent835_source_decision_synthesis_packet/MVOS_OWNER_WEB_AUTOMATION_SUPPLEMENT_20260515_143545.md`
7. this starter prompt

## Assignment

Build the source-fact packet for the cashflow blocker:

- compact SKU economics for `LINE-31-TS`, `SUIT-21-TS`, `SUIT-31-LS`, `SUIT-31-TS`;
- exact affected order IDs `910723255`, `912293165`, `912796611`, `912080412`, `914625635`, `918458392`, `919763375`, `918492540`;
- current bank/manual freshness posture for `src_bank_manual_ingest`.

Evidence root:

`~/Docs/Autonomous_business/exports/validation/mvos_source_fact_implementation/20260515_174424/agent836_cashflow_compact_sku_bank/`

Required packet:

`~/Docs/Autonomous_business/exports/validation/mvos_source_fact_implementation/20260515_174424/agent836_cashflow_compact_sku_bank/CASHFLOW_COMPACT_SKU_BANK_SOURCE_PACKET.md`

Closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-15_mvos_source_fact_implementation/agent836_cashflow_compact_sku_bank_closeout.md`

## Required Work

- Verify the current DB SHA/integrity at start and write it to evidence.
- Reproduce or copy the exact 8-row decision matrix from Agent829 evidence.
- Read Web_automation read-only for relevant source context, especially:
  - `~/Docs/Web_automation/exports/pricelist_snapshots/min_price_floor_35pct_by_sku_v6.csv`
  - `~/Docs/Web_automation/config/experiments/acmewear_bundles_experiment_calendar.yaml`
- Search Web_automation read-only for strategy/experiment/schedule/source files that mention `LINE-31-TS`, `SUIT-21-TS`, `SUIT-31-LS`, `SUIT-31-TS`, `CL_OC_MEN_LINE51_WHITE`, or `CL_NEW-CLO2_MEN_SUIT-61_BLACK`.
- Produce a candidate economics table with source path, SHA-256, mtime, observed value, and whether it is exact child truth, parent carry-forward candidate, or supporting evidence only.
- Inspect current bank/manual freshness evidence without writing bank data. If fresh source exists, record path/stat/SHA/timestamp and coverage. If not, state the exact remaining blocker.

## Boundaries

No production DB writes, workbook writes, bank writes, cash movement, supplier payment, owner publication, scheduler mutation, Web_automation mutation, external writes, ads, PO, price, stock, or lifecycle/status production repair.

You are not alone in the codebase. Do not revert or overwrite edits made by others.

Gate: YELLOW
