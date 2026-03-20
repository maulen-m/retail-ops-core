# PLAN_OWNER_TRUTH_GREEN_CLOSEOUT_HARDENING_2026-03-12

## Purpose
Take the current green owner-truth closeout on `codex/TASK-webui-owner-truth-operationalization-v1` and harden it into a clean, committed, rollback-safe, owner-trustworthy release state.

This plan does **not** reopen:
- WebUI source acquisition
- full-range historical debt cleanup beyond current contract buckets
- scheduler/import parity proving with `AB_INCLUDE_OPS_SELECTION_PARITY=1`
- broader owner-daily expansion beyond the three current surfaces

Execution model:
- single-agent
- sequential
- fail-closed
- one worktree / branch only
- human only for prompt copy/paste unless a proven external auth issue appears

Baseline assumptions:
- active repo/worktree: `~/Docs/wt_webui_owner_truth_operationalization_v1`
- active branch: `codex/TASK-webui-owner-truth-operationalization-v1`
- current head: `b6d6bbe684ba0204ddbcab66b8928d2d765bbabb`
- baseline release commit: `86ce447782a005c47ac3d1b61dde8414900320a8`
- rollback anchor: `exports/validation/owner_truth_release/2026-03-04/full_gates_green_final.md`
- latest merge manifest is GREEN but current worktree still has phase-local delta
- `Owner Profit Daily` is green but semantically provisional
- `Cash Risk Daily` and `PO / SKU Daily` are green live-chain outputs

Evidence root:
- `exports/validation/owner_truth_green_closeout_hardening/2026-03-12/`

Global non-negotiables:
1. Do not break any of the four current green gates.
2. Do not fabricate logs or derived artifacts.
3. Do not introduce replay fallback into live mode.
4. Do not reopen source-truth debates or historical cleanup outside the deferred scope.
5. Do not claim “finished” until the green state is committed and `Owner Profit Daily` semantics are explicitly settled.

---

## Phase C0 — Green-State Freeze + Commit Hygiene

### Goal (measurable)
Preserve the current green local delta, then split it into atomic, reviewable commits.

### Inputs
- current green worktree
- `merge_manifest.json`
- `merge_manifest.md`
- `full_gates_green_live_ops.md`
- rollback anchor `exports/validation/owner_truth_release/2026-03-04/full_gates_green_final.md`

### Outputs
- `exports/validation/owner_truth_green_closeout_hardening/2026-03-12/readcheck.md`
- `exports/validation/owner_truth_green_closeout_hardening/2026-03-12/worktree_status.txt`
- `exports/validation/owner_truth_green_closeout_hardening/2026-03-12/checkpoint_decision.md`
- one of:
  - checkpoint commit SHA(s) in `checkpoint_decision.md`
  - or `exports/validation/owner_truth_green_closeout_hardening/2026-03-12/worktree_checkpoint.patch`
- `exports/validation/owner_truth_green_closeout_hardening/2026-03-12/commit_split_plan.md`

### Definition of Done
Accepted as done only when:
- exact branch/head are recorded
- dirty/clean state is recorded
- rollback anchor is recorded
- current green delta is preserved safely
- commit split plan maps one intent per commit

### Validation/Gates
- `git rev-parse --abbrev-ref HEAD`
- `git rev-parse HEAD`
- `git status --short`
- `bash scripts/check_no_db_tracked.sh`
- `bash scripts/lint_docs.sh`

### Rollback / backout strategy
- revert/drop only C0 artifacts or reset to checkpoint commit
- no DB writes and no code changes in C0

### Stop-the-line criteria
- unexplained head mismatch
- tracked/staged `.db` file appears
- dirty delta is not preserved before edits

---

## Phase C1 — Owner Profit Semantics Unlock

### Goal (measurable)
Convert `Owner Profit Daily` from `PASS_PROVISIONAL_DERIVED_FROM_GREEN_LIVE_CHAIN` to a fully unlocked decision-grade semantics state without breaking upstream green gates.

### Inputs
- `build_owner_profit_daily.py`
- `owner_profit_daily.json`
- `owner_profit_daily.md`
- `trust_report.json`
- current upstream profit lock semantics (`profit_locked=true` behavior)
- scorecard priorities

