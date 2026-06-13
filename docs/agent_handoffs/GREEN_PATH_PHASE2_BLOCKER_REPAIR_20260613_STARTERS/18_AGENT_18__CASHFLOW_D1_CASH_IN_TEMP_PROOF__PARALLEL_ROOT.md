# Agent 18 - Cashflow D1 Cash-In Temp Proof

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-06-13_green_path_resume/agent_18_cashflow_d1_cash_in_temp_proof_closeout.md`

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/KASPI_ORDER_CASHFLOW_TRACKING.md`
4. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/handoff/ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_REMAINING_BLOCKERS_20260613_STARTERS/RUN_CLOSEOUT.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-06-13_green_path_resume/agent_15_ab_internal_freshness_writer_closeout.md`
7. This starter prompt.

Role: prove the minimum safe path to clear `cashflow_source_truth` after Agent 15 made the AB cashflow child source fresh but C3 still blocks on `CASHFLOW_D1_CASH_IN_MISSING`.

Hard boundary:

- Do not mutate production `db/app.db`.
- Do not convert bank balance snapshots into fake order-level cash-in events.
- Do not write Telegram, LaunchAgents, Web_automation, Facebook_ads, Kaspi merchant state, workbooks, or customer/operator messages.
- You may create copied DBs with `sqlite3 db/app.db ".backup ..."` and apply only to those copies.

Allowed writes:

- Evidence under `~/Docs/Autonomous_business/exports/validation/agent18_cashflow_d1_cash_in_temp_proof_20260613/`
- Copied DBs under that evidence folder or `exports/validation/`
- Assigned closeout.
- Focused code/test patch only if a validator or translator bug blocks the copied-DB proof. If patching code, keep it narrowly scoped and do not apply production DB writes.

Tasks:

1. Reproduce the blocker read-only:

```bash
PYTHONPATH=. .venv/bin/python scripts/validate_order_cashflow_coverage.py --db db/app.db --as-of 2026-06-13 --strict --json
PYTHONPATH=. .venv/bin/python scripts/validate_policy_gate_results.py --db db/app.db --strict --json
```

2. Identify exact missing D1 cash-in rows, dates, stores, order IDs, line evidence state, and whether each row is eligible under the D1 delivered-order contract.
3. Create a copied DB via online backup, never raw `cp` from the hot DB:

```bash
sqlite3 db/app.db ".backup 'exports/validation/agent18_cashflow_d1_cash_in_temp_proof_20260613/agent18_cashflow_probe.db'"
```

4. On the copied DB only, test the existing order-to-cashflow translator path. Start with dry-run, then copied-DB apply only if the dry-run is scoped and sane:

```bash
PYTHONPATH=. .venv/bin/python scripts/translate_orders_to_cashflow_events.py --db exports/validation/agent18_cashflow_d1_cash_in_temp_proof_20260613/agent18_cashflow_probe.db --as-of 2026-06-13 --report-path exports/validation/agent18_cashflow_d1_cash_in_temp_proof_20260613/orders_to_cashflow_dryrun_report.txt
```

If the script requires different flags, inspect `--help`, use the repo-supported interface, and record the exact command.

5. If copied-DB apply is safe, use only the script's documented env gate and `--apply`. Then rebuild daily cashflow on the copy and materialize C3 gates on the copy.
6. Validate on copied DB:

```bash
sqlite3 -readonly exports/validation/agent18_cashflow_d1_cash_in_temp_proof_20260613/agent18_cashflow_probe.db 'PRAGMA integrity_check;'
PYTHONPATH=. .venv/bin/python scripts/validate_order_cashflow_coverage.py --db exports/validation/agent18_cashflow_d1_cash_in_temp_proof_20260613/agent18_cashflow_probe.db --as-of 2026-06-13 --strict --json
PYTHONPATH=. .venv/bin/python scripts/validate_cashflow_invariants.py --db exports/validation/agent18_cashflow_d1_cash_in_temp_proof_20260613/agent18_cashflow_probe.db
PYTHONPATH=. .venv/bin/python scripts/validate_policy_gate_results.py --db exports/validation/agent18_cashflow_d1_cash_in_temp_proof_20260613/agent18_cashflow_probe.db --strict --json
```

Closeout requirements:

- Standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
- Before/after counts for `cash_in_missing_count`, `duplicate_cash_in_count`, `balance_anchor_fake_cash_in_count`, `fact_cashflow_events`, and `fact_cashflow_daily` on the copied DB.
- Exact copied-DB commands, row counts, and validator results.
- If `GREEN`, include exact serialized production apply proposal with backup command, env gates, expected row deltas, and rollback path. Do not run it.
- If `YELLOW`, state the missing source/contract/code gap and the smallest next action.

