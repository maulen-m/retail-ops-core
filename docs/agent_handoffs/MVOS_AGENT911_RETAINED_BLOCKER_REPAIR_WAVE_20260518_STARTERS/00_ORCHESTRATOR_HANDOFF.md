# MVOS Agent911 Retained-Blocker Repair Wave Starters

Created: `2026-05-18T22:02:03+05:00`

Repo: `~/Docs/Autonomous_business`

Canonical plan:

`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos_agent911_retained_blocker_repair_wave/PLAN.md`

Starter folder:

`~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT911_RETAINED_BLOCKER_REPAIR_WAVE_20260518_STARTERS`

Dependency review:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_option1_next_repair_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT910.md`

Agent910 closeout:

`~/Docs/Autonomous_business/exports/validation/mvos_option1_next_repair_wave/agent910_copied_temp_contract_proof/AGENT910_COPIED_TEMP_CONTRACT_PROOF_CLOSEOUT.md`

Owner overlay:

`~/Docs/Autonomous_business/docs/contracts/mvos_source_contracts/OWNER_QA_PRIORITY_20260518_RETAINED_BLOCKERS.md`

## Launch Order

Launch now in parallel:

- Agent911A
- Agent911B
- Agent911C
- Agent911D

Do not launch Agent911E until the orchestrator has reviewed all four root closeouts.

## Starter Prompts

- `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT911_RETAINED_BLOCKER_REPAIR_WAVE_20260518_STARTERS/01_AGENT_9111__STOREB_HEADER_ONLY_WEBUI_API_FETCH__PARALLEL_ROOT.md`
- `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT911_RETAINED_BLOCKER_REPAIR_WAVE_20260518_STARTERS/02_AGENT_9112__AB_OPERATIONAL_TRUTH_SOURCE_FRESHNESS__PARALLEL_ROOT.md`
- `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT911_RETAINED_BLOCKER_REPAIR_WAVE_20260518_STARTERS/03_AGENT_9113__STOCK_PO_RETAINED_BLOCKER_ROUTE__PARALLEL_ROOT.md`
- `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT911_RETAINED_BLOCKER_REPAIR_WAVE_20260518_STARTERS/04_AGENT_9114__INBOUND_WORKBOOK_SCHEMA_CORRECTION__PARALLEL_ROOT_SERIALIZED_CODE.md`
- `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT911_RETAINED_BLOCKER_REPAIR_WAVE_20260518_STARTERS/05_AGENT_9115__COMBINED_SYNTHESIS_RERUN__AFTER_9111_9112_9113_9114.md`

## Launch Lines

```text
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT911_RETAINED_BLOCKER_REPAIR_WAVE_20260518_STARTERS/01_AGENT_9111__STOREB_HEADER_ONLY_WEBUI_API_FETCH__PARALLEL_ROOT.md
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT911_RETAINED_BLOCKER_REPAIR_WAVE_20260518_STARTERS/02_AGENT_9112__AB_OPERATIONAL_TRUTH_SOURCE_FRESHNESS__PARALLEL_ROOT.md
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT911_RETAINED_BLOCKER_REPAIR_WAVE_20260518_STARTERS/03_AGENT_9113__STOCK_PO_RETAINED_BLOCKER_ROUTE__PARALLEL_ROOT.md
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT911_RETAINED_BLOCKER_REPAIR_WAVE_20260518_STARTERS/04_AGENT_9114__INBOUND_WORKBOOK_SCHEMA_CORRECTION__PARALLEL_ROOT_SERIALIZED_CODE.md
```

Gated later:

```text
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT911_RETAINED_BLOCKER_REPAIR_WAVE_20260518_STARTERS/05_AGENT_9115__COMBINED_SYNTHESIS_RERUN__AFTER_9111_9112_9113_9114.md
```

## Shared Boundary

- `db/app.db` SHA-256: `8d45d928888b0a03b42d8a2e73638a5f0ac30caa82b45943623e8df6433196d3`
- `excel_ui/SALES_KSP_CRM_V3.xlsx` SHA-256: `0dd9da0233fd30607b6f858db2ea7532bc9ec954021f5e9c195814a41d128313`

If the protected production DB or workbook no longer matches this boundary at agent start, the assigned agent must stop `RED`.
