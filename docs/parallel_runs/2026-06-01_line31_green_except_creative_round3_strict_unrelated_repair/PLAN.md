# LINE31 GREEN_EXCEPT_CREATIVE Round 3 - Strict And Unrelated Failure Repair

Generated: 2026-06-01

## Objective

Move LINE31 countrywide Meta launch-readiness from current `YELLOW` toward `GREEN_EXCEPT_CREATIVE` by clearing the remaining Autonomous Business non-creative blockers, while also adding the owner-requested option 2: repair unrelated broad-suite failures first where they are reproducible, safe, and not a distraction from the LINE31 readiness goal.

Current round-2 synthesis:

`~/Docs/Autonomous_business/exports/validation/line31_green_except_creative_repair_round2_20260601/final_synthesis/FINAL_GREEN_EXCEPT_CREATIVE_MATRIX.md`

## Current Truth

Round 2 result:

- Website/live-proof gate: `GREEN`.
- Autonomous Business strict repo gate: `YELLOW`.
- Final synthesis: `YELLOW`.

The remaining non-creative blockers are in Autonomous Business:

- `validate_params.py --strict` fails on:
  - `on_delivery_freeze`: missing `INVENTORY_ON_DELIVERY_COST` balances for orders `938256969`, `940453925`, `941824782`;
  - `cogs_integrity`: one unresolved production COGS row for `SUIT-31-TS`;
  - `profit_publication_integrity`: blocked by the same unresolved `SUIT-31-TS` COGS row.
- `validate_po_dashboard_invariants.py` separately flags stale stock snapshot freshness: `2026-05-04` versus cutoff `2026-05-31`.
- Previous broad `pytest -q` had unrelated failures and was interrupted after `12 failed, 1000 passed, 1 skipped`.

## Owner Answers And Approvals To Preserve

- Owner fully approves required actions for this implementation lane.
- Cash source: `Cash_Balances` sheet in `~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/Inbound_calendar_V10.002.xlsx`.
- SHR payment timing: what is paid to SHR is paid before the last cash-balance snapshot. The 18th `7000 CNY` payment must count as paid and supplier-paid even though the exchanger receipt screenshot is still pending.
- Protected reserve: only `800000 KZT` is untouchable.
- LINE31 stock: use the exact rebuild from April leftovers plus PO1-A arrival.
- Creative asset URI, thumbnail, and SHA-256 mapping is still in preparation and does not block non-creative implementation work.

## Execution Model

Follow repo protocol: one write-capable integrator only. Analysts run first and write only local evidence/handoff files.

| Agent | Lane | Parallel Group | Write Authority |
|---:|---|---|---|
| 1 | Strict blocker authority scout | root | Read-only repo/DB/workbook/source inspection; local evidence only |
| 2 | Unrelated broad-suite failure triage | root | Read-only repo/DB inspection; local evidence only |
| 3 | Serialized integrator | after_1_2 | Only write-capable lane; may repair code/docs/tests and production DB only under backup/write-gated rules |
| 4 | Final synthesis | after_3 | Evidence packet and closeout only |

## Required Sequence

1. Agents 1 and 2 run in parallel.
2. Agent 3 starts only after Agents 1 and 2 close out.
3. Agent 3 first addresses the owner-requested option 2:
   - reproduce and repair unrelated broad-suite failures that are safe, bounded, and not tied to live external state;
   - explicitly quarantine unrelated failures that are stale-test/environmental/not safe to repair in this lane.
4. Agent 3 then repairs or durably classifies the LINE31 strict blockers.
5. Agent 4 synthesizes whether the repo can honestly claim `GREEN_EXCEPT_CREATIVE`.

## Authorized Surfaces

Authorized if required for this exact objective:

- read-only source inspection across current local evidence;
- copied-temp DB proofs;
- production `db/app.db` write-gated repair for the named strict blockers, only with backup, before/after evidence, validator replay, and rollback instructions;
- code/docs/config/tests updates needed to make validators truthful and durable;
- local evidence generation and closeouts.

Not authorized:

- Meta publish;
- website/Cloudflare deploy;
- internal LINE31 Kaspi campaign isolation or seller-bonus changes;
- Kaspi/API/WebUI/CRM mutations;
- external writes;
- workbook writes unless explicitly needed and backed up by Agent 3 for a named validator failure;
- price changes;
- stock offer changes;
- cash movement;
- supplier payment;
- PO commitment;
- owner publication;
- invented COGS, zeroed missing costs, or hidden publication blockers.

## Required Green Conditions

This can become `GREEN_EXCEPT_CREATIVE` only if:

- `python3 scripts/validate_params.py --strict` passes, or every remaining strict failure has durable launch-accepted authority and is documented transparently;
- `python3 scripts/validate_po_dashboard_invariants.py` passes or its stock freshness warning is durably classified as not blocking LINE31 launch-readiness;
- focused tests for touched areas pass;
- unrelated broad-suite failures are either repaired or explicitly classified as non-blocking with evidence;
- `scripts/check_no_db_tracked.sh`, docs lint, JSON artifacts, and SQLite integrity pass;
- creative mapping and final Meta publish approval are the only remaining blockers.

## Evidence Roots

Round 3 evidence root:

`~/Docs/Autonomous_business/exports/validation/line31_green_except_creative_round3_strict_unrelated_repair_20260601/`

Round 3 handoff folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-06-01_line31_green_except_creative_round3_strict_unrelated_repair/`

Starter folder:

`~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_GREEN_EXCEPT_CREATIVE_ROUND3_STRICT_UNRELATED_20260601_STARTERS/`

## Stop Conditions

Close `YELLOW` if:

- production COGS authority remains insufficient;
- DB write cannot be made safely with rollback;
- unrelated failures are too broad or unsafe to repair in this lane;
- strict validators still fail and no durable launch acceptance exists.

Close `RED` if:

- production DB/workbook is changed without backup;
- unauthorized external/live action occurs;
- evidence is missing or materially contradictory;
- a lane hides unresolved COGS or treats missing cost as zero.
