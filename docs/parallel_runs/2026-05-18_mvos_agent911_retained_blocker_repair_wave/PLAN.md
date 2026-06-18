# MVOS Agent911 Retained-Blocker Repair Wave Plan

Created: `2026-05-18T22:02:03+05:00`

Repo: `~/Docs/Autonomous_business`

Gate entering this wave: `YELLOW_RETAINED_BLOCKER_BOARD_PROOF`

Dependency proof:

- `~/Docs/Autonomous_business/exports/validation/mvos_option1_next_repair_wave/agent910_copied_temp_contract_proof/AGENT910_COPIED_TEMP_CONTRACT_PROOF_CLOSEOUT.md`
- `~/Docs/Autonomous_business/exports/validation/mvos_option1_next_repair_wave/agent910_copied_temp_contract_proof/PROOF_BOARD.json`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_option1_next_repair_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT910.md`

Owner overlay:

- `~/Docs/Autonomous_business/docs/contracts/mvos_source_contracts/OWNER_QA_PRIORITY_20260518_RETAINED_BLOCKERS.md`

## Goal

Resolve or precisely retain the remaining Agent910 blockers without fake green declarations.

Agent910 already proved these lanes green on a copied DB:

- day-complete;
- COGS completeness with Agent873 copied-temp evidence;
- ads offer-universe coverage;
- ads spend reality;
- exception queue;
- cashflow invariants;
- order-cashflow coverage.

This wave must not reopen those lanes unless a new dependency contradiction appears.

## Remaining Blockers

1. `validate_order_entries_freshness`: STOREB remains below threshold because the `15` header-only rows remain intentionally unmaterialized.
2. `validate_policy_source_freshness`: `src_ab_db_operational_truth` remains blocked for requested as-of `2026-05-18`.
3. `validate_policy_gate_results`: `ads_source_truth`, `source_freshness`, and `stock_source_truth` still block owner publication.
4. `validate_po_dashboard_invariants`: stale stock snapshot remains, stock date `2026-05-04` vs cutoff `2026-05-17`.
5. `validate_po_money_gate`: `inbound_sheet_consistency`, `single_truth_system`, `cogs_integrity`, and `single_truth_alignment` still fail.

## Owner Clarifications To Apply

- For the 15 STOREB header-only rows: use Computer Use / Chrome / read-only WebUI archive fetch/download or API fallback. If still header-only, keep them quarantined.
- For stock: no fresher source than existing evidence exists yet. Do not fake May 18 stock freshness.
- For PO-4.0 Line61: ordered `115`, actual received `92`, shortage `23` is true business fact.
- For inbound workbook schema: missing `To_pay_BASE_KZT` / `To_pay_DLV_KZT` is not expected; recent owner workbook format edits likely moved columns/cells. The workbook remains canonical priority. Inspect and correct parsing/validator logic, not the workbook.

## Execution Shape

Parallel root agents:

- Agent911A: STOREB 15 header-only WebUI/API evidence route.
- Agent911B: `src_ab_db_operational_truth` freshness route.
- Agent911C: stock/PO retained blocker route under no-fresher-stock-source truth.
- Agent911D: inbound workbook schema correction, serialized code/test lane.

After all four close out:

- Agent911E: combined copied-temp rerun and CodeCaptain packet writer.

## Authority Boundary

Allowed:

- read-only local analysis;
- read-only browser/Chrome/Computer Use/WebUI/API fetching for the 15 STOREB rows only;
- copied-temp DB proof;
- local evidence generation;
- repo docs/tests/validator edits needed for the assigned schema/contract behavior;
- closeout writing.

Forbidden:

- production DB writes;
- workbook writes;
- scheduler, LaunchAgent, or cron changes;
- source-pointer writes;
- Web_automation mutation;
- Kaspi/API/WebUI mutation;
- ad-platform writes;
- bid/budget/campaign changes;
- external writes;
- cash movement;
- supplier payment;
- PO commitment;
- stock changes;
- price changes;
- owner publication/send;
- production preflight;
- production apply.

## Success Criteria

The wave is successful if it produces one of these honest outcomes:

- `GREEN_COPIED_TEMP_PROOF_CANDIDATE`: all copied-temp validators pass and protected surfaces are unchanged.
- `YELLOW_RETAINED_BLOCKER_BOARD_PROOF`: some blockers remain, but each is source-classified, owner-contextualized, and visible.
- `RED_INVALID_PROOF`: protected boundary drift, unauthorized write, source contradiction, or validator/code regression invalidates the wave.

Do not declare green if any required validator still fails.
