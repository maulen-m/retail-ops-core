# Agent912D / Transport Agent9124 - DIM_SKU_light Parser Repair

Gate target: `GREEN` if focused tests pass and sync dry-run no longer fails on the `DIM_SKU_light` header parser issue. Otherwise `YELLOW`.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos_agent912_operational_source_refresh_c3_split/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT912_OPERATIONAL_SOURCE_REFRESH_C3_SPLIT_20260518_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT912_OPERATIONAL_SOURCE_REFRESH_C3_SPLIT_20260518_STARTERS/04_AGENT_9124__DIM_SKU_LIGHT_PARSER_REPAIR__PARALLEL_ROOT.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_agent911_retained_blocker_repair_wave/agent911d_inbound_workbook_schema_correction_closeout.md`
7. `~/Docs/Oracle/Autonomous_business/2026-05-18/225410_TASK-000_mvos-agent911-yellow-retained-blocker-codecaptain/answer/Code Captain_18.05.2026_23_25_41.md`

## Assignment

Repair the narrow `DIM_SKU_light` header parser issue used by `sync_po_parts_from_inbound_calendar.py` dry-run.

## Scope

Primary write scope:
- `~/Docs/Autonomous_business/scripts/sync_po_parts_from_inbound_calendar.py`
- focused parser tests only.

Do not edit PO money gate or C3 source contract files. You are not alone in the codebase.

## Required Behavior

- write or extend failing tests first;
- support the current `DIM_SKU_light` header variant;
- rerun focused tests;
- rerun sync dry-run enough to prove the failure is no longer the header parser;
- do not mutate workbook;
- do not mutate production DB;
- do not broad-refactor PO sync.

## Required Artifacts

Evidence root:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_agent912_operational_source_refresh_c3_split/agent9124_dim_sku_light_parser_repair_evidence/`

Artifacts:
- `DIM_SKU_LIGHT_PARSER_REPAIR_PLAN.md`;
- `PARSER_TEST_OUTPUT.txt`;
- `SYNC_DRY_RUN_AFTER.txt`;
- command logs;
- closeout.

## Closeout

Write:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_agent912_operational_source_refresh_c3_split/agent9124_dim_sku_light_parser_repair_closeout.md`

The closeout must include:

```text
Gate: <GREEN/YELLOW/RED>
```

State whether Agent9125 can use this parser repair in the copied-temp rerun.
