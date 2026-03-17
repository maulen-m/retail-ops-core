File: DOCS/PLAN_OWNER_COCKPIT_RECONCILIATION_AND_CASHFLOW_FIRST_REACTIVATION_2026-03-14.md

# Plan: Owner Cockpit Reconciliation and Cashflow-First Reactivation

## Purpose
Turn the current green-but-not-fully-explained owner-output layer into a decision-grade, merge-safe owner cockpit, then reactivate broader modules in the lowest-risk order: cashflow first, inventory second.

## Current execution findings
- Canonical owner-runtime green center is `ebd24b7`; current HEAD is a packaging/context-copy delta on top, not a semantic owner-runtime fork.
- Repo-local `2026-03-09` owner artifacts are available; `/mnt/data` prompt attachments are not. Scope therefore remains repo-local and fail-closed.
- Raw recent staging currently leads published owner-facing sales truth by 2 days (`sales_fact_v2` max `2026-03-07` vs published `view_sales_daily_truth` max `2026-03-05`), and the lag is explained by workbook chronology binding (`fact_sales_workbook_anchor` max `2026-03-05`).
- `cashflow_calendar_daily` needed semantic tightening so zero/unknown rows do not appear as “largest outflow days”; this is now part of the contract/validator path.
- Execution status in this worktree:
  - P0-P5 completed green with evidence under `exports/validation/owner_cockpit_reactivation/2026-03-14/`
  - P6 cashflow dashboard opened after P0-P5 green and completed as a composition-only owner surface
  - P7 inventory capital radar opened after P6 green and completed as a composition-only owner surface
  - P8/P9 remain deferred by contract

## Global execution rules
- Single-agent sequential execution in one worktree/branch.
- Fail-closed by default.
- No DB/network apply writes in P0-P5.
- Human involvement target: prompt paste only; no human work unless a later phase explicitly requires login/secret entry.
- Use the repo source-of-truth ladder:
  1. `docs/inventory/Master_Inventory_Rules_v8.md`
  2. `docs/protocol/active/PO_making_logic_v2.md`
  3. `docs/inventory/Sales_Data_Model_V16.md`
  4. `docs/ARCHITECTURE.md`
  5. `docs/inventory/Excel_UI_Contract_for_CRM_*` + `docs/inventory/Automation_Handoff_V16.md`

