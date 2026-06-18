# Agent 6 — Cash Source Recheck

Before executing, read:
1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/plan/green_path_2026-06/MASTER_REMEDIATION_PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_OWNER_ACTIONS_20260618_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_OWNER_ACTIONS_20260618_STARTERS/06_AGENT_6__CASH_SOURCE_RECHECK__PARALLEL_READONLY_AFTER_01.md`
6. Dependency closeout from Agent 1.

Objective: recheck the `G-SCHED-02` cash-source/cash-floor blockers without writing protected state.

Allowed commands:
```bash
cd ~/Docs/Autonomous_business
.venv/bin/python scripts/report_owner_action_queue.py --strict --output-dir exports/validation/owner_action_queue/agent6_cash_$(date +%Y%m%d_%H%M%S)
.venv/bin/python scripts/validate_transfer_ledger_sync_freshness.py || true
.venv/bin/python scripts/sync_cash_balances_from_inbound_calendar.py --dry-run || true
.venv/bin/python scripts/run_end_of_day.py --dry-run --skip-api-sync --skip-workbook-sync --verbose || true
```

Rules:
- This starter is read-only by default.
- If `OA-CASH-SOURCE` includes a new owner source or decision, produce a copied-DB proof before any production write.
- Do not apply cash anchors, cash-floor overrides, workbook writes, Google Sheet writes, Telegram sends, external account changes, LaunchAgent changes, PO/cash movement, or DB writes without a separate exact approval and backup-first plan.

Return contract:
- Fresh cash-source status, dry-run EOD blockers, whether `G-SCHED-02` can advance, and exact next safe command.
