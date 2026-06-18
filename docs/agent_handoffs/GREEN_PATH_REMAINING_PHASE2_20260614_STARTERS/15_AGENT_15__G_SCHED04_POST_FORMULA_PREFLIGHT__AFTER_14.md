# Agent 15 - G-SCHED-04 Post-Formula Preflight

Closeout path:

`~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_remaining_phase2/agent15_g_sched04_post_formula_preflight_closeout.md`

Gate expectation: `GREEN` if you complete the read-only preflight and produce a precise `G-SCHED-04` classification with no unexpected regressions; `YELLOW` if the preflight is stable but `G-SCHED-04` remains blocked by known data gates; `RED` if DB integrity, DB guard, daily-ops pause, residuals, or cashflow invariants regress.

## Role And Boundary

You are a read-only post-formula preflight agent. You may write only:

- the closeout file above
- scratch/evidence under `/tmp/green_path_scratch/g_sched04_post_formula_preflight_<timestamp>/`

No DB writes. No code edits. No dashboard/status/scoreboard/docs/config/plist/workbook writes. No LaunchAgent load/unload. No Telegram, Kaspi, Repricer, pricing, browser, customer, operator-message, or external-system writes. No `--apply`. No write-enable env vars.

Daily business automations must remain paused; do not resume/load anything.

## Must Read

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/green_path_run/STATUS.md`
5. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/green_path_run/scoreboard.csv`
6. `~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_remaining_phase2/agent13_shipped_freeze_formula_writer_closeout.md`
7. `~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_remaining_phase2/agent14_post_formula_authority_and_next_lane_scout_closeout.md`
8. `~/Docs/Autonomous_business/docs/plan/green_path_2026-06/green_gates.csv`

## Accepted Baseline

- Expected DB SHA: `d9a12a54ba32c77478abb6369980dce2a173de43e7a89fd48f991ae1b05604a1`
- `G-RESID-01` is PARTIAL: residual_count is 0, but freeze validator retains parked `956748585 / ACMEWEAR / LINE-21-TS_3XL`.
- `G-COGS-01/02/03` remain PARTIAL and exact owner COGS authority is absent for `953395459` and `956748585`.
- Daily ops should remain paused (`0/10 loaded`).

## Task

Run a read-only `G-SCHED-04` post-formula preflight re-check and classify the gate:

1. Prove DB boundary, integrity, DB guard, and no SQLite sidecars.
2. Prove daily ops remain paused using `manage_business_automation.py --evidence-root "$OUT/..." verify --scope daily-ops --expect paused`.
3. Re-run cashflow invariants, on-delivery residuals, and on-delivery freeze validator.
4. Inspect `green_gates.csv` for `G-SCHED-04` and, if a repo strict preflight command exists and is safely read-only, run it with output under `/tmp` and captured exit code. If it is missing or not safe/read-only, state that and rely on the component validators above.
5. Return exact classification:
   - Can `G-SCHED-04` flip from PENDING to GREEN now?
   - If not, should it become PARTIAL, remain PENDING, or be blocked? Name the exact retained blocker rows/classes.
   - What lane must run next to clear it?

## Required Command Skeleton

Use this shape, adapting only timestamp and strict-preflight command after inspection:

```bash
OUT="/tmp/green_path_scratch/g_sched04_post_formula_preflight_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUT"

shasum -a 256 db/app.db > "$OUT/01_db_sha.txt"
sqlite3 -readonly db/app.db 'PRAGMA integrity_check;' > "$OUT/02_integrity_check.txt"
scripts/check_no_db_tracked.sh > "$OUT/03_check_no_db_tracked.txt" 2>&1
find db -maxdepth 1 \( -name 'app.db-wal' -o -name 'app.db-shm' -o -name 'app.db-journal' \) -print | sort > "$OUT/04_sqlite_sidecars.txt"

python3 scripts/manage_business_automation.py \
  --evidence-root "$OUT/business_automation_verify" \
  verify --scope daily-ops --expect paused \
  > "$OUT/05_daily_ops_paused_verify.txt" 2>&1

.venv/bin/python scripts/validate_cashflow_invariants.py \
  --db db/app.db \
  > "$OUT/06_validate_cashflow_invariants.txt" 2>&1

.venv/bin/python scripts/check_on_delivery_residuals.py \
  --db db/app.db \
  --until 2026-06-14 \
  --output-dir "$OUT/check_on_delivery_residuals" \
  > "$OUT/07_check_on_delivery_residuals.txt" 2>&1

set +e
.venv/bin/python scripts/validate_on_delivery_freeze.py \
  --db db/app.db \
  --until 2026-06-14 \
  > "$OUT/08_validate_on_delivery_freeze.txt" 2>&1
FREEZE_RC=$?
printf "%s\n" "$FREEZE_RC" > "$OUT/08_validate_on_delivery_freeze.exit"
set -e

shasum -a 256 db/app.db > "$OUT/09_final_db_sha.txt"
find db -maxdepth 1 \( -name 'app.db-wal' -o -name 'app.db-shm' -o -name 'app.db-journal' \) -print | sort > "$OUT/10_sqlite_sidecars_after.txt"
```

## Stoplines

- Stop if DB SHA differs from `d9a12a54ba32c77478abb6369980dce2a173de43e7a89fd48f991ae1b05604a1`.
- Stop if integrity is not `ok`, DB guard fails, or SQLite sidecars appear.
- Stop if daily ops verifier does not report paused/OK.
- Stop if cashflow invariants fail.
- Stop if residual checker does not report `residual_count=0` and `STATUS=PASS`.
- `validate_on_delivery_freeze.py` may exit non-zero only if the sole retained failure is `956748585: status=SHIPPED has missing INVENTORY_ON_DELIVERY_COST balance (balance=0.00)`. Any other row/reason is a stopline.
- Stop if a strict preflight command requires writes, external systems, sends messages, loads LaunchAgents, or mutates repo/DB/workbook/config.

## Closeout Format

Include:

- standalone `Gate: GREEN|YELLOW|RED`
- evidence root
- DB SHA/integrity/guard results
- daily-ops pause result
- cashflow/residual/freeze results
- strict preflight command decision/result
- recommended `G-SCHED-04` scoreboard/dashboard state and exact evidence text
- next lane recommendation
- browser/MCP cleanup statement

Then record completion with the tmux orchestrator helper appended by the launcher. Do not manually ping the orchestrator.
