# Agent 2 — G-PRICE-03 ACMEWEAR Compact SUIT/LINE Lane

Before executing, read:
1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/plan/green_path_2026-06/MASTER_REMEDIATION_PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_OWNER_ACTIONS_20260618_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_OWNER_ACTIONS_20260618_STARTERS/02_AGENT_2__PRICE03_ACMEWEAR_COMPACT__AFTER_01.md`
6. Dependency closeout from Agent 1.

Objective: execute only the approved `OA-PRICE03-SUIT` and/or `OA-PRICE03-LINE` path.

Fail-closed preflight:
```bash
cd ~/Docs/Autonomous_business
.venv/bin/python scripts/report_owner_action_queue.py --strict --output-dir exports/validation/owner_action_queue/agent2_price03_$(date +%Y%m%d_%H%M%S)
```

Rules:
- If `OA-PRICE03-SUIT` is not `APPROVED`, do not run any Web_automation safe-active-patch command.
- If `OA-PRICE03-LINE` is not `APPROVED`, do not add compact LINE floor inheritance to scoring.
- If approved, run ONLY the exact dry-run command from `exports/validation/g_price03_remediation_packet_20260618_1548/STOPLINE_TRIAGE.md`; review output; then run live apply only if the approval explicitly permits live apply with `--confirm FULL_ACTIVE_STATE`.
- After any allowed live apply, rerun readback and the AB `G-PRICE-03` strict report.

Forbidden without exact approval:
- Repricer writes, unrelated Kaspi writes, production DB writes, workbook/Google/Telegram/stock/customer/operator/LaunchAgent/cash/PO writes.

Return contract:
- Gate result for `G-PRICE-03`, exact commands run, dry-run/apply artifacts, readback evidence, and no-drift statement.
