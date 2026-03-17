# Owner Surface Consistency Contract

Date: `2026-03-14`

## Goal

Define the semantic boundaries between the owner-facing daily surfaces so they do not silently contradict each other.

## Surface roles

### `cash_risk_daily`
- Scope: runway and PO burden against modeled cash floor.
- Upstream facts: `cashfloor_gate.json`, `po_dashboard_data.json`, owner/system gates.
- Not responsible for identifying the dominant per-day cashflow driver.

### `cashflow_calendar_daily`
- Scope: modeled daily cash close over the calendar horizon.
- Upstream facts: cashflow scorecard, cash-floor gate, DB calendar rebuild, owner/system gates.
- `critical_days` show the lowest modeled cash-close days.
- `largest_outflow_days` may include only rows where `cash_flow_kzt < 0`.
- `largest_outflow_days` must not expose `primary_driver=UNKNOWN`. If no negative outflow rows exist, the list must be empty.

### `po_sku_daily`
- Scope: reorder, freeze/kill, and tied-up capital review from the PO dashboard.
- `planning_snapshot.freshness=STALE_VS_CUTOFF` is allowed only for monitoring scope and must remain visible in both trust banner and owner brief.

### `owner_profit_daily`
- Scope: monthly monitoring profit view derived from release-gated monthly review outputs.
- If profit is provisional or derived, `decision_scope` must stay `OWNER_DAILY_MONITORING_ONLY`.

### `owner_daily_brief`
- Scope: cockpit summary only.
- Must inherit trust banners and decision scope from upstream owner surfaces.
- Must not introduce new business math.
- Must keep stale planning visible when PO planning is stale.
- If the first critical-day driver is `UNKNOWN`, the brief must explicitly say the driver is unresolved rather than pretending certainty.

## Required consistency checks

- brief trust banners must match source surfaces
- brief profit decision scope must match `owner_profit_daily`
- stale PO planning must be visible in brief text
- `cashflow_calendar_daily.largest_outflow_days` must be negative-only and driver-resolved

## Validation path

- `python3 scripts/validate_owner_surface_consistency.py ...`
- artifact outputs:
  - `owner_surface_consistency_report.json`
  - `owner_surface_consistency_report.md`
