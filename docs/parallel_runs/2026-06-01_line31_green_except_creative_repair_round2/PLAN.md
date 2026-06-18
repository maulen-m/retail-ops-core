# LINE31 Green Except Creative Repair Round 2

Generated: 2026-06-01

## Objective

Move the LINE31 countrywide Meta launch-readiness state from the current `YELLOW` toward `GREEN_EXCEPT_CREATIVE`.

The prior final synthesis at:

`~/Docs/Autonomous_business/exports/validation/line31_green_except_creative_repair_20260601/final_synthesis/FINAL_GREEN_EXCEPT_CREATIVE_MATRIX.md`

proved that these gates are already acceptable for this launch-readiness decision:

- Cash/SHR reserve: `GREEN`
- LINE31 stock: `GREEN`
- Launch-day source refresh: `GREEN`
- Internal-Kaspi attribution rule: `GREEN_ACCEPTED_RULE`

The only remaining non-creative blockers are:

- NB1: Autonomous_business strict repo gate retained failures.
- NB2: acmewear.pro LINE31 website tracking is not production live-proof green because Cloudflare deploy auth failed.

Creative assets remain in preparation and are allowed to remain blocked after the non-creative blockers are green.

## Owner Facts To Preserve

- Current cash and SHR payment timing source is the `Cash_Balances` sheet plus SHR payment log in:
  `~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/Inbound_calendar_V10.002.xlsx`
- The 18th `7000 CNY` SHR payment counts as paid and supplier-paid, even though the receipt screenshot is pending from the exchanger.
- Protected reserve is `800000 KZT` untouchable.
- LINE31 physical/sellable stock uses the exact rebuild from April leftovers plus PO1-A arrival.
- Creative video assets are still in preparation and must not be treated as a blocker for continuing non-creative readiness work.

## Execution Model

Run two root agents in parallel, then synthesize:

| Agent | Lane | Parallel Group | Write Authority |
|---|---|---|---|
| Agent 1 | Autonomous_business strict-gate retained blocker repair | root | Serialized repo/DB/workbook writes only for named strict blockers, with backup and validators |
| Agent 2 | acmewear_web_v2 Cloudflare deploy auth + LINE31 live tracking proof | root | External Cloudflare website deploy only for the already-validated LINE31 tracking patch |
| Agent 3 | Final synthesis | after_1_2 | Evidence files and closeout only |

No Meta publish is authorized in this round.

## Boundaries

Authorized if required for this exact objective:

- production `db/app.db` write-gated repair for the named strict-gate blockers;
- production workbook repair only if necessary to clear the named PO/single-truth blockers, with backup and before/after evidence;
- repo docs/config/tests/scripts required to make the validators truthful and durable;
- Cloudflare/acmewear.pro website deploy of the already-validated LINE31 tracking patch;
- local evidence generation and closeouts.

Not authorized:

- Meta campaign publish;
- internal LINE31 Kaspi campaign isolation or seller-bonus changes;
- Kaspi/WebUI/API/CRM mutations unrelated to the named blockers;
- price changes;
- stock offer changes;
- cash movement;
- supplier payment;
- PO commitment;
- owner publication;
- broad refactors or cleanup outside the named blockers.

## Required Green Conditions

The round can become `GREEN_EXCEPT_CREATIVE` only if:

- `python3 scripts/validate_params.py --strict` is green, or every retained failure is durably accepted for LINE31 launch-readiness by a repo-owned contract and the synthesis documents that acceptance.
- acmewear.pro production live proof shows LINE31 tracking preserves the required UTM fields, especially `utm_placement` and `utm_id`, through root runtime config and `/go/:color` redirects.
- cash/SHR and LINE31 stock stay green.
- launch-day source refresh remains green or prelaunch-not-applicable.
- creative mapping plus final Meta publish approval are the only remaining blockers.

## Evidence Roots

Prior round:

- `~/Docs/Autonomous_business/exports/validation/line31_green_except_creative_repair_20260601/`
- `~/Docs/Autonomous_business_agent_handoffs/2026-06-01_line31_green_except_creative_repair/`

This round:

- `~/Docs/Autonomous_business/exports/validation/line31_green_except_creative_repair_round2_20260601/`
- `~/Docs/Autonomous_business_agent_handoffs/2026-06-01_line31_green_except_creative_repair_round2/`

## Stop Conditions

Stop and close `YELLOW` if:

- a validator remains non-green and cannot be durably classified in this lane;
- Cloudflare auth still cannot deploy the patch;
- production live proof still fails required UTM preservation;
- any write path lacks backup, explicit apply gate, or rollback instructions.

Close `RED` if:

- an unauthorized external mutation occurs;
- production DB/workbook is changed without backup;
- live Meta publish happens;
- evidence is missing or materially contradictory.
