# Agent798 Starter - Exception Owner/Source Fact Packet

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-13_autonomous_phase0_3_source_truth_wave/agent798_exception_owner_source_packet_20260513_192243_closeout.md`

## Bootstrap

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AUTONOMOUS_PHASE0_3_SOURCE_TRUTH_WAVE_PLAN_20260513_192243.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AUTONOMOUS_PHASE0_3_SOURCE_TRUTH_WAVE_HANDOFF_20260513_192243.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-13_autonomous_phase0_3_source_truth_wave/agent793_boundary_reanchor_20260513_192243_closeout.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AGENT793_ORCHESTRATOR_REVIEW_ACCEPT_BOUNDARY_GREEN_20260513_193650.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent792_exception_owner_decision_packet_20260513_121500_closeout.md`
8. this starter prompt

## Mission

Refresh the high-severity exception owner/source fact packet so synthesis can separate automatable repairs from human facts.

## Scope

Read-only/source-decision work only.

Allowed writes:

- evidence under `~/Docs/Autonomous_business/exports/validation/autonomous_phase0_3_source_truth_wave/20260513_192243/agent798_exception_owner_source_packet/`
- assigned closeout only.

Forbidden:

- production DB mutation;
- workbook mutation;
- stock changes;
- owner publication;
- source pointer changes.

## Required Work

1. Verify Agent793 `Domain Status: BOUNDARY_GREEN` and the orchestrator routing review above, then use its boundary.
2. Recompute/open the current exception queue state and compare to Agent792.
3. Keep warning/exception cohorts visible; do not smooth them into product truth.
4. For each high-severity exception, classify:
   - can be resolved by existing deterministic source evidence;
   - needs owner/warehouse physical fact;
   - needs policy decision;
   - should stay blocked.
5. Build an owner/source fact packet with exact questions and acceptable answer shapes.
6. If any copied-temp proof is safe using existing deterministic evidence only, stage it under evidence root; do not production-apply.
7. Closeout must include:
   - `Gate: GREEN` if packet is complete;
   - `Domain Status: GREEN/YELLOW/RED`;
   - current exception counts by reason/severity;
   - exact owner/source facts still required;
   - copied-temp proof status if any;
   - non-mutation statement.
