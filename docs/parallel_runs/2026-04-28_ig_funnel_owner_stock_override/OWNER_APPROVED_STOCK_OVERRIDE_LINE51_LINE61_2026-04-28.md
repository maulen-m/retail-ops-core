# Owner-Approved Stock Override - LINE51 and Line61

Decision timestamp: `2026-04-28 21:08:57 +0500`

Owner: Adil

Scope: Instagram direct funnel and downstream launch/economics assumptions for LINE51 White and Line61 Black.

## Decision

The owner approves the following stock layer as the current active override for these two products. This supersedes the stale Autonomous Business DB stock snapshot used by the earlier IG funnel contribution.

This override should be used for:

- IG funnel stock/economics assumptions.
- Ads and landing-page availability claims.
- Manager scripts and sales forms.
- External expert packs that need current LINE51/Line61 stock context.

This override remains active until superseded by a newer owner-approved physical count, canonical inventory rebuild, or DB-ingested stock correction.

## Owner-Approved Values

### LINE51 White

SKU key: `CL_OC_MEN_LINE51_WHITE`

Basis: human-approved proportional 20 percent reduction from the active proxy layer.

Landed COGS/unit used for funnel economics: `6006.76 KZT`

Total owner-approved stock: `764`

Total landed COGS value: `4,589,166 KZT`

| Size | Owner-approved stock |
|---|---:|
| S | 62 |
| M | 90 |
| L | 154 |
| XL | 185 |
| 2XL | 133 |
| 3XL | 106 |
| 4XL | 34 |
| Total | 764 |

### Line61 Black

SKU key: `CL_NEW-CLO2_MEN_SUIT-61_BLACK`

Basis: active proxy layer with invalid `4XL=-5` floored to `0`.

Landed COGS/unit used for funnel economics: `5567.22 KZT`

Total owner-approved stock: `862`

Total landed COGS value: `4,798,941 KZT`

| Size | Owner-approved stock |
|---|---:|
| S | 49 |
| M | 105 |
| L | 202 |
| XL | 233 |
| 2XL | 161 |
| 3XL | 112 |
| 4XL | 0 |
| Total | 862 |

## Operational Rules

- Line61 `4XL` must be excluded from ads, product forms, manager scripts, and availability claims.
- The previous Autonomous Business IG funnel contribution used stale DB stock and must not be used as stock truth for LINE51/Line61.
- These values are an owner-approved override layer, not proof that the full repo inventory system is globally decision-grade.
- Do not apply a global 20 percent haircut to other products from this decision.

## Machine-Readable Sidecar

CSV sidecar:

`docs/parallel_runs/2026-04-28_ig_funnel_owner_stock_override/line51_line61_owner_stock_override_2026-04-28.csv`

Generated mirror:

`exports/owner_stock_overrides/2026-04-28/line51_line61_owner_stock_override_2026-04-28.csv`

## Source Context

This decision is tied to the second-take IG funnel pack:

`~/Docs/Oracle/oracle_packs/Instagram_funnel_packs/ig_line51_line61_astana_direct_funnel__2026-04-28_GMT5/second_take_gap_closure__2026-04-28_GMT5/agent_contributions/01_autonomous_business/AUTONOMOUS_BUSINESS_FRESH_STOCK_ECONOMICS.md`