## Shared gates
Run these whenever the touched scope requires them:
- `bash scripts/check_no_db_tracked.sh`
- `bash scripts/lint_docs.sh` (if docs touched)
- `AB_CRM_WORKBOOK_PATH=config/anchors/SALES_KSP_CRM_LATEST.xlsx python3 scripts/validate_params.py --strict --as-of 2026-03-09`
- `./.venv/bin/python scripts/system_doctor.py --strict --project-root . --as-of 2026-03-09`
- `./.venv/bin/python scripts/run_owner_truth_daily.py --mode live --as-of 2026-03-09 --strict`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_owner_daily_surfaces.py tests/test_owner_daily_brief.py tests/test_run_owner_review_cycle.py tests/test_cashflow_calendar_daily.py tests/test_inventory_capital_radar.py tests/test_sales_truth_views.py`
- `python3 -m py_compile scripts/build_cash_risk_daily.py scripts/build_owner_daily_brief.py scripts/build_po_sku_daily.py scripts/build_cashflow_calendar_daily.py scripts/run_owner_review_cycle.py core/sales/truth_views.py`
- `python3 scripts/validate_cashflow_invariants.py` (if cashflow semantics or outputs touched)
- `python3 scripts/validate_webui_archive_vs_current_db.py --start 2025-06-06 --end 2026-03-09 --range-policy full_range_owner_truth --statusdate-cutover 2026-02-27 --strict` (if truth-source mapping or truth views touched)
- `python3 scripts/validate_po_dashboard_invariants.py` only if PO dashboard math/inputs change; not required for pure owner-surface wording/trust-banner changes

## Phase P0 — Baseline Freeze + READCHECK
### Goal
Create one auditable baseline before any new edits.

### Inputs
- `AGENTS.md`
- `00_START_HERE.md`
- `ARCHITECTURE.md`
- `DASHBOARD_CONTRACT.md`
- `GOALS.md`
- `TASKS.md`
- `204559_TASK-000_owner-outputs-decision-activation-latest.md`
- `owner_truth_summary.json`
- `system_health.json`
- `cash_risk_daily.json`
- `cashflow_calendar_daily.json`
- `owner_daily_brief.json`
- `po_sku_daily.json`
- `worktree_status.txt`

### Outputs
- `exports/validation/owner_cockpit_reactivation/2026-03-14/readcheck.md`
- `exports/validation/owner_cockpit_reactivation/2026-03-14/baseline_worktree_status.txt`
- `exports/validation/owner_cockpit_reactivation/2026-03-14/baseline_head_and_commits.md`
- `exports/validation/owner_cockpit_reactivation/2026-03-14/rollback_anchor.md`
- `exports/validation/owner_cockpit_reactivation/2026-03-14/implementation_breakdown.md`

### Definition of Done
Accepted as done only when the authoritative doc stack, current head, dirty/clean state, rollback anchor, and exact scope are written to disk and journaled.

### Validation/Gates
- `git status --short`
- `git rev-parse HEAD`
- `git log --oneline -n 12`
- `bash scripts/check_no_db_tracked.sh`

### Rollback / backout strategy
- No writes expected.
- Save pre-change diff/patch if any edits are started.
- If READCHECK finds contradiction, stop before code changes.

### Stop-the-line criteria
- Missing canonical docs
- Missing rollback anchor
- Ambiguous task scope
- Unexplained unrelated changes in touched files

## Phase P1 — Canonical State Reconciliation
### Goal
Declare exactly one canonical current implementation tip and classify all competing SHA narratives.

### Inputs
- P0 artifacts
- current git history
- owner-output activation pack
- any later handoff SHAs mentioned in current task context

### Outputs
- `exports/validation/owner_cockpit_reactivation/2026-03-14/state_reconciliation.md`
- `exports/validation/owner_cockpit_reactivation/2026-03-14/head_chronology.md`
- `exports/validation/owner_cockpit_reactivation/2026-03-14/reconciliation_decision.json`

### Definition of Done
Accepted as done only when one SHA/head is declared canonical for new work and all others are tagged as local delta, superseded, or handoff-only.

### Validation/Gates
- `git log --decorate --oneline -n 30`
- `git show --stat <candidate_sha>`
- `git merge-base <candidate_a> <candidate_b>` when needed
- `bash scripts/check_no_db_tracked.sh`

### Rollback / backout strategy
- Docs-only phase.
- Revert only new reconciliation docs if later evidence invalidates them.

### Stop-the-line criteria
- Canonical head cannot be established with evidence
- Same owner-surface files differ across candidate heads without resolution
- Reconciliation depends on memory rather than visible artifacts

## Phase P2 — Owner Truth Source Map + DB Recency Closure
### Goal
Explain how raw DB sales recency and published owner-truth outputs relate, and make the explanation machine-checkable.

### Inputs
- `ARCHITECTURE.md`
- `owner_truth_summary.json`
- `system_health.json`
- `core/sales/truth_views.py`
- owner-surface JSON artifacts
- `db/app.db`

### Outputs
- `DOCS/OWNER_TRUTH_SOURCE_MAP_AND_DB_RECENCY_2026-03-14.md`
- `exports/validation/owner_cockpit_reactivation/2026-03-14/source_map_owner_truth.md`
- `exports/validation/owner_cockpit_reactivation/2026-03-14/raw_vs_published_sales_max_dates.json`
- `exports/validation/owner_cockpit_reactivation/2026-03-14/raw_vs_published_sales_max_dates.md`
- If needed: `scripts/report_sales_truth_max_dates.py`
- If needed: `tests/test_sales_truth_views.py` updates

### Definition of Done
Accepted as done only when every owner surface has an explicit upstream source map and the repo can print both raw and published sales max dates in one report.

### Validation/Gates
- Shared gates
- `python3 scripts/validate_webui_archive_vs_current_db.py --start 2025-06-06 --end 2026-03-09 --range-policy full_range_owner_truth --statusdate-cutover 2026-02-27 --strict`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_sales_truth_views.py`

### Rollback / backout strategy
- Revert code/docs added for max-date reporting
- Do not change DB contents in this phase

### Stop-the-line criteria
- Any explanation contradicts `ARCHITECTURE.md`
- Any proposed fix moves business math into UI/report composition
- Any hidden DB write is required to “explain” the issue

## Phase P3 — Owner Surface Semantic Closure
### Goal
Remove silent contradictions between cash-risk, cashflow-calendar, PO/SKU, and owner-brief semantics.

### Inputs
- `scripts/build_cash_risk_daily.py`
- `scripts/build_cashflow_calendar_daily.py`
- `scripts/build_po_sku_daily.py`
- `scripts/build_owner_daily_brief.py`
- current owner-surface artifacts
- P2 source-map artifacts

