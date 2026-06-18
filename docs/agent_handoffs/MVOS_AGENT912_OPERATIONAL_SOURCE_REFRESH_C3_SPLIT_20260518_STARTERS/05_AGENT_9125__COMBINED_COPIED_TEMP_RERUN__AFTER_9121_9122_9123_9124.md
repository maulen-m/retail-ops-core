# Agent912E / Transport Agent9125 - Combined Copied-Temp Rerun

Gate target: `COPIED_TEMP_GREEN_PROOF` only if all required validators pass. Otherwise `YELLOW_RETAINED_BLOCKER_BOARD_PROOF`.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos_agent912_operational_source_refresh_c3_split/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT912_OPERATIONAL_SOURCE_REFRESH_C3_SPLIT_20260518_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT912_OPERATIONAL_SOURCE_REFRESH_C3_SPLIT_20260518_STARTERS/05_AGENT_9125__COMBINED_COPIED_TEMP_RERUN__AFTER_9121_9122_9123_9124.md`
6. Agent9121 closeout: `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_agent912_operational_source_refresh_c3_split/agent9121_operational_source_refresh_packet_closeout.md`
7. Agent9122 closeout: `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_agent912_operational_source_refresh_c3_split/agent9122_c3_source_contract_split_closeout.md`
8. Agent9123 closeout: `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_agent912_operational_source_refresh_c3_split/agent9123_po_line61_accepted_shortage_closeout.md`
9. Agent9124 closeout: `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_agent912_operational_source_refresh_c3_split/agent9124_dim_sku_light_parser_repair_closeout.md`
10. Orchestrator root review: `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos_agent912_operational_source_refresh_c3_split/ORCHESTRATOR_REVIEW_AFTER_AGENT912_ROOT.md`

## Assignment

Run one combined copied-temp rerun only after the orchestrator confirms Agents9121-9124 closeouts.

Orchestrator confirmation:

- Agent9121 is accepted as `GREEN` operational source refresh packet for copied-temp use, while still retaining unresolved stock/sales/ads freshness caveats exactly as documented.
- Agent9122 is accepted as `GREEN` C3 child-source contract split. Promote/refresh the C3 policy registry on the copied DB before source freshness materialization so child rows exist in the copied DB.
- Agent9123 is accepted as `GREEN` Line61 shortage classification. Use it only to remove the exact `23` delta from unknown mismatch; do not green unrelated PO failures.
- Agent9124 is accepted as `GREEN` `DIM_SKU_light` parser repair. Use the current repo code/tests in the copied-temp rerun.

## Required Work

1. Verify all dependency closeouts exist.
2. Verify protected DB/workbook boundary.
3. Create a fresh copied DB under assigned evidence root.
4. Apply only accepted copied-temp inputs and current repo code changes.
5. Run validators:
   - `validate_policy_source_freshness.py --as-of 2026-05-18 --strict --json`;
   - `validate_policy_gate_results.py --strict --json`;
   - `validate_po_dashboard_invariants.py`;
   - `validate_po_money_gate.py --as-of 2026-05-18 --json`;
   - `sync_po_parts_from_inbound_calendar.py` dry-run;
   - `validate_single_truth_system.py`;
   - `validate_exception_queue_db.py`;
   - `validate_cashflow_invariants.py`;
   - `validate_order_cashflow_coverage.py`;
   - ads/order-entry/day-complete validators as needed.
6. Produce proof board and retained blocker matrix.

## Outputs

Closeout path:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_agent912_operational_source_refresh_c3_split/agent9125_combined_copied_temp_rerun_closeout.md`

Evidence root:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_agent912_operational_source_refresh_c3_split/agent9125_combined_copied_temp_rerun_evidence/`

Required artifacts:
- `PROOF_BOARD.json`
- `PROOF_BOARD.md`
- `VALIDATOR_EXIT_MATRIX.tsv`
- `RETAINED_BLOCKER_MATRIX.tsv`
- `CODECAPTAIN_PACKET_RECOMMENDATION.md`
- boundary hashes and DB integrity outputs

## Stoplines

- Do not run until Agents9121-9124 closeouts exist and are reviewed.
- Do not claim green if any required validator fails.
- Do not production-apply anything.
