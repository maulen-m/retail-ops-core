# PLAN_2_WEEK_EXECUTION_BOARD_A_C_B_V2_2026-02-21

## Purpose
Promotion + operationalization board for sprint A->C->B (`trust closure -> ads profit realism -> shipment safety`) on branch `codex/TASK-2w-board-ACB-v2-ads-sidecar`.

This V2 plan is explicitly aligned to the stock single-truth cutover:
- canonical stock source: `config/anchors/STOCK_SNAPSHOT_LATEST.xlsx`
- current pointer target: `excel/stock_snapshot_19.2.2026.xlsx`
- stock snapshot semantics: `Snapshot_date=2026-02-19`, `Cutoff_sales_date=2026-02-18`
- legacy `excel/Current_stock_*.xlsx` chain is deprecated for decision-grade flows

## Tracking Surfaces
- `.claude/TASKS.md` - canonical checklist
- `.claude/PROGRESS.md` - gate status now
- `.claude/ISSUES.md` - active blockers
- `.claude/DECISIONS.md` - locked decisions
- `.claude/SESSION_LOG.md` + `claude/journal.md` - append-only command/evidence trail

## Global Constraints (Fail-Closed)
- Fail-closed behavior overrides convenience.
- No write/apply paths unless explicit dual gate (`ENV=1` + `--apply`) and contract tested.
- No synthetic money defaults (`0`) for missing ads/profit semantics: use `N/A` + reason.
- Active docs must not use absolute personal paths; use repo-relative paths + anchor contracts.
- Stock/inbound trust contract:
  - current stock comes from stock anchor snapshot (`Stock_snapshot` column).
  - inbound transit comes from inbound anchor workbook (`Inbounds_sheet`, `Status=Transit`).

## Primary Gates (must be green for promotion)
- `G0` strict validation
  - `python3 scripts/validate_params.py --strict`
- `G1` test suite
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
- `G2` contract suite
  - `python3 scripts/run_contract_suite.py --fixture small`
- `G3` system validation
  - `python3 scripts/validate_single_truth_system.py`
- `G4` docs + repo hygiene
  - `bash scripts/lint_docs.sh`
  - `bash scripts/check_no_db_tracked.sh`
- `G5` ops stop-line checks
  - `bash scripts/install_single_truth_ops_scheduler.sh --validate-only`
  - `python3 scripts/check_anchor_health.py --project-root <REPO_PATH>`
  - `python3 scripts/ops_status.py --project-root <REPO_PATH>`
  - `python3 scripts/preflight_shipment.py --project-root <REPO_PATH> --json`

## Phase List
## P0_PROMOTION - Promote to `main` (single PR, agent-owned)
### Goal
Promote branch to `main` with decision-grade evidence and rollback.

### Inputs
- branch: `codex/TASK-2w-board-ACB-v2-ads-sidecar`
- evidence root: `exports/validation/board_2w_2026-02-21/`

### Outputs
- evidence doc: `docs/OPS_ROLLOUT_EVIDENCE_TASK_392_ACB_V2_PROMOTION_2026-02-21.md`
- PR link + merge SHA recorded in evidence doc
- `.claude/*` updated to post-merge state

### DoD
- PR merged to `main`
- evidence doc includes G0-G5 pass checklist with artifact pointers
- rollback commands documented

### Stop-line
- any G0-G5 gate red
- any absolute personal path in active docs
- any newly reachable write path without dual gate

## P1_TRUST_CLOSURE_OPS - Inbound + Offer + Profit contracts
### Goal
Keep trust validators fail-closed and stock-cutover consistent with new anchor contract.

### Inputs
- `config/anchors/INBOUND_CALENDAR_LATEST.xlsx`
- `config/anchors/STOCK_SNAPSHOT_LATEST.xlsx`
- `db/app.db`

### Canonical docs
- `docs/po/INBOUND_MISMATCH_RUNBOOK.md`
- `docs/offer/offer_linkage_contract.md`
- `docs/profit/PROFIT_REALISM_CONTRACT.md`

### DoD
- strict chain fails when inbound/offer/profit prerequisites fail
- no numeric profit is published with unresolved prerequisites
- stock truth in active docs points to stock anchor contract only

### Stop-line
- any decision surface emits numeric profit with unresolved prerequisites > 0
- pipeline defaults back to deprecated `Current_stock_*.xlsx` while stock anchor exists

## P2_ADS_SIDECAR_OPS - Read-only ads integration
### Goal
Keep ads sidecar strictly read-only and fail-closed in profit outputs.

### Inputs
- ads contract path resolution (`--ads-db` / `AB_ADS_DB_PATH` / default contract)
- optional effective-cost policy (`AB_ADS_EFFECTIVE_COST_POLICY_PATH` / `config/kaspi_ads_cost_adjustments.yaml`)

### Canonical docs
- `docs/marketing/ADS_SIDE_CAR_CONTRACT.md`
- `docs/marketing/PROFIT_AFTER_ADS_CONTRACT.md`
- `docs/marketing/ADS_EFFECTIVE_COST_POLICY.md`

### DoD
- missing/stale ads source => `N/A` ads metrics and `N/A` profit_after_ads (never `0`)
- outputs include explicit reason string

### Stop-line
- any surface treats missing ads as `0 spend`
- any ads-side write path is reachable without explicit dual gate

## P3_SHIPMENT_SAFETY - No partial silent shipment runs
### Goal
Block shipment/waybill flows when preflight is red; classify partial states with non-zero exit.

### Inputs
- `scripts/ship_orders_api.py`
- `scripts/download_waybills_api.py`
- `excel_ui/run_build_waybills.command`
- `scripts/preflight_shipment.py`

### Canonical docs
- `docs/ops/SHIPMENT_HEALTH_STATES.md`
- `docs/ops/SHIPMENT_PREFLIGHT.md`

### DoD
- shipment does not proceed when preflight is red
- `partial|delayed|api_error|invalid_pdf` states return non-zero and are machine-readable

### Stop-line
- half-done shipment run returns zero exit
- any bypass path skips preflight

## Rollback Baseline
- Revert promotion commit range listed in evidence doc.
- Minimum recheck after rollback:
  - `python3 scripts/validate_params.py --strict`
  - `bash scripts/install_single_truth_ops_scheduler.sh --validate-only`
  - `python3 scripts/check_anchor_health.py --project-root <REPO_PATH>`

## Assumptions policy
- Missing referenced artifacts => phase considered not done.
- Ambiguous data/mapping => fail closed, record issue, lock decision, add regression test.
