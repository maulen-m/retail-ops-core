# Agent873 Starter: COGS And ChildSum Route

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_post_codecaptain_source_contract_addition_wave/agent873_cogs_childsum_route_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business/exports/validation/mvos_post_codecaptain_source_contract_addition_wave/20260517_210554/agent873_cogs_childsum_route`

## Bootstrap

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/inventory/Sales_Data_Model_V16.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/CHILDSUM_BUNDLE_COGS_CONTRACT_20260517_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/agent_handoffs/CHILDSUM_BUNDLE_COGS_CONTRACT_20260517_STARTERS/01_AGENT_COGS__CHILDSUM_BUNDLE_COGS_CONTRACT__ROOT.md`
7. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-17_mvos_post_codecaptain_source_contract_addition_wave/PLAN.md`
8. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-17_mvos_post_codecaptain_source_contract_addition_wave/ORCHESTRATOR_HANDOFF.md`
9. `~/Docs/Oracle/Autonomous_business/2026-05-17/190620_TASK-000_mvos-freeze-to-codecaptain-current-boundary-yellow-review/answer/Code Captain - Branch_17.05.2026_20_58_49.md`
10. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-17_mvos_freeze_to_codecaptain_wave/AGENT867_SYNTHESIS_FOR_CODECAPTAIN.md`
11. `~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_freeze_to_codecaptain_wave/agent867_synthesis_codecaptain_packet_closeout.md`
12. this starter prompt.

## Assignment

Produce the COGS route addition needed before copied-temp proof.

CodeCaptain accepted route:

`OWNER_APPROVED_PARENT_UNIT_COGS_FOR_COPIED_TEMP_ONLY`

Owner-approved copied-temp parent unit values:

- `LINE-31-TS=6006.76 KZT` from `CL_OC_MEN_LINE51_WHITE`;
- `SUIT-21-TS=5567.22 KZT` from `CL_NEW-CLO2_MEN_SUIT-61_BLACK`;
- `SUIT-31-LS=5567.22 KZT` from `CL_NEW-CLO2_MEN_SUIT-61_BLACK`;
- `SUIT-31-TS=5567.22 KZT` from `CL_NEW-CLO2_MEN_SUIT-61_BLACK`;
- cancelled order `912293165` remains included in copied-temp evidence.

Known failure to preserve:

- `ACMEWEAR 909054064 / SUIT-31-TS` must not be falsely claimed as ChildSum component economics.

You may read repo docs, prior evidence, and run copied-temp-only checks. You may write only to your assigned evidence folder and assigned closeout.

Do:

- Reproduce or cite the current COGS blocker for `ACMEWEAR 909054064 / SUIT-31-TS`.
- Create a clear copied-temp tactical parent-COGS contract for the accepted values.
- Separately state what remains required for production-grade ChildSum component economics.
- If safe, run `validate_cogs_completeness_by_month.py` against read-only/copy-temp surfaces.
- Do not edit production code unless you find that this starter has been superseded by an explicit code-write authorization in the local plan.

Do not:

- mutate production DB, workbook, scheduler, or external systems;
- treat parent unit COGS as component ChildSum economics;
- hide cancelled-order inclusion.

Closeout must include:

- standalone `Gate: <GREEN/YELLOW/RED>` line;
- exact copied-temp COGS contract;
- validation commands/results;
- production ChildSum remaining requirement;
- remaining CodeCaptain questions, if any.
