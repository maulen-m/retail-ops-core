# Launch Order

Parallel wave now:
- `01_AGENT_1__PHASE2_GATE_REBASELINE__PARALLEL.md`
- `02_AGENT_2__COGS_FX_PROFIT_SCOUT__PARALLEL.md`
- `03_AGENT_3__CASH_ANCHOR_SCOUT__PARALLEL.md`
- `04_AGENT_4__RETURNS_QUAR_SCHED_SCOUT__PARALLEL.md`

Hold until all four closeouts are reviewed:
- `05_AGENT_5__SERIAL_WRITE_INTEGRATOR__AFTER_01_02_03_04.md`

Do not launch agent 5 automatically. The orchestrator must choose the next single write lane after reading closeouts.

After Agent 5 closeout review:
- `06_AGENT_6__CASH_ANCHOR_WRITER__AFTER_05.md`

After Agent 6 closeout review:
- `07_AGENT_7__RESIDUAL_SETTLEMENT_WRITER__AFTER_06.md`

Do not launch Agent 7 automatically before Agent 6 is independently verified. Agent 7 is the next single DB writer and must stop if the fresh 2026-06-14 residual dry-run does not match the exact 10-row re-baseline.

After Agent 7 closeout review:
- `08_AGENT_8__RESIDUAL_CORRECTED_WINDOW_WRITER__AFTER_07.md`

Agent 8 may launch only after Agent 7 proves no DB write occurred and the 10 rows are still present under the corrected `MIN..2026-06-14` report window. It must stop unless dry-run matches the exact 10-order allowlist.

After Agent 8 closeout review:
- `09_AGENT_9__SHIPPED_FREEZE_SCOUT__AFTER_08.md`
- `10_AGENT_10__COGS_AUTHORITY_SCOUT__AFTER_08.md`

Agents 9-10 are read-only and can run in parallel. They are scouts for the next writer choice; they must not mutate DB, code, dashboard/status, LaunchAgents, Telegram, external systems, or workbooks.
