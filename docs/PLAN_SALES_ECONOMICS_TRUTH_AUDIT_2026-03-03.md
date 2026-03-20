## Risks + likely regressions to watch

False-green economics: using fact_sales as “economics truth” without proving it implements v8 net-rev + COGS formulas and without proving coverage completeness for the month.

Anchor drift: CSV anchors sitting outside repo can change; must pin with config/anchors/* manifests and validate hashes/staleness.

Date-basis mismatch: “delivered month” cannot be verified using a dataset missing status-change dates (e.g., the mapped all-store file reported to have empty Дата изменения статуса).

Store alias normalization: mismatches caused by UNIVERSAL vs Universal, etc; must be centralized and unit-tested.

## Biggest unknowns (assumptions; no questions unless blocking)

Assumption A: Closeout commits above exist as stated and are either merged to main or will be merged; plan treats them as current working baseline.

Assumption B: There is not yet a single status-date mapped all-store archive export spanning 2025-06-06..2026-03-02; it must be produced to validate monthly economics externally.

Assumption C: Monthly profit figures shown are gross profit (not including OPEX) unless the v8 ads/VAT components are explicitly proven to be included; this must be made explicit in a contract.

# PLAN_SALES_ECONOMICS_TRUTH_AUDIT_2026-03-03

## Purpose
Produce decision-grade, fail-closed monthly sales economics (Units / NetRev / COGS / Profit) and eliminate “suspicious profit” ambiguity by:
1) Locking definitions + formulas to canonical docs (v8 rules),
2) Generating a single status-date mapped all-store sales archive dataset for 2025-06-06..2026-03-02,
3) Implementing a parity gate that prevents profit inflation and blocks decision-grade outputs when any comparison is uncertain.

This plan assumes shipped-truth closeout exists on branch `codex/TASK-shipped-truth-remediation-v1` (commits a08b421, 2a0bcc0, 4c5f513, 5e2bf37 reported) and that shipped truth gates are green for 2026-02-01..2026-03-01.

## Global constraints (non-negotiable)
- Fail-closed: missing inputs, stale anchors, missing tokens, schema drift, or parity mismatch => STOP.
- Single-truth ladder:
  1) `docs/inventory/Master_Inventory_Rules_v8.md` (formulas/parameters) is canonical.
  2) Repo contracts + runbooks.
  3) DB is operational truth; dashboards/exports are derived.
- No “false-green”: do not relax thresholds to make tests pass.
- Writes are opt-in only. Default mode is validate-only / dry-run.

## Phase List

### P0 — READCHECK + Baseline Verification (Shipped-Truth Closeout)
**Goal (measurable)**
- Confirm repo baseline is deterministic and all existing strict gates are green.
- Record a baseline snapshot of git state + key validation artifacts.

**Inputs (files/systems)**
- Repo: `<REPO_PATH>`
- Branch: `codex/TASK-shipped-truth-remediation-v1` (or merge-base main)
- Gates: `scripts/system_doctor.py`, shipped-truth validators, BI shipped validator
- Existing artifacts (reported):
  - `exports/validation/shipped_truth_crm_waybill/closeout_2026-03-03/full_gates_green_final.md`
  - `exports/validation/business_insides_shipped_truth/2026-02-01_to_2026-03-01/summary.json`

**Outputs (artifacts + exact paths)**
- `exports/validation/economics_truth_audit/2026-03-03/baseline_git_state.json`
- `exports/validation/economics_truth_audit/2026-03-03/baseline_gates.md` (full transcript)
- `docs/PLAN_SALES_ECONOMICS_TRUTH_AUDIT_2026-03-03.md` (this plan file)

**Accepted as done only when**
- `git status --porcelain` is empty.
- Baseline evidence files above exist and reference exact commands and outputs.
- All P0 gates are green.

**Validation/Gates**
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
- `python3 scripts/validate_params.py --strict`
- `python3 scripts/validate_single_truth_system.py`
- `bash scripts/lint_docs.sh`
- `python3 scripts/system_doctor.py --strict --project-root . --as-of 2026-03-02`

**Rollback / backout**
- No writes expected. If anything wrote to DB, stop and restore from latest backup, then re-run P0.

**Stop-the-line**
- Any gate fails, or git is dirty, or DB writes occurred without explicit apply/backup evidence.


### P1 — Economics Truth Contract (Definitions + Formula Alignment)
**Goal (measurable)**
- Make economics definitions unambiguous and machine-testable:
  - What counts as delivered sales (date basis)
  - Exact NetRev/COGS/Profit formulas (match v8 or explicitly document exceptions)
  - Whether Profit includes VAT and Ads costs (as per v8) or is “gross profit before ads” (must be explicit)

**Inputs**
- Canonical: `docs/inventory/Master_Inventory_Rules_v8.md`
- Architecture: `docs/ARCHITECTURE.md`
- Existing data model for sales (DB views/tables; inspect in repo)

**Outputs**
- New contract doc: `docs/validation/SALES_ECONOMICS_TRUTH_CONTRACT.md`
- New helper module (if needed): `core/economics/economics_math.py`
- Unit tests: `tests/test_economics_math_contract.py`

**Accepted as done only when**
- Contract doc defines:
  - `delivered_truth_date` (e.g., statusChangeDate) and “closed month” rule
  - NetRev/COGS/Profit formulas, including VAT/commission/delivery/ads treatment
  - Handling of returns/cancellations/chargebacks
  - “Decision-grade” vs “provisional/estimate” labeling rules
- Unit test(s) validate formula outputs on fixed fixtures (no floating ambiguity; define rounding rules).

**Validation/Gates**
- `bash scripts/lint_docs.sh`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_economics_math_contract.py`

**Rollback**
- Revert new contract + helper if conflicts found; do not ship partial definitions.

**Stop-the-line**
- Any formula ambiguity remains (e.g., Profit definition differs across docs/code), or tests cannot pin rounding/inputs.


### P2 — Canonical Status-Date Sales Archive Dataset (All Stores, Mapped; 2025-06-06..2026-03-02)
**Goal (measurable)**
- Produce a single all-store dataset that supports delivered-month aggregation and SKU mapping:
  - Includes delivered status + status-change date
  - Includes store, order_id, quantity, amounts
  - Includes mapped SKU key and size
- Coverage requirement:
  - All configured stores present
  - For delivered rows: status-change date is non-null
  - Deterministic outputs (stable ordering + stable schema)

**Inputs**
- API/UI archive sources available in repo (per existing contracts):
  - `docs/validation/KASPI_ARCHIVE_API_PACK_CONTRACT.md`
  - `docs/validation/KASPI_ARCHIVE_UI_PACK_CONTRACT.md`
  - `config/anchors/kaspi_archive_ui_pack.json` (if UI pack source is used)
- SKU mapping logic (existing)
- Target range: `since=2025-06-06`, `until=2026-03-02`

**Outputs**
- New exporter: `scripts/export_sales_archive_statusdate_mapped.py`
- New validator: `scripts/validate_sales_archive_statusdate_mapped.py`
- Export artifacts:
  - `exports/sales_archive_statusdate_mapped/2025-06-06_to_2026-03-02/ArchiveSales_ALL_STORES_statusdate_mapped.csv`
  - `exports/sales_archive_statusdate_mapped/2025-06-06_to_2026-03-02/schema.json`
  - `exports/sales_archive_statusdate_mapped/2025-06-06_to_2026-03-02/summary_by_store_month.csv`
  - `exports/sales_archive_statusdate_mapped/2025-06-06_to_2026-03-02/source_manifest.json` (what sources were used; hashes if local files)

**Accepted as done only when**
- Validator PASS:
  - Schema matches `schema.json`
  - No missing status-change date for delivered rows
  - No duplicate primary keys (`store_code + order_id + line_id` or documented equivalent)
  - Mapping coverage meets minimum threshold (e.g., ≥ 99.5% mapped_sku_key on delivered rows; any unmapped rows are explicitly listed and block decision-grade economics)
- Exporter supports `--reuse-cache` and does not re-fetch when cached files exist.

**Validation/Gates**
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_export_sales_archive_statusdate_mapped.py`
- `python3 scripts/validate_sales_archive_statusdate_mapped.py --since 2025-06-06 --until 2026-03-02 --strict`
- Plus P0 gates.

**Rollback**
- Pure export + validation should be non-destructive.
- If exporter writes to DB: STOP; require apply flag + DB backup + documented rollback.

**Stop-the-line**
- Any store missing.
- Any delivered rows without status-change date.
- Any missing API tokens / missing anchor pack => fail-closed with actionable error message.


### P3 — Monthly Economics Parity Gate (DB Truth vs Archive-Mapped; Conservative)
**Goal (measurable)**
- Compute monthly Units/NetRev/COGS/Profit from canonical DB truth and compare against the new archive-mapped dataset for the same delivered-month basis.
- Block “too-good” profit by enforcing conservative inequality:
  - DB delivered Units and NetRev must NOT exceed archive-mapped delivered Units/Amount beyond a small tolerance for closed months.

**Inputs**
- DB delivered truth views/tables (as defined in P1 contract)
- P2 dataset CSV
- Optional external CSV anchors (non-decision-grade; used for diagnostics only):
  - `/.../Archive_sales_normalized_backfilled_22.2.26.csv`
  - `/.../ArchiveOrders_ALL_STORES_mapped_20260228_200146_final.csv`

**Outputs**
- New parity validator:
  - `scripts/validate_monthly_economics_parity.py`
- Artifacts:
  - `exports/validation/economics_parity/2025-06-06_to_2026-03-02/summary.json`
  - `exports/validation/economics_parity/2025-06-06_to_2026-03-02/monthly_db.csv`
  - `exports/validation/economics_parity/2025-06-06_to_2026-03-02/monthly_archive.csv`
  - `exports/validation/economics_parity/2025-06-06_to_2026-03-02/diffs_by_month.csv`
  - `exports/validation/economics_parity/2025-06-06_to_2026-03-02/mismatch_ids.csv` (if applicable)
  - `exports/validation/economics_parity/2025-06-06_to_2026-03-02/report.md`

**Accepted as done only when**
- For each closed month in range:
  - `db_units <= archive_units * (1 + tol)` and `db_net_rev <= archive_amount_proxy * (1 + tol)` where `tol` is defined by contract (default: 0.5%).
  - Any exception requires explicit allowlist entry with evidence + expiry.
- Script exits non-zero on failure (strict fail-closed).
- `system_doctor --strict` can include a bounded version of this gate (e.g., last closed month only).

**Validation/Gates**
- Unit tests: `tests/test_validate_monthly_economics_parity.py`
- Gate run:
  - `python3 scripts/validate_monthly_economics_parity.py --since 2025-06-06 --until 2026-03-02 --strict`
- Full chain transcript:
  - `exports/validation/economics_parity/2026-03-03/full_gates_green_final.md`

**Rollback**
- Revert code + remove doctor wiring if it breaks runtime budgets.

**Stop-the-line**
- Any month where DB economics exceed archive-derived delivered totals beyond tolerance.
- Any “estimate tail” included in a month labeled decision-grade.


### P4 — Profit Suspicion Root-Cause + Remediation Loop
**Goal (measurable)**
- Explain “high profit” with evidence, or fix inflation.
- Deliver an auditable breakdown by store + SKU of profit drivers.

**Inputs**
- Outputs from P3 (diffs + mismatch IDs)
- P1 formula contract
- Existing validators (COGS integrity, SKU mapping integrity)

**Outputs**
- `scripts/audit_profit_outliers.py` (or integrated into parity tool)
- Artifacts:
  - `exports/validation/economics_parity/2025-06-06_to_2026-03-02/profit_outliers.csv`
  - `exports/validation/economics_parity/2025-06-06_to_2026-03-02/root_cause_report.md`
  - If fixes are made: regenerate P3 artifacts and show deltas before/after.

**Accepted as done only when**
- Every flagged anomaly has a classified root cause:
  - formula mismatch, missing cost inputs, mapping error, duplicate counting, returns handling, etc.
- After remediation, P3 parity is PASS for closed months and outlier counts are within contract thresholds.

**Validation/Gates**
- Re-run P0 + P3 gates.
- Add regression tests for any identified root cause.

**Rollback**
- If remediation touches DB write paths: require backup + apply flag + rollback script or documented restore.

**Stop-the-line**
- Any change that alters formulas without updating `docs/inventory/Master_Inventory_Rules_v8.md` first.
- Any silent “best-effort” fallback that publishes profit when inputs are incomplete.


### P5 — Automation + Observability
**Goal (measurable)**
- Make economics parity visible and automatic with minimal human involvement.

**Inputs**
- Existing orchestration + scorecards:
  - `scripts/system_doctor.py`
  - daily/weekly scorecard builders
  - exceptions pipeline

**Outputs**
- Doctor wiring (bounded):
  - add an option like `--economics-window last_closed_month` default in strict mode
- Daily/weekly artifacts:
  - `exports/diagnostics/<date>/economics_health.{json,md}`
  - `exports/exceptions/<date>/exceptions.json` includes economics parity failures

**Accepted as done only when**
- Doctor is GREEN when parity is green; RED with actionable diffs when parity fails.
- Runtime remains within budgets (documented).

**Validation/Gates**
- `python3 scripts/system_doctor.py --strict --project-root . --as-of 2026-03-02`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`

**Rollback**
- Feature-flag doctor wiring; revert if runtime or flakiness increases.

**Stop-the-line**
- Any automation that can publish decision-grade economics without passing P3.


### P6 — Scale/Hardening
**Goal (measurable)**
- Deterministic, cached, bounded historical recompute; no re-fetch storms.
- Stable schemas and pinned anchors.

**Outputs**
- Cache manifest + reuse policy in exporter
- Documentation update in ops runbooks
- Optional: performance benchmarks in exports

**Accepted as done only when**
- Historical recompute can be re-run without changing outputs (idempotent) and without manual steps.

**Stop-the-line**
- Any non-deterministic behavior in scheduler paths.

## If attachments are missing — assumptions policy
- Missing external CSV anchors: do NOT guess. Record missing paths in `source_manifest.json`.
  - In `--strict` mode for parity: FAIL if contract requires them; otherwise continue but mark “anchor unavailable”.
- Missing API tokens: FAIL immediately (fail-closed).
- Missing UI pack anchor: FAIL if UI pack is configured as required source; otherwise downgrade to API-only and mark “coverage incomplete”.
- Any conflicting definition between code and v8 rules: v8 wins; update doc first, then code; log to `.claude/DECISIONS.md`.
