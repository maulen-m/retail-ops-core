# Agent 3 — G-PRICE-05 Repricer Backlog Disposition

Before executing, read:
1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/plan/green_path_2026-06/MASTER_REMEDIATION_PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_OWNER_ACTIONS_20260618_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_OWNER_ACTIONS_20260618_STARTERS/03_AGENT_3__PRICE05_REPRICER_DISPOSITION__AFTER_02.md`
6. Dependency closeout from Agent 2.

Objective: close `G-PRICE-05` by either approved apply or approved formal drop.

Fail-closed preflight:
```bash
cd ~/Docs/Autonomous_business
.venv/bin/python scripts/report_owner_action_queue.py --strict --output-dir exports/validation/owner_action_queue/agent3_price05_$(date +%Y%m%d_%H%M%S)
```

Rules:
- If `OA-PRICE05` is still `WAITING_OWNER`, stop no-write.
- If owner chose formal drop, run `scripts/report_g_price05_fresh_backlog.py` with `formal_drop_approved` and the approval evidence path; do not write Repricer.
- If owner chose apply, use only the existing guarded Web_automation Repricer writer against `~/Docs/Web_automation/runs/green_path_g_price05_fresh_backlog_20260618/20260618_161005`, with post-readback verification.
- Do not combine apply and drop.

Return contract:
- `G-PRICE-05` report path, source run path, disposition, readback or drop evidence, and explicit list of surfaces untouched.
