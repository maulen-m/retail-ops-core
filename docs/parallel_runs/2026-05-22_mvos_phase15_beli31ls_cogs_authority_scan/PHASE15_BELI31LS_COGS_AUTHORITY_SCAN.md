# Phase 15 LINE-31-LS COGS Authority Scan

Gate: `YELLOW`

Completed: `2026-05-22T03:11:52+0500`

This lane is read-only/review-only except for this local evidence note, the blocker-board update, and the external closeout. It does not authorize production DB writes, copied DB materialization, workbook writes, source-pointer writes, scheduler/LaunchAgent/cron changes, Web_automation writes, Kaspi/API/WebUI mutations, external writes, ad-platform writes, stock changes, price changes, cash movement, PO commitment, owner publication, production preflight, or production apply.

## Question

Can the final B012 retained row be closed in copied-temp by applying `LINE-31-LS` COGS authority?

Retained row from Phase 13:

| order_id | store | status | delivery_type | sku_key | sku_id | blocker |
|---|---|---|---|---|---|---|
| `929183530` | `ACMEWEAR` | `SHIPPED` | `KASPI_DELIVERY` | `LINE-31-LS` | `LINE-31-LS_2XL` | no accepted `LINE-31-LS` copied-temp COGS authority |

## Evidence Inspected

### Current accepted COGS contract

`docs/contracts/mvos_source_contracts/ACTIVE_MVOS_SOURCE_CONTRACT_REGISTRY.json` contains the active copied-temp parent-unit COGS contract `OWNER_APPROVED_PARENT_UNIT_COGS_FOR_COPIED_TEMP_ONLY_20260517`.

The accepted source route includes:

| child sku_key | accepted copied-temp unit COGS |
|---|---:|
| `LINE-31-TS` | `6006.76` |
| `SUIT-21-TS` | `5567.22` |
| `SUIT-31-LS` | `5567.22` |
| `SUIT-31-TS` | `5567.22` |

It does not include `LINE-31-LS`. Therefore the current accepted contract does not authorize applying `6006.76` to `LINE-31-LS`.

### Local identity evidence

`docs/offer_creation/LINE51_BUNDLE_DB_INGEST_HANDOFF_2026-04-23.md` confirms `LINE-31-LS` is a canonical bundle family row and maps `2XL-52` to normalized `sku_id` `LINE-31-LS_2XL`.

`~/Docs/Web_automation/exports/acmewear_bundle_publication_capture/20260427_104746/bundle_publication_capture.csv` includes the exact `LINE-31-LS-ST-2XL-52` row with:

| field | value |
|---|---|
| `sku_key` | `LINE-31-LS` |
| `sku_id` | `LINE-31-LS_2XL` |
| `parent_family` | `LINE51` |
| `category_code` | `ST` |
| `source_state` | `ARCHIVE` |
| `current_state` | `inactive_no_price_no_stock` |
| `price` | `0` |

`~/Docs/Web_automation/Docs/experiments/acmewear_bundles/acmewear_bundles_experiment_calendar.md` classifies `beli-31_ls` as:

| Stage-2 SKU key | Parent | Shape | Priority | Initial price | First launch mode |
|---|---|---|---|---:|---|
| `LINE-31-LS` | `LINE51` | `3-in-1` | `minimal` | `9490` | `minimal capped` |

This proves identity and product-family context. It does not by itself authorize copied-temp COGS inheritance.

### Parent LINE51 economics evidence

`docs/parallel_runs/2026-04-28_ig_funnel_owner_stock_override/OWNER_APPROVED_STOCK_OVERRIDE_LINE51_LINE61_2026-04-28.md` records parent `CL_OC_MEN_LINE51_WHITE` owner-approved landed COGS/unit as `6006.76 KZT`.

`docs/parallel_runs/2026-04-28_ig_funnel_owner_stock_override/line51_line61_owner_stock_override_2026-04-28.csv` records the same `6006.76 KZT` parent value for each LINE51 size.

This is parent LINE51 funnel economics. It is not an explicit `LINE-31-LS` child-bundle copied-temp COGS contract.

