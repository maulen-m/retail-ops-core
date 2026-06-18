# Agent912C / Transport Agent9123 - PO Line61 Accepted Shortage Classification

Gate target: `GREEN` if the exact Line61 shortage is classified without greening unrelated PO failures. Otherwise `YELLOW`.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos_agent912_operational_source_refresh_c3_split/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT912_OPERATIONAL_SOURCE_REFRESH_C3_SPLIT_20260518_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT912_OPERATIONAL_SOURCE_REFRESH_C3_SPLIT_20260518_STARTERS/03_AGENT_9123__PO_LINE61_ACCEPTED_SHORTAGE__PARALLEL_ROOT.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos_agent911_retained_blocker_repair_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT9115.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_agent911_retained_blocker_repair_wave/agent911c_stock_po_retained_blocker_route_closeout.md`
8. `~/Docs/Oracle/Autonomous_business/2026-05-18/225410_TASK-000_mvos-agent911-yellow-retained-blocker-codecaptain/answer/Code Captain_18.05.2026_23_25_41.md`

## Assignment

Add a narrow accepted-shortage classification for the exact PO-4.0 Line61 `23` delta.

## Scope

Primary write scope:
- PO accepted-shortage contract docs;
- focused PO money gate code/tests only if required.

Do not edit C3 source split files or DIM parser files. You are not alone in the codebase.

## Accepted Facts

Classification id:

`PO_ACCEPTED_REAL_SHORTAGE_LINE61_2026_05_OWNER_CONFIRMED`

Facts:
- ordered/cargo `115`;
- actual received `92`;
- shortage `23`;
- XL `7`;
- 2XL `5`;
- 3XL `6`;
- 4XL `5`.

## Required Behavior

- remove the exact Line61 `23` delta from "unknown mismatch";
- do not make PO money gate green by this alone;
- keep `inbound_sheet_consistency`, `single_truth_system`, `cogs_integrity`, and `single_truth_alignment` failures visible unless independently fixed;
- do not mutate workbook, production DB, PO commitments, stock, or prices.

## Required Artifacts

Evidence root:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_agent912_operational_source_refresh_c3_split/agent9123_po_line61_accepted_shortage_evidence/`

Artifacts:
- `PO_LINE61_ACCEPTED_SHORTAGE_CLASSIFICATION.md`;
- `PO_MONEY_GATE_BEFORE_AFTER.tsv`;
- focused test output if code changed;
- copied-temp validator output if runnable;
- closeout.

## Closeout

Write:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_agent912_operational_source_refresh_c3_split/agent9123_po_line61_accepted_shortage_closeout.md`

The closeout must include:

```text
Gate: <GREEN/YELLOW/RED>
```

State whether Agent9125 can use the classification in the copied-temp rerun.
