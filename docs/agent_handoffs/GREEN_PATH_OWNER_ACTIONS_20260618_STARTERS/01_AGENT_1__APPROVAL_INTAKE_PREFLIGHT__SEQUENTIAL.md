# Agent 1 — Approval Intake Preflight

Before executing, read:
1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/plan/green_path_2026-06/MASTER_REMEDIATION_PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_OWNER_ACTIONS_20260618_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_OWNER_ACTIONS_20260618_STARTERS/01_AGENT_1__APPROVAL_INTAKE_PREFLIGHT__SEQUENTIAL.md`

Objective: validate the owner-action queue and produce a no-write readiness report for the orchestrator.

Commands:
```bash
cd ~/Docs/Autonomous_business
.venv/bin/python scripts/report_owner_action_queue.py --strict --output-dir exports/validation/owner_action_queue/agent1_intake_$(date +%Y%m%d_%H%M%S)
.venv/bin/python scripts/manage_business_automation.py verify --scope daily-ops --json
```

Return contract:
- Report whether the queue is `GREEN`, `ARMED`, or `RED`.
- List which `OA-*` rows are still waiting and which are dispatch-ready.
- Confirm no production DB, workbook, Google Sheet, Telegram, Kaspi, Repricer, price, stock, customer/operator-message, LaunchAgent, cash, PO, purchase, or external write was performed.
