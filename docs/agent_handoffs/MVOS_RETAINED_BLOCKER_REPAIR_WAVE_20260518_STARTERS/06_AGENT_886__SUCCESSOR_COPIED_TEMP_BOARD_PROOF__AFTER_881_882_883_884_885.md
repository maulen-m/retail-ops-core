# Agent886 Starter: Successor Copied-Temp Board Proof

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_retained_blocker_repair_wave/agent886_successor_copied_temp_board_proof_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business/exports/validation/mvos_retained_blocker_repair_wave/20260518/agent886_successor_copied_temp_board_proof`

## Bootstrap

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos_retained_blocker_repair_wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos_retained_blocker_repair_wave/ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_retained_blocker_repair_wave/agent881_storeb_ads_mapping_source_decision_closeout.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_retained_blocker_repair_wave/agent882_c3_source_freshness_bridge_closeout.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_retained_blocker_repair_wave/agent883_day_complete_two_row_repair_closeout.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_retained_blocker_repair_wave/agent884_status_ledger_scope_five_store_closeout.md`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_retained_blocker_repair_wave/agent885_po_nike_shirt_invariant_closeout.md`
11. this starter prompt.

## Assignment

Run the successor copied-temp MVOS board proof after Agents881-885 close out and the orchestrator has reviewed their actual artifacts.

Produce:

- successor board matrix JSON/CSV;
- validator command manifest and exits;
- final blocker board;
- protected boundary hashes;
- copied DB path and SHA;
- assigned closeout with a standalone `Gate: <GREEN/YELLOW/RED>` line.

Rules:

- Copy production `db/app.db` into assigned evidence before copied-temp mutation.
- Apply only accepted copied-temp repair artifacts.
- Use `COPIED_TEMP_GREEN_PROOF_READY` only if all required validators genuinely pass and no retained blocker remains.
- Otherwise use `YELLOW_RETAINED_BLOCKER_BOARD_PROOF` with blockers visible.

Do not:

- production-apply anything;
- mutate workbook, scheduler, source pointers, Web_automation, Kaspi/API/WebUI, ad platforms, cash, PO, stock, price, owner publication, or external systems;
- treat missing spend as zero;
- synthesize WebUI `status_change_at`;
- call copied-temp evidence production truth;
- hide day-complete, PO, status-ledger, source-freshness, or policy-gate failures.

Gate guidance:

- `GREEN` only for true copied-temp green proof.
- `YELLOW` for blocker-visible successor proof.
- `RED` for invalid proof or authority violation.