### Outputs
- `DOCS/OWNER_SURFACE_CONSISTENCY_CONTRACT_2026-03-14.md`
- `exports/validation/owner_cockpit_reactivation/2026-03-14/owner_surface_consistency_report.json`
- `exports/validation/owner_cockpit_reactivation/2026-03-14/owner_surface_consistency_report.md`
- updated owner-surface scripts/tests as required

### Definition of Done
Accepted as done only when:
- every owner-brief headline points to a named upstream field,
- metric-lens differences are explicit,
- no surface silently contradicts another,
- and `cashflow_calendar_daily` no longer emits ambiguous top-driver output without either explanation or fail-closed behavior.

### Validation/Gates
- Shared gates
- `python3 scripts/validate_cashflow_invariants.py`
- targeted rebuild of owner surfaces
- targeted pytest bundle

### Rollback / backout strategy
- Revert only owner-surface code/docs changes
- Keep pre-change artifacts for diff comparison

### Stop-the-line criteria
- Cross-surface contradiction remains unresolved
- Profit provisionality or PO staleness caveat gets hidden
- Calendar semantics still look “green” while materially ambiguous

## Phase P4 — Owner Brief Cockpit Hardening
### Goal
Make `owner_daily_brief` the single owner control file for the 3-day review rhythm.

### Inputs
- `scripts/build_owner_daily_brief.py`
- upstream owner surfaces
- scorecard questions / owner action requirements

### Outputs
- updated `exports/owner/2026-03-09/owner_daily_brief.json`
- updated `exports/owner/2026-03-09/owner_daily_brief.md`
- updated `exports/validation/owner_daily_brief/2026-03-09/trust_report.json`
- `exports/validation/owner_cockpit_reactivation/2026-03-14/owner_cockpit_acceptance.md`

### Definition of Done
Accepted as done only when the brief answers, in plain English:
- are we profitable,
- why,
- when cash gets dangerous,
- what capital is frozen,
- what to reorder,
- what to freeze,
- what to kill,
- what to do before the next review.

### Validation/Gates
- Shared gates
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_owner_daily_brief.py tests/test_owner_daily_surfaces.py`

### Rollback / backout strategy
- Revert brief-builder changes only
- Preserve previous brief artifacts for compare

### Stop-the-line criteria
- Brief introduces new hidden logic
- Brief overclaims publication-grade profit
- Brief suppresses stale planning trust banner

## Phase P5 — Review Cycle / Observability / Docs Hardening
### Goal
Make one command refresh the owner cockpit and keep docs aligned with current truth behavior.

### Inputs
- `scripts/run_owner_review_cycle.py`
- `DASHBOARD_CONTRACT.md`
- `ARCHITECTURE.md`
- `docs/DAILY_SOP.md`
- outputs from P1-P4

### Outputs
- updated `scripts/run_owner_review_cycle.py`
- updated `DOCS/PLAN_OWNER_COCKPIT_RECONCILIATION_AND_CASHFLOW_FIRST_REACTIVATION_2026-03-14.md`
- updated `docs/DAILY_SOP.md`
- updated `DASHBOARD_CONTRACT.md`
- updated `ARCHITECTURE.md` or `Automation_Handoff_V16.md` with source-map explanation
- `exports/validation/owner_cockpit_reactivation/2026-03-14/review_cycle_reprove.md`
- refreshed release/oracle refs only after all gates pass

### Definition of Done
Accepted as done only when one command can refresh surfaces, brief, scorecard, and supporting evidence without manual cleanup, and docs explain current semantics.

### Validation/Gates
- Shared gates
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_run_owner_review_cycle.py`
- `bash scripts/lint_docs.sh`

### Rollback / backout strategy
- Revert docs/review-cycle changes
- Do not refresh release refs until all gates are green

### Stop-the-line criteria
- Docs claim more maturity than evidence supports
- Review cycle can pass without refreshed source-map/consistency artifacts
- Release refs are refreshed before gates are green

## Phase P6 — Cashflow Dashboard Expansion
### Goal
Expand from daily calendar to richer owner cashflow dashboard without changing canonical cash truth.

### Inputs
- `CASHFLOW_TRUTH_CONTRACT_2026-01-26.md`
- current cash surfaces
- `DASHBOARD_CONTRACT.md`
- P3/P4 semantics decisions

