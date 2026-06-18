# Phase 7 Offer-Linkage Optional Narrowing

Status: `PHASE7_OFFER_LINKAGE_YELLOW_OPTIONAL_DEFECTS_EXACT`
Created: `2026-05-22`

This is a copied-temp-only evidence lane. It does not authorize production DB writes, workbook writes, source-pointer writes, scheduler/LaunchAgent/cron changes, WebUI/API/Kaspi/external mutations, Web_automation writes, ad-platform writes, bank/cash movement, supplier payment, PO commitment, stock or price changes, owner publication, production preflight, or production apply.

## Purpose

`B008_po_money_gate` was already narrowed by Agent 13: required failures were reduced to `single_truth_alignment`, while optional `offer_linkage` failed because `fact_offer_stock_mapper_current` did not exist.

This lane tested the smallest safe local move: create the mapper table on a copied DB only, then rerun offer-linkage and PO-money validation.

## Boundary

- Source copied DB: `~/Docs/Autonomous_business_agent_handoffs/2026-05-22_mvos_phase4_po_single_truth_local_route/agent13_po_single_truth_evidence/copied_db/agent13_po_single_truth_copied_temp.db`
- Phase 7 copied DB: `~/Docs/Autonomous_business_agent_handoffs/2026-05-22_mvos_phase7_offer_linkage_optional_narrowing/agent16_offer_linkage_evidence/copied_db/agent16_offer_linkage_copied_temp.db`
- Final copied DB SHA-256: `9e561a0f44998ec46470686ca7fc8684825967ed041f0297d4ddbf66fc708862`
- Production protected surfaces were hash-checked before and after; no differences were observed.

## Mapper Materialization

Command class:

`python3 scripts/build_offer_stock_mapper.py --db <copied_db> --store UNIVERSAL --store STOREB --store ACMEWEAR --window-days 90`

Result:

- rows total: `2640`
- unresolved rows: `91`
- ambiguous rows: `87`
- methods:
  - `article_map_sku_id`: `2364`
  - `article_map_article_size`: `94`
  - `offer_size_stats`: `32`
  - `recent_sales_offer_mode`: `16`
  - `size_probability_offer`: `33`
  - `size_probability_style`: `10`
  - `unresolved`: `91`

By store:

| store | unresolved rows | ambiguous rows |
| --- | ---: | ---: |
| `STOREB` | `39` | `20` |
| `ACMEWEAR` | `26` | `36` |
| `UNIVERSAL` | `26` | `31` |

## Validator Result

`validate_offer_linkage.py` no longer fails as `mapper table missing`. It now fails on exact retained defects:

- resolved rows: `2462`
- unresolved rows: `91`
- ambiguous rows: `87`
- missing bidirectional rows: `4`

The four missing bidirectional rows are all Universal HUS Green links:

| store | kaspi_article | sku_key | sku_id | method |
| --- | --- | --- | --- | --- |
| `UNIVERSAL` | `CL_NEW-CLO_MEN_HUS_GREEN_102792061_48_(XL)` | `CL_NEW-CLO2_MEN_HUS_GREEN` | `CL_NEW-CLO2_MEN_HUS_GREEN_XL` | `offer_size_stats` |
| `UNIVERSAL` | `CL_NEW-CLO_MEN_HUS_GREEN_102792061_52_(2XL)` | `CL_NEW-CLO2_MEN_HUS_GREEN` | `CL_NEW-CLO2_MEN_HUS_GREEN_2XL` | `offer_size_stats` |
| `UNIVERSAL` | `CL_NEW-CLO_MEN_HUS_GREEN_102792061_54_(3XL)` | `CL_NEW-CLO2_MEN_HUS_GREEN` | `CL_NEW-CLO2_MEN_HUS_GREEN_2XL` | `offer_size_stats` |
| `UNIVERSAL` | `CL_NEW-CLO_MEN_HUS_GREEN_102792061_56_(4XL)` | `CL_NEW-CLO2_MEN_HUS_GREEN` | `CL_NEW-CLO2_MEN_HUS_GREEN_4XL` | `recent_sales_offer_mode` |

## PO Money Gate Result

`validate_po_money_gate.py --json` after mapper materialization still returns:

- `ok=false`
- required failed: `single_truth_alignment`
- optional failed: `offer_linkage`

This is correct. The lane did not and must not claim PO-money green because physical-stock inventory-cost drift remains the required blocker:

- snapshot date: `2026-05-04`
- snapshot cost: `40,195,486.88 KZT`
- cashflow cost: `23,360,148.00 KZT`
- diff: `16,835,338.88 KZT`
- allowed: `803,909.74 KZT`

## Board Decision

`B008_po_money_gate` remains `STOP`.

The useful progress is narrower: optional `offer_linkage` is no longer a vague missing-table problem. It is now a precise future repair lane with `91` unresolved rows, `87` ambiguous rows, and `4` missing bidirectional rows.

## Evidence

- Mapper stdout: `~/Docs/Autonomous_business_agent_handoffs/2026-05-22_mvos_phase7_offer_linkage_optional_narrowing/agent16_offer_linkage_evidence/commands/010_build_offer_stock_mapper.stdout.txt`
- Offer-linkage validator: `~/Docs/Autonomous_business_agent_handoffs/2026-05-22_mvos_phase7_offer_linkage_optional_narrowing/agent16_offer_linkage_evidence/validator_outputs/020_validate_offer_linkage.stdout.txt`
- PO-money validator: `~/Docs/Autonomous_business_agent_handoffs/2026-05-22_mvos_phase7_offer_linkage_optional_narrowing/agent16_offer_linkage_evidence/validator_outputs/030_validate_po_money_gate_after_mapper.pretty.json`
- Method summary: `~/Docs/Autonomous_business_agent_handoffs/2026-05-22_mvos_phase7_offer_linkage_optional_narrowing/agent16_offer_linkage_evidence/extracts/offer_mapper_method_summary.csv`
- Unresolved preview: `~/Docs/Autonomous_business_agent_handoffs/2026-05-22_mvos_phase7_offer_linkage_optional_narrowing/agent16_offer_linkage_evidence/extracts/unresolved_preview_100.csv`
- Ambiguous preview: `~/Docs/Autonomous_business_agent_handoffs/2026-05-22_mvos_phase7_offer_linkage_optional_narrowing/agent16_offer_linkage_evidence/extracts/ambiguous_preview_100.csv`
- Missing bidirectional rows: `~/Docs/Autonomous_business_agent_handoffs/2026-05-22_mvos_phase7_offer_linkage_optional_narrowing/agent16_offer_linkage_evidence/extracts/missing_bidirectional_rows.csv`

## Next Best Route

Do not spend effort repairing optional offer linkage before the required PO-money blocker is reviewed. The next business-critical route remains CodeCaptain review of the current Phase 4/5/7 yellow boundary, especially the physical-stock substitute/retained contract question.

If CodeCaptain requires strict offer-linkage before production preflight, the now-scoped Agent16 evidence can launch a focused mapper repair lane.
