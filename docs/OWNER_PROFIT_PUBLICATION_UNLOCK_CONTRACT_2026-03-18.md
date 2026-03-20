# Owner Profit Publication Unlock Contract

Date: `2026-03-18`
As-of evaluated: `2026-03-09`

## Goal

Define when `owner_profit_daily` may be promoted beyond `OWNER_DAILY_MONITORING_ONLY`.

## Unlock preconditions

Promotion is allowed only when all of the following are true for the same reporting window:

1. `exports/daily/<as_of>/owner_truth_summary.json` is `PASS`.
2. `exports/diagnostics/<as_of>/system_health.json` is `GREEN`.
3. `python3 scripts/validate_profit_publication_integrity.py --as-of <as_of>` passes.
4. `exports/north_star_owner_review/<as_of>/publication_readiness.json` is `PASS`.
5. Every target month/store pair has `decision_grade=true` in `exports/owner_pnl/<as_of>/OWNER_PNL.json`.
6. Owner-facing `statusdate_coverage_pct` is reported on a bounded `0..100` scale; diagnostic over-coverage belongs in lower-level parity/projection reports, not publication surfaces.

## Current decision

`NO_CHANGE_BLOCKED`.

For `2026-03-09`, profit remains intentionally locked to:

- `trust_banner=PASS_PROVISIONAL_DERIVED_FROM_GREEN_LIVE_CHAIN`
- `decision_scope=OWNER_DAILY_MONITORING_ONLY`

Reason:

- upstream month/store `decision_grade` flags remain false for Jan-Feb 2026 even though publication readiness and profit integrity are green.
- therefore widening semantics would be wording-only, not evidence-backed.

## Operator-safe surface hygiene

The owner-facing surfaces must also preserve these rules:

- `statusdate_coverage_pct` must never exceed `100.0` in owner-facing outputs.
- `locked_flags_monthly_by_store.csv` must emit one row per `sale_month/store_code` pair.
- any diagnostic over-coverage or projection-over-db signal must remain in lower-level validation artifacts.

## Unlock path

Promotion out of monitoring-only requires:

1. clearing the remaining month/store `decision_grade=false` blockers in `OWNER_PNL.json`,
2. regenerating `NORTH_STAR_OWNER_REVIEW` with unlocked months,
3. replaying owner-profit and owner-surface consistency gates,
4. only then changing the trust banner / decision scope.
