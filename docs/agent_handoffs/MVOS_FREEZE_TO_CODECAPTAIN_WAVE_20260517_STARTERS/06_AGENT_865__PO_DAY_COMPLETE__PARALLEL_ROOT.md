# Agent865 Starter: PO And Day-Complete Route

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_freeze_to_codecaptain_wave/agent865_po_day_complete_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business/exports/validation/mvos_freeze_to_codecaptain_wave/20260517_183241/agent865_po_day_complete`

## Bootstrap

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/protocol/active/PO_making_logic_v3.md`
5. `~/Docs/Autonomous_business/docs/size_engine_specification.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-17_mvos_freeze_to_codecaptain_wave/PLAN.md`
7. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-17_mvos_freeze_to_codecaptain_wave/ORCHESTRATOR_HANDOFF.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_agent846_yellow_repair_wave/agent859_synthesis_copied_temp_rerun_closeout.md`

## Assignment

Resolve or narrow PO dashboard/day-complete blockers.

Known blockers:

- `CL_NEW-CLO_MEN_NIKE-SHIRT_BLACK`: `sum(d_size)=9.5726` vs `d_sku=10.0000`
- day-complete gate failed because sizes were pending during Agent859
- `2026-05-17` day-complete had `8797` eligible orders and `74` violations in Agent859 proof

Current context:

- today's shipping and Telegram bundle sending are complete;
- all business automations are now stopped again.

Do:

- Run read-only validators for PO dashboard invariants and day-complete against current production inputs.
- If a copied-temp DB/workbook copy is needed for diagnostics, keep it inside your assigned evidence folder.
- Determine whether blockers are resolved by completed size entry, still true, or require a reviewed contract.
- Build a precise PO/day-complete source-decision table for Agent867.

Do not:

- write the workbook;
- mutate production DB;
- run schedulers or Google board jobs;
- change stock or PO commitments.

Closeout must include:

- standalone `Gate: <GREEN/YELLOW/RED>` line;
- validator command outputs;
- row-level PO/day-complete blocker status;
- exact next action if still blocked.
