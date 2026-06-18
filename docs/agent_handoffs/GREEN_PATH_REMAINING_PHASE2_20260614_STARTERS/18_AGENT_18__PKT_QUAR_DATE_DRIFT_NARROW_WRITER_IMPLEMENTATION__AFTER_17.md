# Agent 18 - PKT-QUAR Date-Drift Narrow Writer Implementation

Closeout path:

`~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_remaining_phase2/agent18_pkt_quar_date_drift_narrow_writer_implementation_closeout.md`

Gate expectation: `GREEN` if you implement a narrow dry-run/default, env-gated date-drift writer, add focused tests, and prove copied-DB apply clears the workbook-anchor class without production DB mutation; `YELLOW` if code exists but copied-DB apply still does not clear the class; `RED` if production DB boundary/pause/guard regresses or any forbidden write occurs.

## Role And Boundary

You are a code-only implementation agent plus copied-DB rehearsal agent.

Allowed writes:

- `scripts/apply_workbook_anchor_date_drift_repair.py`
- focused test file(s) under `tests/`
- minimal config gate metadata if the repo uses it, likely `config/write_side_gating_manifest.yaml`
- the closeout file above
- scratch/evidence under `/tmp/green_path_scratch/pkt_quar_date_drift_narrow_writer_<timestamp>/`
- copied SQLite DB files under that `/tmp` folder

Forbidden writes:

- production `db/app.db`
- dashboard/status/scoreboard/green_path_run files
- workbooks
- LaunchAgents/plists
- Telegram, Kaspi, Repricer, pricing, browser, customer/operator-message, or external systems
- cashflow, COGS/profit overrides, stock ledger, PO payable data

No production DB `--apply`. No production write-enable env vars. Daily business automations must remain paused; do not resume/load anything.

## Must Read

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/green_path_run/STATUS.md`
5. `~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_remaining_phase2/agent17_pkt_quar_workbook_anchor_date_drift_rehearsal_closeout.md`
6. `scripts/classify_workbook_anchor_overages.py`
7. `scripts/rebuild_sales_fact_v2_from_kaspi_entries.py`
8. `scripts/validate_sales_against_workbook.py`
9. `tests/test_classify_workbook_anchor_overages.py`
10. `tests/test_rebuild_sales_fact_v2_anchor_precedence.py`

## Accepted Baseline

- Current accepted production DB SHA: `2d04788a36ced89de74bc135680cf068cde64615e3e0f1d65a2a6163ddb9b317`
- Agent17 evidence root: `/tmp/green_path_scratch/pkt_quar_workbook_anchor_date_drift_20260614_111409`
- Workbook-anchor class is fully classified: 9/9 refs, 0 unresolved, 6 failing dates, buckets only date drift/order-in-workbook-other-day.
- Existing full rebuild route is too broad: 51 inserts / 52 deletes.
- `G-SCHED-04` remains RED; COGS/freeze exact rows are owner-authority blocked and out of scope.
- Daily ops should remain paused (`0/10 loaded`).

## Implementation Contract

Add a narrow script, preferably:

`scripts/apply_workbook_anchor_date_drift_repair.py`

CLI must include:

- `--db`
- `--workbook`
- `--start`
- `--end`
- `--as-of`
- `--expected-error-references`
- `--expected-failing-dates`
- `--expected-unresolved-error-references`
- `--expected-units-overage`
- `--expected-net-overage-kzt`
- `--expected-pre-sha256` optional, required by future production writer
- `--backup-dir`
- `--output-dir`
- `--apply`

Behavior:

- Default is dry-run.
- Apply requires `--apply` and env `ENABLE_WORKBOOK_ANCHOR_DATE_DRIFT_REPAIR=1`.
- Candidate rows must be derived from the workbook-anchor classifier/source lineage and DB re-query, not from ad hoc hard-coded order IDs.
- The only allowed mutation is `sales_fact_v2.order_date` for exact date-drift candidates.
- Do not insert or delete sales rows.
- Do not touch COGS/profit/cashflow/stock/workbook/PO/config/external surfaces.
- Fail closed unless the pre-repair classifier exactly matches:
  - `error_references_total=9`
  - `unique_failing_dates=6`
  - `unresolved_error_references=0`
  - `units_overage=17.0`
  - `net_overage_kzt=278207.01`
  - buckets only `KASPI_REBUILD_DATE_DRIFT` and `INTERNAL_SOURCE_DATE_DRIFT`
  - pair status only `ORDER_IN_WB_OTHER_DAY`
- Emit JSON/CSV evidence with candidate rows, before/after dates, dry-run/apply mode, pre/post validator summaries, and backup metadata.
- For apply, create a SQLite backup with `.backup` or repo helper before mutating the target DB path.

Focused tests:

- dry-run does not mutate `sales_fact_v2`
- apply requires both env gate and `--apply`
- candidate selection refuses unresolved classifier rows or unexpected buckets
- apply updates only `sales_fact_v2.order_date`
- backup/pre-SHA behavior is enforced
- copied-DB post-apply replay can run validators in the intended order

## Required Copied-DB Rehearsal

After implementation and focused tests, run on copied DB only:

```bash
OUT="/tmp/green_path_scratch/pkt_quar_date_drift_narrow_writer_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUT"

