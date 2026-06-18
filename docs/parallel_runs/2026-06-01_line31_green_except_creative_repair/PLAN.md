# LINE31 Green-Except-Creative Repair Plan

Created: 2026-06-01 10:24 +05

Gate: ROOT_READY_OWNER_APPROVED_GREEN_REPAIR

## Objective

Move LINE31 countrywide Meta launch readiness from `YELLOW` to `GREEN_EXCEPT_CREATIVE`.

This means every non-creative blocker should be closed or explicitly converted into an accepted launch rule with evidence. Final LINE31 video assets, thumbnails, asset URIs, and SHA-256 hashes remain in preparation and are allowed to stay blocked.

## Source Inputs

- Prior final matrix: `~/Docs/Autonomous_business/exports/validation/line31_countrywide_meta_launch_readiness_20260531/final_synthesis/FINAL_LINE31_COUNTRYWIDE_META_READINESS_MATRIX.md`
- Retained blockers: `~/Docs/Autonomous_business/exports/validation/line31_countrywide_meta_launch_readiness_20260531/final_synthesis/RETAINED_BLOCKERS_AND_FASTEST_PATH.md`
- Next approval phrases: `~/Docs/Autonomous_business/exports/validation/line31_countrywide_meta_launch_readiness_20260531/final_synthesis/NEXT_OWNER_APPROVAL_PHRASES.md`
- Cash/PO workbook: `~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/Inbound_calendar_V10.002.xlsx`
- Owner-ready cashflow cockpit workbook: `~/Docs/Oracle/Autonomous_business/2026-05-30/131112_TASK-000_cashflow-po-decision-workbook-external-eval-20260530/Answer/assets_of_answer/ACMEWEAR_cashflow_inventory_po_decision_cockpit_20260530.xlsx`

## Owner Facts Recorded For This Repair

- The owner fully approves required actions to implement the green-repair plan as main orchestrator.
- The owner wants option 2 included: repair unrelated `validate_params.py --strict` failures first instead of ignoring them.
- Current cash and SHR timing source is the `Cash_Balances` sheet plus SHR payments log in `Inbound_calendar_V10.002.xlsx`.
- The 18th `7000 CNY` SHR payment is owner-confirmed paid and supplier-paid, even though the exchanger receipt screenshot will arrive later.
- Protected reserve is `800000 KZT` untouchable. Prior `1500000 KZT` reserve assumption must not be used for this launch gate.
- Current LINE31 physical/sellable stock should use the exact rebuild from April leftovers plus PO1-A arrival.
- Final creative videos are still in preparation and do not block this repair wave; they remain the one allowed non-green launch gate.
- LINE31 internal Kaspi marketing and seller-bonus surfaces remain ON unless a later creative-ready declaration and separate exact isolation approval are issued.

## Current Strict Gate Failures To Repair Or Classify

The current `python3 scripts/validate_params.py --strict` fails on:

- `inbound_sheet_consistency`: PO-4.0 LINE61 shortage truth mismatch; owner truth is ordered/cargo 115, received 92, shortage 23.
- `single_truth_system`: workbook/DB part ID and amount/weight mismatches, including PO-5.2 payable and PO-4.0 lifecycle weight.
- `on_delivery_freeze`: shipped orders missing `INVENTORY_ON_DELIVERY_COST` balances.
- `business_insides`: missing `BUSINESS_INSIDES_2026-05-31.md` snapshot.
- `cogs_integrity` and `profit_publication_integrity`: one unresolved COGS/publication SKU row, `SUIT-31-TS`.
- `dim_sku_light_alignment`: weight mismatches against the dim-sku-light workbook.

## Execution Shape

Use one write-capable Autonomous_business repair lane, one website deploy/live-proof lane, one read-only launch-day source refresh lane, and one final synthesis lane.

| Agent | Scope | Role | Dependency |
| --- | --- | --- | --- |
| 1 | `Autonomous_business` | strict-gate repair plus cash/SHR/LINE31 stock truth repair | root |
| 2 | `acmewear_web_v2` | isolated website deploy and live tracking proof | root |
| 3 | `Facebook_ads` + `Web_automation` | launch-day Meta/Web/Kaspi context refresh, read-only | root |
| 4 | `Autonomous_business` | final bridge rebuild and `GREEN_EXCEPT_CREATIVE` synthesis | after 1,2,3 |

## Safety Rules

- Do not deploy `acmewear.pro` unless the LINE31 tracking changes can be isolated from unrelated dirty worktree changes.
- If deploy isolation cannot be proven, Agent 2 must stop `YELLOW` with exact blocker and no deploy.
- No Meta campaign publish is authorized in this wave.
- No creative-ready declaration is made in this wave.
- No internal LINE31 Kaspi isolation is authorized in this wave.
- Any production DB or workbook mutation must be backup-first, narrow, evidence-backed, and followed by validator replay.
- If a validator failure is broader than LINE31 launch readiness and cannot be safely repaired in this wave, classify it with a durable acceptance rule or exact retained blocker; do not fake `GREEN`.

## Target Final Gate

The target is:

`Gate: GREEN_EXCEPT_CREATIVE`

This is valid only if:

- strict repo gate is green or all remaining failures are proven unrelated and accepted by the launch-readiness contract;
- website tracking is live-deployed and live-proven, or deploy is not needed because live already matches the reviewed build;
- current cash uses the `800000 KZT` protected reserve and owner-confirmed SHR payment truth;
- LINE31 stock uses April leftovers plus PO1-A arrival exact rebuild;
- launch-day bridge rows distinguish `PRELAUNCH_NOT_APPLICABLE` from genuinely missing metrics;
- internal LINE31 Kaspi noise remains accepted as directional-attribution rule while surfaces stay ON;
- the only retained blocker is creative asset completion plus final Meta publish approval.
