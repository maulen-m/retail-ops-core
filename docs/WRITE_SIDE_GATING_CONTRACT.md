# WRITE_SIDE_GATING_CONTRACT

## Purpose
Define one fail-closed contract for write-capable scripts so writes cannot happen accidentally.

## Contract (non-negotiable)
1. Default mode is dry-run / read-only.
2. Any write path requires both:
   - explicit environment gate (`ENABLE_* = 1`), and
   - explicit CLI write flag (`--apply`).
3. Missing either condition must produce a non-zero exit.
4. If a script mutates DB/external state, the gate check must run before the first write operation.

## Canonical gated scripts
- `scripts/rebuild_cashflow_calendar.py` → `ENABLE_CASHFLOW_WRITE` + `--apply`
- `scripts/sync_opex_schedule.py` → `ENABLE_CASHFLOW_WRITE` + `--apply`
- `scripts/reconcile_on_delivery_settlement.py` → `ENABLE_CASHFLOW_WRITE` + `--apply`
- `scripts/sync_po_parts_from_inbound_calendar.py` → `ENABLE_PO_PART_SYNC_WRITE` + `--apply`
- `scripts/sync_dim_sku_from_dim_sku_light.py` → `ENABLE_DIM_SKU_SYNC_WRITE` + `--apply`
- `scripts/migrate_023_po_parts_schema.py` → `ENABLE_SCHEMA_WRITE` + `--apply`
- `scripts/migrate_025_dim_sku_weight_guard.py` → `ENABLE_SCHEMA_WRITE` + `--apply`

## Validation
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_write_side_gating_contract.py`
- `python3 scripts/validate_params.py --strict`

## Rollback
- `git revert <commit_sha>`
- Re-run the two validation commands above.
