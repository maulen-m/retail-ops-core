# Agent 7 - Serialized Copied-Temp Integrator

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-21_mvos_phase2_owner_confirmed_blocker_closure/agent7_serialized_copied_temp_integrator_closeout.md`

Assigned evidence root:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-21_mvos_phase2_owner_confirmed_blocker_closure/agent7_evidence/`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/current/FINAL_10_OUT_OF_10_EXECUTION_PLAN.md`
4. `~/Docs/Autonomous_business/docs/current/CURRENT_BLOCKER_BOARD.tsv`
5. `~/Docs/Autonomous_business/docs/current/CURRENT_GATE_MATRIX.tsv`
6. `~/Docs/Autonomous_business/docs/current/CURRENT_SOURCE_TRUTH_MAP.md`
7. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-21_mvos_phase1_clean_then_blocker_closure/PHASE1_ORCHESTRATOR_REVIEW.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-21_mvos_phase1_bounded_blocker_closure/agent6_phase1_synthesis_closeout.md`
9. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-21_mvos_phase2_owner_confirmed_blocker_closure/PHASE2_OWNER_CONFIRMATION_BOUNDARY.md`
10. this starter prompt

Read dependency closeouts as needed:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-21_mvos_phase1_bounded_blocker_closure/agent1_physical_stock_po_route_closeout.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-21_mvos_phase1_bounded_blocker_closure/agent2_order_sales_identity_route_closeout.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-21_mvos_phase1_bounded_blocker_closure/agent3_single_truth_po_money_route_closeout.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-21_mvos_phase1_bounded_blocker_closure/agent4_cashflow_freshness_route_closeout.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-21_mvos_phase1_bounded_blocker_closure/agent5_ads_truth_route_closeout.md`

## Mission

Run the next continuous non-production MVOS blocker-closure phase as one serialized copied-temp integration proof.

The goal is not to declare production success. The goal is to produce the strongest honest copied-temp proof board possible after the new owner confirmation, while keeping every retained blocker visible.

## Owner Truth To Apply In Copied DB Only

Treat this Human Owner confirmation as authoritative for copied-temp proof planning only:

```text
UNIVERSAL offer 132822924_328581041
Product id MTE3MDQ5MjU1, decoded product code 117049255
Name: Леггинсы PRO COMBAT 2010 белый XL / Леггинсы PRO COMBAT белый
Category: Мужское термобелье
Candidate SKU family: CL_NEW-CLO_MEN_LEG_WHITE
Price seen: 1500 KZT
Warehouse: 30000001_PP1
```

Also treat this as current owner truth:

```text
No fresher physical stock data exists than the last physical stock source already used.
```

## Hard Boundary

Allowed:

- read local repo evidence and read-only local handoffs;
- read `~/Docs/Web_automation` read-only if needed for local source context;
- create copied DBs and local evidence under the assigned evidence root;
- materialize copied-temp rows into copied DBs only;
- apply the owner-confirmed Universal identity into copied DB only;
- update local evidence, route, proof-board, and closeout files;
- run validators and focused tests against copied DBs or read-only repo state.

Forbidden:

- production DB writes;
- workbook writes;
- source-pointer writes;
- scheduler, LaunchAgent, or cron changes;
- Web_automation writes;
- Kaspi/API/WebUI mutations;
- external writes;
- ad-platform writes, ad spend, bid, budget, or campaign changes;
- stock changes;
- price changes;
- cash movement;
- supplier payment;
- PO commitment;
- owner publication;
- production preflight;
- production apply.

## Required Sequence

1. Create the assigned evidence root.
2. Record boundary evidence:
   - current `db/app.db` SHA-256;
   - copied DB SHA-256 after copy;
   - `PRAGMA integrity_check` on the copied DB;
   - protected-surface baseline evidence sufficient to prove no production DB/workbook/scheduler/external mutation.
3. Create one integrated copied DB from current `~/Docs/Autonomous_business/db/app.db`.
4. Reapply the Agent 4 cashflow copied-temp route if reproducible from evidence/commands, then rerun relevant cashflow validators against the copied DB.
5. Apply Agent 2 order-entry entry-required recovery as copied-temp evidence only. Keep no-real-entry rows retained unless an accepted local contract proves they can be handled without inventing order entries.
6. Resolve Universal offer `132822924_328581041` in copied DB only using owner-confirmed identity:
   - verify active `dim_sku_size` rows for `sku_key=CL_NEW-CLO_MEN_LEG_WHITE` and `my_size=XL`;
   - choose the validator-compatible canonical `sku_id` with evidence;
   - do not use stale inactive no-size rows without documenting why the validator accepts them;
   - write a small evidence note explaining the exact row update/upsert made in the copied DB.
7. Materialize any already-proven STOREB `sku_identity` evidence only if it is source-backed and already local; do not invent missing identity.
8. Run strict sales rebuild/order-entry freshness validators against the copied DB and capture stdout/stderr.
9. Run the Agent 3 single-truth, inbound, alignment, and PO-money copied-temp route if reproducible. Keep the Line61 shortage contract limited to the exact accepted `23`-unit shortage truth.
10. Preserve physical stock blockers as retained because no fresher physical stock source exists. Do not promote offer availability to physical stock truth.
11. Preserve ads blockers honestly unless local source packets can be materialized into the copied DB without zeroing STOREB retained positive spend. STOREB retained positive spend `3837.32 KZT` must remain visible if not fully materialized.
12. Rerun the most relevant gates from `CURRENT_GATE_MATRIX.tsv`, especially source freshness, policy gates, order-entry freshness, strict sales rebuild, single-truth system/alignment, PO-money, COGS/drift, and write-side gating.
13. Produce:
   - `FULL_MVOS_COPIED_TEMP_PROOF_BOARD.json`
   - `FULL_MVOS_COPIED_TEMP_PROOF_BOARD.md`
   - `VALIDATOR_EXIT_MATRIX.tsv`
   - `RETAINED_BLOCKER_BOARD.md`
   - `COPIED_DB_BOUNDARY_SHA256.tsv`
   - the assigned closeout.

## Gate Rules

Use `GREEN` only if:

- all declared copied-temp validators pass;
- all retained blockers are outside the declared proof claim and explicitly visible;
- protected surfaces remain unchanged;
- no production/external/protected write happened.

Use `YELLOW` if:

- any copied-temp validator still fails;
- retained blockers remain inside the declared proof claim;
- source freshness remains stale;
- physical stock, ads, order status, STOREB identity, workbook anchor, single-truth, PO money, or drift blockers still block 10/10 readiness.

Use `RED` if:

- a protected surface was mutated;
- production DB/workbook/source-pointer/scheduler/external write occurred;
- owner confirmation contradicts source evidence;
- the copied-temp route cannot be audited.

## Required Closeout Content

The closeout must include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- exact copied DB path and SHA;
- protected-surface before/after statement;
- exact Universal mapping decision and copied DB SQL/update evidence;
- validator matrix with commands, exit codes, and artifact paths;
- blockers closed, partially closed, retained, and newly discovered;
- whether CodeCaptain review is needed next and why;
- one exact next action for the Main Orchestrator.

Do not call the business system production-ready. Do not ask for production apply. Do not ask for owner publication.