### Outputs
- `docs/validation/OWNER_PROFIT_DAILY_SEMANTICS_CONTRACT.md`
- updated `build_owner_profit_daily.py` if needed
- updated `test_owner_daily_surfaces.py` and/or a new targeted semantics contract test
- refreshed:
  - `exports/owner/2026-03-09/owner_profit_daily.json`
  - `exports/owner/2026-03-09/owner_profit_daily.md`
  - `exports/validation/owner_profit_daily/2026-03-09/trust_report.json`
- `exports/validation/owner_truth_green_closeout_hardening/2026-03-12/profit_semantics_decision.md`

### Definition of Done
Accepted as done only when:
- the trust banner explains a fully decision-grade profit state, or
- the semantics contract explicitly defines the remaining limitation and proves it is acceptable for owner use
- no current green gate regresses

### Validation/Gates
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_owner_daily_surfaces.py`
- `python3 -m py_compile scripts/build_owner_profit_daily.py`
- `python3 scripts/build_owner_profit_daily.py --as-of 2026-03-09 ...`
- `./.venv/bin/python scripts/run_owner_truth_daily.py --mode live --as-of 2026-03-09 --strict`
- `./.venv/bin/python scripts/system_doctor.py --strict --project-root . --as-of 2026-03-09`

### Rollback / backout strategy
- revert C1 code/docs/tests only
- preserve pre-change trust artifacts for comparison

### Stop-the-line criteria
- any change to profit semantics without an explicit contract/doc
- any green gate turns red
- provisional banner is removed without evidence

---

## Phase C2 — Owner Surface Hardening

### Goal (measurable)
Ensure `Owner Profit Daily`, `Cash Risk Daily`, and `PO / SKU Daily` are mutually consistent and remain fail-closed.

### Inputs
- C1 outputs
- `build_cash_risk_daily.py`
- `build_po_sku_daily.py`
- current trust reports for all three surfaces
- cashflow and PO/inventory contracts

### Outputs
- refreshed:
  - `exports/owner/2026-03-09/cash_risk_daily.json`
  - `exports/owner/2026-03-09/cash_risk_daily.md`
  - `exports/validation/cash_risk_daily/2026-03-09/trust_report.json`
  - `exports/owner/2026-03-09/po_sku_daily.json`
  - `exports/owner/2026-03-09/po_sku_daily.md`
  - `exports/validation/po_sku_daily/2026-03-09/trust_report.json`
- `exports/validation/owner_truth_green_closeout_hardening/2026-03-12/owner_surface_consistency_report.md`

### Definition of Done
Accepted as done only when:
- all three surfaces exist
- all three have explicit trust semantics
- no cross-surface contradiction exists on core shared facts

### Validation/Gates
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_owner_daily_surfaces.py`
- `python3 -m py_compile scripts/build_cash_risk_daily.py scripts/build_po_sku_daily.py`
- `python3 scripts/build_cash_risk_daily.py --as-of 2026-03-09 ...`
- `python3 scripts/build_po_sku_daily.py --as-of 2026-03-09 ...`
- if cashflow touched: `python3 scripts/validate_cashflow_invariants.py`
- if ordering touched: `python3 scripts/validate_po_dashboard_invariants.py`

### Rollback / backout strategy
- revert C2 code/docs only
- restore prior output files from artifacts if needed

### Stop-the-line criteria
- any owner surface is “green” without a trust banner
- any cashflow or PO invariant goes red
- any mixed-source contradiction appears

---

## Phase C3 — Release / Oracle Refresh from Committed Tip

### Goal (measurable)
Refresh merge/release/oracle evidence from a committed green tip, not from dirty local state.

### Inputs
- committed C0–C2 state
- current `merge_manifest.json`
- current `full_gates_green_live_ops.md`
- current pack files

