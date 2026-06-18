# MVOS Option 1 Next Repair Wave Starters

Created: `2026-05-18T19:07:35+05:00`

Repo: `~/Docs/Autonomous_business`

Canonical plan:

`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos_option1_next_repair_wave/PLAN.md`

Starter folder:

`~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_OPTION1_NEXT_REPAIR_WAVE_20260518_STARTERS`

Dependency review:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_owner_approved_green_repair/ORCHESTRATOR_REVIEW_AFTER_901_904.md`

Owner Q&A completion audit:

`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos_owner_approved_green_repair/OWNER_QA_COMPLETION_AUDIT.md`

## Launch Order

Launch now in parallel:

- Agent905
- Agent906
- Agent907

Do not launch Agent908 until the orchestrator has reviewed all three root closeouts.

## Starter Prompts

- `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_OPTION1_NEXT_REPAIR_WAVE_20260518_STARTERS/01_AGENT_905__ORDER_ENTRY_SOURCE_HIERARCHY__PARALLEL_ROOT.md`
- `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_OPTION1_NEXT_REPAIR_WAVE_20260518_STARTERS/02_AGENT_906__STOCK_PO_SHORTAGE__PARALLEL_ROOT.md`
- `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_OPTION1_NEXT_REPAIR_WAVE_20260518_STARTERS/03_AGENT_907__CASHFLOW_SOURCE_FRESHNESS__PARALLEL_ROOT.md`
- `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_OPTION1_NEXT_REPAIR_WAVE_20260518_STARTERS/04_AGENT_908__COMBINED_SYNTHESIS__AFTER_905_906_907.md`

## Launch Lines

```text
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_OPTION1_NEXT_REPAIR_WAVE_20260518_STARTERS/01_AGENT_905__ORDER_ENTRY_SOURCE_HIERARCHY__PARALLEL_ROOT.md
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_OPTION1_NEXT_REPAIR_WAVE_20260518_STARTERS/02_AGENT_906__STOCK_PO_SHORTAGE__PARALLEL_ROOT.md
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_OPTION1_NEXT_REPAIR_WAVE_20260518_STARTERS/03_AGENT_907__CASHFLOW_SOURCE_FRESHNESS__PARALLEL_ROOT.md
```

Gated later:

```text
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_OPTION1_NEXT_REPAIR_WAVE_20260518_STARTERS/04_AGENT_908__COMBINED_SYNTHESIS__AFTER_905_906_907.md
```

## Shared Boundary

- `db/app.db` SHA-256: `8d45d928888b0a03b42d8a2e73638a5f0ac30caa82b45943623e8df6433196d3`
- `excel_ui/SALES_KSP_CRM_V3.xlsx` SHA-256: `0dd9da0233fd30607b6f858db2ea7532bc9ec954021f5e9c195814a41d128313`

If the protected production DB or workbook no longer matches this boundary at agent start, the assigned agent must stop `RED`.
