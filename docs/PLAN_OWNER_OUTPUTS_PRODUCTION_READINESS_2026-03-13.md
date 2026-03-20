# PLAN_OWNER_OUTPUTS_PRODUCTION_READINESS_2026-03-13

## Purpose
Take the current green owner-output activation layer and finish the last two production-readiness blockers:
1. stale PO-side stock snapshot invariant
2. live rerun parent-process hang

Then stamp the result into a clean committed release state so broader business modules can be reactivated in order.

This plan is not for:
- reopening WebUI archive truth work
- replay-mode changes
- scheduler/import parity proving
- broad module reactivation
- new source-truth arguments

Execution model:
- single-agent
- sequential
- fail-closed
- one worktree / branch only
- human only for prompt copy/paste unless a proven external auth issue appears

Baseline assumptions:
- active repo/worktree: `~/Docs/wt_webui_owner_truth_operationalization_v1`
- active branch: `codex/TASK-webui-owner-truth-operationalization-v1`
- current committed base from latest handoff: `6e1cbc3190793c6edd166fa1bd1847ddd25c06e1`
- current owner-output activation delta is local/uncommitted and must be frozen first
- rollback anchor: `exports/validation/owner_truth_release/2026-03-04/full_gates_green_final.md`
- current owner outputs already exist:
  - `owner_profit_daily`
  - `cash_risk_daily`
  - `cashflow_calendar_daily`
  - `po_sku_daily`
  - `owner_daily_brief`
- current green runtime gates remain green in the latest available artifacts
- no new WebUI scrape
- no replay-only fallback in live mode
- no DB write unless a new, separate necessity is proven for the PO snapshot path

Evidence root:
- `exports/validation/owner_outputs_production_readiness/2026-03-13/`

Global non-negotiables:
1. Do not break any current green runtime gate.
2. Do not fabricate logs or derived artifacts.
3. Do not widen scope into broader module reactivation until the activation layer is clean.
4. Do not hide the stale-planning trust label unless its freshness problem is actually fixed.
5. Do not claim completion unless both the PO invariant and the rerun clean-exit issue are green.

---

## Phase Q0 — Green Activation Freeze + Commit Split

### Goal (measurable)
Preserve the current owner-output activation delta and split it into atomic commit intentions before more edits.

### Inputs
- current worktree state
- latest owner-output activation docs and artifacts
- rollback anchor `exports/validation/owner_truth_release/2026-03-04/full_gates_green_final.md`

### Outputs
- `exports/validation/owner_outputs_production_readiness/2026-03-13/readcheck.md`
- `exports/validation/owner_outputs_production_readiness/2026-03-13/worktree_status.txt`
- `exports/validation/owner_outputs_production_readiness/2026-03-13/checkpoint_decision.md`
- one of:
  - checkpoint commit SHA(s)
  - or `exports/validation/owner_outputs_production_readiness/2026-03-13/worktree_checkpoint.patch`
- `exports/validation/owner_outputs_production_readiness/2026-03-13/commit_split_plan.md`

### Definition of Done
Accepted as done only when:
- exact branch/head are recorded
- current dirty delta is preserved safely
- rollback anchor is recorded
- commit split plan maps one intent per commit

### Validation/Gates
- `git rev-parse --abbrev-ref HEAD`
- `git rev-parse HEAD`
- `git status --short`
- `bash scripts/check_no_db_tracked.sh`
- `bash scripts/lint_docs.sh`

### Rollback / backout strategy
- revert/drop Q0 artifacts or reset to checkpoint commit
- no code changes and no DB writes in Q0

### Stop-the-line criteria
- unexplained head mismatch
- tracked/staged `.db` file appears
- dirty delta not preserved before edits

---

## Phase Q1 — PO Snapshot Freshness Closure

### Goal (measurable)
Make `python3 scripts/validate_po_dashboard_invariants.py` pass by fixing only the minimal stale-stock-snapshot readiness problem.

### Inputs
- current `po_sku_daily` outputs
- current PO/dashboard snapshot path
- `validate_po_dashboard_invariants.py`
- any canonical stock snapshot / PO-readiness refresh entrypoint already in the repo
- current trust semantics for stale planning snapshot

