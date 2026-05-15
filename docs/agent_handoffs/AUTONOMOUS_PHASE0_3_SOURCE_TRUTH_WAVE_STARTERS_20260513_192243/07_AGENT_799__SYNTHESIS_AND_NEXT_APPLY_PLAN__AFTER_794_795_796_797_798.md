# Agent799 Starter - Phase 3 Synthesis And Next Apply Plan

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-13_autonomous_phase0_3_source_truth_wave/agent799_synthesis_20260513_192243_closeout.md`

## Bootstrap

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AUTONOMOUS_PHASE0_3_SOURCE_TRUTH_WAVE_PLAN_20260513_192243.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AUTONOMOUS_PHASE0_3_SOURCE_TRUTH_WAVE_HANDOFF_20260513_192243.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-13_autonomous_phase0_3_source_truth_wave/agent793_boundary_reanchor_20260513_192243_closeout.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AGENT793_ORCHESTRATOR_REVIEW_ACCEPT_BOUNDARY_GREEN_20260513_193650.md`
7. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/CURRENT_BOUNDARY_REANCHOR_FOR_AGENT799_20260513_212152.md`
8. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/ORCHESTRATOR_REVIEW_LAUNCH_AGENT799_SYNTHESIS_20260513_212300.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-13_autonomous_phase0_3_source_truth_wave/agent794_order_entry_source_packet_20260513_192243_closeout.md`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-13_autonomous_phase0_3_source_truth_wave/agent795_ads_source_packet_20260513_192243_closeout.md`
11. `~/Docs/Autonomous_business_agent_handoffs/2026-05-13_autonomous_phase0_3_source_truth_wave/agent796_po_inbound_source_packet_20260513_192243_closeout.md`
12. `~/Docs/Autonomous_business_agent_handoffs/2026-05-13_autonomous_phase0_3_source_truth_wave/agent797_cashflow_cost_bank_packet_20260513_192243_closeout.md`
13. `~/Docs/Autonomous_business_agent_handoffs/2026-05-13_autonomous_phase0_3_source_truth_wave/agent798_exception_owner_source_packet_20260513_192243_closeout.md`
14. this starter prompt

## Mission

Synthesize the autonomous Phase 0-3 wave into the next decision-grade plan toward the `100%` autonomous business system.

## Scope

Read-only synthesis and copied-temp proof only.

Allowed writes:

- evidence under `~/Docs/Autonomous_business/exports/validation/autonomous_phase0_3_source_truth_wave/20260513_192243/agent799_synthesis/`
- copied DB under that evidence root if all source lanes make it safe;
- assigned closeout only.

Forbidden:

- production DB mutation;
- workbook mutation;
- source pointer changes;
- scheduler mutation;
- owner publication;
- external writes;
- cash/PO/ad/price/stock action.

## Required Work

1. Read Agent793-798 closeouts and the 2026-05-13 21:21 current-boundary reanchor.
2. Do not require Agents795-798 to be GREEN. They are intentionally available as RED decision/source packets for synthesis. Use the orchestrator review to separate boundary-only REDs from true domain blockers.
3. Build a domain matrix:
   - boundary;
   - stock/order source truth;
   - ads source truth;
   - PO/inbound source truth;
   - cashflow source truth;
   - exception queue;
   - owner publication readiness.
4. If all required source packets are present and safe, run one copied-temp combined replay/validator pass. If not safe, do not fake it; synthesize exact blockers.
5. Produce the next production-apply prep plan as inert plan only, including backups, env gates, rollback, and validators that would be required later.
6. State current progress score from `0` to `10`.
7. State which next tasks are autonomous and which require owner/source approval.
8. Create or index owner-decision packets for PO replacement source bundle, compact SKU cost inheritance/exclusion, and stock exception facts. Do not apply any decisions.
9. Closeout must include:
   - `Gate: GREEN` if synthesis completed;
   - `Domain Status: GREEN/YELLOW/RED`;
   - exact remaining blockers;
   - exact recommended next wave;
   - no-production-mutation statement.
