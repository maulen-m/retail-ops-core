# Agent 17 - PKT-QUAR Workbook-Anchor Date-Drift Copied-DB Rehearsal

Closeout path:

`~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_remaining_phase2/agent17_pkt_quar_workbook_anchor_date_drift_rehearsal_closeout.md`

Gate expectation: `GREEN` if you prove the workbook-anchor date-drift class is fully classified on a copied DB and return an exact safe next production route; `YELLOW` if only a broad rebuild route exists or a new narrow implementation is needed; `RED` if DB boundary/pause/guard regresses or any forbidden write occurs.

## Role And Boundary

You are a copied-DB/read-only rehearsal agent for `PKT-QUAR_WORKBOOK_ANCHOR_DATE_DRIFT_COPIED_DB_REHEARSAL`.

You may write only:

- the closeout file above
- scratch/evidence under `/tmp/green_path_scratch/pkt_quar_workbook_anchor_date_drift_<timestamp>/`
- copied SQLite DB files under that `/tmp` folder

No production DB writes. No code edits. No dashboard/status/scoreboard/docs/config/plist/workbook writes. No LaunchAgent load/unload. No Telegram, Kaspi, Repricer, pricing, browser, customer, operator-message, or external-system writes. No production `--apply`. No write-enable env vars.

Daily business automations must remain paused; do not resume/load anything.

## Must Read

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/green_path_run/STATUS.md`
5. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/green_path_run/scoreboard.csv`
6. `~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_remaining_phase2/agent16_g_sched04_failure_classifier_closeout.md`
7. `~/Docs/Autonomous_business/docs/plan/green_path_2026-06/green_gates.csv`

## Accepted Baseline

- Current accepted production DB SHA: `2d04788a36ced89de74bc135680cf068cde64615e3e0f1d65a2a6163ddb9b317`
- `G-SCHED-04` remains RED on data gates.
- Agent16 classified all 9 `sales_workbook_anchor` errors with zero unresolved references, mostly date drift.
- COGS/freeze exact rows are owner-authority blocked and out of scope.
- Daily ops should remain paused (`0/10 loaded`).

## Task

Rehearse the workbook-anchor date-drift class on a copied DB only:

1. Prove production DB boundary before and after: SHA, integrity, DB guard, no SQLite sidecars.
2. Prove daily ops remain paused using `manage_business_automation.py --evidence-root "$OUT/..." verify --scope daily-ops --expect paused`.
3. Create a copied DB under `/tmp` with SQLite `.backup` and prove copied DB integrity.
4. Re-run `classify_workbook_anchor_overages.py` against the copied DB for `2026-05-30..2026-06-08`; require 9/9 classified and 0 unresolved references.
5. Re-run `validate_sales_vs_workbook_anchor.py` before any copied-DB mutation; require the known 9 errors.
6. Inspect existing routes (`rebuild_sales_fact_v2_from_kaspi_entries.py`, `sync_sales_workbook_anchor.py`, related tests/docs) and determine whether an exact production writer can be launched next without code changes.
7. If a copied-DB `--apply` rehearsal is clearly safe and targets only the copied DB, you may run it only on the copied DB and only if no write-enable env var is needed. If the available route remains broad, do not run copied-DB apply; classify it as needing a narrow implementation/writer first.
8. Return exactly one next recommendation:
   - exact production writer lane if safe now, with allowed write scope and stoplines; or
   - narrow code/writer implementation lane if existing routes are too broad; or
   - stop/owner-needed if evidence shows this cannot be fixed without owner input.

## Required Command Skeleton

Adapt only timestamp and output filenames:

