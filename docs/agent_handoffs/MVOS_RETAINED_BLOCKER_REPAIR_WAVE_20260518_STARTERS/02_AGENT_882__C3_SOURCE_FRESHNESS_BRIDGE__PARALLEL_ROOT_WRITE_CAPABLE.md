# Agent882 Starter: C3 Source-Freshness Bridge

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_retained_blocker_repair_wave/agent882_c3_source_freshness_bridge_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business/exports/validation/mvos_retained_blocker_repair_wave/20260518/agent882_c3_source_freshness_bridge`

## Bootstrap

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos_retained_blocker_repair_wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos_retained_blocker_repair_wave/ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Oracle/Autonomous_business/2026-05-17/231037_TASK-000_mvos-owner-qa-board-proof-codecaptain-final/ANSWER/Code Captain_18.05.2026_09_08_18.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_owner_qa_repair_wave/agent880_synthesis_copied_temp_board_proof_closeout.md`
8. `~/Docs/Autonomous_business/docs/contracts/mvos_source_contracts/ACTIVE_MVOS_SOURCE_CONTRACT_REGISTRY.json`
9. this starter prompt.

## Assignment

Implement the copied-temp C3 source-freshness bridge lane.

This is the only root write-capable repo lane for this wave. Make the smallest correct repo docs/tests/validator/materializer edits needed to support the CodeCaptain-approved copied-temp bridge contract:

```text
COPIED_TEMP_SOURCE_FRESHNESS_BRIDGE_ONLY
Accepted source packets and source contracts may be materialized into the copied validation DB as source_freshness_result rows for proof replay only. This does not update production db/app.db, does not authorize owner publication, and does not convert copied-temp source freshness into production source freshness.
```

Produce:

- `COPIED_TEMP_SOURCE_FRESHNESS_BRIDGE_CONTRACT.md`
- `SOURCE_FRESHNESS_BRIDGE_MATERIALIZATION_SUMMARY.json`
- copied DB proof outputs only inside the assigned evidence folder
- focused tests or validator outputs proving fail-closed behavior
- assigned closeout with a standalone `Gate: <GREEN/YELLOW/RED>` line

Minimum bridge fields:

- source id
- source packet path
- source packet SHA
- captured_at
- as_of
- status
- blocks_publication
- proof_scope=`copied_temp`
- production_authority=false

Do not:

- write production `db/app.db`;
- write workbook, scheduler, source pointers, Web_automation, Kaspi/API/WebUI, ad platforms, cash, PO, stock, price, owner-publication, or external systems;
- create production source-freshness authority;
- clear owner-publication gates unless validators genuinely pass on accepted copied-temp proof.

Validation expectations:

- JSON artifacts parse.
- Focused tests pass for any edited code.
- `scripts/lint_docs.sh` passes if docs touched.
- `scripts/check_no_db_tracked.sh` passes.

Gate guidance:

- `GREEN` if copied-temp bridge behavior is implemented/proven and protected surfaces remain untouched.
- `YELLOW` if a safe contract is documented but implementation/proof still needs CodeCaptain/owner decision.
- `RED` if production mutation or source-authority confusion occurs.
