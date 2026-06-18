# Agent906 - Stock, PO, And Line61 Shortage Repair

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_option1_next_repair_wave/agent906_stock_po_shortage_repair_closeout.md`

Assigned evidence root:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_option1_next_repair_wave/agent906_stock_po_shortage_repair_evidence`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/protocol/active/PO_making_logic_v3.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos_option1_next_repair_wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_OPTION1_NEXT_REPAIR_WAVE_20260518_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_OPTION1_NEXT_REPAIR_WAVE_20260518_STARTERS/02_AGENT_906__STOCK_PO_SHORTAGE__PARALLEL_ROOT.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_owner_approved_green_repair/agent904_po_stock_exception_repair_closeout.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_owner_approved_green_repair/ORCHESTRATOR_REVIEW_AFTER_901_904.md`

## Mission

Repair or sharply classify the stock/PO blockers from Agent904 on a copied DB only.

Owner truth to preserve:

- PO-4.0 Line61 actual received: `92`;
- ordered/cargo: `115`;
- real shortage: `23`;
- size shortages: XL `7`, 2XL `5`, 3XL `6`, 4XL `5`;
- all `9` high-stock exceptions remain visible retained blockers.

Do not mutate the workbook to hide the shortage. Do not mutate production stock, production DB, PO commitment, supplier payment, scheduler, or external systems.

## Required Work

1. Verify accepted DB/workbook boundary at start.
2. Copy `db/app.db` to the evidence folder.
3. Reproduce Agent904 failures:
   - `validate_po_money_gate.py --db <copy> --as-of 2026-05-18 --json`;
   - `validate_po_dashboard_invariants.py --db <copy>`;
   - source freshness / stock snapshot freshness diagnostics.
4. Inventory local stock truth routes:
   - latest `fact_inventory_snapshot_size`;
   - `stock_ledger`;
   - local stock snapshot workbooks or inbound workbook columns if already present;
   - existing evidence from recent agents.
5. Attempt a copied-temp stock snapshot refresh or rebuild only if an existing repo command supports copied DB target and dry-run/apply-to-copy semantics.
6. Reconcile ledger-to-snapshot on the copied DB and record mismatches.
7. Produce a Line61 shortage contract/proof artifact that keeps the real `23` shortage visible and prevents treating the shortage as missing stock.
8. Rerun PO money/dashboard validators on the copied DB.
9. Write closeout with `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.

## Suggested Commands

```bash
python3 scripts/validate_po_money_gate.py --db <copied-db> --as-of 2026-05-18 --json
python3 scripts/validate_po_dashboard_invariants.py --db <copied-db>
python3 scripts/rebuild_snapshot.py --db <copied-db> --date 2026-05-18 --compare --mode auto
python3 scripts/rebuild_snapshot.py --db <copied-db> --date 2026-05-18 --mode auto --apply
python3 scripts/validate_exception_queue_db.py --db <copied-db> --strict --json
```

Only run `--apply` against the copied DB. If a command appears to target production by default, stop and use explicit `--db <copied-db>`.

## Gate Rules

- `GREEN`: stock snapshot freshness/ledger proof and PO money/dashboard gates are green on the copied DB for the declared scope, with the Line61 shortage and 9 high-stock blockers handled visibly.
- `YELLOW`: source route or validator support remains incomplete, but blockers are specific and visible.
- `RED`: protected boundary drift, workbook mutation, production mutation, hidden shortage/blocker, or false green.

## Non-Authorization

This task does not authorize production DB writes, workbook writes, scheduler changes, external writes, stock changes, PO commitment, supplier payment, cash movement, price changes, owner publication, or production apply.
