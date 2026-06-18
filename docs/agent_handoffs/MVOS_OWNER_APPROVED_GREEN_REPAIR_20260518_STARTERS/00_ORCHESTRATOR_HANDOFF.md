# MVOS Owner-Approved Green Repair Starters

Created: `2026-05-18T18:35:00+05:00`

Repo: `~/Docs/Autonomous_business`

Canonical plan:

`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos_owner_approved_green_repair/PLAN.md`

Owner-approved rebaseline closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos-10-out-of-10-contract-execution/ORCHESTRATOR_OWNER_APPROVED_REBASELINE_CLOSEOUT.md`

Starter folder:

`~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_OWNER_APPROVED_GREEN_REPAIR_20260518_STARTERS`

## Launch Order

Agents `901`, `902`, `903`, and `904` may run in parallel from the accepted rebaseline boundary.

Do not launch a synthesis/preflight/Agent 7 lane until all four closeouts are reviewed by the orchestrator.

## Starter Prompts

- `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_OWNER_APPROVED_GREEN_REPAIR_20260518_STARTERS/01_AGENT_901__SOURCE_CASH_PAYMENT__PARALLEL_ROOT.md`
- `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_OWNER_APPROVED_GREEN_REPAIR_20260518_STARTERS/02_AGENT_902__ORDERS_LIFECYCLE_COGS__PARALLEL_ROOT.md`
- `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_OWNER_APPROVED_GREEN_REPAIR_20260518_STARTERS/03_AGENT_903__ADS_TRUTH_MAPPING__PARALLEL_ROOT.md`
- `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_OWNER_APPROVED_GREEN_REPAIR_20260518_STARTERS/04_AGENT_904__PO_STOCK_EXCEPTION__PARALLEL_ROOT.md`

## Copy-Paste Launch Lines

```text
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_OWNER_APPROVED_GREEN_REPAIR_20260518_STARTERS/01_AGENT_901__SOURCE_CASH_PAYMENT__PARALLEL_ROOT.md
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_OWNER_APPROVED_GREEN_REPAIR_20260518_STARTERS/02_AGENT_902__ORDERS_LIFECYCLE_COGS__PARALLEL_ROOT.md
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_OWNER_APPROVED_GREEN_REPAIR_20260518_STARTERS/03_AGENT_903__ADS_TRUTH_MAPPING__PARALLEL_ROOT.md
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_OWNER_APPROVED_GREEN_REPAIR_20260518_STARTERS/04_AGENT_904__PO_STOCK_EXCEPTION__PARALLEL_ROOT.md
```

## Shared Boundary

Use the accepted boundary from the plan:

- `db/app.db` SHA-256: `8d45d928888b0a03b42d8a2e73638a5f0ac30caa82b45943623e8df6433196d3`
- `excel_ui/SALES_KSP_CRM_V3.xlsx` SHA-256: `0dd9da0233fd30607b6f858db2ea7532bc9ec954021f5e9c195814a41d128313`

If the protected production DB or workbook no longer matches this boundary at agent start, the assigned agent must stop `RED` and write a closeout. Do not silently re-baseline.
