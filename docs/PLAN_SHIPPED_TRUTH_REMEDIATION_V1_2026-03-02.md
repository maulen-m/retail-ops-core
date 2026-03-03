# PLAN_SHIPPED_TRUTH_REMEDIATION_V1_2026-03-02

## Scope
- Repo: `~/Docs/Autonomous_business`
- Branch/worktree: `codex/TASK-shipped-truth-remediation-v1` (single worktree)
- Phases: `ST0, ST1, ST2, ST3, ST4, ST5` (optional `ST6` proving-run resume)

## Operating Constraints
- Append-only journal at `claude/journal.md` with Asia/Qyzylorda timestamps.
- Fail-closed on missing inputs (tokens, archives, anchors): emit exception artifact and classify `INCONCLUSIVE`.
- Docs/contracts define formulas/thresholds; DB is operational truth; exports are derived.
- Default DRY-RUN; any write/apply path requires explicit gate + backup + write log.

## READCHECK Authority
- `docs/inventory/Master_Inventory_Rules_v8.md`
- `docs/protocol/active/PO_making_logic_v2.md` (resolved from requested `protocol/active/...`)
- `docs/inventory/Sales_Data_Model_V16.md`
- `docs/ARCHITECTURE.md`
- `docs/validation/PO_CONTRACT.md`
- `docs/validation/SHIPPED_TRUTH_CRM_WAYBILL_CONTRACT.md`

## ST0 — Provenance Lock + Baseline
### Deliverables
- `exports/validation/shipped_truth_crm_waybill/remediation_2026-03-02/baseline_repo_state.json`
- `exports/validation/shipped_truth_crm_waybill/remediation_2026-03-02/baseline_commands.md`

### Gates
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
- `python3 scripts/validate_params.py --strict`
- `python3 scripts/validate_single_truth_system.py`
- `bash scripts/lint_docs.sh`

## ST1 — Contract/Metric Alignment (Cancel Drift Semantics)
### Implementation
- Update cancel-drift semantics in:
  - `docs/validation/SHIPPED_TRUTH_CRM_WAYBILL_CONTRACT.md`
  - `scripts/validate_shipped_truth_crm_waybill.py`
- Update tests:
  - `tests/test_validate_shipped_truth_crm_waybill.py`
  - `tests/test_shipped_truth_contract.py`

### Evidence
- `exports/validation/shipped_truth_crm_waybill/semantics_fix_2026-03-02/`

### Gates
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
- `bash scripts/lint_docs.sh`
- `python3 scripts/validate_shipped_truth_crm_waybill.py --since 2026-02-01 --until 2026-03-02 --strict`

## ST2 — Last 30 Completed Days to PASS
### Implementation
- Build mismatch triage pack with root-cause labels:
  - `exports/validation/shipped_truth_crm_waybill/triage_last30_2026-03-02/`
- Remediate true mismatches without hidden threshold loosening.
- If DB writes are required:
  - backup to `db/backups/app.db.pre_st2_<timestamp>.sqlite`
  - write `db_write_log.md` in triage folder.

### Acceptance Gate
- `python3 scripts/validate_shipped_truth_crm_waybill.py --since 2026-02-01 --until 2026-03-01 --strict`
- Target: PASS (`0% mismatch`, `<=2% drift`, `<=2% waybill missing`).

## ST3 — Integrate into BI/Daily Outputs
### Implementation
- Ensure BUSINESS_INSIDES shipped totals align to shipped-truth totals (last 30 completed days).
- Add BI alignment validator and tests.

### Gates
- Baseline gates
- shipped-truth gate PASS
- BI validator PASS

## ST4 — Observability + Exceptions Loop
### Implementation
- Typed shipped-truth exception emission with links to mismatch IDs + reports.
- Ensure strict doctor is GREEN when shipped-truth gate is GREEN and red otherwise.

### Gate
- `python3 scripts/system_doctor.py --strict --project-root . --as-of 2026-03-02`

## ST5 — Full Historical Audit Closure
### Implementation
- Rerun `2024-06-06..today` in deterministic monthly windows.
- Emit:
  - `window_summary.{md,json}`
  - `coverage_index.csv`
  - `top_root_causes.md`
- Explicit classification per window/day: `PASS` / `FAIL` / `INCONCLUSIVE`.

### Stop-the-line Rules
- Any skipped/failed gate.
- Missing tokens/archives for decision-grade scope.
- Any mixed truth-source logic that bypasses contract.

## Optional ST6 — Proving-Run Resume
- Resume strict proving run only after ST2–ST5 gates are green.
