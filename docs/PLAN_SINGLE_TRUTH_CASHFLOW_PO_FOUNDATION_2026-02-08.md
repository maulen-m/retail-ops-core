# Plan: Single-Truth Cashflow + PO Foundation (2026-02-08)

## Goal
Unify PO dashboard and cashflow outputs under one auditable truth model:
- PO plans use config-driven schedule truth.
- Real archives are part-grain and chronological.
- Cashflow default lens is paid truth (bank + paid inventory), with model ledger explicitly opt-in.

## Scope
- `scripts/generate_po_dashboard_data.py`
- `scripts/rebuild_cashflow_calendar.py`
- `scripts/update_cashflow_dashboard.py`
- `scripts/validate_on_delivery_freeze.py`
- `scripts/validate_params.py`
- contracts/docs in `docs/`

## Phase Breakdown
1. **Tests-first fail stage**
   - Added targeted tests for paid lens, legacy receivables filter, schedule anchor, archive sort, active-part projection, prep lanes, on-delivery validator.
2. **Cashflow foundation**
   - Added paid-default row lens transform.
   - Added model-ledger UI toggle.
   - Excluded `ORDER_MODELLED` receivables from actual roll-forward.
3. **PO engine foundation**
   - Added `config/po_schedule.yaml`.
   - PLAN-0 anchor and +10 day schedule applied from config.
   - Added active part projection helpers.
   - Added prep lane logic (`CORE_PRINT_SUIT`, `GENERAL_CL`, `ELS`).
   - Archive/lifecycle ordering switched to cargo-send chronological ascending.
4. **Validation chain**
   - Added `scripts/validate_on_delivery_freeze.py`.
   - Wired on-delivery freeze validation into `scripts/validate_params.py --strict`.
5. **Contracts/docs**
   - Updated dashboard, architecture, cashflow tracking, and data model docs.

## Verification Matrix
- Unit tests:
  - `tests/test_cashflow_paid_default_lens.py`
  - `tests/test_rebuild_cashflow_legacy_receivables_filter.py`
  - `tests/test_po_schedule_anchor.py`
  - `tests/test_po_archive_sorting.py`
  - `tests/test_po_projection_all_active_parts.py`
  - `tests/test_prep_lane_parallelism.py`
  - `tests/test_validate_on_delivery_freeze.py`
- Runtime checks:
  - `python3 scripts/generate_po_dashboard_data.py`
  - `python3 scripts/update_cashflow_dashboard.py`
  - `python3 scripts/validate_on_delivery_freeze.py`

## Known Follow-up
- Existing SHIPPED/RETURNED orders with missing or unsettled `INVENTORY_ON_DELIVERY_COST`
  are now surfaced by `validate_on_delivery_freeze.py` and must be repaired via enrichment + translator backfill.
