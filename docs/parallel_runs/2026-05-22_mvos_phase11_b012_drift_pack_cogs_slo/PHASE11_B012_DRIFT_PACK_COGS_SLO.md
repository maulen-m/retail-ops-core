# Phase 11 B012 Drift Pack COGS SLO Copied-Temp Proof

Status: `B012_COGS_CRITICAL_REDUCED_TO_WARN_IN_EVIDENCE_LOCAL_COPY`
Created: `2026-05-22`

This is a non-production, evidence-local proof lane. It does not authorize production DB writes, workbook writes, source-pointer writes, scheduler/LaunchAgent/cron changes, Web_automation writes, Kaspi/API/WebUI writes, external writes, ad-platform writes, cash movement, PO commitment, stock changes, price changes, owner publication, production preflight, or production apply.

## Purpose

`B012_may21_drift_pack_critical` was blocked because the May 21 drift pack was `CRITICAL` with:

- `cogs_integrity unresolved_rows=1`
- unresolved SKU: `SUIT-31-TS`

The goal of this lane was to test whether the already accepted copied-temp unit COGS route can clear the COGS-critical part of B012 without touching production.

## Evidence Boundary

Evidence root:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-22_mvos_phase11_b012_drift_pack_cogs_slo/agent20_b012_drift_pack_evidence`

Copied DB:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-22_mvos_phase11_b012_drift_pack_cogs_slo/agent20_b012_drift_pack_evidence/copied_db/agent20_b012_drift_pack_copied_temp.db`

Accepted copied-temp unit COGS evidence:

`~/Docs/Autonomous_business/exports/validation/mvos_post_codecaptain_source_contract_addition_wave/20260517_210554/agent873_cogs_childsum_route/copied_temp_parent_unit_cogs_contract.csv`

Relevant accepted row:

| sku_key | approved_unit_cogs_kzt | source_parent_sku | route |
| --- | ---: | --- | --- |
| `SUIT-31-TS` | `5567.22` | `CL_NEW-CLO2_MEN_SUIT-61_BLACK` | `OWNER_APPROVED_PARENT_UNIT_COGS_FOR_COPIED_TEMP_ONLY` |

## Result

Evidence-local copied-temp drift pack:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-22_mvos_phase11_b012_drift_pack_cogs_slo/agent20_b012_drift_pack_evidence/drift_pack_output/2026-05-21/single_truth_drift_pack.json`

`validate_cogs_integrity.py` on copied DB with unit COGS evidence:

- window: `2026-04-22..2026-05-21`
- total rows: `596`
- formula rows: `595`
- unresolved rows after copied-temp overlay: `0`
- unresolved SKUs after copied-temp overlay: `0`
- unit COGS evidence applied rows: `1`

`validate_drift_pack_slo.py --strict` against the evidence-local output root:

- result: `DRIFT_PACK_SLO PASS`
- status: `WARN`
- age hours: `0.0`

## Remaining Warnings

The evidence-local pack is not full daily-autonomy green. It remains `WARN` because:

- `dim_sku_alignment status=error`
- `dim_sku_alignment` error: `Failed to locate DIM_SKU_light header row`
- `on_delivery_residuals residual_count=133`

## Board Decision

`B012_may21_drift_pack_critical` remains blocked for current daily autonomy, but the reason is now narrower:

- copied-temp COGS-critical row is repairable and passes in evidence-local proof;
- production/default drift-pack builder was not changed in this lane;
- repeated-run autonomy remains unproven;
- remaining `WARN` reasons need their own bounded lanes before a full daily-autonomy green claim.

## Next Best Route

The next safe route is either:

- add a reviewed, explicit copied-temp unit-COGS evidence input to the drift-pack builder, then rerun the exact drift SLO in a copied-temp output root; or
- keep this proof as CodeCaptain review evidence and move to the next retained warning lane: DIM_SKU_light workbook header route or on-delivery residual settlement classification.
