# Owner Truth Runtime Mode Contract

## Purpose

Define fail-closed runtime behavior for owner-truth execution when the operator chooses `live` versus `replay`.

## Modes

- `live`
  - must run fresh `scripts/run_kaspi_daily_ops.py`
  - must not consume `exports/validation/board_v8_runtime/<AS_OF>/ops_selection_seed.json`
  - may overwrite or refresh `daily_ops_summary.json` through the live daily-ops run
  - must export `AB_CRM_WORKBOOK_PATH` from `config/anchors/SALES_KSP_CRM_LATEST.xlsx` before strict truth gates
  - must keep write-side refreshers apply-only; a non-apply live proving run may validate current sidecar/readiness state, but it must not execute `scripts/sync_ads_sidecar.py`
- `replay`
  - may consume frozen `exports/validation/board_v8_runtime/<AS_OF>/daily_ops_summary.json`
  - may consume `ops_selection_seed.json` when it exists
  - must regenerate deterministic downstream outputs from frozen runtime inputs
  - must fail closed if required replay summary input or release validation anchor is missing

## Non-Negotiables

- live mode must not silently fall back to replay-only seed artifacts
- live mode must not silently fall back to replay release outputs
- live mode must not skip workbook-anchor validation
- replay mode must be explicit
- historical release smoke for `2026-03-08` uses replay mode
- fresh-date proving for `2026-03-09` and later uses live mode

## Truth Authority Defaults

- `scripts/run_owner_truth_daily.py` defaults to `truth_source=webui_archive`
- `scripts/system_doctor.py` defaults to `truth_source=webui_archive`
- explicit `--truth-source db` remains valid for DB-surface diagnostics and legacy parity checks
- owner-truth operational proving must evaluate the same promoted truth source in both entrypoints unless the operator explicitly overrides it

## Enforcement Surface

- `scripts/resolve_owner_truth_runtime_mode.py`
- `scripts/run_owner_truth_daily.py`
- `scripts/smoke_test_owner_truth_daily.py`
- `scripts/system_doctor.py`

## Test Ownership

- `tests/test_owner_truth_runtime_mode.py`
- `tests/test_run_owner_truth_daily_contract.py`
- `tests/test_system_doctor_contract.py`
- `tests/test_smoke_test_owner_truth_daily.py`
