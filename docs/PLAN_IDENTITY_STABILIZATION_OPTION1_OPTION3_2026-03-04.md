# Plan: Identity Stabilization (Option 1 + Option 3) — 2026-03-04

## Objective
Stabilize SKU identity for active stores (`UNIVERSAL`, `STOREB`) with fail-closed controls:
- import read-only external mapping from `Web_automation` snapshots,
- validate identity coverage + reference freshness,
- run deterministic recent-window backfill (dry-run default, apply-gated),
- wire checks into `system_doctor --strict` with explicit stopline codes.

## Scope
- Repo: `~/Docs/Autonomous_business`
- External repo (read-only reference only): `~/Docs/Web_automation`
- As-of target: `2026-03-04`
- Default mode: validate/dry-run

## Non-Negotiables
- No heuristic/random identity fills.
- Unresolved rows stay unresolved with explicit reason.
- DB writes require `--apply` + `ENABLE_DB_WRITE=1` + backup + manifest.
- Missing/stale inputs fail closed with explicit codes:
  - `EXTERNAL_MAPPING_STALE`
  - `REFERENCE_STALE`
  - `IDENTITY_COVERAGE_FAIL`

## Phases
### P0 Baseline + Readcheck
- Record branch/HEAD and baseline identity evidence in `.claude/SESSION_LOG.md` and `claude/journal.md`.
- Reuse baseline anchors from:
  - `exports/validation/identity_option1_option3_plan_2026-03-03/baseline_identity_gap_summary.json`

### P1 External Identity Bridge (Option 1)
- Implement `scripts/import_web_automation_offer_identity.py`.
- Outputs per as-of:
  - `offer_identity_reference.csv`
  - `unresolved_rows.csv`
  - `source_manifest.json` (sha256 + row counts + source files)
  - `import_report.{json,md}`
- Optional apply path writes `dim_offer_identity_external` with backup + apply manifest.

### P2 Identity Gates + Parity
- Implement `scripts/validate_recent_identity_coverage.py`.
- Implement `scripts/validate_external_snapshot_parity.py`.
- Threshold policy:
  - `missing_all_identity_core == 0`
  - `missing_any_identity_core <= 0.5%` OR `<=1 order/day`
  - unresolved snapshot parity must not regress vs baseline limits.

### P3 Deterministic Recent Backfill (Option 1 Containment)
- Implement `scripts/backfill_recent_order_identity.py`.
- Matching priority:
  1. CRM exact (`store_code + order_id`)
  2. external exact (`store_code + normalized offer name`)
- Outputs:
  - `backfill_recent_order_identity_diff_fact_orders_kaspi.csv`
  - `backfill_recent_order_identity_unresolved.csv`
  - `backfill_recent_order_identity_summary.{json,md}`

### P4 Ingestion Integrity (Option 3)
- Implement `scripts/validate_order_entries_freshness.py`.
- Enforce active-store recent orders keep entry-row coverage above threshold.

### P5 Reference Freshness
- Implement `scripts/validate_reference_freshness.py`.
- Detect stale mapped statusdate reference windows and fail with `REFERENCE_STALE`.
- Persist failure artifacts even when failing.

### P6 Doctor Wiring
- Wire validators into `scripts/system_doctor.py` governance chain in this order:
  1. `validate_reference_freshness`
  2. `import_web_automation_offer_identity`
  3. `validate_external_snapshot_parity`
  4. `validate_recent_identity_coverage`
  5. `validate_order_entries_freshness`
- Doctor summary extraction prefers `error_code=`/`status=` lines to keep stopline code explicit.

## Test Plan
Deterministic fixture tests:
- `tests/test_import_web_automation_offer_identity.py`
- `tests/test_validate_recent_identity_coverage.py`
- `tests/test_validate_external_snapshot_parity.py`
- `tests/test_backfill_recent_order_identity.py`
- `tests/test_validate_order_entries_freshness.py`
- `tests/test_validate_reference_freshness.py`

## Evidence Paths
- `exports/validation/identity_stabilization/2026-03-04/*`
- `exports/diagnostics/2026-03-04/system_health.{json,md}`
- gate transcript:
  - `exports/validation/identity_stabilization/2026-03-04/full_gates_identity_stabilization.md`

## Gate Chain
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
- `python3 scripts/validate_params.py --strict`
- `python3 scripts/validate_single_truth_system.py`
- `bash scripts/lint_docs.sh`
- `python3 scripts/system_doctor.py --strict --project-root . --as-of 2026-03-04`

## Stopline Conditions
- External mapping missing/stale -> `EXTERNAL_MAPPING_STALE`.
- Mapped reference stale/no delivered rows -> `REFERENCE_STALE`.
- Identity null/entries thresholds breached -> `IDENTITY_COVERAGE_FAIL`.
