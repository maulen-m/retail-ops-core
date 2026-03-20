# PLAN INBOUND FULL REPO STATE SYNC — 2026-03-02

## Objective
Apply inbound single-truth updates from `Inbound_calendar_V10.002.xlsx` into DB + validators + dashboard, with strict parity checks and evidence.

## Scope Implemented
- `po_part` schema extended for actual delivery/payment truth fields.
- Workbook->DB single-truth validator extended to compare new actual delivery fields.
- PO part sync extended to ingest new actual delivery fields.
- Inbound cargo validator hardened for styled `Cargo_send_*` sheets and fail-closed parse contract.
- New Astana totals alignment validator added and wired into strict validation.
- Cash balances sync added from workbook `Cash_Balances` into history/current config and totals.
- Dashboard real-archive flow updated to use actual-first weight/delivery basis when part status is `RECEIVED` and actual fields exist.

## Files Added
- `scripts/migrate_026_po_part_actual_dlv_fields.py`
- `scripts/validate_astana_totals_alignment.py`
- `scripts/sync_cash_balances_from_inbound_calendar.py`
- `tests/test_validate_astana_totals_alignment.py`
- `tests/test_sync_cash_balances_from_inbound_calendar.py`
- `docs/PLAN_INBOUND_FULL_REPO_STATE_SYNC_2026-03-02.md`

## Files Updated (key)
- `scripts/sync_po_parts_from_inbound_calendar.py`
- `scripts/validate_single_truth_system.py`
- `scripts/validate_inbound_sheet_consistency.py`
- `scripts/validate_params.py`
- `scripts/validate_schema.py`
- `scripts/generate_po_dashboard_data.py`
- `tests/test_sync_po_parts_from_inbound_calendar.py`
- `tests/test_sync_po_parts_parser_guard.py`
- `tests/test_validate_inbound_sheet_consistency.py`
- `tests/test_validate_single_truth_system.py`
- `config/bank_accounts_history.yaml`
- `config/bank_accounts.yaml`
- `config/bank_accounts_history_totals.md`

## DB Safety + Apply Evidence
- DB backup created before writes:
  - `~/Docs/Oracle/Autonomous_business/backups/app_2026-03-02_185836.db.gz`
- Migration applied (schema write enabled):
  - `migrate_026_po_part_actual_dlv_fields.py --apply`
- PO sync applied (write enabled):
  - `sync_po_parts_from_inbound_calendar.py --apply`
  - updated `po_header=7`, `po_part=9`, `po_line=237`
- Cash balance sync applied (write enabled):
  - selected snapshot: `02.03.2026 14:41:00`
  - updated `bank_accounts_history.yaml`, `bank_accounts.yaml`, totals markdown
- Cashflow updated:
  - `import_cashflow_balance_checks.py --apply --run-id inbound_cash_20260302_144100`
  - `rebuild_cashflow_calendar.py --apply`

## Validation + Test Evidence

### Script validators on real workbook
- `validate_inbound_sheet_consistency.py` => `ok=true`, `checked_keys=28`, `mismatch_count=0`
- `validate_astana_totals_alignment.py` => `ok=true`

### Warning (expected)
- Astana per-bag weight total is estimate-based and differs from summary actual weight:
  - per_bag=`1231.3`
  - summary_actual=`1186.2`
- Interpretation: this is a modeling basis difference, not a key mismatch.

### Unit/integration tests
- Targeted suite run:
  - `python3 -m pytest -q ...`
  - result: `32 passed`

## Dashboard Regeneration
- Regenerated:
  - `exports/po_dashboard_data.json`
  - `exports/po_dashboard.html`
- Real archive + real_pos now carry actual/estimated basis markers:
  - `po_weight_basis`
  - `po_dlv_basis`
- `RECEIVED` parts now prefer actual weight + actual delivery totals when available.

## Strict Validation Status (`2026-03-02`)
- Command: `python3 scripts/validate_params.py --strict --as-of 2026-03-02`
- Result: **FAIL** (non-inbound blockers only)

Blocking errors:
1. Missing business-insides snapshot for `2026-03-02`:
   - `config/business_insides/BUSINESS_INSIDES_2026-03-02.md`
   - or `config/business_insides/snapshots/BUSINESS_INSIDES_2026-03-02.md`
2. Profit publication integrity depends on the same missing snapshot.

Inbound-related checks in strict run:
- `single_truth_system: OK`
- `inbound_sheet_consistency: OK`
- `astana_totals_alignment: OK`

## Notes
- A `single_truth_system` NaN crash (`cannot convert float NaN to integer`) was fixed by hardening numeric parsers in `validate_single_truth_system.py` and adding regression test coverage.
- Dashboard generator still reports an existing production-readiness blocker unrelated to this inbound sync (`stock snapshot stale vs cutoff` inside production-readiness check path).

## Next Step to make strict fully green
1. Publish/generate business-insides snapshot for `2026-03-02`.
2. Re-run strict validation:
   - `python3 scripts/validate_params.py --strict --as-of 2026-03-02`
