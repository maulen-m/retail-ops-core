File: DOCS/PLAN_OWNER_COCKPIT_POST_P7_VALUE_UNLOCK_2026-03-18.md

# Plan: Owner Cockpit Post-P7 Value Unlock

## Purpose
Take the now-green owner cockpit through the next fastest safe chapter:
1. unlock Owner Profit Daily from monitoring-only if and only if publication-grade evidence allows it,
2. close PO planning freshness so inventory/capital views can be used more operationally,
3. prove the cockpit stays green under scheduler/import automation,
4. finish release/promotion closeout,
5. only then reopen broader scale modules.

## Global execution rules
- Single-agent sequential execution in one worktree/branch.
- Fail-closed by default.
- Human time target: prompt paste, existing login/secrets availability only, and final promotion decision only.
- No silent contract widening.
- Any write path must be dry-run first, explicit apply only, backup first, rollback documented.
- Use the source-of-truth ladder:
  1. `docs/inventory/Master_Inventory_Rules_v8.md`
  2. `docs/protocol/active/PO_making_logic_v2.md`
  3. `docs/inventory/Sales_Data_Model_V16.md`
  4. `docs/ARCHITECTURE.md`
  5. `docs/inventory/Excel_UI_Contract_for_CRM_V1.md`
  6. `docs/DAILY_SOP.md`
  7. current accepted owner cockpit artifacts and release evidence

