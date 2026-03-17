# Owner Truth Source Map And DB Recency

Date: `2026-03-14`
As-of used for evidence: `2026-03-09`

## Canonical rule

Owner surfaces do not read raw `sales_fact_v2` directly. They read published truth or higher-level owner artifacts that already passed `owner_truth_summary` and `system_health` gates.

## Source-of-truth ladder

1. Raw order recency: `fact_orders_kaspi`
2. Raw recent sales staging: `sales_fact_v2`
3. Published chronology anchors: `fact_sales_workbook_anchor`, `fact_sales_external_ref`
4. Published sales truth consumers must use only:
   - `view_sales_line_truth`
   - `view_sales_daily_truth`
5. Owner gating layer:
   - `exports/daily/<as_of>/owner_truth_summary.json`
   - `exports/diagnostics/<as_of>/system_health.json`
6. Owner surfaces:
   - `owner_profit_daily`
   - `cash_risk_daily`
   - `cashflow_calendar_daily`
   - `po_sku_daily`
   - `owner_daily_brief`

## Current proven recency split

See `exports/validation/owner_cockpit_reactivation/2026-03-14/raw_vs_published_sales_max_dates.json`.

For the current baseline:
- `sales_fact_v2` delivered max date = `2026-03-07`
- published sales truth max date = `2026-03-05`
- workbook anchor max date = `2026-03-05`
- lag between raw delivered staging and published truth = `2` day(s)

Interpretation:
- raw DB recency is ahead of owner-facing published sales truth
- this is not a silent bug in owner surfaces
- it is an explicit chronology ceiling driven by workbook anchoring

## Surface mapping

### `owner_profit_daily`
- Reads monthly review outputs and publication readiness, not raw staging tables.
- Profit remains monitoring-only/provisional when source months are locked or derived.

### `cash_risk_daily`
- Reads cash-floor and PO dashboard outputs.
- Answers runway and PO burden, not per-day cashflow drivers.

### `cashflow_calendar_daily`
- Reads cashflow scorecard + cash-floor + DB calendar rebuild.
- Answers day-by-day modeled cash pressure.
- `largest_outflow_days` must show only negative-cashflow rows; zero/unknown rows are excluded.

### `po_sku_daily`
- Reads PO dashboard outputs.
- Monitoring-only when planning snapshot freshness is stale; staleness must stay visible.

### `owner_daily_brief`
- Combines the four owner surfaces only.
- It is a cockpit layer, not a new truth source.

## Waybill parity rule

- `validate_sales_vs_waybill_parity.py` is a governance guard, not a source of business math.
- If BUSINESS_INSIDES carries non-zero waybill totals, parity must prove those totals against either:
  - the canonical shipped-truth summary, or
  - the waybill selection/archive snapshot for the same `as_of`.
- If BUSINESS_INSIDES carries a zero-order waybill snapshot for a historical day and no live waybill source exists because the API also returns no open orders, that case is treated as a neutral zero-source pass rather than a false failure.

## Operator usage

- For "latest raw activity": inspect raw DB/order recency.
- For "owner-facing monitored revenue/profit": inspect published truth and owner surfaces.
- Never widen monitoring-only profit into decision-grade publication without updated contract evidence.
