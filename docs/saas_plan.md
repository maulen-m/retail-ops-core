# AcmeWear Insights — SaaS Analytics Webapp Plan (V1)
**Repo location:** `docs/saas_plan.md`  
**Timezone:** Asia/Almaty (GMT+5)  
**Currency:** KZT  
**Primary DB source:** `sales_fact_v2` (raw line sales facts)  
**Formula authority:** `docs/inventory/Master_Inventory_Rules_v6.md` (authoritative)

---

## 1) V1 Product Spec (UI + behavior)

### 1.1 Product goal
Build a premium internal analytics webapp with exactly 3 primary tabs:
1) **Dashboard**
2) **Cashflow Calendar**
3) **Period Comparison**

The app must be:
- **Read-only by default** (protect capital; no accidental writes)
- **DB-first** (Excel is never required for analytics pages)
- **Explainable** (every KPI has an info tooltip showing definition + formula + “Source:”)

> Design rule: Metrics are computed server-side using a shared formula layer; the frontend never “re-derives” business math.

---

### 1.2 UX layout (premium baseline)
**Global shell**
- Left sidebar: Logo + Tabs + quick links (Exports, Data freshness, Definitions)
- Top bar (sticky):
  - “Today: YYYY-MM-DD” (Almaty)
  - Global filters (always visible):
    - Date range (default depends on tab)
    - Store filter (`store_code`, multi-select)
    - SKU filter (`sku_key`, multi-select)
    - Search box (typeahead for SKU_key / Kaspi offer)
  - “Data freshness” badge: last order_date ingested + last pipeline run status (if available)

**Interaction design**
- Everything filterable without page reload.
- Hover tooltips for KPI definitions + formula.
- Click on a KPI card drills into a detail drawer (daily trend + top SKUs contributing).
- Tables support: search, sort, pin columns, export CSV.

**Design system**
- Use a modern component kit (clean cards, subtle borders, dark mode).
- Avoid “Excel vibes”: no dense grids by default; tables are optional, drill-down friendly.

---

### 1.3 Tab 1 — Dashboard (Main Page)

#### A) Header / Inputs
Top-left (read-only system facts):
- Today (Almaty)
- Data freshness
- Selected filters summary

Top-right (editable operator inputs):
- OPEX per month (KZT) — stored in DB
- Cash on hand (KZT) — stored in DB

Auto-calculated (read-only):
- Total inventory value (KZT) — **UNDEFINED in rules** (see Metric Dictionary)
- Capital (KZT) — **UNDEFINED in rules** (see Metric Dictionary)

**V1 storage requirement:** create a simple DB table (e.g., `dim_finance_inputs`) keyed by `effective_date` (or latest wins).

#### B) “Last 30 days” KPI strip
Default window: rolling last 30 calendar days ending today (Almaty).

KPI cards (V1):
- Units sold
- Net revenue (KZT)
- COGS (KZT)
- Profit (KZT)
- Margin % (UNDEFINED — candidate definition in Metric Dictionary)

Each KPI card:
- Value
- Delta vs previous 30-day period (A vs immediately prior period)
- Mini sparkline (daily)

#### C) 12-month chart
Monthly aggregation for last 12 full months + current month-to-date.

Chart toggles (V1):
- Net revenue
- COGS
- Profit
- Margin %
- “Capital frozen” (K_avg) — if available for SKU rollup (see Metric Dictionary)
- ROIC (Monthly_ROIC) — if available for SKU rollup (see Metric Dictionary)

Rules:
- Revenue/COGS/Profit: monthly sums
- Margin: monthly Profit / monthly Revenue (candidate)
- ROIC: weighted aggregation rule required (see Metric Dictionary)

#### D) Business Health panel (inventory + efficiency)
This section is allowed to use tables other than `sales_fact_v2` (inventory tables / sku metrics),
BUT every metric must still map back to Master rules formulas.

Show:
- Warehouse COGS value (UNDEFINED formula; candidate: sum(current_stock * COGS_unit))
- Inbound COGS value (UNDEFINED formula; candidate: sum(inbound_stock * COGS_unit))
- Total COGS value (warehouse + inbound)
- Stock status distribution: % SKUs in REORDER / WAIT / OK
- Stock efficiency % (UNDEFINED; candidate defined in Metric Dictionary)

