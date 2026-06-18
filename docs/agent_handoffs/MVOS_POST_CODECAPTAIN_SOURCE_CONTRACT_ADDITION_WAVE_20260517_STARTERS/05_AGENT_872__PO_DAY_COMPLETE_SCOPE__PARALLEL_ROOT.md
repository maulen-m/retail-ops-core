# Agent872 Starter: PO And Day-Complete Scope

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_post_codecaptain_source_contract_addition_wave/agent872_po_day_complete_scope_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business/exports/validation/mvos_post_codecaptain_source_contract_addition_wave/20260517_210554/agent872_po_day_complete_scope`

## Bootstrap

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/inventory/Master_Inventory_Rules_v9.md`
5. `~/Docs/Autonomous_business/docs/protocol/active/PO_making_logic_v3.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-17_mvos_post_codecaptain_source_contract_addition_wave/PLAN.md`
7. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-17_mvos_post_codecaptain_source_contract_addition_wave/ORCHESTRATOR_HANDOFF.md`
8. `~/Docs/Oracle/Autonomous_business/2026-05-17/190620_TASK-000_mvos-freeze-to-codecaptain-current-boundary-yellow-review/answer/Code Captain - Branch_17.05.2026_20_58_49.md`
9. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-17_mvos_freeze_to_codecaptain_wave/AGENT867_SYNTHESIS_FOR_CODECAPTAIN.md`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_freeze_to_codecaptain_wave/agent867_synthesis_codecaptain_packet_closeout.md`
11. this starter prompt.

## Assignment

Resolve or scope the PO/day-complete blockers CodeCaptain retained.

Known retained blockers:

- day-complete: `8797` eligible orders, `44` violations;
- PO dashboard: `CL_NEW-CLO_MEN_NIKE-SHIRT_BLACK` has `sum(d_size)=9.5726` vs `d_sku=10.0000`.

You may read repo docs, copied DBs, derived exports, and local evidence. You may write only to your assigned evidence folder and assigned closeout.

Do:

- Reproduce the current day-complete and PO invariant failures on read-only or copied-temp surfaces.
- Classify whether each blocker prevents copied-temp MVOS GREEN, production preflight, owner publication, or PO commitment.
- If a copied-temp-safe correction exists without production mutation, prove it locally in assigned evidence.
- If not, draft a scoped retained-blocker contract that keeps this lane YELLOW and prevents false production/PO claims.
- Run `validate_day_complete.py --cutoff-date 2026-05-17` and `validate_po_dashboard_invariants.py` where safe.

Do not:

- commit PO, supplier payment, cash movement, stock change, price change, production DB write, workbook write, or scheduler mutation;
- hide validator failures;
- claim PO/day-complete GREEN while validators fail.

Closeout must include:

- standalone `Gate: <GREEN/YELLOW/RED>` line;
- validator commands and outputs;
- blocker classification;
- copied-temp correction or scope contract;
- remaining CodeCaptain questions, if any.
