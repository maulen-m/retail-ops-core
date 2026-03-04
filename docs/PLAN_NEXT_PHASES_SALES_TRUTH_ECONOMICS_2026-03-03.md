# PLAN_NEXT_PHASES_SALES_TRUTH_ECONOMICS_2026-03-03

## Purpose
Lock in decision-grade shipped truth + sales economics truth so:
1) daily ops cannot go “false-green” on shipped counts,
2) monthly economics cannot drift silently (net rev parity vs independent archive source),
3) profits/COGS are trustworthy enough for PO/capital decisions,
4) human time stays near zero (logins/secrets only),
5) every claim has reproducible evidence (tests + gate transcripts).

This plan is fail-closed by default.

## Phase List

### P0 — Consolidate + Merge to Main (Release-grade evidence)
**Goal (measurable)**
- Merge the consolidation branch into main with a final, commit-matched evidence run:
  - `system_doctor --strict` GREEN on main as-of “today”
  - all required gates GREEN
  - evidence transcript stamped with the final merge commit hash

**Inputs**
- Branch: `codex/TASK-sales-economics-truth-audit-v1` (assumed contains shipped truth + economics audit)
- Key commits (reported): `a08b421`, `2a0bcc0`, `4c5f513`, `5e2bf37`, `1e0199e`, `3ab964d`, `b33116c`
- Gates/entrypoints:
  - `scripts/system_doctor.py`
  - `scripts/validate_shipped_truth_crm_waybill.py`
  - `scripts/validate_business_insides_shipped_truth.py`
  - `scripts/validate_monthly_economics_parity.py`
  - `scripts/validate_sales_archive_statusdate_mapped.py`

**Outputs (artifacts + exact paths)**
- Merge commit on `main`
- Evidence folder (new):
  - `exports/validation/release_sales_truth_econ_<YYYY-MM-DD>/full_gates_green_final.md`
  - `exports/validation/release_sales_truth_econ_<YYYY-MM-DD>/baseline_git_state.json`
  - `exports/validation/release_sales_truth_econ_<YYYY-MM-DD>/doctor_asof_<YYYY-MM-DD>/full_doctor_run.md`
- Optional: Oracle pack for merged main (if standard)

**Definition of Done**
Accepted as done only when:
- Main branch includes the merged changes AND
- All gates are green on main AND
- Evidence transcript includes the exact final merge commit hash and is stored under `exports/validation/release_sales_truth_econ_<YYYY-MM-DD>/`.

**Validation / Gates**
Run (on main, clean status):
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
- `python3 scripts/validate_params.py --strict`
- `bash scripts/lint_docs.sh`
- `python3 scripts/system_doctor.py --strict --project-root . --as-of <today>`
- `python3 scripts/validate_shipped_truth_crm_waybill.py --since 2026-02-01 --until 2026-03-01 --strict`
- `python3 scripts/validate_business_insides_shipped_truth.py --since 2026-02-01 --until 2026-03-01 --strict`
- `python3 scripts/validate_monthly_economics_parity.py --since 2025-06-06 --until 2026-03-02 --strict`

**Rollback / Backout**
- Revert the merge commit (single revert commit).
- Do not delete evidence artifacts; mark rollback in `.claude/DECISIONS.md`.

**Stop-the-line**
- Any required gate fails.
- Evidence transcript does not match the commit that was merged.
- Any change recomputes business math in UI layer instead of DB/script layer.

---

### P1 — H5 Proving Run Continuation (Daily fail-closed discipline)
**Goal (measurable)**
- 14 consecutive days where daily ops produces required artifacts and strict doctor is GREEN.

**Inputs**
- Runbooks/contracts:
  - `docs/ops/H5_OPERATIONAL_PROVING_RUN_CONTRACT.md`
  - `docs/ops/H5_DAILY_EXECUTION_RUNBOOK.md`
- Entrypoints:
  - `scripts/run_h5_proving_day.py` (or daily orchestrator)
  - `scripts/system_doctor.py`