### Current production DB snapshot

Read-only query against `db/app.db`:

```text
LINE-31-LS|LINE-31-LS|BLACK_WHITE|CL|0.0|0.0||||1
LINE-31-TS|LINE-31-TS|BLACK_WHITE|CL|0.0|0.0||||1
CL_OC_MEN_LINE51_WHITE|LINE51|WHITE|CL|60.0|0.95|4680.0|14990.0|INBOUND_CALENDAR_V10.002|1
```

`LINE-31-LS` has no source-backed `base_cost_cny`, `weight_kg`, or `cogs_kzt` in production DB. The parent DB value also differs from the owner-approved `6006.76 KZT` parent economics value used by the copied-temp contract for `LINE-31-TS`, which is another reason not to infer silently.

## Decision

`LINE-31-LS` identity is proven enough for a review packet:

- `LINE-31-LS_2XL` is a valid normalized bundle SKU.
- The exact `LINE-31-LS-ST-2XL-52` platform row exists in the Web_automation publication capture.
- The bundle is associated with parent `LINE51`.

`LINE-31-LS` copied-temp COGS authority is not proven:

- The active owner/CodeCaptain accepted parent-unit COGS contract names `LINE-31-TS`, not `LINE-31-LS`.
- Parent `CL_OC_MEN_LINE51_WHITE=6006.76 KZT` evidence exists, but no current accepted contract says `LINE-31-LS` may inherit it.
- Production DB has no usable direct `LINE-31-LS` cost inputs.

Therefore no copied-temp COGS patch was applied in this lane. B012 remains `YELLOW`, now narrowed to a pure authority gap rather than an identity gap.

## Fastest Safe Next Route

Option A: owner provides an explicit copied-temp-only `LINE-31-LS` COGS approval phrase. Then a follow-up copied-temp proof may apply only that single row route and rerun `validate_on_delivery_freeze.py`.

Option B: keep `LINE-31-LS` quarantined and ask CodeCaptain whether existing parent LINE51 economics can be accepted as copied-temp authority for `LINE-31-LS`.

Option C: wait for a true component-level ChildSum COGS contract. This is safest architecturally, but slower than Option A or B.

Non-authorizing draft phrase if the owner chooses Option A later:

```text
I approve copied-temp-only use of LINE-31-LS parent-unit COGS as 6006.76 KZT from CL_OC_MEN_LINE51_WHITE for order 929183530 / ACMEWEAR / LINE-31-LS_2XL only. This does not authorize production DB writes, workbook writes, source-pointer writes, scheduler changes, external writes, stock changes, price changes, cash movement, PO commitment, owner publication, production preflight, or production apply.
```

## Verification

Commands run:

```text
sed -n '1,240p' AGENTS.md
sed -n '1,220p' docs/00_START_HERE.md
sed -n '1,220p' .claude/OPERATING.md
sed -n '250,310p' docs/contracts/mvos_source_contracts/ACTIVE_MVOS_SOURCE_CONTRACT_REGISTRY.json
rg -n "LINE-31-LS|LINE31LS|LINE-31-TS|CL_OC_MEN_LINE51_WHITE|6006\.76|OWNER_APPROVED_PARENT_UNIT_COGS|parent-unit COGS" docs scripts tests core config imports -S
rg -n "LINE-31-LS.*6006\.76|6006\.76.*LINE-31-LS|LINE-31-LS.*COGS|COGS.*LINE-31-LS|LINE-31-LS.*parent-unit|parent-unit.*LINE-31-LS" ~/Docs/Autonomous_business ~/Docs/Web_automation -S
sqlite3 db/app.db "SELECT sku_key, model, color, product_type, base_cost_cny, weight_kg, cogs_kzt, avg_sell_price_kzt_used, avg_sell_price_source, active_flag FROM dim_sku WHERE sku_key IN ('LINE-31-LS','LINE-31-TS','CL_OC_MEN_LINE51_WHITE') ORDER BY sku_key;"
```

No production DB, workbook, source-pointer, scheduler, Web_automation, or external surface was edited.