#### E) “Top Movers” table (premium ops table)
Two modes (toggle):
- “Top profit SKUs (30d)”
- “Top revenue SKUs (30d)”
Columns:
- SKU_key
- Units (30d)
- Revenue (30d)
- Profit (30d)
- Status (OK/WAIT/REORDER) if available
- ROIC (Monthly_ROIC) if available
Click row => opens SKU drawer:
- Daily trend chart (units, profit)
- Breakdown by MY_SIZE (if present)
- Returns/cancellations counts

---

### 1.4 Tab 2 — Cashflow Calendar

#### A) Core view
A calendar heatmap/grid (daily):
- Each day cell shows:
  - Primary metric (selectable)
  - Optional secondary metric (small text)
- Default date range: last 60 days (fast and useful)

Metric selector (single):
- Units sold
- Net revenue
- Profit
- ROIC (if available)
- Avg sell price (candidate definition)

#### B) Day detail drawer
Click a day:
- Summary KPIs for that day
- Top SKUs table for that day (units / revenue / profit)
- Status breakdown (optional)

#### C) Filters
Same global filters:
- sku_key multi-select
- store_code multi-select
Optional filters (V1 if present in schema):
- product_type (CL/ELS/FUR)
- my_size

---

### 1.5 Tab 3 — Period Comparison

#### A) Mode toggle
Compare: ON/OFF
- OFF: behaves like a calendar + KPI strip for a single period.
- ON: shows Period A vs Period B.

#### B) Period logic
- Period A: user-selected start/end date (inclusive)
- Period B: immediately preceding period of equal length (auto)

#### C) Outputs
- Summary comparison table:
  - Metric | Period A | Period B | Δ abs | Δ %
Metrics (V1):
- Units
- Net revenue
- COGS
- Profit
- Margin % (candidate)
- ROIC (if available)

Optional (nice-to-have V1):
- Overlay time-series chart (A vs B) for selected metric

---

### 1.6 Architecture (tailored to this repo)

#### A) Compute model (must match truth policy)
- The frontend is purely a viewer.
- All metric math lives server-side in a shared layer that already respects Master rules.
- Prefer building/using **DB views** so both scripts and webapp read the same derived fields.

Recommended derived view layer:
- `v_sales_enriched`:
  - Base: `sales_fact_v2`
  - Adds: Net_rev_unit (if needed), Line_NetRev, COGS_unit, COGS_line, Profit_line
  - Joins:
    - `dim_sku_size` (BaseCost_CNY, Weight_kg, SKU_ID → SKU_key)
    - `dim_fx_rates` (effective FX)
    - `dim_params` (VAT_rate, commission, cargo_rate, etc.)

Recommended aggregate layer:
- `v_sales_daily` (Date x SKU_key): Units, Revenue, Delivery, COGS, Profit
- `v_sales_monthly`

#### B) App structure
- Backend API (FastAPI recommended):
  - `/kpis/last30`
  - `/timeseries/monthly`
  - `/calendar/daily`
  - `/compare/summary`
  - `/filters/options`
- Frontend (Next.js recommended):
  - 3 routes / tabs
  - Shared filter store
  - Component library for premium UI

#### C) Safety & correctness gates
- Read-only by default.
- Any “edit inputs” (OPEX, Cash) must:
  - log who/when (even if single-user now)
  - be idempotent and reversible
- Add a “Definitions” panel that renders metric dictionary content from a JSON spec
  so the UI can’t drift from formulas.

---

## 2) Metric Dictionary (definitions + formulas + sources)

> If a formula is not explicitly defined in the authoritative docs, mark as UNDEFINED and provide candidate definitions labeled “ASSUMPTION”.

