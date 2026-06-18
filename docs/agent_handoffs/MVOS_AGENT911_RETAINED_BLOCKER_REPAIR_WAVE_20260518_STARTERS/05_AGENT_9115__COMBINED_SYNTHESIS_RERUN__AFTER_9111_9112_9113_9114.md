# Agent911E / Transport Agent9115 - Combined Synthesis Rerun

Gate target: `GREEN_COPIED_TEMP_PROOF_CANDIDATE` only if validators pass. Otherwise `YELLOW_RETAINED_BLOCKER_BOARD_PROOF`.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos_agent911_retained_blocker_repair_wave/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT911_RETAINED_BLOCKER_REPAIR_WAVE_20260518_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT911_RETAINED_BLOCKER_REPAIR_WAVE_20260518_STARTERS/05_AGENT_9115__COMBINED_SYNTHESIS_RERUN__AFTER_9111_9112_9113_9114.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_agent911_retained_blocker_repair_wave/agent911a_storeb_header_only_webui_api_fetch_closeout.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_agent911_retained_blocker_repair_wave/agent911b_ab_operational_truth_source_freshness_closeout.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_agent911_retained_blocker_repair_wave/agent911c_stock_po_retained_blocker_route_closeout.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_agent911_retained_blocker_repair_wave/agent911d_inbound_workbook_schema_correction_closeout.md`
10. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos_agent911_retained_blocker_repair_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT911_ROOT.md`

## Assignment

Run one final combined copied-temp rerun after Agents911A-D close out and the orchestrator confirms their gates.

Orchestrator confirmation:

- Agent9111 is accepted as `GREEN` copied-temp input for the 15 STOREB identity-bearing API rows.
- Agent9114 is accepted as `GREEN` local parser/schema correction input for migrated `To_pay_* (live)` workbook labels.
- Agent9112 remains `YELLOW`; do not clear `src_ab_db_operational_truth` unless validators truly pass.
- Agent9113 remains `YELLOW`; do not clear stock/PO readiness without real fresh source evidence.

## Required Work

1. Verify all four dependency closeouts exist.
2. Verify protected DB/workbook boundary.
3. Copy production DB to a new evidence folder.
4. Apply only dependency-approved copied-temp inputs.
5. Run the Agent910 validator matrix plus any new focused validators from Agent911D.
6. Produce:
   - proof board;
   - validator exit matrix;
   - retained blocker matrix;
   - CodeCaptain packet recommendation if still yellow.

## Outputs

Closeout path:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_agent911_retained_blocker_repair_wave/agent911e_combined_synthesis_rerun_closeout.md`

Evidence root:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_agent911_retained_blocker_repair_wave/agent911e_combined_synthesis_rerun_evidence`

Required artifacts:

- `PROOF_BOARD.json`
- `PROOF_BOARD.md`
- `VALIDATOR_EXIT_MATRIX.tsv`
- `RETAINED_BLOCKER_MATRIX.tsv`
- `CODECAPTAIN_PACKET_RECOMMENDATION.md`
- boundary hashes and DB integrity outputs

## Stoplines

- Do not run until Agents911A-D closeouts exist and are reviewed.
- Do not claim green if any required validator fails.
- Do not production-apply anything.
