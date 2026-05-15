# STOREB Owner SKU Mapping Decision Packet

Generated at: `2026-05-11T21:12:50+0500`

Gate: `OWNER_MAPPING_CONFIRMED_REPLAY_REQUIRED`

## Purpose

This packet converts Agent772 and Agent773 proof into a simple owner decision surface for the seven STOREB ads product codes that still cannot be mapped from deterministic repo evidence.

This packet is inert. It does not authorize production DB writes, workbook writes, Web_automation writes, scheduler execution, owner publication, external writes, Kaspi merchant writes, ad spend, bid/budget/campaign/product mutation, cash movement, PO commitment, price changes, or stock changes.

## Current State

Agent772 resolved the STOREB source-date gap in copied/temp proof:

- Source window covered: `2026-05-05..2026-05-11`
- Fresh source rows: `70`
- Product codes in campaign: `10`
- Total report cost: `38624.07` KZT

Agent773 proved the remaining blocker:

- Final label: `STOREB_ADS_MAPPING_BLOCKER_VISIBLE`
- Deterministic new mappings found: `0`
- Blocked product-code mappings: `7/10`
- Unmapped source rows: `49`
- Blocked source ad cost: `10206.80` KZT
- Product-name-only mapping was not used and remains forbidden.

## Decision Needed

The owner needs to decide whether the seven blocked Kaspi Marketing product codes are all the same AB SKU as the three already deterministically mapped campaign codes:

`CL_OC_MEN_LINE52_BLACK`

If not, provide the correct SKU per product code or keep the row blocked.

## Owner Decision Recorded

Recorded at: `2026-05-12T10:03:58+0500`

Owner response, exact wording:

`Yes, all of them are offered groups of Line52 product.`

Normalized decision token:

`OWNER_CONFIRMED_ALL_7_STOREB_BLOCKED_PRODUCT_CODES_ARE_LINE52_PRODUCT_GROUPS_2026-05-12`

Decision interpretation:

All seven blocked STOREB Kaspi Marketing product codes in this packet are owner-confirmed Line52 product groups and may be mapped to the same AB SKU used by the already mapped Line52 campaign codes:

`CL_OC_MEN_LINE52_BLACK`

This is mapping-truth authority only. It still does not authorize production apply, workbook mutation, scheduler work, owner publication, external writes, Kaspi merchant writes, ad spend, cash movement, PO commitment, price changes, or stock changes.

## Blocked Codes

| Product code | Product name | Rows | Ad cost KZT | Current proof status | Owner decision |
|---|---|---:|---:|---|---|
| `11391140b` | Комплект ALPIKA черный | `7` | `0.00` | No exact product-code article-map hit, no exact order-entry join, no source related token | choose SKU or keep blocked |
| `11391205b` | Комплект Antec черный | `7` | `5351.33` | No exact product-code article-map hit, no exact order-entry join, no source related token | choose SKU or keep blocked |
| `11391711b` | Комплект S SPORT серый | `7` | `3565.47` | No exact product-code article-map hit, no exact order-entry join, no source related token | choose SKU or keep blocked |
| `11869884b` | Спортивный костюм PRO COMBAT черный | `7` | `0.00` | No exact product-code article-map hit, no exact order-entry join, no source related token | choose SKU or keep blocked |
| `11956144b` | Спортивный костюм черный | `7` | `1290.00` | Only product-name evidence exists; product-name-only mapping is forbidden | choose SKU or keep blocked |
| `12071269b` | Спортивный костюм Fashion черный | `7` | `0.00` | No exact product-code article-map hit, no exact order-entry join, no source related token | choose SKU or keep blocked |
| `12236047b` | Спортивный костюм IMPERIAL черный | `7` | `0.00` | No exact product-code article-map hit, no exact order-entry join, no source related token | choose SKU or keep blocked |

Owner decision applied to the row-level sidecar:

| Product code | Owner-selected SKU key | Decision basis |
|---|---|---|
| `11391140b` | `CL_OC_MEN_LINE52_BLACK` | owner confirmed all seven are Line52 product groups |
| `11391205b` | `CL_OC_MEN_LINE52_BLACK` | owner confirmed all seven are Line52 product groups |
| `11391711b` | `CL_OC_MEN_LINE52_BLACK` | owner confirmed all seven are Line52 product groups |
| `11869884b` | `CL_OC_MEN_LINE52_BLACK` | owner confirmed all seven are Line52 product groups |
| `11956144b` | `CL_OC_MEN_LINE52_BLACK` | owner confirmed all seven are Line52 product groups |
| `12071269b` | `CL_OC_MEN_LINE52_BLACK` | owner confirmed all seven are Line52 product groups |
| `12236047b` | `CL_OC_MEN_LINE52_BLACK` | owner confirmed all seven are Line52 product groups |

## Already Deterministically Mapped

These three product codes are already mapped to `CL_OC_MEN_LINE52_BLACK` and do not need an owner decision in this packet:

- `11120372b` - Спортивный костюм ALPIKA черный
- `11122298b` - Спортивный костюм черный
- `11942309b` - Спортивный костюм PRO COMBAT черный

## CSV Sidecar

Owner decision CSV:

`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/STOREB_OWNER_SKU_MAPPING_DECISION_PACKET_20260511_211250.csv`

The CSV is the row-level sidecar. It now records the owner-selected SKU key for all seven rows as `CL_OC_MEN_LINE52_BLACK`, preserving the exact owner response and normalized decision token.

## Approval Options

### Option A - Owner Approves All Seven As Line52 Black

Use this only if the owner knows all seven blocked product codes represent the same sellable AB SKU:

`CL_OC_MEN_LINE52_BLACK`

Exact phrase:

`OWNER_APPROVES_ALL_7_STOREB_BLOCKED_PRODUCT_CODES_TO_CL_OC_MEN_LINE52_BLACK_2026-05-11`

### Option B - Owner Provides Row-Level Overrides

Use this if some codes map to a different SKU or should stay blocked.

Exact phrase shape:

`OWNER_APPROVES_STOREB_ROW_LEVEL_SKU_MAPPING_2026-05-11: 11391140b=<SKU_OR_KEEP_BLOCKED>; 11391205b=<SKU_OR_KEEP_BLOCKED>; 11391711b=<SKU_OR_KEEP_BLOCKED>; 11869884b=<SKU_OR_KEEP_BLOCKED>; 11956144b=<SKU_OR_KEEP_BLOCKED>; 12071269b=<SKU_OR_KEEP_BLOCKED>; 12236047b=<SKU_OR_KEEP_BLOCKED>`

### Option C - Keep Blocked

Use this if the owner cannot confirm the product identity safely.

Exact phrase:

`OWNER_KEEP_STOREB_7_BLOCKED_PRODUCT_CODES_BLOCKED_2026-05-11`

## After Owner Decision

After this owner decision, the next implementation lane should:

1. Materialize an owner-truth mapping sidecar under a new evidence root.
2. Replay the STOREB ads adapter against a copied/temp DB only.
3. Rerun ads validators.
4. Package the result for review before any production apply or owner publication.

## Still Forbidden

Even if Option A or B is approved, the approval is mapping-truth authority only. It is not production apply authority and does not authorize:

- production `db/app.db` mutation;
- protected workbook mutation;
- scheduler install/enablement/execution;
- owner publication/send/approval request;
- Web_automation write;
- browser-login automation;
- credential/session export;
- external writes;
- Kaspi merchant writes;
- ad spend or campaign mutation;
- cash movement;
- supplier payment;
- PO commitment;
- price changes;
- stock changes.
