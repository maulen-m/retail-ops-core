# Agent 5 - Serialized Write Integrator

## Selected Lane For Launch 2026-06-14 08:11 +05

The orchestrator selects **PKT-FX / G-FX-02 only** for this launch.

Why this lane:
- Agent 2 proved `G-FX-01` is now GREEN from the 2026-06-13 owner-actual FX row.
- Agent 2 also proved `G-FX-02` remains open because the active FX authority doc and code/constant surfaces are not yet collapsed to one documented source.
- The tempting one-row COGS repair for `953395459 / LINE-31-LS_XL` is **not selected** because repo evidence says `LINE-31-LS` does not yet have a production COGS inheritance contract. Do not apply that COGS row.
- Agent 3 marked cash RED; do not run cash anchor work in this launch.
- Agent 4 marked returns/quarantine/scheduler YELLOW; do not run those writes in this launch.

Allowed for this selected lane:
- Patch the FX authority documentation required by OD-013.
- Patch code/helpers only as narrowly needed to route FX/landed-cost constants through one documented authority path or clearly documented compatibility fallbacks.
- Add/update focused tests for the changed helper/contract behavior.
- Run repo validators/tests relevant to FX authority and touched code.
- Use copied/scratch DBs for validator probes if a validator may refresh SQLite views. Do not mutate production `db/app.db`.

Forbidden for this selected lane:
- No production DB writes or `--apply`.
- No cash anchor, COGS override, stock, returns, quarantine, price, Kaspi, Repricer, Telegram, LaunchAgent, workbook, or browser actions.
- No floor value changes and no price uploads. PKT-PRICE owns pricing.
- No attempt to green `G-CASH-01`, `G-COGS-*`, `G-RESID-01`, or returns/quarantine gates.

Closeout expectation for this launch:
- `Gate: GREEN` only if `G-FX-02` is actually supported by docs/code/tests and the remaining caveats are explicit.
- `Gate: YELLOW` if the authority doc improves but some legacy constants/validators remain as accepted compatibility/follow-up.
- `Gate: RED` if a production DB mutation is required or if the source contract is still ambiguous after inspection.
- Include exact files changed, tests/validators run, and the current DB SHA before/after proving production DB did not change. Current accepted boundary before launch: `5d2233bf8a0956d95a1cac39b416553b81a6db8ee9879d5e364b1d61ca0307d9`.

Before executing, read:
1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/handoff/ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/MASTER_REMEDIATION_PLAN.md`
6. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/OWNER_DECISIONS_RECORDED.yaml`
7. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/starter_pack/03_packets_phase2.md`
8. `~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_remaining_phase2/agent1_phase2_gate_rebaseline_closeout.md`
9. `~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_remaining_phase2/agent2_cogs_fx_profit_scout_closeout.md`
10. `~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_remaining_phase2/agent3_cash_anchor_scout_closeout.md`
11. `~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_remaining_phase2/agent4_returns_quar_sched_scout_closeout.md`
12. `~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_REMAINING_PHASE2_20260614_STARTERS/05_AGENT_5__SERIAL_WRITE_INTEGRATOR__AFTER_01_02_03_04.md`

Assigned closeout:
`~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_remaining_phase2/agent5_serial_write_integrator_closeout.md`

Role: single write-capable execution agent, but only after the orchestrator explicitly launches you. You are not eligible until agents 1-4 closeouts exist and the orchestrator has selected exactly one write lane.

Objective:
Execute the one serialized write lane named by the orchestrator at launch time, using the current closeouts as input. If no lane is explicitly named in the launch message, stop with `Gate: RED` and do not write.

Write contract:
- Backup first for any DB apply. Use `sqlite3 .backup`, not file copy.
- Dry-run before apply.
- No `--apply` without the lane's explicit env gate and the recorded owner decision/contract allowing it.
- Scope must match the accepted closeout and packet. Unexpected out-of-scope rows stop the lane.
- Update only the selected lane's necessary files and the assigned closeout. The orchestrator updates scoreboard/dashboard/status.

Forbidden:
- No concurrent DB writes.
- No broad refactors.
- No Meta/Instagram actions.
- No Kaspi/Repricer/Telegram/LaunchAgent external writes unless the selected lane explicitly authorizes them.
- No hidden manual DB inserts.
- No attempt to make all remaining lanes green in one mixed diff.

Closeout must include:
- Standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
- The selected lane.
- Backup path and integrity result if DB touched.
- Dry-run evidence, apply evidence, before/after counts, validators run, and rollback command.
- Exact files changed.