### 2.1 Sales economics (per line)
| Metric | Definition | Formula | Inputs | Source |
|---|---|---|---|---|
| Units | Units sold | `SUM(quantity)` | `sales_fact_v2.quantity` | Sales facts conventions |
| Delivery_fee | Kaspi delivery fee (seller-side) | tiered: `0 / 856 / 1259` by sell_price | sell_price_kzt | `Master_Inventory_Rules_v6.md` §6.1 |
| Net_rev_unit | Net revenue per unit (after commission, delivery fee, VAT) | `(Price*(1-commission)-Delivery_fee)*(1-VAT)` | sell_price, commission, VAT, delivery_fee | `Master_Inventory_Rules_v6.md` §6.1 |
| Line_NetRev | Net revenue line | `Net_rev_unit * quantity` | Net_rev_unit, quantity | `Sales_Data_Model_V15.md` §3.3 |
| COGS_unit | Unit cost (KZT) | `BaseCost_CNY*FX_CNY_KZT + Weight_kg*Cargo_rate*FX_USD_KZT` | base_cost_cny, weight_kg, fx rates, cargo rate | `Master_Inventory_Rules_v6.md` §6.1 |
| COGS_line | Line COGS | `COGS_unit * quantity` | cogs_unit, quantity | `Sales_Data_Model_V15.md` §3.3 |
| Profit_unit | Unit profit | `Net_rev_unit - COGS_unit` | net_rev_unit, cogs_unit | `Master_Inventory_Rules_v6.md` §6.1 |
| Profit_line | Line profit | `Profit_unit * quantity` | profit_unit, quantity | `Sales_Data_Model_V15.md` §3.3 |

### 2.2 Demand + inventory planning (per SKU_key)
| Metric | Definition | Formula | Inputs | Source |
|---|---|---|---|---|
| D_30 | Daily demand estimate from last 30 days | `SUM(sales_30d)/30` | sales history | `Master_Inventory_Rules_v6.md` §5.1 |
| Sigma (σ) | Demand volatility proxy | `σ = D_30 * 0.4` | D_30 | `Master_Inventory_Rules_v6.md` §5.1 |
| SS_demand | Safety stock (demand) | `z * σ * sqrt(L)` | z, σ, L | `Master_Inventory_Rules_v6.md` §5.2 |
| SS_floor | Safety stock floor | `D * B` | D, B | `Master_Inventory_Rules_v6.md` §5.2 |
| SS_mix | Size-mix buffer (CL only) | `TV * D * L` (else 0) | TV, D, L | `Master_Inventory_Rules_v6.md` §5.2 |
| SS_total | Total safety stock | `SS_demand + SS_floor + SS_mix` | above | `Master_Inventory_Rules_v6.md` §5.2 |
| ROP | Reorder point (units) | `D*L + SS_total` | D, L, SS_total | `Master_Inventory_Rules_v6.md` §5.3 |
| T_post | Target cover after arrival (days) | `R + SS_total/D` | R, SS_total, D | `Master_Inventory_Rules_v6.md` §5.3 |
| Status | Inventory action status | Total-first logic: REORDER / WAIT / OK | current_stock, inbound, ROP | `Master_Inventory_Rules_v6.md` §5.1.1 |
| K_avg | Avg capital frozen (KZT) | `D*(L+R/2)*COGS + SS_total*COGS` | D, L, R, COGS, SS_total | `Master_Inventory_Rules_v6.md` §5.4 |
| Monthly_Profit | Profit per month (KZT) | `UnitProfit * D * 30` | unit_profit, D | `Master_Inventory_Rules_v6.md` §5.4 |
| Monthly_ROIC | Monthly return on invested capital | `Monthly_Profit / K_avg` | monthly_profit, K_avg | `Master_Inventory_Rules_v6.md` §5.4 |

### 2.3 Dashboard-only (portfolio-level) metrics
| Metric | Definition | Formula | Inputs | Source |
|---|---|---|---|---|
| Margin % | **UNDEFINED** in rules. Candidate: contribution margin | ASSUMPTION A: `Profit / NetRevenue` | profit, revenue | ASSUMPTION |
| Total inventory value | **UNDEFINED** in rules. Candidate: inventory at COGS | ASSUMPTION: `SUM(current_stock_units * COGS_unit)` | current_stock, cogs_unit | ASSUMPTION |
| Capital | **UNDEFINED** in rules. Candidate: cash + inventory value + inbound | ASSUMPTION: `cash_on_hand + inv_value + inbound_value` | cash input + stock valuation | ASSUMPTION |
| Stock efficiency % | **UNDEFINED** in rules. Candidate: coverage quality vs ROP | ASSUMPTION A: `%SKUs with Total_stock >= ROP` | total_stock, ROP | ASSUMPTION |