### Outputs
- `scripts/build_cashflow_dashboard_owner.py` (or equivalent)
- `exports/owner/2026-03-09/cashflow_dashboard_owner.json`
- `exports/owner/2026-03-09/cashflow_dashboard_owner.md`
- `DOCS/CASHFLOW_OWNER_DASHBOARD_CONTRACT_2026-03-14.md`
- tests + validation artifacts

### Definition of Done
Accepted as done only when the richer dashboard adds decision value without mixing paid truth and model truth, and without creating a second cash authority.

### Validation/Gates
- Shared gates
- `python3 scripts/validate_cashflow_invariants.py`
- `python3 scripts/validate_cashfloor.py --strict --as-of 2026-03-09 --db db/app.db --output-root exports/daily`
- cashflow-focused pytest suite

### Rollback / backout strategy
- Revert dashboard builder/tests/docs
- No cash truth contract changes without doc-first update

### Stop-the-line criteria
- Any mixed paid/model truth
- Any new write path
- Any contradiction with `CASHFLOW_TRUTH_CONTRACT_2026-01-26.md`

## Phase P7 — Inventory Analysis / Capital Freeze Radar
### Goal
Broaden PO/SKU surface into fuller inventory/capital analysis after cashflow dashboard is green.

### Inputs
- `docs/inventory/Master_Inventory_Rules_v8.md`
- `docs/protocol/active/PO_making_logic_v2.md`
- current `po_sku_daily` artifacts
- P3/P4 semantics decisions

### Outputs
- `scripts/build_inventory_capital_radar.py` (or equivalent)
- `exports/owner/2026-03-09/inventory_capital_radar.json`
- `exports/owner/2026-03-09/inventory_capital_radar.md`
- `DOCS/INVENTORY_CAPITAL_RADAR_CONTRACT_2026-03-14.md`
- tests + validation artifacts

### Definition of Done
Accepted as done only when reorder/freeze/kill, tied-up capital, and staleness are explicit and rule-aligned, with no execution-grade claim while planning freshness remains stale.

### Validation/Gates
- Shared gates
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_inventory_capital_radar.py tests/test_owner_daily_surfaces.py`
- `python3 scripts/validate_po_dashboard_invariants.py` only if PO dashboard math or source inputs change

### Rollback / backout strategy
- Revert radar-specific code/docs/tests
- Keep current `po_sku_daily` as fallback surface

### Stop-the-line criteria
- Any rule contradiction with `Master_Inventory_Rules_v8.md`
- Any implicit claim that stale planning is fresh
- Any widening into autonomous PO execution

## Phase P8 — Deferred Profit Semantics Unlock
### Goal
Run a narrow semantics-only phase to unlock Owner Profit Daily from monitoring-only, if explicitly approved.

### Inputs
- current owner profit semantics
- workbook/publication integrity contracts
- owner surface consistency outputs

### Outputs
- contract doc
- updated owner profit surface
- tests and publication evidence

### Definition of Done
Accepted as done only when profit can be publication-grade by contract, not just by wording.

### Validation/Gates
- `python3 scripts/validate_profit_publication_integrity.py`
- workbook anchor/parity gates
- targeted profit/brief tests

### Rollback / backout strategy
- Revert semantics-only changes
- Restore monitoring-only contract

### Stop-the-line criteria
- Any hidden widening from monitoring to publication
- Any missing workbook/publication evidence

## Phase P9 — Deferred Scheduler/Import Proving
### Goal
Prove scheduler/import parity separately from owner-cockpit work.

### Inputs
- scheduler/import contracts
- current owner cockpit outputs

### Outputs
- separate proving pack
- parity evidence
- ops docs updates if needed

### Definition of Done
Accepted as done only when scheduler/import proving is green and the owner cockpit chain remains green before and after.

### Validation/Gates
- scheduler/ops-specific gate chain
- current owner-cockpit shared gates remain green

### Rollback / backout strategy
- Revert proving-specific changes
- Do not fold proving fixes into cockpit work without evidence

### Stop-the-line criteria
- Any regression in current owner cockpit chain
- Any attempt to hide import/scheduler drift under owner-output green status

## If attachments are missing — assumptions policy
- Use the latest attachment-backed implementation pack as the default execution baseline.
- Treat any later SHA mentioned only in chat text as a reconciliation candidate, not canonical fact, until proven in git history.
- Never invent formulas, freshness, or source precedence.
- If an attachment needed for a phase is missing, narrow the phase, log the assumption in the journal and phase artifacts, and keep fail-closed behavior.
- Do not perform DB/network apply writes to compensate for missing attachments.
- If `DOCS/` does not exist, create it explicitly and keep docs lint green.
