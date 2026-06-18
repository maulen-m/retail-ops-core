# Agent 2 - COGS, FX, Profit Scout

Before executing, read:
1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/OWNER_DECISIONS_RECORDED.yaml`
5. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/starter_pack/03_packets_phase2.md`
6. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/green_path_run/scoreboard.csv`
7. `~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_REMAINING_PHASE2_20260614_STARTERS/02_AGENT_2__COGS_FX_PROFIT_SCOUT__PARALLEL.md`

Assigned closeout:
`~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_remaining_phase2/agent2_cogs_fx_profit_scout_closeout.md`

Role: read-only analyst. You may write only the assigned closeout file and temporary files under `/tmp/green_path_scratch/agent2_cogs_fx_profit/`.

Objective:
Re-baseline the remaining COGS/profit and FX work without applying anything. Produce the exact writer-ready scope, validators, expected diffs, and stoplines.

Required work:
- Inspect COGS completeness and profit publication validators enough to know what they actually check.
- Re-baseline current COGS/profit state from DB/read-only validators.
- Inspect FX authority/cadence surfaces and identify whether G-FX-01/G-FX-02 can be closed before COGS apply.
- Identify if the next serialized write should be FX first, COGS first, or a combined docs-before-code lane.
- Call out any mismatch between packet assumptions and current code/data.

Suggested read-only commands:
- `python3 scripts/validate_cogs_completeness_by_month.py`
- `python3 scripts/validate_profit_publication_integrity.py`
- `python3 scripts/validate_inventory_cost_drift.py`
- `python3 scripts/validate_policy_source_freshness.py`
- `rg -n "LINE52|dim_fx_rates|cogs_kzt|floor|FX" docs core scripts config`

Forbidden:
- No `--apply`.
- No write-enable env vars.
- No DB, workbook, scheduler, price upload, Kaspi, Repricer, Telegram, or browser actions.
- No edits to repo files except the assigned closeout.

Closeout must include:
- Standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
- Current COGS coverage by month or the strongest available current proxy.
- FX authority/cadence status.
- Exact recommended writer command sequence and required backup/rollback evidence.
- Commands run and key outputs.