### Outputs
- `exports/validation/owner_outputs_production_readiness/2026-03-13/po_snapshot/po_snapshot_probe.json`
- `exports/validation/owner_outputs_production_readiness/2026-03-13/po_snapshot/po_snapshot_probe.md`
- `exports/validation/owner_outputs_production_readiness/2026-03-13/po_snapshot/refresh_decision.md`
- if code changes are needed:
  - updated relevant PO snapshot / PO readiness scripts
  - `tests/test_inventory_capital_radar.py`
- if a write is actually required:
  - `exports/validation/owner_outputs_production_readiness/2026-03-13/po_snapshot/db_backup_path.txt`
  - `exports/validation/owner_outputs_production_readiness/2026-03-13/po_snapshot/db_write_log.md`
  - `exports/validation/owner_outputs_production_readiness/2026-03-13/po_snapshot/before_after_diffs/`

### Definition of Done
Accepted as done only when:
- `validate_po_dashboard_invariants.py` passes
- the stale snapshot cause is explicitly documented
- the stale-planning trust label is either preserved honestly or upgraded with evidence
- no broader PO reactivation was mixed into the phase

### Validation/Gates
- `python3 scripts/validate_po_dashboard_invariants.py`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_inventory_capital_radar.py tests/test_owner_daily_surfaces.py`
- if snapshot refresh touched cashflow/PO logic:
  - `python3 scripts/validate_cashflow_invariants.py`

### Rollback / backout strategy
- if read-only fix: revert code/docs only
- if any write path is used: restore DB backup, invalidate downstream outputs, rerun invariant to confirm rollback

### Stop-the-line criteria
- any DB write without backup + env gate + `--apply`
- broad PO planning reactivation enters scope
- stale label is removed without evidence

---

## Phase Q2 — Live Runner Exit-Clean Fix

### Goal (measurable)
Make a fresh live rerun exit cleanly after producing green artifacts.

### Inputs
- `scripts/run_owner_truth_daily.py`
- any subprocess/runner wrappers it invokes
- current green runtime outputs

### Outputs
- `exports/validation/owner_outputs_production_readiness/2026-03-13/runner/runner_hang_probe.md`
- `exports/validation/owner_outputs_production_readiness/2026-03-13/runner/runner_fix_decision.md`
- if code changes are needed:
  - updated `scripts/run_owner_truth_daily.py`
  - targeted test(s) for clean exit behavior

### Definition of Done
Accepted as done only when:
- a fresh `run_owner_truth_daily.py --mode live --as-of 2026-03-09 --strict` exits 0 cleanly
- no manual `pkill` or process cleanup is needed
- green artifacts remain semantically the same

### Validation/Gates
- `./.venv/bin/python scripts/run_owner_truth_daily.py --mode live --as-of 2026-03-09 --strict`
- targeted pytest if runner code changes
- compare semantic outputs against prior green artifacts

### Rollback / backout strategy
- revert Q2 code/docs only
- preserve prior green artifacts for comparison

### Stop-the-line criteria
- any fix changes business output semantics
- any fix introduces replay fallback or artifact fabrication

---

## Phase Q3 — Full Production-Readiness Re-Prove

### Goal (measurable)
Re-run all relevant green gates plus the two new production-readiness gates together.

### Inputs
- Q1 and Q2 outputs
- current owner outputs and brief
- current release evidence

### Outputs
- `exports/validation/owner_outputs_production_readiness/2026-03-13/final_reprove/final_gate_report.md`
- refreshed current green artifacts if needed

### Definition of Done
Accepted as done only when all of these are green in one coherent pass:
- `validate_params.py --strict --as-of 2026-03-09`
- `validate_webui_archive_vs_current_db.py --range-policy full_range_owner_truth --strict`
- `run_owner_truth_daily.py --mode live --as-of 2026-03-09 --strict`
- `system_doctor.py --strict --project-root . --as-of 2026-03-09`
- `validate_po_dashboard_invariants.py`
- owner-surface tests
- `run_owner_review_cycle.py`

### Validation/Gates
- `bash scripts/check_no_db_tracked.sh`
- `bash scripts/lint_docs.sh`
- `python3 scripts/check_release_hygiene.py --strict --project-root .`
- `bash scripts/install_single_truth_ops_scheduler.sh --validate-only`
- `python3 scripts/check_anchor_health.py --project-root .`
- `./.venv/bin/python scripts/ops_status.py --project-root .`
- `AB_CRM_WORKBOOK_PATH=config/anchors/SALES_KSP_CRM_LATEST.xlsx python3 scripts/validate_params.py --strict --as-of 2026-03-09`
- `python3 scripts/validate_webui_archive_vs_current_db.py --start 2025-06-06 --end 2026-03-09 --range-policy full_range_owner_truth --statusdate-cutover 2026-02-27 --strict`
- `./.venv/bin/python scripts/run_owner_truth_daily.py --mode live --as-of 2026-03-09 --strict`
- `./.venv/bin/python scripts/system_doctor.py --strict --project-root . --as-of 2026-03-09`
- `python3 scripts/validate_po_dashboard_invariants.py`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_owner_daily_surfaces.py tests/test_owner_daily_brief.py tests/test_run_owner_review_cycle.py tests/test_cashflow_calendar_daily.py tests/test_inventory_capital_radar.py`
- `python3 -m py_compile scripts/build_owner_profit_daily.py scripts/build_cash_risk_daily.py scripts/build_po_sku_daily.py scripts/build_owner_daily_brief.py scripts/build_cashflow_calendar_daily.py scripts/run_owner_review_cycle.py`

