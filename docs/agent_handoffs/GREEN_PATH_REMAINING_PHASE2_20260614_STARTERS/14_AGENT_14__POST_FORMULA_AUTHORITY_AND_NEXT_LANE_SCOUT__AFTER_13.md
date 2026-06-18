# Agent 14 - Post-Formula Authority And Next-Lane Scout

Closeout path:

`~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_remaining_phase2/agent14_post_formula_authority_and_next_lane_scout_closeout.md`

Gate expectation: `GREEN` if you can return one concrete no-human next lane with exact commands, stop rules, and gate impact; `YELLOW` if the best path is blocked on exact owner authority; `RED` only if current repo/DB guards regress or you find a real contradiction in the accepted baseline.

## Role And Boundary

You are a read-only scout after Agent13. You may write only:

- the closeout file named above
- temporary scratch under `/tmp/green_path_scratch/agent14_post_formula_authority/`

No DB writes. No code edits. No dashboard, scoreboard, STATUS, docs, config, plist, workbook, Telegram, Kaspi, Repricer, pricing, LaunchAgent, browser, customer, or operator-message writes. No external-system writes. Do not run scripts with `--apply` or write-enable env vars.

Daily business automations must remain paused. Verify that only if needed, with evidence under `/tmp`.

## Must Read

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/green_path_run/STATUS.md`
5. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/green_path_run/scoreboard.csv`
6. `~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_remaining_phase2/agent10_cogs_authority_scout_closeout.md`
7. `~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_remaining_phase2/agent13_shipped_freeze_formula_writer_closeout.md`
8. `~/Docs/Autonomous_business/config/owner_decisions/owner_stock_approval_2026_06_14.json`
9. `~/Docs/Autonomous_business/config/governed_stock_owner_approval_repairs_20260614.json`
10. `~/Docs/Autonomous_business/docs/plan/green_path_2026-06/starter_pack/03_packets_phase2.md`
11. `~/Docs/Autonomous_business/docs/plan/green_path_2026-06/green_path_run/go_no_go.md`

## Current Accepted Baseline

Agent13 applied the formula-landed shipped-freeze repair:

- production DB SHA now expected: `d9a12a54ba32c77478abb6369980dce2a173de43e7a89fd48f991ae1b05604a1`
- 36 inventory-move events inserted for 18 allowlisted shipped orders
- `check_on_delivery_residuals.py` passes with `residual_count=0`
- `validate_on_delivery_freeze.py --until 2026-06-14` may still fail only for parked `956748585 / ACMEWEAR / LINE-21-TS_3XL`
- `G-RESID-01` is PARTIAL, not GREEN

COGS/profit has two known exact authority gaps:

- current publication blocker: `953395459 / ACMEWEAR / LINE-31-LS_XL`
- shipped-freeze parked row: `956748585 / ACMEWEAR / LINE-21-TS_3XL`

The owner's June 14 stock approval and compatibility note are recorded, but prior Agent10 concluded they authorize stock mapping/allocation only, not production COGS inheritance. Re-check that conclusion from current repo evidence; do not broaden the approval unless an exact COGS authorization is actually present in repo artifacts.

## Task

Produce a closeout that answers these questions:

1. Does any current repo artifact, including the June 14 owner stock approval, authorize a production COGS override or COGS inheritance for either `953395459 / LINE-31-LS_XL` or `956748585 / LINE-21-TS_3XL`?
2. If yes, give the exact writer route, env gate, dry-run proof shape, backup requirements, validators, expected gate flips, and stoplines. Do not apply it.
3. If no, provide the exact owner approval phrase(s) needed, but also identify the highest-value Phase-2 lane that can proceed now without human approval.
4. For that no-human next lane, return:
   - lane name and gate IDs
   - whether it is read-only, code-only, copied-DB, or production DB write
   - exact first command(s) and expected safe preconditions
   - stoplines
   - expected closeout evidence path
   - why it should run before or after COGS

Consider at least these candidate lanes and reject any unsafe one explicitly:

- `PKT-LINES` / order-entry backfill and `G-ORD-02`
- `PKT-QUAR` / quarantine disposition and `G-QUAR-01..04`
- `PKT-RETURNS` / forward returns pickup/QC telemetry and `G-RET-01..02`
- `G-SCHED-04` / strict preflight re-check after residual/freeze repair
- `G-PRICE-01/G-PRICE-04` read-only floor-vintage/pricing input readiness

## Required Checks

Run read-only checks only:

- `shasum -a 256 db/app.db`
- `sqlite3 -readonly db/app.db 'PRAGMA integrity_check;'`
- `scripts/check_no_db_tracked.sh`
- Parse current scoreboard/dashboard status enough to avoid stale gate claims.
- Any validator you run against the production DB must be read-only. If a validator is known to write views or cache, copy the DB to `/tmp` using `sqlite3 db/app.db ".backup '/tmp/...sqlite'"` first and run against the copy.

## Stoplines

- Stop if DB SHA differs from Agent13 accepted post SHA before your analysis, unless the orchestrator has updated STATUS after Agent13.
- Stop if any "read-only" validator mutates production DB or creates SQLite sidecars.
- Stop if a no-human lane would need external writes, customer/operator messages, LaunchAgent load/unload, workbook writes, or invented business facts.
- Stop if the only possible next write requires the owner to approve COGS, price values, or physical QC facts.

## Closeout Format

Your closeout must include:

- standalone `Gate: GREEN|YELLOW|RED`
- accepted DB SHA and integrity result
- COGS authority answer for both exact rows
- no-human next lane recommendation, or explicit `NONE_SAFE_WITHOUT_OWNER` if true
- commands run and key outputs
- browser/MCP cleanup statement

Then record completion with the tmux orchestrator helper appended by the launcher. Do not manually ping the orchestrator.