```bash
OUT="/tmp/green_path_scratch/pkt_quar_workbook_anchor_date_drift_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUT"

shasum -a 256 db/app.db > "$OUT/01_db_sha.txt"
sqlite3 -readonly db/app.db 'PRAGMA integrity_check; PRAGMA schema_version; PRAGMA user_version;' > "$OUT/02_integrity_pragmas.txt"
scripts/check_no_db_tracked.sh > "$OUT/03_check_no_db_tracked.txt" 2>&1
find db -maxdepth 1 \( -name 'app.db-wal' -o -name 'app.db-shm' -o -name 'app.db-journal' \) -print | sort > "$OUT/04_sqlite_sidecars.txt"

python3 scripts/manage_business_automation.py \
  --evidence-root "$OUT/business_automation_verify" \
  verify --scope daily-ops --expect paused \
  > "$OUT/05_daily_ops_paused_verify.txt" 2>&1

sqlite3 db/app.db ".backup '$OUT/app_quar_rehearsal.db'"
sqlite3 "$OUT/app_quar_rehearsal.db" 'PRAGMA integrity_check;' > "$OUT/06_copy_integrity.txt"

.venv/bin/python scripts/classify_workbook_anchor_overages.py \
  --db "$OUT/app_quar_rehearsal.db" \
  --workbook excel_ui/SALES_KSP_CRM_V3.xlsx \
  --start 2026-05-30 \
  --end 2026-06-08 \
  --output-dir "$OUT/workbook_anchor_overages" \
  --strict \
  > "$OUT/07_classify_workbook_anchor_overages.txt" 2>&1

set +e
.venv/bin/python scripts/validate_sales_vs_workbook_anchor.py \
  --db "$OUT/app_quar_rehearsal.db" \
  --workbook excel_ui/SALES_KSP_CRM_V3.xlsx \
  --as-of 2026-06-12 \
  > "$OUT/08_validate_sales_vs_workbook_anchor_before.txt" 2>&1
ANCHOR_RC=$?
printf "%s\n" "$ANCHOR_RC" > "$OUT/08_validate_sales_vs_workbook_anchor_before.exit"
set -e

.venv/bin/python scripts/rebuild_sales_fact_v2_from_kaspi_entries.py \
  --db "$OUT/app_quar_rehearsal.db" \
  --as-of 2026-06-08 \
  --start-date 2026-05-30 \
  --output-root "$OUT/rebuild_sales_fact_v2_dry_run" \
  --backup-root "$OUT/rebuild_sales_fact_v2_backup_unused" \
  --strict \
  > "$OUT/09_rebuild_sales_fact_v2_dry_run.txt" 2>&1

shasum -a 256 db/app.db > "$OUT/10_final_production_db_sha.txt"
find db -maxdepth 1 \( -name 'app.db-wal' -o -name 'app.db-shm' -o -name 'app.db-journal' \) -print | sort > "$OUT/11_sqlite_sidecars_after.txt"
```

## Stoplines

- Stop and write `Gate: RED` if production DB SHA differs from the accepted baseline after your work.
- Stop and write `Gate: RED` if integrity is not `ok`, DB guard fails, SQLite sidecars appear, or daily ops are not paused.
- Stop if classifier has unresolved references or root-cause buckets outside date drift / order-in-workbook-other-day.
- Stop if the route would alter COGS, profit overrides, cashflow, stock ledger, workbook, dashboard/status/scoreboard, external systems, or customer/operator surfaces.
- Stop if the only available production route is broad (`sales_fact_v2` thousands/100+ row changes); recommend a narrow implementation first.

## Closeout Format

Include:

- standalone `Gate: GREEN|YELLOW|RED`
- evidence root
- DB SHA/integrity/guard/sidecar/daily-pause results
- classifier metrics and root-cause buckets
- before-anchor validator result
- rebuild/sync route assessment
- one recommended next lane with exact allowed write scope and stoplines
- exact scoreboard/dashboard recommendation for `G-QUAR-*` and `G-SCHED-04`
- browser/MCP cleanup statement

Then record completion with the tmux orchestrator helper appended by the launcher. Do not manually ping the orchestrator.

Assigned closeout path for this Agent 17 task:

`~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_remaining_phase2/agent17_pkt_quar_workbook_anchor_date_drift_rehearsal_closeout.md`
