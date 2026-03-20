# Cashflow Owner Dashboard Contract

Date: `2026-03-14`

## Goal

Expose a richer owner-facing cashflow dashboard without creating a second cash-truth authority.

## Source boundary

- `cashflow_dashboard_owner` is a composition layer only.
- It may read only:
  - `exports/daily/<as_of>/owner_truth_summary.json`
  - `exports/diagnostics/<as_of>/system_health.json`
  - `exports/owner/<as_of>/cash_risk_daily.json`
  - `exports/owner/<as_of>/cashflow_calendar_daily.json`
  - `exports/owner/<as_of>/owner_profit_daily.json`
- It must not recompute cash business math from DB tables or Excel inputs.

## Required semantics

- Cash truth remains owned by the existing cash-risk and cashflow-calendar surfaces.
- Profit semantics remain inherited from `owner_profit_daily`.
- `decision_scope` must be copied through from `owner_profit_daily`.
- A PASS dashboard may still be monitoring-only.

## Required output

- `exports/owner/<as_of>/cashflow_dashboard_owner.json`
- `exports/owner/<as_of>/cashflow_dashboard_owner.md`

## Minimum fields

- `generated_at`
- `as_of`
- `status`
- `trust_banner`
- `decision_scope`
- `cash_position`
- `calendar_focus`
- `profit_focus`
- `sources`

## Stop conditions

- any mixed paid/model truth
- any new write path
- any hidden cash math outside the upstream owner surfaces
