# Agent797 Starter - Cashflow Cost And Bank Freshness Packet

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-13_autonomous_phase0_3_source_truth_wave/agent797_cashflow_cost_bank_packet_20260513_192243_closeout.md`

## Bootstrap

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AUTONOMOUS_PHASE0_3_SOURCE_TRUTH_WAVE_PLAN_20260513_192243.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AUTONOMOUS_PHASE0_3_SOURCE_TRUTH_WAVE_HANDOFF_20260513_192243.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-13_autonomous_phase0_3_source_truth_wave/agent793_boundary_reanchor_20260513_192243_closeout.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AGENT793_ORCHESTRATOR_REVIEW_ACCEPT_BOUNDARY_GREEN_20260513_193650.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent788_cashflow_copy_temp_replay_20260513_121500_closeout.md`
8. this starter prompt

## Mission

Clear or sharply isolate cashflow source blockers: missing SKU costs and stale bank manual/statement ingest.

## Scope

Read-only/source-packet and copied-temp work only.

Allowed writes:

- evidence under `~/Docs/Autonomous_business/exports/validation/autonomous_phase0_3_source_truth_wave/20260513_192243/agent797_cashflow_cost_bank_packet/`
- copied DB under that evidence root if needed;
- assigned closeout only.

Forbidden:

- production DB mutation;
- workbook mutation;
- cash movement;
- bank account mutation;
- source pointer changes;
- owner publication.

## Required Work

1. Verify Agent793 `Domain Status: BOUNDARY_GREEN` and the orchestrator routing review above, then use its boundary.
2. Reconfirm the missing-cost SKU set from Agent788, especially `LINE-31-TS`, `SUIT-21-TS`, `SUIT-31-LS`, and `SUIT-31-TS`.
3. Search repo-local trusted cost sources for deterministic metadata.
4. If deterministic cost metadata exists, prepare copied-temp-only application evidence; do not production-apply.
5. If not, produce an exact missing-cost owner/source decision packet or deterministic exclusion proposal for the affected lines.
6. Recheck bank manual/statement freshness through current as-of and identify the exact fresh evidence needed.
7. If existing safe scripts can refresh a copied-temp/manual evidence packet without cash movement or production writes, run them under the evidence root only.
8. Closeout must include:
   - `Gate: GREEN` if packet/proof is complete;
   - `Domain Status: GREEN/YELLOW/RED`;
   - missing-cost line count and SKU list;
   - bank freshness status;
   - copied-temp replay status if run;
   - exact remaining owner/source inputs;
   - non-mutation statement.