### Rollback / backout strategy
- revert Q1/Q2/Q3 code only if any green gate regresses
- if any write path was used in Q1, restore DB backup before another attempt

### Stop-the-line criteria
- any previously green gate turns red
- any new blocker appears without classification
- outputs stay green only if manual process cleanup is required

---

## Phase Q4 — Release / Oracle Refresh from Clean Tip

### Goal (measurable)
Refresh release and Oracle evidence from a clean committed activation tip after Q3.

### Inputs
- Q3 green state
- current merge/release/oracle artifacts

### Outputs
- refreshed:
  - `merge_manifest.json`
  - `merge_manifest.md`
  - `full_gates_green_live_ops.md`
  - `PACK_SUMMARY.md`
  - `bundle.md`
  - `oracle_files_manifest.txt`
  - `ArchiveOrders_WEBUI_MERGED_ALL_STORES.csv`
- `exports/validation/owner_outputs_production_readiness/2026-03-13/release_refresh_report.md`

### Definition of Done
Accepted as done only when:
- release/oracle docs point to the clean committed activation tip
- rollback mapping is explicit
- canonical merged orders CSV is included
- `ok_to_merge` remains true

### Validation/Gates
- `bash scripts/lint_docs.sh`
- `bash scripts/check_no_db_tracked.sh`
- `python3 scripts/check_release_hygiene.py --strict --project-root .`

### Rollback / backout strategy
- revert Q4 docs/pack refresh only
- preserve prior green evidence

### Stop-the-line criteria
- release/oracle docs still point to dirty local-only state
- wrong canonical CSV is packed
- rollback mapping missing

---

## Phase Q5 — Business Module Reactivation Queue

### Goal (measurable)
Queue the next broader modules in business order after production readiness is truly complete.

### Inputs
- current scorecard
- current owner surfaces
- deferred module list

### Outputs
- `exports/validation/owner_outputs_production_readiness/2026-03-13/deferred_module_reactivation_queue.md`

### Definition of Done
Accepted as done only when the queue clearly orders:
- inventory analysis
- cashflow dashboard / calendar
- sales analysis
- pillow engine
- pillow dashboard

### Validation/Gates
- `bash scripts/lint_docs.sh`

### Rollback / backout strategy
- revert Q5 backlog doc only

### Stop-the-line criteria
- broader modules start before production readiness is complete
- unrelated architecture detours enter the closeout

---

## If attachments are missing — assumptions policy
- If older green packs conflict with the latest owner-output activation pack, prefer the latest activation pack plus current worktree.
- If the worktree contains additional local delta not represented in the current pack, freeze it first before edits.
- If no clean production-readiness freeze can be made safely, emit a checkpoint patch and stop instead of forcing packaging.
- If the PO snapshot freshness issue cannot be fixed without broader DB work, stop and spin out a separate write-gated plan rather than widening scope here.
- If any new red gate appears, stop and emit a fresh divergence/closeout pack before continuing.