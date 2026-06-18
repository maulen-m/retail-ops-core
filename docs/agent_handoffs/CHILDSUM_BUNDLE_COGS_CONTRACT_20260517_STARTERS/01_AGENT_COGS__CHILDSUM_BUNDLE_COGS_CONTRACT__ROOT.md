# Agent COGS - ChildSum Bundle COGS Contract

You are the COGS agent for the May 17 MVOS copied-temp proof blocker.

## Bootstrap

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/inventory/Sales_Data_Model_V16.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/CHILDSUM_BUNDLE_COGS_CONTRACT_20260517_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-17_mvos_agent846_post_codecaptain_webui/ORCHESTRATOR_REVIEW_AFTER_AGENT846.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_agent846_post_codecaptain_webui/agent846_full_copied_temp_mvos_proof_closeout.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-16_mvos_source_fact_repair_round2/agent848_cashflow_cogs_balance_repair_closeout.md`

## Assignment

Fix or contract the one remaining ACMEWEAR COGS representation blocker for:

- order: `909054064`
- store: `ACMEWEAR`
- sku_key: `SUIT-31-TS`
- sku_id observed in copied DB: `SUIT-31-TS_3XL`
- sale date: `2026-05-04`
- current blocker: `cogs_source=unresolved`, blank `cogs_kzt`, `base_cost_cny=0.0`, `weight_kg=0.0`, reason `MISSING_BASE_AND_WEIGHT`

The intended business contract is ChildSum bundle COGS:

```text
child_unit_cogs_kzt =
  sum(component_base_cost_cny * CNY_KZT)
  + sum(component_weight_kg * USD_KZT * DLV_RATE_USD_PER_KG)
```

Use the included component items for the child bundle, with base cost and weight inherited from the respective parental bundle part source. Do not copy the whole parent COGS as the final formula unless an explicit copied-temp unit override is the only approved route and is labeled as such.

## Write Scope

You may edit repo code, focused tests, and owning docs only as needed to define the ChildSum COGS contract.

You may write evidence under a new timestamped subfolder:

`~/Docs/Autonomous_business/exports/validation/childsum_bundle_cogs_contract/`

You may write the final closeout to:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-17_childsum_bundle_cogs_contract/agent_cogs_childsum_bundle_cogs_contract_closeout.md`

If you need a copied DB, create it only inside your evidence root.

## Protected Boundaries

No production write is authorized.

Do not mutate:

- `~/Docs/Autonomous_business/db/app.db`
- `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`
- source manifests or source pointers used by production gates
- LaunchAgents, cron, scheduler config, or automation-control runtime state
- Web_automation, Kaspi, ads platforms, bank/cash systems, PO commitments, prices, stock, owner publication, or external systems

Do not put secrets into prompts, evidence, logs, commits, or closeouts.

## Required Work

1. Reproduce the failing COGS validator result on the Agent846 copied DB.
2. Inspect the exact COGS resolution path:
   - `scripts/validate_cogs_completeness_by_month.py`
   - `view_sales_line_truth`
   - `sales_fact_v2`
   - `dim_sku`
   - cashflow translator COGS handling if relevant
3. Locate current child-bundle source truth and verify the exact `SUIT-31-TS` component list before applying any formula.
4. Implement the narrowest safe contract:
   - preferred: component-sum ChildSum source with auditable component base costs and weights;
   - fallback only if component truth is not available and orchestrator accepts it: explicit copied-temp unit COGS override, labeled non-formula and non-production-authorizing.
5. Add focused tests before or alongside implementation:
   - ChildSum component truth resolves `SUIT-31-TS` to positive COGS;
   - missing component truth remains unresolved;
   - missing COGS is never treated as zero;
   - validator strictness still fails for unrelated unresolved COGS rows.
6. Rerun the focused validator on the copied DB for `2026-05-01..2026-05-17`.
7. Record production DB/workbook hashes before and after to prove protected surfaces were unchanged.

## Suggested Commands

Reproduce current failure:

```bash
python3 scripts/validate_cogs_completeness_by_month.py \
  --start 2026-05-01 \
  --end 2026-05-17 \
  --strict \
  --db-path exports/validation/mvos_agent846_post_codecaptain_webui/20260517_101248/agent846_full_copied_temp_mvos_proof/agent846_copied_temp_mvos_20260517.db \
  --truth-source db \
  --as-of 2026-05-17 \
  --output-dir exports/validation/childsum_bundle_cogs_contract/<timestamp>/baseline_cogs
```

Inspect the failing row:

```bash
sqlite3 exports/validation/mvos_agent846_post_codecaptain_webui/20260517_101248/agent846_full_copied_temp_mvos_proof/agent846_copied_temp_mvos_20260517.db \
  ".headers on" ".mode column" \
  "select order_id, sale_date, store_code, sku_key, sku_id, my_size, units, net_rev_kzt, cogs_kzt, cogs_source, source_table, source_sku_key, source_cogs_kzt from view_sales_line_truth where cast(order_id as text)='909054064';"
```

Rerun after the copied-temp contract proof:

```bash
python3 scripts/validate_cogs_completeness_by_month.py \
  --start 2026-05-01 \
  --end 2026-05-17 \
  --strict \
  --db-path <copied_db_after_childsum_contract> \
  --truth-source db \
  --as-of 2026-05-17 \
  --output-dir <evidence_root>/after_childsum_cogs
```

## Stoplines

Stop `YELLOW` if exact component source truth is missing or if the current repo lacks an approved source-basis contract for ChildSum component costs.

Stop `YELLOW` if the only workable path is Agent848's copied-temp unit override and the orchestrator has not explicitly accepted that tactical route.

Stop `RED` if a protected production surface must be mutated to continue.

## Closeout

Write the closeout first. Include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- exact source basis used for `SUIT-31-TS`;
- component formula rows or explicit copied-temp unit override basis;
- before/after validator paths and statuses;
- tests run and results;
- production DB/workbook hash proof;
- explicit non-authorization statement for production apply and owner publication.
