# Phase 13 B012 On-Delivery Residuals Copied-Temp Proof

Status: `B012_ON_DELIVERY_RESIDUALS_NARROWED_TO_ONE_RETAINED_ROW`

Gate: `YELLOW`

## Boundary

This lane stayed inside the owner-approved non-production envelope:

- no production DB writes;
- no workbook writes;
- no source-pointer writes;
- no scheduler, LaunchAgent, cron, WebUI, API, ad-platform, cash, PO, stock, price, or owner-publication writes;
- copied DB writes only under local evidence.

Evidence root:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-22_mvos_phase13_b012_on_delivery_residuals/agent22_on_delivery_evidence`

Primary copied DB branches:

- settlement-only DB: `~/Docs/Autonomous_business_agent_handoffs/2026-05-22_mvos_phase13_b012_on_delivery_residuals/agent22_on_delivery_evidence/copied_db/agent22_b012_on_delivery_copied_temp.db`
- translator branch DB: `~/Docs/Autonomous_business_agent_handoffs/2026-05-22_mvos_phase13_b012_on_delivery_residuals/agent22_on_delivery_evidence/copied_db/agent22_b012_on_delivery_translate_copied_temp.db`
- parent-unit COGS branch DB: `~/Docs/Autonomous_business_agent_handoffs/2026-05-22_mvos_phase13_b012_on_delivery_residuals/agent22_on_delivery_evidence/copied_db/agent22_b012_on_delivery_translate_parent_cogs_copied_temp.db`

## Result

The original B012 on-delivery validator warning was reduced from `133` failures to `1` retained failure on copied DB only.

Sequence:

1. Baseline `validate_on_delivery_freeze.py` found `133` failures.
2. `reconcile_on_delivery_settlement.py --apply` on a copied DB inserted `64` settlement rows and reduced failures to `69`.
3. `translate_orders_to_cashflow_events.py --apply` plus a post-translation settlement pass reduced failures to `3`.
4. A separate copied DB branch applied only already-accepted parent-unit COGS values for `LINE-31-TS`, `SUIT-21-TS`, `SUIT-31-LS`, and `SUIT-31-TS`.
5. Re-running translation plus settlement on that parent-unit COGS branch reduced failures to `1`.

Final retained validator failure:

| order_id | store | status | kaspi_status | sku_key | sku_id | reason |
| --- | --- | --- | --- | --- | --- | --- |
| `929183530` | `ACMEWEAR` | `SHIPPED` | `KASPI_DELIVERY` | `LINE-31-LS` | `LINE-31-LS_2XL` | `LINE-31-LS` has no accepted copied-temp unit COGS or source-backed base/weight in `dim_sku` |

## Evidence

Key evidence files:

- `commands/010_validate_on_delivery_before.stdout.txt`
- `commands/030_validate_on_delivery_after_settlement.stdout.txt`
- `commands/070_validate_on_delivery_after_translate_then_settlement.stdout.txt`
- `commands/083_validate_on_delivery_after_parent_cogs_translate_settlement.stdout.txt`
- `reports/orders_to_cashflow_parent_cogs_translate_copied_db_apply.txt`
- `reports/parent_unit_cogs_branch_dim_sku_after.csv`
- `reports/final_retained_on_delivery_residual_order.csv`
- `reports/final_retained_beli31ls_dim_sku_cost_gap.csv`
- `reports/parent_cogs_branch_inserted_event_summary.csv`

Accepted copied-temp parent-unit COGS values used:

| sku_key | copied-temp unit COGS |
| --- | ---: |
| `LINE-31-TS` | `6006.76` |
| `SUIT-21-TS` | `5567.22` |
| `SUIT-31-LS` | `5567.22` |
| `SUIT-31-TS` | `5567.22` |

`LINE-31-LS` was intentionally not inferred from LINE51/LINE-31-TS authority. It remains fail-closed.

## Decision

B012 is still `YELLOW`, not green.

Closed inside copied-temp proof:

- DIM_SKU_light parser/alignment subgate;
- settled on-delivery residual class;
- all but one in-flight on-delivery residual after accepted parent-unit COGS.

Retained:

- `LINE-31-LS` copied-temp COGS authority is missing;
- DIM_SKU_light v7 source-authority review is still required;
- default/repeated-run daily autonomy is still unproven;
- production or final route requires CodeCaptain review before any production preflight/apply conversation.

## Verification

Commands run:

- `bash scripts/lint_docs.sh` -> OK.
- `./scripts/check_no_db_tracked.sh` -> OK.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_dim_sku_light_parser.py tests/test_validate_dim_sku_light_alignment.py` -> `7 passed`.
- `git diff --check -- core/excel/dim_sku_light_parser.py tests/test_dim_sku_light_parser.py docs/current/CURRENT_BLOCKER_BOARD.tsv docs/parallel_runs/2026-05-22_mvos_phase12_b012_dim_sku_light_alignment/PHASE12_B012_DIM_SKU_LIGHT_ALIGNMENT.md docs/parallel_runs/2026-05-22_mvos_phase13_b012_on_delivery_residuals/PHASE13_B012_ON_DELIVERY_RESIDUALS.md` -> OK.
- `python3 scripts/validate_dim_sku_light_alignment.py --db <agent21_copied_db>` -> OK with `weight_mismatches=0`, `base_mismatches=11` warning-only.
- `python3 scripts/validate_on_delivery_freeze.py --db <parent_unit_cogs_branch_db> --until 2026-05-21 --lookback-days 30` -> expected FAIL with one retained `LINE-31-LS` row.
- `sqlite3 db/app.db "PRAGMA integrity_check;"` -> `ok`.
- `sqlite3 <parent_unit_cogs_branch_db> "PRAGMA integrity_check;"` -> `ok`.
- protected-surface SHA diff from Phase13 start to end -> empty.