**Outputs**
- Daily artifacts under:
  - `exports/daily/<YYYY-MM-DD>/daily_ops_report.json`
  - `exports/daily/<YYYY-MM-DD>/daily_ops_report.md`
  - `exports/diagnostics/<YYYY-MM-DD>/system_health.{json,md}` (if configured)
- Weekly rollups as configured (scorecards)

**Definition of Done**
Accepted as done only when:
- A 14-day streak exists with:
  - `system_doctor --strict` GREEN each day
  - no missing daily artifact sets
  - exceptions triaged and recorded
- Streak evidence index exists:
  - `exports/validation/h5_proving_streak_<start>_to_<end>/streak_summary.md`

**Validation / Gates**
Daily:
- `python3 scripts/system_doctor.py --strict --project-root . --as-of <day>`
- `python3 scripts/validate_h5_artifact_set.py --as-of <day> --strict` (if present)

**Rollback**
- Disable/stop scheduler job (fail-closed) and revert the last automation change if needed.

**Stop-the-line**
- Any day produces doctor RED.
- Any required artifact is missing.
- Any auto-write path runs without canary/rollback evidence.

---

### P2 — Economics Trust Hardening (line-level formula parity vs v8)
**Goal (measurable)**
- Prove that DB economics outputs (net_rev, COGS, profit) match owning formulas for a deterministic sample, then scale to “all rows” where feasible.
- Eliminate the “profits look suspicious” class of failures by making formula compliance machine-verified.

**Inputs**
- Owning rules/spec:
  - `docs/inventory/Master_Inventory_Rules_v8.md`
- Data:
  - DB tables/views used by `fact_sales` and published truth
  - Exported mapped archive dataset:
    - `exports/sales_archive_statusdate_mapped/2025-06-06_to_2026-03-02/ArchiveSales_ALL_STORES_statusdate_mapped.csv`

**Outputs**
- New validator (proposed):
  - `scripts/validate_sales_economics_line_parity.py`
- New tests:
  - `tests/test_validate_sales_economics_line_parity.py`
- New evidence artifacts:
  - `exports/validation/economics_line_parity/<YYYY-MM-DD>/report.md`
  - `exports/validation/economics_line_parity/<YYYY-MM-DD>/mismatches.csv`

**Definition of Done**
Accepted as done only when:
- Validator exists with strict mode and deterministic sampling rules.
- Validator is wired into `system_doctor --strict` (or equivalent strict chain).
- For decision-grade months (>= contract cutover), mismatch count is 0 in strict mode.

**Validation / Gates**
- Unit tests for formula components (commission, delivery, VAT, landed COGS, returns semantics).
- `python3 scripts/validate_sales_economics_line_parity.py --since 2026-01-01 --until <today-1> --strict`
- `python3 scripts/system_doctor.py --strict --as-of <today>`

**Rollback**
- If the validator finds mismatches: STOP, log mismatches, and fix formulas or data mappings.
- If validator itself is wrong: update owning contract doc first, then code.

**Stop-the-line**
- Any attempt to “fix” parity by loosening tolerances without updating the contract doc.
- Any formula conflict with v8 not resolved via doc-first change control.

---

### P3 — Decision-Grade Scope Expansion (StatusDate backfill pre-2026-01) — OPTIONAL
**Goal (measurable)**
- Increase statusDate coverage for delivered rows prior to 2026-01-01 OR explicitly lock “provisional-only” policy for those months (with hard labeling everywhere).

**Inputs**
- `exports/sales_archive_statusdate_mapped/.../source_manifest.json`
- UI export sources (may require minimal human login once to refresh)
- `scripts/export_sales_archive_statusdate_mapped.py`

**Outputs**
- Updated UI pack anchor + hashes (if additional sources are added):
  - `config/anchors/<new_ui_pack>.json`
- Expanded mapped dataset and parity outputs.

**Definition of Done**
Accepted as done only when EITHER:
- StatusDate coverage is materially improved (target: >=95% for delivered rows in expanded window), and monthly parity remains GREEN; OR
- The system enforces and displays “PROVISIONAL” for pre-cutover months everywhere, and no operator-facing output presents it as decision-grade.

