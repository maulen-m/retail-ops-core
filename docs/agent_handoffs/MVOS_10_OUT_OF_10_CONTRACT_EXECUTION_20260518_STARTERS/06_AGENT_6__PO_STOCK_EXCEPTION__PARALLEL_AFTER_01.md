# Agent 6: PO, Stock, Inbound, Exception Queue, And Retained Blockers

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/contracts/MVOS_10_OUT_OF_10_DECISION_GRADE_ACCEPTANCE_CONTRACT.md`
4. `~/Docs/Autonomous_business/docs/inventory/Master_Inventory_Rules_v9.md`
5. `~/Docs/Autonomous_business/docs/protocol/active/PO_making_logic_v3.md`
6. `~/Docs/Autonomous_business/docs/size_engine_specification.md`
7. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos-10-out-of-10-contract-execution/PLAN.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos-10-out-of-10-contract-execution/agent1_scope_registry_boundary_closeout.md`
9. this assigned starter prompt

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos-10-out-of-10-contract-execution/agent6_po_stock_exception_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos-10-out-of-10-contract-execution/agent6_po_stock_exception_evidence`

## Task

Build read-only or copied-temp evidence for:

- PO, Stock, And Inbound Gate;
- Exception Queue And Retained Blocker Gate.

Produce:

- `PO_STOCK_FRESHNESS_AND_PRODUCTION_READINESS_RERUN.json`
- `STOCK_SNAPSHOT_FRESHNESS_REPORT.json`
- `PO_DASHBOARD_INVARIANTS_REPORT.txt`
- `PO_INBOUND_ACCEPTED_FACTS_MATRIX.tsv`
- `PO_AUTHORITY_BLOCKERS.md`
- `EXCEPTION_QUEUE_STATUS.json`
- `RETAINED_BLOCKER_BOARD.md`
- `RETAINED_BLOCKER_BOARD.json`
- `OWNER_ACTION_LIST.md`

Run where safe:

```bash
python3 scripts/validate_po_dashboard_invariants.py --strict
python3 scripts/validate_inventory_snapshot_freshness.py --strict
python3 scripts/validate_stock_ledger_to_snapshot.py --strict
python3 scripts/validate_po_contract.py --strict
python3 scripts/validate_po_money_gate.py --strict
python3 scripts/validate_exception_queue_db.py --strict
python3 scripts/validate_exceptions_schema.py --strict
python3 scripts/validate_retained_blocker_board.py --strict
```

## Boundary

Read-only or copied-temp only. Do not mutate production DB, protected workbook, stock, PO commitments, supplier payment, cash, source pointers, schedulers, external systems, prices, or owner-publication surfaces.

## Gate Guidance

Use `Gate: GREEN` only if PO/stock/inbound and exception/retained blocker gates pass for the declared scope.

Use `Gate: YELLOW` if stock freshness, PO invariants, inbound facts, exception rows, retained blockers, or owner actions remain.

Use `Gate: RED` if a hidden high-risk exception is found, PO authority is implied, stock is changed, or protected production state drifts.