### 2.4 Aggregation rules (non-negotiable)
- Revenue/COGS/Profit: **sum** over rows.
- Units: **sum** quantity.
- Avg sell price: **weighted avg** by quantity (candidate).
- ROIC rollup (portfolio): **UNDEFINED** in rules.
  - Candidate A: weighted by K_avg (capital-weighted ROIC).
  - Candidate B: compute portfolio profit and portfolio capital then divide.

---

## 3) Data Requirements (fields/tables needed, per metric)

### 3.1 Required tables (V1)
**sales_fact_v2** (must exist)
- order_id
- order_date
- sku_key
- sku_id
- my_size (optional but valuable)
- store_code
- quantity
- sell_price_kzt
- delivery_fee (preferred; else derived)
- net_rev (preferred; else derived)
- status
- return_flag

**dim_sku_size**
- sku_id
- sku_key
- base_cost_cny
- weight_kg

**dim_fx_rates**
- fx_cny_kzt
- fx_usd_kzt
- effective_date

**dim_params**
- commission
- vat_rate
- cargo_rate (by product_type if supported)
- constants: L, R, B, z, TV (or separate table)

### 3.2 Inventory/health data (if available)
Any one of:
- `fact_sku_metrics` (preferred): current_stock, inbound_stock, rop, status, roic_monthly, d30
OR
- stock ledger + inbound tables that can derive these fields

### 3.3 Finance inputs table (new, V1)
- `dim_finance_inputs`:
  - effective_date (date)
  - cash_on_hand_kzt (numeric)
  - opex_monthly_kzt (numeric)
  - updated_at (timestamp)
  - updated_by (text; even “local”)

---

## 4) Acceptance Criteria (testable checklist per tab)

### Dashboard
- [ ] Loads in <2 seconds on local DB for last 30 days.
- [ ] KPI strip values match DB query results for the same filters.
- [ ] Delta vs previous 30 days is correct.
- [ ] 12-month chart shows exactly 12 months + MTD.
- [ ] Each KPI has a tooltip showing definition + formula + Source path.

### Cashflow Calendar
- [ ] Default range loads last 60 days.
- [ ] Clicking a day opens a drawer with top SKU breakdown.
- [ ] Filters apply consistently across calendar and drawer.

### Period Comparison
- [ ] Period B auto-calculates equal-length preceding window.
- [ ] Δ and Δ% are correct and handle divide-by-zero safely.
- [ ] Comparison works for “All SKUs” and for single SKU_key.

---

## 5) Edge Cases + Defaults

- Dates: always interpret “today” in Asia/Almaty.
- Missing FX rates: show explicit “FX missing” error state (don’t silently compute).
- Returns/cancellations:
  - Default: exclude `CANCELLED` and `RETURNED` from KPI totals (unless user toggles “include”).
- Zero revenue periods: margin % should show “—” (not infinity).
- Unknown meaning of `sales_fact_v2.net_rev` (unit vs line):
  - Add a one-time validation check (compare `net_rev / quantity` distributions) and log assumption.

---

## 6) V1 vs V2 Scope

### V1 ships
- 3 tabs + premium filtering + drill-down drawers
- Metric definitions + tooltips with sources
- Read-only analytics + editable cash/OPEX inputs
- DB views for consistent derived economics

### V2 backlog (high ROI, but gated)
- Demand override manager (time-bounded overrides; audit logged)
- ROIC gate visualizer (≥20%, 10–20%, <10%) + PO recommendations explainability
- Alert center (Telegram summaries mirrored in UI)
- Multi-channel (Kaspi + WB) unified P&L
- Role-based auth, multi-user, deployment hardening

---

## 7) How to Run (Local, V1)

Backend API (no external deps):
```bash
python3 scripts/run_saas_api.py --host 127.0.0.1 --port 8008
```

Frontend (static UI):
```bash
cd webapp
python3 -m http.server 5173
```

Open: `http://127.0.0.1:5173` (API expects `http://127.0.0.1:8008`).

Notes:
- API uses DB views and requires `sales_fact_v2`, `dim_sku`, `dim_params`, `dim_fx_rates`.
- If FX rates are missing for the queried range, the API returns an explicit error.
