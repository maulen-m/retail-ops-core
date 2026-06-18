# Agent 3: Orders, Sales, Lifecycle, And COGS Gate Proof

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/contracts/MVOS_10_OUT_OF_10_DECISION_GRADE_ACCEPTANCE_CONTRACT.md`
4. `~/Docs/Autonomous_business/docs/inventory/Sales_Data_Model_V16.md`
5. `~/Docs/Autonomous_business/docs/validation/WEBUI_ARCHIVE_SINGLE_TRUTH_CONTRACT.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos-10-out-of-10-contract-execution/PLAN.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos-10-out-of-10-contract-execution/agent1_scope_registry_boundary_closeout.md`
8. this assigned starter prompt

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos-10-out-of-10-contract-execution/agent3_orders_sales_lifecycle_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos-10-out-of-10-contract-execution/agent3_orders_sales_lifecycle_evidence`

## Task

Build read-only or copied-temp evidence for the Orders, Sales, And Lifecycle Gate.

Produce:

- `ORDER_ENTRY_FRESHNESS_REPORT.json`
- `DAY_COMPLETE_REPORT.json`
- `STATUS_LEDGER_SCOPE_DECLARATION.md`
- `LIFECYCLE_RESIDUAL_BLOCKER_MATRIX.tsv`
- `SALES_FACT_IDENTITY_QUARANTINE_REPORT.tsv`
- `COGS_COMPLETENESS_GATE_NOTES.md`

Run where safe:

```bash
python3 scripts/validate_order_entries_freshness.py --strict
python3 scripts/validate_day_complete.py --strict
python3 scripts/validate_status_ledger_continuity.py --strict
python3 scripts/validate_sales_truth_consumers.py --strict
python3 scripts/validate_cogs_completeness_by_month.py --strict
```

If scripts do not support copied DB targeting, document that limitation instead of forcing production claims.

## Boundary

Read-only or copied-temp only. Do not edit source contracts, production DB, protected workbook, schedulers, external systems, or owner-publication surfaces.

## Gate Guidance

Use `Gate: GREEN` only if order rows, sales facts, lifecycle/status, cancellations, and COGS completeness pass for the declared scope.

Use `Gate: YELLOW` if retained lifecycle, day-complete, identity, cancellation, or COGS blockers remain.

Use `Gate: RED` if lifecycle truth is invented, status source classes are mixed without contract, or protected production state changes.
