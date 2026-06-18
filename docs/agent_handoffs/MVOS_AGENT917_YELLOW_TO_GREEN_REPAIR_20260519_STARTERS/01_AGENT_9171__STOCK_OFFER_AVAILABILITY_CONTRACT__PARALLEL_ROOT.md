# Agent9171 Starter - Stock Offer Availability Contract

You are Agent9171. Your lane is read-only/evidence-only with respect to repo state.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/.claude/OPERATING.md`
4. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-19_mvos_agent917_yellow_to_green_repair_wave/PLAN.md`
6. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT917_YELLOW_TO_GREEN_REPAIR_20260519_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
7. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT917_YELLOW_TO_GREEN_REPAIR_20260519_STARTERS/01_AGENT_9171__STOCK_OFFER_AVAILABILITY_CONTRACT__PARALLEL_ROOT.md`
8. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-19_mvos_agent916_nonproduction_repair_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT9167.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent916_nonproduction_repair_wave/agent9167_copied_temp_rerun_closeout.md`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent916_nonproduction_repair_wave/agent9167_implementation_copied_temp_rerun_evidence/materialization/offer_availability_snapshot_manifest.json`

## Scope

Write only under:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent917_yellow_to_green_repair_wave/agent9171_stock_offer_availability_contract_evidence/`

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent917_yellow_to_green_repair_wave/agent9171_stock_offer_availability_contract_closeout.md`

Do not edit repo files, production DB, workbooks, config, source pointers, schedulers, Web_automation, external systems, or ad platforms.

## Task

Turn CodeCaptain's stock guidance into an implementable copied-temp source contract and test route.

Required decisions:

- Merchant Cabinet/pricelist packets may materialize `offer_availability_snapshot` only.
- They must not become canonical physical warehouse stock truth.
- They must not update `stock_ledger` or `fact_inventory_snapshot_size.current_stock`.
- The `9` `STOCK/HIGH/OPEN` exceptions remain visible unless an independent physical-stock source closes them.

Inspect the existing scripts/tests around `offer_availability_snapshot`, `stock_ledger`, `fact_inventory_snapshot_size`, and Agent9167 evidence. Produce exact recommendations for Agent9178.

## Required Outputs

Inside your evidence folder:

- `MERCHANT_CABINET_PRICELIST_OFFER_AVAILABILITY_COPIED_TEMP_V1.md`
- `STOCK_PHYSICAL_TRUTH_SEPARATION_MATRIX.tsv`
- `OFFER_AVAILABILITY_MATERIALIZER_TEST_PLAN.tsv`
- `COMMANDS_RUN.tsv`

The closeout must include a standalone line:

`Gate: <GREEN/YELLOW/RED>`

Use `GREEN` only if Agent9178 has an exact contract/test route and no physical-stock false-green risk. Use `YELLOW` if physical stock truth still blocks copied-temp green. Use `RED` for boundary violation or unsafe recommendation.
