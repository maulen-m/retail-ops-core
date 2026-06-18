# Agent 16 - G-SCHED-04 Failure Classifier After DB-Boundary Hardening

Closeout path:

`~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_remaining_phase2/agent16_g_sched04_failure_classifier_closeout.md`

Gate expectation: `GREEN` if you fully classify the current strict-preflight failure classes and return the safest next executable lane; `YELLOW` if classification is incomplete but no boundary regresses; `RED` if DB integrity/guard/SHA/pause state regresses or any forbidden write occurs.

## Role And Boundary

You are a read-only classifier. You may write only:

- the closeout file above
- scratch/evidence under `/tmp/green_path_scratch/g_sched04_failure_classifier_<timestamp>/`

No DB writes. No code edits. No dashboard/status/scoreboard/docs/config/plist/workbook writes. No LaunchAgent load/unload. No Telegram, Kaspi, Repricer, pricing, browser, customer, operator-message, or external-system writes. No `--apply`. No write-enable env vars.

Daily business automations must remain paused; do not resume/load anything.

If a probe needs sales truth views or any command may create/drop derived SQLite views, run it only on a copied DB under `/tmp` using SQLite `.backup` or the repo's validation-copy helper. Do not run a view-refreshing command directly against production `db/app.db`.

## Must Read

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/green_path_run/STATUS.md`
5. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/green_path_run/scoreboard.csv`
6. `~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_remaining_phase2/agent15_g_sched04_post_formula_preflight_closeout.md`
7. `/tmp/green_path_scratch/g_sched04_db_boundary_hardening_20260614_104411/03_strict_preflight_stdout.txt`
8. `/tmp/green_path_scratch/g_sched04_db_boundary_hardening_20260614_104411/11_sha_compare.txt`
9. `~/Docs/Autonomous_business/docs/plan/green_path_2026-06/green_gates.csv`

## Accepted Baseline

- Current accepted production DB SHA: `2d04788a36ced89de74bc135680cf068cde64615e3e0f1d65a2a6163ddb9b317`
- DB integrity is ok and DB guard is ok after strict-preflight hardening.
- `G-SCHED-04` is RED because strict preflight still exits rc=1 on data gates.
- `G-RESID-01` is PARTIAL: current residual_count is 0, and focused current freeze retains parked `956748585 / ACMEWEAR / LINE-21-TS_3XL`.
- Exact owner COGS authority is absent for `953395459 / ACMEWEAR / LINE-31-LS_XL` and `956748585 / ACMEWEAR / LINE-21-TS_3XL`; do not invent it.
- Daily ops should remain paused (`0/10 loaded`).

## Task

Classify the remaining strict-preflight failure classes into route-ready lanes:

1. Prove current DB boundary: SHA, integrity, DB guard, no SQLite sidecars before and after your work.
2. Prove daily ops remain paused using `manage_business_automation.py --evidence-root "$OUT/..." verify --scope daily-ops --expect paused`.
3. Parse the hardened strict-preflight output and classify each current class:
   - `single_truth_system: PO-5.2 To_pay_BASE_KZT workbook/db mismatch`
   - `on_delivery_freeze` historical rows resolved at strict as_of `2026-06-12`, and the current parked `956748585` row
   - `sales_workbook_anchor` overages for 2026-05-30, 2026-05-31, 2026-06-01, 2026-06-02, 2026-06-05, and 2026-06-08
   - `cogs_integrity` and `profit_publication_integrity` unresolved LINE-31-LS / Business Insides / PO dashboard markers
4. For each class, state:
   - likely source table/artifact
   - whether it is no-human executable now, owner-approval required, or should remain parked
   - the minimum next writer/scout lane with exact allowed write scope, or exact owner approval phrase if needed
5. Recommend exactly one next lane for the orchestrator to launch after you, prioritizing maximum `G-SCHED-04` reduction without human input and without broad writes.

## Helpful Commands

Use only read-only/copy-safe variants. Adapt paths/timestamps:

```bash
OUT="/tmp/green_path_scratch/g_sched04_failure_classifier_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUT"

shasum -a 256 db/app.db > "$OUT/01_db_sha.txt"
sqlite3 -readonly db/app.db 'PRAGMA integrity_check; PRAGMA schema_version; PRAGMA user_version;' > "$OUT/02_integrity_pragmas.txt"
scripts/check_no_db_tracked.sh > "$OUT/03_check_no_db_tracked.txt" 2>&1
find db -maxdepth 1 \( -name 'app.db-wal' -o -name 'app.db-shm' -o -name 'app.db-journal' \) -print | sort > "$OUT/04_sqlite_sidecars.txt"

python3 scripts/manage_business_automation.py \
  --evidence-root "$OUT/business_automation_verify" \
  verify --scope daily-ops --expect paused \
  > "$OUT/05_daily_ops_paused_verify.txt" 2>&1

sqlite3 db/app.db ".backup '$OUT/app_classifier_copy.db'"
sqlite3 "$OUT/app_classifier_copy.db" 'PRAGMA integrity_check;' > "$OUT/06_copy_integrity.txt"
```

If you rerun strict preflight, use the hardened wrapper only and capture output under `$OUT`; it is expected to exit non-zero until data lanes are repaired:

```bash
set +e
.venv/bin/python scripts/run_strict_daily_preflight.py \
  --db db/app.db \
  --workbook excel_ui/SALES_KSP_CRM_V3.xlsx \
  --no-ensure-business-insides \
  --no-emit-drift-pack \
  > "$OUT/strict_stdout.txt" 2> "$OUT/strict_stderr.txt"
STRICT_RC=$?
printf "%s\n" "$STRICT_RC" > "$OUT/strict.exit"
set -e
```

## Stoplines

- Stop and write `Gate: RED` if production DB SHA differs from the accepted baseline above after your work.
- Stop and write `Gate: RED` if integrity is not `ok`, DB guard fails, SQLite sidecars appear, or daily ops are not paused.
- Stop and write `Gate: RED` if any command needs production DB writes, external systems, workbooks, LaunchAgents, Telegram, browser, pricing, or customer/operator surfaces.
- Do not recommend a production COGS override unless exact owner production COGS authority exists in current repo artifacts.

## Closeout Format

Include:

- standalone `Gate: GREEN|YELLOW|RED`
- evidence root
- DB SHA/integrity/guard/sidecar/daily-pause results
- strict failure class table
- no-human lanes vs owner-required lanes
- one recommended next lane with exact allowed write scope and stoplines
- exact scoreboard/dashboard recommendation for `G-SCHED-04`
- browser/MCP cleanup statement

Then record completion with the tmux orchestrator helper appended by the launcher. Do not manually ping the orchestrator.

Assigned closeout path for this Agent 16 task:

`~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_remaining_phase2/agent16_g_sched04_failure_classifier_closeout.md`
