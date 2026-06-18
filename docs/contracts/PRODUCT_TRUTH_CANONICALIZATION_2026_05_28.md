# Product Truth Canonicalization Contract - 2026-05-28

Status: `ACTIVE_READ_ONLY_PLANNING_CONTRACT`

Config: `config/product_truth_canonicalization_2026_05_28.json`

This contract supersedes stale dry-run classifications from the first Product
Truth Correction Wave where they conflict with owner truth. It is a repo
documentation/config/test contract for planning and validation only. It does not
authorize production DB writes, workbook writes, source-pointer writes,
scheduler changes, Web_automation live writes, Kaspi/API/WebUI/Meta/CRM
mutations, campaign bid/budget/state changes, price changes, stock changes,
supplier messages, payment, PO commitment, owner publication, production
preflight, or production apply.

## RUSH31 Canonical Identity

RUSH31 is an independent men's RUSH 3-in-1 product route:

- canonical SKU key: `CL_NC_MEN_RUSH-31_BLACK`
- Kaspi offer: `165486887`
- campaign: `2794142`
- product SKU: `21282790b`
- owner stock total: `290`
- size stock: S=60, M=30, L=50, XL=70, 2XL=50, 3XL=30, 4XL=0

Do not classify campaign `2794142`, offer `165486887`, or product SKU
`21282790b` as `LINE61_CHILD`, LINE31, or LINE31S. Historical stale labels may be kept
as evidence only when they are explicitly marked superseded by this owner truth.

Kaspi pricelist warehouse columns such as `PP1`, `PP2`, `PP3`, `PP4`, `PP5`,
or preorder quantities are not physical inventory truth for RUSH31 or any other
product. They may be used only as prior pricelist/offer-state evidence. RUSH31
planning must use the owner physical count above as canonical unless a later
owner-approved physical count, source stock anchor, accepted inbound event, or
shipment/status depletion rule supersedes it.

## Pricelist Stock Non-Authority

Merchant Cabinet / Kaspi pricelist stock values are not inventory source of
truth. They must never drive physical stock, reorder quantity, or owner stock
truth by themselves.

Allowed uses:

- offer availability / pricelist-state evidence;
- route discovery evidence when paired with independent identity proof;
- copied-temp offer availability materialization with `physical_stock_qty=NULL`.

Forbidden uses:

- physical warehouse stock truth;
- economic final-sales stock truth;
- owner physical count replacement;
- inventory capital/reorder planning quantities.

Real inventory truth must come from owner physical overrides, source stock
anchors, accepted inbound events, and shipment/status depletion rules.

## LINE31 Canonical Stock Exception

LINE31 and LINE31S are the same LINE31 family for this lane. LINE31 is not RUSH31.

LINE31 stock planning must use the LINE31-specific source stack:

1. April 13 stock anchor:
   `~/Cowork/Projects/E-commerce/docs/inventory/products/LINE31_sales__STOCK_13.4.26.md`
2. Historical LINE31 sales rows:
   `~/Cowork/Projects/E-commerce/docs/inventory/products/LINE31_sales__LINE31_sales.md`
3. PO-1A non-Olive arrived quantities:
   `~/Cowork/Projects/Sourcing-Research/docs/agent_handoffs/LINE31_PO1A_NON_OLIVE_ASTANA_SALES_ACTIVATION__2026-05-24/line31_po1a_non_olive_arrived_quantities.csv`

The repaired parser must read the Markdown sheet matrix row-by-row. It must not
coerce `Sell_price_kzt` into zero. Source-backed historical LINE31 sales contain
`16,990 KZT` sell-price evidence.

For PO-1A addback, only source-mapped arrived colors with a valid sellable route
are added to sellable planning stock. Owner clarification on 2026-05-29
reclassifies Bean Paste Pink, Pomelo Pink, and Eggplant Purple as real physical
stock that is not for sale yet. Those `32` units must be preserved as
`PHYSICAL_NOT_FOR_SALE_RESERVE`, not as a blocker requiring immediate offer
creation.

