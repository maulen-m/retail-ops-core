# Agent 5 — G-RET-02 Real QC Fact Apply

Before executing, read:
1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/plan/green_path_2026-06/MASTER_REMEDIATION_PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_OWNER_ACTIONS_20260618_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_OWNER_ACTIONS_20260618_STARTERS/05_AGENT_5__RET02_QC_FACT_APPLY__AFTER_04.md`
6. Dependency closeout from Agent 4.

Objective: apply only a real owner/staff return QC fact for `G-RET-02`.

Fail-closed preflight:
```bash
cd ~/Docs/Autonomous_business
.venv/bin/python scripts/report_owner_action_queue.py --strict --output-dir exports/validation/owner_action_queue/agent5_ret02_$(date +%Y%m%d_%H%M%S)
```

Rules:
- If `OA-RET02` is not `FACT_READY`, stop no-write.
- Use `scripts/apply_return_qc_events.py` dry-run first; production apply requires the script's env gate, expected DB SHA, and backup.
- Do not invent QC. Required fact fields: order ID, pass/fail, sellable quantity, defect/writeoff quantity, staff/source evidence.
- After apply, rerun returns economics audit, `G-RET-02`, `G-RET-03`, `G-MET-01`, and dependent PO/metric reports as needed.

Return contract:
- Backup path, dry-run/apply reports, before/after QC counts, validators, rollback instructions, and untouched-surface list.