shasum -a 256 db/app.db > "$OUT/01_production_db_sha.txt"
sqlite3 -readonly db/app.db 'PRAGMA integrity_check; PRAGMA schema_version; PRAGMA user_version;' > "$OUT/02_production_integrity_pragmas.txt"
scripts/check_no_db_tracked.sh > "$OUT/03_check_no_db_tracked.txt" 2>&1
find db -maxdepth 1 \( -name 'app.db-wal' -o -name 'app.db-shm' -o -name 'app.db-journal' \) -print | sort > "$OUT/04_sqlite_sidecars.txt"
python3 scripts/manage_business_automation.py --evidence-root "$OUT/business_automation_verify" verify --scope daily-ops --expect paused > "$OUT/05_daily_ops_paused_verify.txt" 2>&1

sqlite3 db/app.db ".backup '$OUT/app_copy.db'"
sqlite3 "$OUT/app_copy.db" 'PRAGMA integrity_check;' > "$OUT/06_copy_integrity.txt"

.venv/bin/python scripts/apply_workbook_anchor_date_drift_repair.py \
  --db "$OUT/app_copy.db" \
  --workbook excel_ui/SALES_KSP_CRM_V3.xlsx \
  --start 2026-05-30 \
  --end 2026-06-08 \
  --as-of 2026-06-12 \
  --expected-error-references 9 \
  --expected-failing-dates 6 \
  --expected-unresolved-error-references 0 \
  --expected-units-overage 17.0 \
  --expected-net-overage-kzt 278207.01 \
  --output-dir "$OUT/date_drift_repair_dry_run" \
  > "$OUT/07_date_drift_repair_dry_run.txt" 2>&1

ENABLE_WORKBOOK_ANCHOR_DATE_DRIFT_REPAIR=1 \
.venv/bin/python scripts/apply_workbook_anchor_date_drift_repair.py \
  --db "$OUT/app_copy.db" \
  --workbook excel_ui/SALES_KSP_CRM_V3.xlsx \
  --start 2026-05-30 \
  --end 2026-06-08 \
  --as-of 2026-06-12 \
  --expected-error-references 9 \
  --expected-failing-dates 6 \
  --expected-unresolved-error-references 0 \
  --expected-units-overage 17.0 \
  --expected-net-overage-kzt 278207.01 \
  --backup-dir "$OUT/backup" \
  --output-dir "$OUT/date_drift_repair_apply" \
  --apply \
  > "$OUT/08_date_drift_repair_apply.txt" 2>&1

.venv/bin/python scripts/validate_sales_vs_workbook_anchor.py \
  --db "$OUT/app_copy.db" \
  --workbook excel_ui/SALES_KSP_CRM_V3.xlsx \
  --as-of 2026-06-12 \
  > "$OUT/09_validate_sales_vs_workbook_anchor_after.txt" 2>&1

.venv/bin/python scripts/classify_workbook_anchor_overages.py \
  --db "$OUT/app_copy.db" \
  --workbook excel_ui/SALES_KSP_CRM_V3.xlsx \
  --start 2026-05-30 \
  --end 2026-06-08 \
  --output-dir "$OUT/workbook_anchor_overages_after" \
  --strict \
  > "$OUT/10_classify_workbook_anchor_overages_after.txt" 2>&1

shasum -a 256 db/app.db > "$OUT/11_final_production_db_sha.txt"
find db -maxdepth 1 \( -name 'app.db-wal' -o -name 'app.db-shm' -o -name 'app.db-journal' \) -print | sort > "$OUT/12_sqlite_sidecars_after.txt"
```

## Stoplines

- Stop and write `Gate: RED` if production DB SHA changes.
- Stop and write `Gate: RED` if production integrity/guard/sidecars or daily-ops pause regresses.
- Stop if implementation would need production DB writes in this lane.
- Stop if copied-DB apply would update anything except `sales_fact_v2.order_date`.
- Stop if copied-DB post-apply `validate_sales_vs_workbook_anchor.py --as-of 2026-06-12` does not improve or if the same 9 errors remain.
- Stop if strict preflight or validators introduce unrelated new failure classes due to your code.

## Closeout Format

Include:

- standalone `Gate: GREEN|YELLOW|RED`
- files changed
- evidence root
- focused tests run and results
- copied-DB dry-run/apply result
- post-apply validator results
- production DB SHA/integrity/guard/pause proof
- next production writer command if GREEN, or exact blocker if YELLOW/RED
- browser/MCP cleanup statement

Then record completion with the tmux orchestrator helper appended by the launcher. Do not manually ping the orchestrator.

Assigned closeout path for this Agent 18 task:

`~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_remaining_phase2/agent18_pkt_quar_date_drift_narrow_writer_implementation_closeout.md`