## Shared gates
Run the full relevant subset before claiming completion:
- `bash scripts/check_no_db_tracked.sh`
- `bash scripts/lint_docs.sh` (if docs touched)
- `AB_CRM_WORKBOOK_PATH=config/anchors/SALES_KSP_CRM_LATEST.xlsx python3 scripts/validate_params.py --strict --as-of 2026-03-09`
- `./.venv/bin/python scripts/system_doctor.py --strict --project-root . --as-of 2026-03-09`
- `./.venv/bin/python scripts/run_owner_truth_daily.py --mode live --as-of 2026-03-09 --strict`
- `python3 scripts/validate_cashflow_invariants.py` (if cashflow surfaces or scheduler proving touched)
- `python3 scripts/validate_webui_archive_vs_current_db.py --start 2025-06-06 --end 2026-03-09 --range-policy full_range_owner_truth --statusdate-cutover 2026-02-27 --strict`
- `env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
- `python3 -m py_compile ...` for every touched script set
- `python3 scripts/validate_po_dashboard_invariants.py` if PO/planning math or PO dashboard inputs changed
- `python3 scripts/validate_profit_publication_integrity.py` if profit semantics are being unlocked
- scheduler/ops gates if R3 is active:
  - `bash scripts/install_single_truth_ops_scheduler.sh --validate-only`
  - `python3 scripts/ops_status.py --project-root .`

## Phase R0 — Baseline Freeze + Release Anchor Sanity
### Goal
Freeze one accepted post-P7 baseline and eliminate state narration ambiguity before new edits.

### Inputs
- `exports/validation/owner_cockpit_reactivation/2026-03-14/owner_cockpit_acceptance.md`
- `exports/validation/owner_cockpit_reactivation/2026-03-14/full_gates_green_final.md`
- `exports/validation/owner_cockpit_reactivation/2026-03-14/state_reconciliation.md`
- `exports/validation/owner_cockpit_reactivation/2026-03-14/reconciliation_decision.json`
- `docs/OWNER_TRUTH_SOURCE_MAP_AND_DB_RECENCY_2026-03-14.md`
- current git history and worktree state

### Outputs
- `exports/validation/owner_cockpit_post_p7/2026-03-18/readcheck.md`
- `exports/validation/owner_cockpit_post_p7/2026-03-18/baseline_release_anchor.md`
- `exports/validation/owner_cockpit_post_p7/2026-03-18/baseline_git_state.txt`
- `exports/validation/owner_cockpit_post_p7/2026-03-18/implementation_breakdown.md`

### Definition of Done
Accepted as done only when:
- one canonical baseline is recorded,
- current head / canonical runtime center / release-evidence lineage are explicit,
- dirty vs clean state is explained,
- rollback anchor is written,
- execution scope is fixed.

### Validation/Gates
- `git status --short`
- `git rev-parse HEAD`
- `git log --decorate --oneline -n 20`
- `bash scripts/check_no_db_tracked.sh`

### Rollback / backout strategy
- Docs/evidence only.
- Revert only new baseline notes if they are later proven wrong.

### Stop-the-line criteria
- Canonical baseline cannot be identified with evidence.
- Worktree state is unclear.
- New unrelated diffs exist in business-critical files.

## Phase R1 — Profit Semantics Unlock (P8)
### Goal
Unlock `owner_profit_daily` from monitoring-only only if publication-grade evidence is real.

### Inputs
- current `exports/owner/2026-03-09/owner_profit_daily.json`
- `docs/validation/OWNER_PROFIT_DAILY_SEMANTICS_CONTRACT.md`
- `exports/north_star_owner_review/2026-03-09/monthly_totals_review.csv`
- `exports/north_star_owner_review/2026-03-09/publication_readiness.json`
- `exports/daily/2026-03-09/owner_truth_summary.json`
- `exports/diagnostics/2026-03-09/system_health.json`
- `docs/ARCHITECTURE.md`

### Outputs
- `DOCS/OWNER_PROFIT_PUBLICATION_UNLOCK_CONTRACT_2026-03-18.md`
- updated `scripts/build_owner_profit_daily.py` if required
- updated `exports/owner/2026-03-09/owner_profit_daily.json`
- updated `exports/owner/2026-03-09/owner_profit_daily.md`
- updated downstream affected surfaces:
  - `exports/owner/2026-03-09/owner_daily_brief.json`
  - `exports/owner/2026-03-09/cashflow_dashboard_owner.json`
  - `exports/owner/2026-03-09/inventory_capital_radar.json`
- `exports/validation/owner_profit_unlock/2026-03-18/profit_unlock_report.md`
- `exports/validation/owner_profit_unlock/2026-03-18/profit_unlock_report.json`

### Definition of Done
Accepted as done only when:
- `owner_profit_daily` no longer depends on monitoring-only semantics,
- `decision_scope` is upgraded by contract and evidence,
- publication-readiness is PASS,
- `validate_profit_publication_integrity.py` is PASS,
- downstream owner surfaces inherit the new semantics correctly,
- no truth banner is widened by wording alone.

### Validation/Gates
- Shared gates
- `python3 scripts/validate_profit_publication_integrity.py`
- workbook/publication parity gates
- targeted profit/brief/dashboard pytest bundle
- `python3 scripts/validate_owner_surface_consistency.py ...`

### Rollback / backout strategy
- Revert profit-only commits in reverse order.
- Restore prior monitoring-only semantics contract and outputs.
- No DB restore unless a write path was explicitly used and backed up.

### Stop-the-line criteria
- Any missing publication evidence.
- Any attempt to widen semantics by wording only.
- Any regression in owner cockpit green chain.
- Any hidden formula drift from canonical docs.

## Phase R2 — PO Planning Freshness Closure
### Goal
Remove or explicitly resolve the `STALE_VS_CUTOFF` planning snapshot caveat that currently limits inventory/capital operational use.

### Inputs
- `exports/owner/2026-03-09/po_sku_daily.json`
- `exports/owner/2026-03-09/inventory_capital_radar.json`
- `exports/po_dashboard_data.json`
- `docs/inventory/Master_Inventory_Rules_v8.md`
- `docs/protocol/active/PO_making_logic_v2.md`
- stock/inbound anchors and canonical refresh inputs
- `Inbound_calendar_V10.002.xlsx` via anchor if needed

### Outputs
- `DOCS/PO_PLANNING_FRESHNESS_CLOSEOUT_CONTRACT_2026-03-18.md`
- updated `scripts/generate_po_dashboard_data.py` and/or relevant freshness logic if required
- updated `exports/owner/2026-03-09/po_sku_daily.json`
- updated `exports/owner/2026-03-09/inventory_capital_radar.json`
- `exports/validation/planning_freshness_closeout/2026-03-18/freshness_closeout_report.md`
- `exports/validation/planning_freshness_closeout/2026-03-18/freshness_closeout_report.json`

### Definition of Done
Accepted as done only when:
- planning freshness is no longer stale against the governing cutoff, or
- a stricter fail-closed blocked-state report proves why it cannot be closed yet without violating contracts,
- PO/inventory surfaces tell the truth about execution readiness,
- no new PO math is introduced outside canonical layers.

### Validation/Gates
- Shared gates
- `python3 scripts/validate_po_dashboard_invariants.py` if PO inputs/math changed
- targeted PO/inventory/owner-surface pytest bundle
- `python3 scripts/validate_owner_surface_consistency.py ...`

### Rollback / backout strategy
- Revert freshness-closeout commits.
- Restore prior owner surfaces and trust banners.
- If any DB write is required, backup first and document exact restore command.

### Stop-the-line criteria
- Any contradiction with inventory rules or PO logic docs.
- Any attempt to hide stale planning.
- Any change that makes monitoring surfaces look execution-grade without evidence.

## Phase R3 — Scheduler / Import Proving (P9)
### Goal
Prove the owner cockpit stays green under scheduler/import automation, not only manual reruns.

### Inputs
- current green owner cockpit outputs
- `docs/DAILY_SOP.md`
- scheduler install/validate scripts
- current launchd or scheduler artifacts
- current import parity contracts

### Outputs
- `DOCS/OWNER_COCKPIT_SCHEDULER_PROVING_2026-03-18.md`
- `exports/validation/owner_cockpit_scheduler_proving/2026-03-18/scheduler_proving_report.md`
- `exports/validation/owner_cockpit_scheduler_proving/2026-03-18/scheduler_proving_report.json`
- updated SOP/runbook docs if needed
- refreshed scheduler validate-only evidence

### Definition of Done
Accepted as done only when:
- scheduler validate-only is green,
- ops_status is green,
- at least one autonomous-style replay path is proven without manual intervention,
- owner cockpit outputs remain green before and after proving,
- import/scheduler parity is explicitly documented and reproducible.

### Validation/Gates
- Shared gates
- `bash scripts/install_single_truth_ops_scheduler.sh --validate-only`
- `python3 scripts/ops_status.py --project-root .`
- relevant scheduler/import pytest or contract tests
- re-run `run_owner_truth_daily.py --mode live --strict`

### Rollback / backout strategy
- Revert scheduler/proving docs/code only.
- Remove new scheduler artifacts if they are noncanonical.
- No DB restore unless writes were explicitly applied with backup.

### Stop-the-line criteria
- Any regression in current green owner cockpit chain.
- Any hidden dependency on manual operator memory.
- Any uncontrolled interpreter/dependency path.

## Phase R4 — Release / Promotion Closeout
### Goal
Ship a clean release/promotion package only after value-unlock and automation-proving phases are green or explicitly blocked with reverted-clean state.

### Inputs
- all prior phase evidence
- current merge/release manifests
- oracle pack tooling
- rollback notes
- current acceptance docs

### Outputs
- `DOCS/OWNER_COCKPIT_RELEASE_CLOSEOUT_2026-03-18.md`
- refreshed release/merge manifests
- refreshed oracle pack
- `exports/validation/owner_cockpit_release_closeout/2026-03-18/release_closeout.md`
- `exports/validation/owner_cockpit_release_closeout/2026-03-18/release_closeout.json`

### Definition of Done
Accepted as done only when:
- worktree is clean,
- release anchor/head is explicit,
- rollback steps are complete,
- required packs/manifests are refreshed,
- all required gates are green for the release scope,
- any remaining deferrals are explicit and non-misleading.

### Validation/Gates
- Shared gates
- full gate replay for release scope
- oracle pack build
- docs lint
- no tracked DB files

### Rollback / backout strategy
- Revert release-closeout-only commits.
- Roll back to pre-closeout clean head.
- Restore prior release anchors/manifests if needed.

### Stop-the-line criteria
- Dirty worktree at release time.
- Missing rollback path.
- Any unresolved contradiction between acceptance docs and oracle pack state.

## Phase R5 — Multi-Day Autonomy Reprove
### Goal
Reduce operational risk by proving a short multi-day, low-touch green cycle after release closeout.

### Inputs
- released owner cockpit
- review cycle runner
- scheduler/proving outputs

### Outputs
- `exports/validation/owner_cockpit_autonomy_reprove/2026-03-18/autonomy_reprove.md`
- `exports/validation/owner_cockpit_autonomy_reprove/2026-03-18/autonomy_reprove.json`

### Definition of Done
Accepted as done only when the cockpit can reproduce a green multi-day review cycle with no new silent failures.

### Validation/Gates
- repeat strict owner-review cycle across defined dates
- shared gates subset for each replay

### Rollback / backout strategy
- docs/evidence only unless bugs are fixed
- revert any new proving-only code

### Stop-the-line criteria
- any day goes false-green
- any silent drift between days
- any scheduler/manual divergence

## Phase R6 — Scale Reactivation Queue
### Goal
Restart broader modules only after the stable center is released and automation-proven.

### Inputs
- released cockpit
- deferred module queue
- scorecard priorities

### Outputs
- `DOCS/OWNER_COCKPIT_SCALE_QUEUE_2026-03-18.md`
- approved module order and gates

### Definition of Done
Accepted as done only when the next broader modules have an approved business order, exact gates, and rollback stories.

### Validation/Gates
- no module opens without its own READCHECK, DoD, and gate chain
- keep owner cockpit baseline green throughout

### Rollback / backout strategy
- queue docs only at this phase

### Stop-the-line criteria
- reopening modules before stable-center release
- multi-worktree expansion without clear isolation value
- “feature first, proof later” planning

## If attachments are missing — assumptions policy
- Use the latest accepted repo-local baseline as canonical:
  - `17ddec4` current accepted HEAD
  - `66ed98c -> 41361a2 -> 17ddec4` accepted lineage
  - `ebd24b7` canonical owner-runtime green center
- Treat oracle-pack-only dirty state from `.oracle_stage_*` as packaging noise unless `git status` proves otherwise.
- Never invent formulas, freshness, or publication semantics.
- If a required attachment is unavailable, narrow scope, log the assumption in `claude/journal.md`, and keep fail-closed behavior.
- No DB/network apply writes may be used to compensate for missing evidence.
- If `DOCS/` does not exist, create it and keep docs lint green.