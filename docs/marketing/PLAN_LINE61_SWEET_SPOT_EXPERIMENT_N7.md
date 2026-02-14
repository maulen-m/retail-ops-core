# PLAN_LINE61_SWEET_SPOT_EXPERIMENT_N7

## Objective
Find the LINE61 bid level with the best profit-efficiency tradeoff using daily completed facts and discount-adjusted (`effective-cost`) ROIC, with minimal daily operator time.

## Experiment loop (fast + low-risk)
Use one completed day per level, then lock winner for confirmation.

### Bid ladder (relative to current safe control bid `B0`)
1. `L1 = 0.80 * B0` (efficiency probe)
2. `L2 = 1.00 * B0` (control baseline)
3. `L3 = 1.20 * B0` (volume probe)
4. `L4 = 1.35 * B0` (stretch, only if `L3` passes guardrails)

### Duration
1. Run each level for 1 full completed day (yesterday-based evaluation).
2. After ladder, run best level for 2 additional days (stability check).

Why: 1-day steps keep cycle fast; 2-day confirmation lowers false winners from day noise.

## KPIs and targets
Primary KPI:
- `effective_roic` (discount-adjusted)

Secondary KPIs:
- spend
- orders
- CPA (`spend / orders`)
- views, clicks, CTR
- avg CPC

Target profile for a winning level:
- `effective_roic` >= control by at least 10%
- orders not down more than 5% vs control
- CPA not worse than control by more than 10%

## Stop conditions (risk guardrails)
Stop current level and step down immediately next cycle if any condition is true:
1. Spend spike with weak conversion: `spend > 1.35x control` and `orders <= 0.8x control`
2. Zero-order burn: `orders = 0` and `spend >= 0.25 * max_daily_spend_cap`
3. Profit collapse: `effective_roic < 0.85 * control`
4. CPC drift: `avg_cpc > 1.30x control` with no order lift

## Decision rule (daily)
1. `Increase one step` only if:
   - `effective_roic >= 1.10x control`, and
   - `orders >= 0.95x control`, and
   - no stop condition hit.
2. `Keep` if:
   - `effective_roic` within `±10%` of control, and
   - orders within `±10%` of control.
3. `Decrease one step` if:
   - `effective_roic < 0.90x control`, or
   - `CPA > 1.15x control`, or
   - any stop condition hit.

## Default experiment caps
- `max_daily_spend_cap`: **30,000 KZT** (or `1.6x` rolling 7-day LINE61 spend average, whichever is lower)
- `max_step_change`: **20%** per day (up or down)

## Daily brief template (must print every day)
```text
LINE61 Daily Brief | date=YYYY-MM-DD | level=Lx | bid=___ KZT
spend_kzt=___
orders=___
cpa_kzt=___
effective_roic=___
views=___
clicks=___
ctr=___%
avg_cpc_kzt=___
decision=INCREASE|KEEP|DECREASE
reason=...
guardrail_flags=[...]
```

## Minimal human workflow (<= 5 minutes/day)
1. Read yesterday brief.
2. Apply bid change only if decision is `INCREASE` or `DECREASE`.
3. Log final action (`old_bid -> new_bid`) and proceed.

## Notes
- Always evaluate completed-day data only (no same-day optimization decisions).
- Use effective-cost policy for all ROIC comparisons (discount-aware).
- Keep control bid `B0` as fallback safe state.
