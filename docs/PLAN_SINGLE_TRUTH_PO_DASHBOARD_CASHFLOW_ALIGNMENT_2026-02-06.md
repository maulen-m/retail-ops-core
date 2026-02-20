# Plan: Single-Truth PO Dashboard + Inventory/Cashflow Alignment
**Date:** 2026-02-06  
**Owner task:** TASK-376  
**Scope:** Kaspi-only

## Objective
Close remaining Reality Bridge gaps by making `REAL_ARCHIVE` PO rows mathematically truthful (timeline-based recompute), aligning PLAN/REAL semantics, and adding cross-realm validators so PO dashboard, inventory snapshots, and cashflow checks cannot drift silently.

## Locked decisions
- `REAL_ARCHIVE` rows use full recompute, not plan-baseline override.
- Real archive baseline uses message-date snapshot (`MAX(snapshot_date <= message_date)`).
- Consumption keeps theoretical `D*L` and adds capped metric for operations.
- DOC display uses half-up rounding to 1 decimal.
- Unrelated unstaged changes are out of scope and must be ignored.

## Single-truth contract
- Formula source: `docs/inventory/Master_Inventory_Rules_v8.md`
- PO logic source: `docs/protocol/active/PO_making_logic_v2.md`
- Schema source: `docs/inventory/Sales_Data_Model_V16.md`
- Dashboard is derived from DB facts; browser must not recompute business math.
- Cashflow drift checks remain mandatory and must stay compatible with PO changes.

## Execution phases

### Phase 0: Governance + memory updates
1. Record task claim and stop conditions in `.claude/TASKS.md`.
2. Set next gate target in `.claude/PROGRESS.md`.
3. Record decisions in `.claude/DECISIONS.md`.
4. Log READCHECK and planned gates in `.claude/SESSION_LOG.md`.

### Phase 1: Tests-first (must fail before code changes)
1. Add `tests/test_real_archive_recompute.py` for:
   - message-date snapshot baseline
   - self-inbound exclusion
   - recomputed pre/post DOC correctness
   - capped consumption field presence
2. Add `tests/test_po_doc_rounding.py` for half-up tie behavior.
3. Extend `tests/test_validate_po_dashboard_invariants.py`:
   - real archive formula consistency
   - real archive DOC monotonicity
   - capped consumption field validation
4. Add `tests/test_validate_single_truth_alignment.py`:
   - `REAL_ARCHIVE` qty matches `po_line`
   - baseline snapshot policy enforcement
   - integration hooks for drift/cashflow checks
5. Run only new/changed tests and capture failing evidence.

### Phase 2: PO engine/dashboard implementation
1. Add reusable helper module: `core/po/dashboard_math.py`
   - half-up 1dp rounding
   - DOC helper from `(pre_arrival, qty, demand)`
2. In `scripts/generate_po_dashboard_data.py`:
   - add full-recompute builder for `REAL_ARCHIVE` rows
   - compute `stock_at_msg`, `consumption_until_arrival`, `consumption_until_arrival_capped`, `pre_arrival`, `pre_arr_doc`, `post_arr_doc`
   - preserve canonical demand/economics inputs from existing generator path
3. Replace archive construction path:
   - remove archive dependence on `apply_po_overrides(copy.deepcopy(base_template), ...)`
   - use new full-recompute path for `PO-*`/`Line52_PO-9`
4. Apply same half-up DOC rounding to PLAN rows for consistent presentation.
5. Keep `apply_po_overrides` for plan bootstrap behavior only.

### Phase 3: Cross-realm alignment validator
1. Add `scripts/validate_single_truth_alignment.py`.
2. Checks:
   - `REAL_ARCHIVE` SKU/size qty equality vs `po_line`
   - message-date snapshot baseline policy in payload
   - dashboard aggregate consistency
   - invocation of drift/cashflow checks in summary mode
3. Integrate validator into strict gate chain (pipeline step and standalone command).

### Phase 4: Docs/contracts updates
1. Update `docs/validation/DASHBOARD_CONTRACT.md`:
   - real archive recompute semantics
   - baseline policy
   - half-up DOC rounding
   - capped consumption field
2. Update `docs/ARCHITECTURE.md`:
   - explicit single-truth flow: inventory snapshot -> PO dashboard state -> cashflow drift gate.
3. Keep `.claude` memory docs updated during and after implementation.

### Phase 5: Validation + completion evidence
1. Targeted tests (new/changed) green.
2. Regenerate dashboard export and verify line61 regression case.
3. Run required gates:
   - `python3 scripts/validate_params.py --strict`
   - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q`
   - `python3 scripts/run_contract_suite.py --fixture small`
   - `python3 scripts/validate_po_dashboard_invariants.py`
   - `python3 scripts/validate_single_truth_alignment.py`
   - `python3 scripts/validate_cashflow_invariants.py`
   - `python3 scripts/validate_inventory_cost_drift.py`
   - `scripts/lint_docs.sh`
   - `scripts/check_no_db_tracked.sh`
4. If all prior gates are green and apply-run is needed:
   - create DB backup first and log path
   - run `ENABLE_CASHFLOW_WRITE=1 python3 scripts/run_end_of_day.py --verbose`

## Rollback
1. Code: `git revert <newest> ... <oldest>`
2. DB: restore from recorded pre-apply backup path.

## Done criteria
- New tests fail-before-fix then pass.
- `REAL_ARCHIVE` rows are no longer stale-plan-derived.
- PLAN/REAL semantics remain explicit and invariant-checked.
- Full gate chain green with evidence logged in `.claude/SESSION_LOG.md`.

## Execution status (2026-02-06)
- Completed:
  - Tests-first coverage added and passing for real-archive recompute, DOC half-up rounding, invariants, and single-truth alignment validator.
  - `REAL_ARCHIVE` generation moved to message-date snapshot recompute path.
  - Half-up DOC rounding enforced through shared helper for plan and archive display fields.
  - Added `scripts/validate_single_truth_alignment.py` and wired it into EOD pipeline pre-export checks.
  - Updated dashboard contract + architecture docs for single-truth semantics.
- Remaining blocker:
  - Cross-realm drift gate still fails (`validate_inventory_cost_drift.py`) with:
    - `snapshot_cost_kzt=28,386,072.00`
    - `cashflow_cost_kzt=26,879,424.00`
    - `diff_kzt=1,506,648.00` (`allowed=567,721.44`)
  - Therefore full-green EOD chain is not complete yet.
