# Agent 4 — G-DARK-01 Relist Correction

Before executing, read:
1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/plan/green_path_2026-06/MASTER_REMEDIATION_PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_OWNER_ACTIONS_20260618_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_OWNER_ACTIONS_20260618_STARTERS/04_AGENT_4__DARK01_RELIST_CORRECTION__AFTER_03.md`
6. Dependency closeout from Agent 3.

Objective: correct only the approved `G-DARK-01` RUSH_WHITE offer-state mismatch.

Fail-closed preflight:
```bash
cd ~/Docs/Autonomous_business
.venv/bin/python scripts/report_owner_action_queue.py --strict --output-dir exports/validation/owner_action_queue/agent4_dark01_$(date +%Y%m%d_%H%M%S)
.venv/bin/python scripts/report_g_dark01_relist_state.py --strict || true
```

Rules:
- If `OA-DARK01` is not `APPROVED`, stop no-write.
- Scope is only RUSH_WHITE `S`, `M`, `3XL` buyable and `L` non-buyable/excluded.
- Use fresh preflight/readback. If current mismatch differs from approval artifact, stop for orchestrator review.
- Do not touch unrelated pricing, stock, DB, workbook, Google Sheet, Telegram, customer/operator messages, LaunchAgents, cash, PO, or purchases.

Return contract:
- Preflight, apply if approved, post-readback, refreshed `G-DARK-01` report, and `G-DARK-02` dependency note.
