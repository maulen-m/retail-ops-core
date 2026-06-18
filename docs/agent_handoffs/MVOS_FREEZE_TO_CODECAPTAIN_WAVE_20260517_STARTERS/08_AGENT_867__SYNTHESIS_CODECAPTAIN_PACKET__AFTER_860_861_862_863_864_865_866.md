# Agent867 Starter: Synthesis And CodeCaptain Packet Preparation

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_freeze_to_codecaptain_wave/agent867_synthesis_codecaptain_packet_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business/exports/validation/mvos_freeze_to_codecaptain_wave/20260517_183241/agent867_synthesis_codecaptain_packet`

Assigned synthesis doc:

`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-17_mvos_freeze_to_codecaptain_wave/AGENT867_SYNTHESIS_FOR_CODECAPTAIN.md`

Assigned review prompt draft:

`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-17_mvos_freeze_to_codecaptain_wave/CODECAPTAIN_REVIEW_PROMPT_DRAFT.md`

## Bootstrap

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-17_mvos_freeze_to_codecaptain_wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-17_mvos_freeze_to_codecaptain_wave/ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_freeze_to_codecaptain_wave/agent860_boundary_source_gate_reanchor_closeout.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_freeze_to_codecaptain_wave/agent861_ads_source_truth_closeout.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_freeze_to_codecaptain_wave/agent862_cash_payment_source_truth_closeout.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_freeze_to_codecaptain_wave/agent863_lifecycle_cancellation_webui_closeout.md`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_freeze_to_codecaptain_wave/agent864_status_ledger_continuity_closeout.md`
11. `~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_freeze_to_codecaptain_wave/agent865_po_day_complete_closeout.md`
12. `~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_freeze_to_codecaptain_wave/agent866_childsum_component_economics_closeout.md`

## Assignment

Synthesize Agents860-866 and prepare the CodeCaptain review surface.

Do:

- Read all root closeouts and evidence references.
- Build a gate matrix and retained-blocker matrix.
- If no root lane is `RED`, run the safest copied-temp MVOS proof rerun possible using accepted copied-temp inputs only.
- If root evidence is insufficient for a full rerun, explain why and produce a review packet without pretending it is green.
- Write the synthesis doc and CodeCaptain review prompt draft.
- Identify the exact files the orchestrator should include in the Oracle pack.

Do not:

- mutate production DB/workbook;
- mutate scheduler or automations;
- perform external writes;
- turn copied-temp evidence into production authority;
- ask owner for production apply phrase.

Closeout must include:

- standalone `Gate: <GREEN/YELLOW/RED>` line;
- root closeout matrix;
- validator results;
- exact CodeCaptain review question;
- list of prioritized files for the Oracle pack.
