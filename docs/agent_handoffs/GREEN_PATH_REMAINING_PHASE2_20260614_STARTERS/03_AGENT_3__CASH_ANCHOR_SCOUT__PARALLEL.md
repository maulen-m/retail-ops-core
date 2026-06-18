# Agent 3 - Cash Anchor Scout

Before executing, read:
1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/OWNER_DECISIONS_RECORDED.yaml`
5. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/starter_pack/03_packets_phase2.md`
6. `~/Docs/Autonomous_business/docs/KASPI_ORDER_CASHFLOW_TRACKING.md`
7. `~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_REMAINING_PHASE2_20260614_STARTERS/03_AGENT_3__CASH_ANCHOR_SCOUT__PARALLEL.md`

Assigned closeout:
`~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_remaining_phase2/agent3_cash_anchor_scout_closeout.md`

Role: read-only analyst. You may write only the assigned closeout file and temporary files under `/tmp/green_path_scratch/agent3_cash_anchor/`.

Objective:
Re-baseline the cash anchor lane and decide whether it is ready for a governed apply after the orchestrator reviews the report.

Required work:
- Verify the owner-approved cash snapshot artifact path from OD-002 is present/readable enough for the lane.
- Inspect the cash anchor scripts and validators enough to distinguish ACTUAL vs MODELLED and avoid partial-range reset risk.
- Re-baseline current cash anchor batches and current cash validator state.
- Identify exact account coverage, FX basis, PO-1B/SHR in-flight treatment, and any missing source artifact.
- Recommend whether the next writer should run cash anchor now or defer until FX/COGS.

Suggested read-only commands:
- `python3 scripts/validate_cashflow_invariants.py`
- `python3 scripts/validate_monthly_cash_reconciliation.py`
- `python3 scripts/validate_cashflow_actual_model_separation.py`
- `python3 scripts/validate_order_cashflow_coverage.py`
- `rg -n "cashflow_cash_anchor|Cash_Balances|actual_model|MODELLED|ACTUAL|anchor" scripts core docs config`

Forbidden:
- No `--apply`.
- No write-enable env vars.
- No workbook edits.
- No DB writes.
- No bank, Binance, Telegram, browser, LaunchAgent, Kaspi, or Repricer actions.
- No edits to repo files except the assigned closeout.

Closeout must include:
- Standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
- Snapshot/source presence and account coverage.
- Current anchor state and validator status.
- Exact recommended writer command sequence and rollback evidence.
- Commands run and key outputs.
