# Agent 15 - AB Internal Freshness Writer

Assigned closeout:
`~/Docs/Autonomous_business_agent_handoffs/2026-06-13_green_path_resume/agent_15_ab_internal_freshness_writer_closeout.md`

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/handoff/ORCHESTRATOR_HANDOFF.md`
4. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/GREEN_PATH_RESUME_ADDENDUM_20260613.md`
5. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/OWNER_DECISIONS_RECORDED.yaml`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-06-13_green_path_resume/agent_5_pkt_lines_writer_closeout.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-06-13_green_path_resume/agent_11_pkt_resid_writer_closeout.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-06-13_green_path_resume/agent_12_pkt_fx_hardener_closeout.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-06-13_green_path_resume/agent_14_bank_source_route_closeout.md`
10. This starter prompt.

Role: clear the internal Autonomous_business child-source freshness blockers if safely possible.

Current assigned blockers:

- `src_ab_db_cashflow_truth`: `fact_cashflow_daily` stale at `2026-05-31`.
- `src_ab_db_sales_truth`: `sales_fact_v2` stale at `2026-05-31`.
- `src_ab_db_stock_truth`: `fact_inventory_snapshot_size` and `stock_ledger` stale at `2026-05-31`.
- `src_ab_db_ads_truth`: ads tables stale at `2026-05-11`; only touch this if an existing governed AB-side materializer can safely refresh from already accepted local evidence. Do not fetch ads externally in this lane.

Scope:

- Allowed writes: `~/Docs/Autonomous_business` code/tests, assigned evidence, assigned closeout, and production `db/app.db` only through env-gated repo scripts with backups.
- Forbidden writes: Web_automation, Facebook_ads, ad-platform APIs, Kaspi merchant writes, Telegram, workbooks, LaunchAgents, shell-sourcing `.env`, and any customer/operator messaging.
- You have the only AB production DB write lease for this wave. Do not run concurrent DB writers.

Safety contract:

- Verify daily ops are paused before any apply:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/manage_business_automation.py verify --scope daily-ops --expect paused
```

- Before any production DB apply, create an evidence folder under:

```text
~/Docs/Autonomous_business/exports/validation/agent15_ab_internal_freshness_20260613/
```

- Copy `db/app.db` into that evidence folder before the first write and record sha256.
- Run dry-runs first. Apply only if the dry-run is scoped and sane.
- Use existing env gates only:
  - `ENABLE_SALES_FACT_V2_REBUILD_APPLY=1`
  - `ENABLE_STOCK_LEDGER_SALES_REPLAY_WRITE=1`
  - `ENABLE_CASHFLOW_WRITE=1`
  - `ENABLE_C3_POLICY_MATERIALIZATION_WRITE=1`
- If a necessary script lacks an env gate or backup behavior, stop that sublane as YELLOW and harden it with focused tests before any apply.

Likely command sequence to evaluate:

```bash
PYTHONPATH=. .venv/bin/python scripts/rebuild_sales_fact_v2_from_kaspi_entries.py --db db/app.db --as-of 2026-06-13 --start-date 2026-06-01 --output-root exports/validation/agent15_ab_internal_freshness_20260613/sales_fact_v2_rebuild --backup-root exports/validation/agent15_ab_internal_freshness_20260613/backups --strict
```

```bash
ENABLE_SALES_FACT_V2_REBUILD_APPLY=1 PYTHONPATH=. .venv/bin/python scripts/rebuild_sales_fact_v2_from_kaspi_entries.py --db db/app.db --as-of 2026-06-13 --start-date 2026-06-01 --output-root exports/validation/agent15_ab_internal_freshness_20260613/sales_fact_v2_rebuild --backup-root exports/validation/agent15_ab_internal_freshness_20260613/backups --strict --apply
```

```bash
PYTHONPATH=. .venv/bin/python scripts/materialize_stock_ledger_sales_from_sales_fact_v2.py --db db/app.db --start-date 2026-06-01 --end-date 2026-06-13 --output-root exports/validation/agent15_ab_internal_freshness_20260613/stock_ledger_sales_replay
```

```bash
ENABLE_STOCK_LEDGER_SALES_REPLAY_WRITE=1 PYTHONPATH=. .venv/bin/python scripts/materialize_stock_ledger_sales_from_sales_fact_v2.py --db db/app.db --start-date 2026-06-01 --end-date 2026-06-13 --output-root exports/validation/agent15_ab_internal_freshness_20260613/stock_ledger_sales_replay --apply
```

```bash
PYTHONPATH=. .venv/bin/python scripts/rebuild_snapshot.py --db db/app.db --date 2026-06-13 --store UNIVERSAL --mode ledger --compare
```

```bash
PYTHONPATH=. .venv/bin/python scripts/rebuild_snapshot.py --db db/app.db --date 2026-06-13 --store UNIVERSAL --mode ledger --compare --apply
```

```bash
PYTHONPATH=. .venv/bin/python scripts/rebuild_cashflow_calendar.py --db db/app.db --start-date 2026-06-01 --end-date 2026-06-13 --run-id agent15_cashflow_daily_20260613
```

```bash
ENABLE_CASHFLOW_WRITE=1 PYTHONPATH=. .venv/bin/python scripts/rebuild_cashflow_calendar.py --db db/app.db --start-date 2026-06-01 --end-date 2026-06-13 --run-id agent15_cashflow_daily_20260613 --apply
```

After any successful applies, materialize source freshness and gates for 2026-06-13:

```bash
ENABLE_C3_POLICY_MATERIALIZATION_WRITE=1 PYTHONPATH=. .venv/bin/python scripts/materialize_policy_source_freshness.py --db db/app.db --as-of 2026-06-13 --run-id agent15_internal_freshness_sources_20260613 --backup-dir exports/validation/agent15_ab_internal_freshness_20260613/backups --apply --json
ENABLE_C3_POLICY_MATERIALIZATION_WRITE=1 PYTHONPATH=. .venv/bin/python scripts/materialize_policy_gate_results.py --db db/app.db --as-of 2026-06-13 --run-id agent15_internal_freshness_gates_20260613 --backup-dir exports/validation/agent15_ab_internal_freshness_20260613/backups --apply --json
```

Validation:

```bash
sqlite3 -readonly db/app.db 'PRAGMA integrity_check;'
scripts/check_no_db_tracked.sh
PYTHONPATH=. .venv/bin/python scripts/validate_policy_source_freshness.py --db db/app.db --as-of 2026-06-13 --strict --json
PYTHONPATH=. .venv/bin/python scripts/validate_policy_gate_results.py --db db/app.db --strict --json
PYTHONPATH=. .venv/bin/python scripts/validate_cashflow_invariants.py --db db/app.db
PYTHONPATH=. .venv/bin/python scripts/validate_ledger.py --db db/app.db
PYTHONPATH=. .venv/bin/python scripts/validate_inventory_cost_drift.py --db db/app.db --as-of 2026-06-13
```

Closeout requirements:

- Standalone line `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
- State exactly which child sources became FRESH and which remain blocked.
- Include before/after max dates and row counts for `sales_fact_v2`, `stock_ledger`, `fact_inventory_snapshot_size`, `fact_cashflow_daily`, and any ads tables you touched.
- Include all backup paths and sha256s.
- Include commands run and validator results.
- Use `Gate: GREEN` only if your assigned internal child blockers are cleared or explicitly proven not safely clearable because of a non-code source gap with all safe sublanes applied.
- Use `Gate: YELLOW` for partial clearance with honest remaining blockers.
- Use `Gate: RED` if a production write failed or rollback is needed.
