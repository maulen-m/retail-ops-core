# Green Path Owner Actions Orchestrator Handoff

Generated: 2026-06-18

Purpose: split the remaining approval/fact/time blockers after `G-ACC-01` into standalone execution prompts. These prompts are fail-closed and must not execute live writes unless the matching owner-action queue item is no longer waiting and the approval/fact evidence is present.

Canonical plan:
- `~/Docs/Autonomous_business/docs/plan/green_path_2026-06/MASTER_REMEDIATION_PLAN.md`
- `~/Docs/Autonomous_business/docs/plan/green_path_2026-06/GREEN_STATE_GATE_MATRIX.md`

Current queue:
- `~/Docs/Autonomous_business/exports/validation/g_acc01_final_acceptance/20260618_192023_0500/owner_action_queue.json`
- `~/Docs/Autonomous_business/exports/validation/g_acc01_final_acceptance/20260618_192023_0500/owner_action_queue.csv`
- Validator: `~/Docs/Autonomous_business/scripts/report_owner_action_queue.py`

Starter folder:
- `~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_OWNER_ACTIONS_20260618_STARTERS`

Launch order:
1. `01_AGENT_1__APPROVAL_INTAKE_PREFLIGHT__SEQUENTIAL.md`
2. `02_AGENT_2__PRICE03_ACMEWEAR_COMPACT__AFTER_01.md`
3. `03_AGENT_3__PRICE05_REPRICER_DISPOSITION__AFTER_02.md`
4. `04_AGENT_4__DARK01_RELIST_CORRECTION__AFTER_03.md`
5. `05_AGENT_5__RET02_QC_FACT_APPLY__AFTER_04.md`
6. `06_AGENT_6__CASH_SOURCE_RECHECK__PARALLEL_READONLY_AFTER_01.md`

Parallel rule:
- Agent 6 is read-only by default and may run after Agent 1 while Agents 2-5 wait for approvals.
- Agents 2-5 are serialized because they may touch live external or production DB surfaces after approval.

Global no-write rule:
- If the assigned queue item is still `WAITING_*`, the agent must produce a no-write closeout and stop.
- If approval/fact evidence is ambiguous, missing, broader than the assigned queue item, or stale, stop no-write.
- Never perform production DB, workbook, Google Sheet, Telegram, Kaspi merchant/UI/API, Repricer, price, stock, customer/operator-message, LaunchAgent, cash, PO, purchase, or other external writes beyond the exact assigned approval.

Launch lines:
- Read the repo bootstrap context and execute `~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_OWNER_ACTIONS_20260618_STARTERS/01_AGENT_1__APPROVAL_INTAKE_PREFLIGHT__SEQUENTIAL.md`.
- Read the repo bootstrap context and execute `~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_OWNER_ACTIONS_20260618_STARTERS/02_AGENT_2__PRICE03_ACMEWEAR_COMPACT__AFTER_01.md`.
- Read the repo bootstrap context and execute `~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_OWNER_ACTIONS_20260618_STARTERS/03_AGENT_3__PRICE05_REPRICER_DISPOSITION__AFTER_02.md`.
- Read the repo bootstrap context and execute `~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_OWNER_ACTIONS_20260618_STARTERS/04_AGENT_4__DARK01_RELIST_CORRECTION__AFTER_03.md`.
- Read the repo bootstrap context and execute `~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_OWNER_ACTIONS_20260618_STARTERS/05_AGENT_5__RET02_QC_FACT_APPLY__AFTER_04.md`.
- Read the repo bootstrap context and execute `~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_OWNER_ACTIONS_20260618_STARTERS/06_AGENT_6__CASH_SOURCE_RECHECK__PARALLEL_READONLY_AFTER_01.md`.