### Outputs
- refreshed:
  - `exports/validation/owner_truth_operationalization/2026-03-09/merge_manifest.json`
  - `exports/validation/owner_truth_operationalization/2026-03-09/merge_manifest.md`
  - `exports/validation/owner_truth_release/2026-03-09/full_gates_green_live_ops.md`
  - `Oracle_listings/packs/owner_truth_live_green_2026-03-09/PACK_SUMMARY.md`
  - `Oracle_listings/packs/owner_truth_live_green_2026-03-09/bundle.md`
  - `Oracle_listings/packs/owner_truth_live_green_2026-03-09/oracle_files_manifest.txt`
  - `Oracle_listings/packs/owner_truth_live_green_2026-03-09/ArchiveOrders_WEBUI_MERGED_ALL_STORES.csv`
- `exports/validation/owner_truth_green_closeout_hardening/2026-03-12/release_refresh_report.md`

### Definition of Done
Accepted as done only when:
- merge manifest remains GREEN
- `ok_to_merge` is still true
- the pack reflects a committed tip
- rollback mapping is explicit
- canonical merged orders CSV is included

### Validation/Gates
- `bash scripts/lint_docs.sh`
- `bash scripts/check_no_db_tracked.sh`
- `python3 scripts/check_release_hygiene.py --strict --project-root .`

### Rollback / backout strategy
- revert C3 docs/pack refresh only
- preserve previous green evidence

### Stop-the-line criteria
- pack still points at dirty-only local state
- wrong canonical CSV is packed
- rollback mapping missing

---

## Phase C4 — Scorecard Refresh + 3-Day Review Hook

### Goal (measurable)
Bring the owner scorecard into sync with the current green closeout and set the next 3-day review baseline.

### Inputs
- `OWNER_PROGRESS_SCORECARD_2026-03-11.md`
- C1/C2 trust semantics
- current release evidence

### Outputs
- updated `OWNER_PROGRESS_SCORECARD_2026-03-11.md` or a new dated successor
- `exports/validation/owner_truth_green_closeout_hardening/2026-03-12/scorecard_refresh_report.md`

### Definition of Done
Accepted as done only when the scorecard can answer:
- Profit view: Yes / No (with exact blocker or caveat)
- Cash-risk view: Yes / No
- PO / SKU decisions: Yes / No

### Validation/Gates
- `bash scripts/lint_docs.sh`

### Rollback / backout strategy
- revert scorecard/docs only

### Stop-the-line criteria
- scorecard claims green without evidence links
- scorecard contradicts current release artifacts

---

## Phase D1 — Deferred Scheduler/Import Proving

### Goal (measurable)
Optionally prove scheduler/import parity with `AB_INCLUDE_OPS_SELECTION_PARITY=1` in a separate, non-blocking follow-on.

### Inputs
- current green release state
- deferred out-of-scope list
- import/scheduler contracts

### Outputs
- deferred proving plan/evidence under a separate validation root

### Definition of Done
Accepted as done only when this proving is clearly separate from the owner-output closeout.

### Validation/Gates
- as defined in the separate proving plan

### Rollback / backout strategy
- separate from this closeout

### Stop-the-line criteria
- any regression in the owner-truth green chain

---

## Phase D2 — Deferred Scale Queue Lock

### Goal (measurable)
Keep broader cleanup and scale work visible but out of the current merge.

### Inputs
- current merge manifest
- deferred items list

### Outputs
- `exports/validation/owner_truth_green_closeout_hardening/2026-03-12/deferred_scale_backlog.md`

### Definition of Done
Accepted as done only when:
- scale items are explicitly marked out-of-scope
- no unrelated cleanup or architecture detour enters the current closeout

### Validation/Gates
- `bash scripts/lint_docs.sh`

### Rollback / backout strategy
- revert D2 backlog doc only

### Stop-the-line criteria
- deferred work is silently pulled into the closeout
- parallel worktrees are introduced without necessity

---

## If attachments are missing — assumptions policy
- If older blocked-state bundles conflict with the latest 2026-03-12 green closeout artifacts, prefer the latest green closeout artifacts.
- If the current worktree contains additional dirty delta not represented in the green pack, freeze it first before edits.
- If no clean commit split can be made safely, emit a checkpoint patch and stop instead of forcing packaging.
- If semantics unlock for `Owner Profit Daily` cannot be proven without broader upstream changes, keep the explicit provisional banner and stop after documenting the exact blocker.
- If any new red gate appears, stop and emit a fresh divergence/closeout pack before continuing.