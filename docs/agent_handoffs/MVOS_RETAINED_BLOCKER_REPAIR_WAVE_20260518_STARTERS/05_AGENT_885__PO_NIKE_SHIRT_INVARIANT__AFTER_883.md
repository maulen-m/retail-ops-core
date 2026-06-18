# Agent885 Starter: PO Nike-Shirt Invariant Analysis

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_retained_blocker_repair_wave/agent885_po_nike_shirt_invariant_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_retained_blocker_repair_wave/agent885_po_nike_shirt_invariant_evidence`

## Bootstrap

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos_retained_blocker_repair_wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos_retained_blocker_repair_wave/ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_retained_blocker_repair_wave/agent883_day_complete_two_row_repair_closeout.md`
7. this starter prompt.

## Assignment

Analyze the retained PO blocker after the day-complete lane:

`CL_NEW-CLO_MEN_NIKE-SHIRT_BLACK: sum(d_size)=9.5726 vs d_sku=10.0000`

Produce:

- `PO_NIKE_SHIRT_INVARIANT_ANALYSIS_AFTER_DAY_COMPLETE.json`
- source extracts/hashes needed to support the analysis
- assigned closeout with a standalone `Gate: <GREEN/YELLOW/RED>` line

Determine whether the `0.4274` delta is:

- source-data mismatch;
- rounding/allocation artifact;
- dashboard regeneration issue;
- still retained blocker.

Do not:

- infer PO green from day-complete repair alone;
- commit PO;
- write production DB/workbook/PO dashboard production truth;
- mutate scheduler/source pointers/Web_automation/Kaspi/API/WebUI/ad platforms/cash/stock/price/owner publication/external systems.

Gate guidance:

- `GREEN` if the invariant route is source-backed and non-mutating.
- `YELLOW` if the PO blocker must remain retained pending source/owner decision.
- `RED` if a protected boundary is violated.