LINE31 Whale Blue currently has no valid live sellable route. The single-size
Whale Blue L URL
`https://kaspi.kz/shop/p/sportivnyi-kostjum-acmewear-of-line31-st-wb-l-sinii-l-162287320/`
is an incorrect/unattached offer and must be ignored for sellable-route proof.
Whale Blue stock may be preserved as physical stock, but it is not sellable
stock until a future source-backed route is proven and separately approved.

## Owner Stock Overrides

The owner override document and CSV are canonical planning inputs:

- `docs/inventory/OWNER_STOCK_OVERRIDES_2026-05-28.md`
- `docs/inventory/owner_stock_overrides_2026-05-28.csv`

Validators must preserve at least these owner facts:

- RUSH31 total `290`, with 4XL `0`
- LINE61 L=151, XL=100, 2XL=24, 3XL=25
- LINE51 WHITE 4XL `0`
- LINE52 total `298`, with XL=0, 2XL=0, 4XL=0
- LINE31 uses the LINE31 exception stack, not the general V3 depleted anchor alone

## Rombik Kid30 Effective-Dated Alias

Owner decision `OWNER_ROMBIK_KID30_ALIAS_2026_06_03` is effective from
`2026-06-03T10:09:14+05:00`.

Only these Kaspi public product codes are authorized sellable routes for
canonical stock pool `CL_NEW-CLO_KID_ROMBIK_BLACK_30`:

- `135222379` / public height `152`
- `128541983` / public height `158`

The canonical physical stock pool remains one `93`-unit owner-approved manual
count for `CL_NEW-CLO_KID_ROMBIK_BLACK_30`. This alias decision must not create
a second physical stock pool, and must not add the same stock to
`CL_NEW-CLO_KID_ROMBIK_BLACK_S`.

Orders imported at or after the effective timestamp may canonicalize those two
product-code routes to:

- `sku_key`: `CL_NEW-CLO_KID_ROMBIK_BLACK`
- `sku_id`: `CL_NEW-CLO_KID_ROMBIK_BLACK_30`
- `MY_SIZE`: `30`

Historical production rows before the effective timestamp are not restated by
this contract. Neighbor Rombik kids S product codes `143893497` (`164`) and
`147855005` (`170`) remain outside this alias decision unless a later owner
decision explicitly changes them.

## Internal Gift-Bag COGS

Internal economics planning for current ACMEWEAR/Kaspi offers and near-term
Instagram offers must include gift-bag cost and weight:

```text
internal COGS =
  garment/base cost
  + allocated delivery/logistics cost
  + 3 CNY gift-bag cost
  + 0.10 kg gift-bag delivery-weight effect
```

This is an internal economics rule. It does not automatically authorize Kaspi
customer-facing `komplekt`/description copy to mention the gift bag. Instagram
copy may mention the gift bag only when the route and owner-approved copy allow
it.

The central economics helper exposes this through
`calc_cogs(..., include_gift_bag=True)` and
`resolve_landed_cogs(..., include_gift_bag=True)`. Existing live calculations
must not be silently changed; review-only planning/export lanes that model
current ACMEWEAR/Kaspi or near-term Instagram offers should opt in explicitly
and label the basis.

## TRM Opportunity Detector Rule

Marketing aggregate attribution and order-level API/product identity are
separate evidence classes.

Line61 TRM campaign `2629982`:

- current planning rule: hold enabled and monitor
- no cap lift while spend is far below the cap
- optional bid test only after fresh preflight and exact owner approval

LINE51 TRM campaign `2690256`:

- dry-run opportunistic re-enable candidate only
- candidate BID may be `>=100 KZT` only after stock/pricelist preflight
- no live state, bid, or budget change without exact owner approval

## Required Local Validation

Focused validation:

```bash
python3 scripts/validate_product_truth_canonicalization.py --strict --json
pytest -q tests/test_product_truth_canonicalization.py tests/test_gift_bag_cogs.py
```

The validator must fail if RUSH31 collapses into LINE61/LINE31, LINE31 historical
sales parse to zero price, owner override totals drift, the gift-bag COGS fields
are missing, or TRM campaign attribution is collapsed into order identity.
