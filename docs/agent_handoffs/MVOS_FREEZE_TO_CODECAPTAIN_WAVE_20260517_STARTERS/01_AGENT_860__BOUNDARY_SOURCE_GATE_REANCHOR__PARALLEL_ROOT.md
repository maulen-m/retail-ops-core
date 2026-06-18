# Agent860 Starter: Boundary And Source-Gate Reanchor

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_freeze_to_codecaptain_wave/agent860_boundary_source_gate_reanchor_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business/exports/validation/mvos_freeze_to_codecaptain_wave/20260517_183241/agent860_boundary_source_gate_reanchor`

## Bootstrap

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-17_mvos_freeze_to_codecaptain_wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-17_mvos_freeze_to_codecaptain_wave/ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_agent846_yellow_repair_wave/agent859_synthesis_copied_temp_rerun_closeout.md`

## Assignment

Reanchor the frozen proof boundary and current C3 source/policy gate state.

You may write only to your assigned evidence folder and assigned closeout.

Do:

- Verify all-business automations are paused using `scripts/manage_business_automation.py verify --scope all-business --expect paused`.
- Record SHA-256, file stats, `lsof`, SQLite sidecars, and `PRAGMA integrity_check` for `db/app.db` and `excel_ui/SALES_KSP_CRM_V3.xlsx`.
- Capture current `v_source_freshness_current`, `v_policy_gate_latest`, and relevant `source_freshness_result` / `policy_gate_result` rows if the views/tables exist.
- Run `validate_policy_source_freshness.py --as-of 2026-05-17 --strict --json` and `validate_policy_gate_results.py --strict --json` against production DB read-only behavior only.
- Classify which rows are current true blockers versus stale stored-row artifacts if code supports that distinction.

Do not:

- mutate production DB/workbook;
- pause/resume schedulers;
- run write materializers on production DB;
- touch external systems.

Closeout must include:

- standalone `Gate: <GREEN/YELLOW/RED>` line;
- current protected SHA table;
- current source and policy gate matrix;
- exact retained blockers;
- whether the freeze boundary is clean enough for Agent867 copied-temp proof.
