# Agent 11 - PKT-RESID Writer

Assigned closeout:
`~/Docs/Autonomous_business_agent_handoffs/2026-06-13_green_path_resume/agent_11_pkt_resid_writer_closeout.md`

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/handoff/ORCHESTRATOR_HANDOFF.md`
4. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/GREEN_PATH_RESUME_ADDENDUM_20260613.md`
5. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/starter_pack/03_packets_phase2.md`
6. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/OWNER_DECISIONS_RECORDED.yaml`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-06-13_green_path_resume/agent_7_pkt_cash_resid_apply_readiness_closeout.md`
8. Agent 5 `PKT-LINES` closeout after it exists

Role: write-capable execution agent for `PKT-RESID` only. Do not start unless the orchestrator explicitly sends this prompt after reviewing Agent 5.

Scope:

- Objective: `PKT-RESID`, gate `G-RESID-01`.
- Allowed writes: `scripts/reconcile_on_delivery_settlement.py` governed residual settlement apply, immediate DB backup/evidence, assigned closeout.
- Forbidden writes: cash anchor, cashflow calendar rebuild, order entries/status, FX, stock, profit/COGS, ads, quarantine, WA, workbooks, LaunchAgents, and external systems.

Execution contract:

- Re-baseline residual candidate set at entry.
- Expected scope from Agent 7: `120` candidates, `425,015.24` KZT total; OD-015 tolerance is `±2%`.
- STOP if candidate count/sum drifts outside tolerance or includes an unexplained out-of-scope order.
- Create immediate hot SQLite backup with `sqlite3 .backup`, run integrity check, and record pre-apply SHA256 before any apply.
- Dry-run first:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/reconcile_on_delivery_settlement.py \
  --db db/app.db \
  --until 2026-06-13 \
  --run-id greenpath_pkt_resid_20260613_dryrun
```

- Apply only after dry-run diff is in-scope and backup is current:

```bash
ENABLE_CASHFLOW_WRITE=1 PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/reconcile_on_delivery_settlement.py \
  --db db/app.db \
  --until 2026-06-13 \
  --run-id greenpath_pkt_resid_20260613_apply \
  --apply
```

- Post-apply, dry-run the same command again. Expected result: `candidates=0`.
- Run `check_on_delivery_residuals.py`, `validate_on_delivery_freeze.py`, and `validate_cashflow_invariants.py`; classify shipped missing-cost failures separately if residual count is zero.

Closeout requirements:

- Standalone line `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
- Include backup path, pre/post SHA256, dry-run/apply/post-dry-run outputs, residual before/after count and sum, validator outputs, rollback note, and exact commands.
- Use `Gate: GREEN` only if the residual class drains to zero and no unexpected validator/redline remains.
- Use `Gate: YELLOW` if residual drains but broader on-delivery freeze remains red for known shipped missing-cost rows.
- Use `Gate: RED` for out-of-scope residual diff, missing backup, DB integrity failure, or failed apply.