**Validation / Gates**
- `python3 scripts/validate_sales_archive_statusdate_mapped.py --since <older> --until <today> --strict`
- `python3 scripts/validate_monthly_economics_parity.py --since <older> --until <today> --strict`
- Schema/hash validation for all anchors.

**Rollback**
- Keep cutover at 2026-01-01 and mark earlier as provisional; do not force backfill with unstable automation.

**Stop-the-line**
- Requires more than “0–5% human time” to maintain.
- UI export automation becomes flaky/non-deterministic (must fail closed).

---

### P4 — Observability + Alerts (economics + shipped truth)
**Goal (measurable)**
- Add anomaly detection and alerting on:
  - unusual margin spikes/drops,
  - sudden COGS zeros,
  - shipped parity drift,
  - economics parity drift.

**Inputs**
- Existing validators + daily artifacts.
- Weekly scorecard contract(s).

**Outputs**
- New anomaly report (proposed):
  - `exports/diagnostics/<YYYY-MM-DD>/economics_anomalies.{json,md}`
- Alerts integrated to existing channel (e.g., WhatsApp sender) but only after strict gates pass.

**Definition of Done**
Accepted as done only when:
- Alerts trigger on injected test anomalies.
- Alerts never “mask” a red gate (i.e., they complement fail-closed gates, not replace them).

**Validation / Gates**
- Tests that simulate anomalies and assert alerts are emitted.
- `system_doctor --strict` remains GREEN in normal conditions.

**Rollback**
- Disable alert sender while keeping validators fail-closed.

**Stop-the-line**
- Alerts are used as a substitute for gates.
- Any silent failure path exists.

---

### P5 — Remove Excel Dependency for SKU Identity in Completed Orders (unlock order-level COGS/profit)
**Goal (measurable)**
- Ensure completed orders have deterministic `sku_key` / `my_size` so order-level BI can compute COGS/profit without N/A.

**Inputs**
- `core/parsers/kaspi_parser.py`, offer mapping tables, `dim_sku`, order ingest pipeline, BI generator.

**Outputs**
- Enrichment logic + validator + tests.
- BI no longer shows N/A COGS/profit in decision windows due to missing identity.

**Definition of Done**
Accepted as done only when:
- Missing sku identity count == 0 for completed orders in BI window (strict).
- BI COGS/profit populate deterministically.
- Strict validators pass.

**Validation / Gates**
- New strict gate: `python3 scripts/validate_completed_orders_identity.py --since <window> --strict`
- Existing BI validators and system doctor strict.

**Rollback**
- Keep fail-closed N/A; do not fill via heuristics.

**Stop-the-line**
- Any non-deterministic mapping (regex hacks) without tests and contract update.

---

### P6 — Governance Hardening (tiny but important)
**Goal (measurable)**
- Remove “missing CLAUDE.md” drift vector and strengthen doc-indexing.

**Inputs**
- `AGENTS.md`, `.claude/*`, docs index.

**Outputs**
- `CLAUDE.md` minimal stub (title + purpose + pointers), committed.
- Doc-lint updated if needed.

**Definition of Done**
Accepted as done only when:
- `CLAUDE.md` exists and points to the canonical reading set.
- Doc-lint + tests remain green.

**Validation / Gates**
- `bash scripts/lint_docs.sh`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`

**Rollback**
- Revert the doc-only commit.

**Stop-the-line**
- None beyond standard required gates.

---

## If attachments are missing — Assumptions Policy
- If an expected export/anchor file is missing: STOP and fail closed, emitting a “missing inputs” report with the exact path(s).
- If commit IDs are missing from context: proceed by referencing file paths + current git HEAD, but do not claim parity or correctness without re-running gates and capturing transcripts.
- If sources conflict:
  - Resolve using the repo’s single-truth ladder (owning docs win; DB is operational truth; exports are derived).
  - Update owning doc FIRST if a formula/rule must change; then update code; then update Excel parity targets.