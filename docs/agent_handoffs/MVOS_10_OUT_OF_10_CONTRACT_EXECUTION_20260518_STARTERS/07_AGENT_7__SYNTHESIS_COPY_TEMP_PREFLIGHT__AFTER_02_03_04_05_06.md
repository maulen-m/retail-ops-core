# Agent 7: Synthesis, Owner Surfaces, Full Copied-Temp Proof, And Preflight Packet

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/contracts/MVOS_10_OUT_OF_10_DECISION_GRADE_ACCEPTANCE_CONTRACT.md`
5. `~/Docs/Autonomous_business/docs/contracts/MVOS_10_OUT_OF_10_ORCHESTRATOR_GOAL_PROMPT.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos-10-out-of-10-contract-execution/PLAN.md`
7. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_10_OUT_OF_10_CONTRACT_EXECUTION_20260518_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos-10-out-of-10-contract-execution/agent2_c3_source_freshness_closeout.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos-10-out-of-10-contract-execution/agent3_orders_sales_lifecycle_closeout.md`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos-10-out-of-10-contract-execution/agent4_ads_truth_closeout.md`
11. `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos-10-out-of-10-contract-execution/agent5_cashflow_bank_closeout.md`
12. `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos-10-out-of-10-contract-execution/agent6_po_stock_exception_closeout.md`
13. this assigned starter prompt

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos-10-out-of-10-contract-execution/agent7_synthesis_copy_temp_preflight_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos-10-out-of-10-contract-execution/agent7_synthesis_copy_temp_preflight_evidence`

## Task

Synthesize Agents 2-6 and execute Phases 5-7 where safe:

- Owner Decision Surface Gate.
- Full Copied-Temp MVOS Proof Gate.
- Production Preflight Packet drafting only if copied-temp proof is green or a narrow production candidate is explicitly separated.

Do not production-apply. Do not request an owner apply phrase unless CodeCaptain review packet is complete and the orchestrator explicitly opens that later lane.

## Required Outputs

Owner decision surfaces:

- `OWNER_DECISION_SURFACE_ACCEPTANCE_MATRIX.tsv`
- validate-only Cash Risk Daily
- validate-only Daily Survival Brief
- validate-only Stock/Order Risk
- validate-only Ads/Profit Readiness
- validate-only PO/Inbound Readiness

Full copied-temp proof:

- `FULL_MVOS_COPIED_TEMP_PROOF_BOARD.json`
- `FULL_MVOS_COPIED_TEMP_PROOF_BOARD.md`
- `VALIDATOR_EXIT_MATRIX.tsv`
- `RETAINED_BLOCKER_BOARD.md`
- `COPIED_DB_BOUNDARY_SHA256.tsv`

If allowed, preflight review packet:

- `PRODUCTION_PREFLIGHT_PACKET.md`
- `OWNER_APPROVAL_PHRASE_REQUEST.md`
- `PRODUCTION_BACKUP_AND_ROLLBACK.md`
- `DRY_RUN_EXPECTED_DIFF.json`
- `WRITE_COMMAND_MANIFEST.tsv`

## Boundary

Serialized repo/evidence writing is allowed for local docs, tests, and evidence. Production DB apply, protected workbook writes, scheduler mutation, external writes, browser-login automation, Web_automation writes, owner publication, cash movement, supplier payment, PO commitment, ad spend, price changes, and stock changes are forbidden.

## Gate Guidance

Use `Gate: COPIED_TEMP_GREEN_PROOF` only if every required validator passes for declared scope and no unaccepted retained blocker affects claimed output.

Use `Gate: YELLOW_RETAINED_BLOCKER_BOARD_PROOF` if the copied-temp proof is useful but retained blockers remain.

Use `Gate: YELLOW` if owner decision surfaces or preflight packet are incomplete but the boundary is safe.

Use `Gate: RED` if protected production state changes, copied-temp proof is described as production truth, scoped proof is described as full-scope proof, or any unauthorized business action is implied.
