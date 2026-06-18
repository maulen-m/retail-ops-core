# Agent 3 - Single-Truth And PO Money Route

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-21_mvos_phase1_bounded_blocker_closure/agent3_single_truth_po_money_route_closeout.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/current/FINAL_10_OUT_OF_10_EXECUTION_PLAN.md`
4. `~/Docs/Autonomous_business/docs/current/CURRENT_BLOCKER_BOARD.tsv`
5. `~/Docs/Autonomous_business/docs/current/CURRENT_GATE_MATRIX.tsv`
6. `~/Docs/Autonomous_business/docs/current/CURRENT_SOURCE_TRUTH_MAP.md`
7. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-21_mvos_phase1_clean_then_blocker_closure/CLEAN_FIRST_BOUNDARY.md`
8. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-21_mvos_phase1_clean_then_blocker_closure/DIRTY_STATE_GROUPS.tsv`
9. this starter prompt

## Mission

Close or precisely route:

- `B006_single_truth_system`
- `B007_single_truth_alignment`
- `B008_po_money_gate`

Do not make PO commitments. The goal is copied-temp diagnosis/proof or exact retained blocker routing.

## Boundary

Read-only and copied-temp only.

Allowed:

- inspect local DB read-only and create copied DBs under `~/Docs/Autonomous_business_agent_handoffs/2026-05-21_mvos_phase1_bounded_blocker_closure/agent3_evidence/`;
- inspect inbound workbook metadata/read-only evidence if needed, without saving or mutating the workbook;
- run copied-temp single-truth, alignment, dashboard, and PO money validators.

Forbidden:

- production DB writes;
- workbook saves/writes;
- PO commitment;
- cash movement;
- stock/price changes;
- implementation edits or `.claude/*` edits.

## Required Output

Write the assigned closeout with:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- exact validator commands and outputs;
- exact single-truth mismatch rows or proof that they are cleared;
- whether PO-4.0 Line61 accepted 23-unit shortage remains correctly separated;
- whether PO money is copied-temp green, retained yellow, or red;
- exact next fix or owner/CodeCaptain request if still blocked.

Use `GREEN` only if copied-temp single-truth system, alignment, and PO money gates pass for declared scope. Use `YELLOW` for retained blockers. Use `RED` for authority conflict or protected-surface drift.
