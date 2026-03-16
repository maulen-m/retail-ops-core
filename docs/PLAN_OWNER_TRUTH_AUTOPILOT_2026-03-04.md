# PLAN_OWNER_TRUTH_AUTOPILOT_2026-03-04

## Purpose
Deliver decision-grade owner economics with fail-closed governance:
- Net Revenue / COGS / Profit
- Profit after Ads (locked unless ads readiness is GREEN)
- Profit after OPEX (locked unless opex readiness is GREEN)
- Profit realism checks to address “profits seem too high” with reconciliation-grade evidence.

This plan assumes the clearance plan is currently GREEN and focuses on making it durable, automated, and harder to falsify via stale sources or UI recomputation.

Risks + likely regressions to watch

UI pack freshness drift: if UI status-date refresh stops, REFERENCE_STALE will return (and should). Main regression risk is “someone loosens lag/tolerances” instead of fixing source freshness.

Ads pipeline drift: ads scheduling noted as daily, not hourly; if it stops running, readiness will correctly fail. Risk is operators bypassing readiness to “see numbers.”

Identity drift relapse: new offers can reintroduce null sku_key/sku_id/my_size if ingestion changes; keep strict gates wired into doctor and treat “auto-fix backfill” as a deliberate write (not silent).

Truth-surface recomputation risk: any ASCII/dashboard surface that re-computes business math from raw exports can diverge. Owner surfaces must render from a single canonical OWNER_PNL.json.

Biggest unknowns (assumptions; no questions unless blocking)

Whether ads DB scheduler is continuously running and updating the external ads DB (the contract expects freshness; the schedule described appears daily). Assume it can be made reliable via heartbeat validation + a single forced refresh run if stale.

Whether OPEX is already being synced daily in the current operational run. Evidence suggests an OPEX sync path exists (scripts/sync_opex_schedule.py) but owner PnL still needs explicit integration + gating (so it can’t silently omit OPEX).

TASKS

Bank/cash reconciliation tolerance policy is not fully codified yet; assume we implement a strict “cash reality” validator scoped to last N months and gated by anchor availability.

## Context / Current Baseline
Evidence indicates strict chain is GREEN for `--as-of 2026-03-04`, with transcript:
- `exports/validation/clearence_plan_2026-03-04/full_execution_transcript.md`

Recorded implementation scope includes base commit `5e2bf37` → HEAD `0d7b0e2` (assumption: clearance plan is included in/after this head). If actual HEAD differs, capture it in Phase P0 READCHECK and treat as the authoritative baseline.

## Phases (single-agent sequential; fail-closed)

### Phase P0 — Baseline Freeze + Owner Decision Pack
**Goal (measurable)**
- Produce a single owner-grade artifact set for the latest `AS_OF` day:
  - Canonical JSON (`OWNER_PNL.json`)
  - Human-readable Markdown (`OWNER_PNL.md`)
  - ASCII table (`OWNER_PNL_ASCII.txt`)
- Guarantee these three are generated from the same canonical calculation (no duplicated business math).

**Inputs**
- `scripts/build_owner_pnl_report.py`
- `docs/validation/OWNER_PNL_PUBLICATION_CONTRACT.md`
- Strict chain/gates referenced in clearance transcript.
- Current db: `db/app.db`

**Outputs (exact paths)**
- `exports/owner_pnl/<AS_OF>/OWNER_PNL.json`
- `exports/owner_pnl/<AS_OF>/OWNER_PNL.md`
- `exports/owner_pnl/<AS_OF>/OWNER_PNL_ASCII.txt`
- `exports/validation/owner_truth_baseline/<AS_OF>/full_gates_green_final.md` (full command transcript)
- `exports/validation/owner_truth_baseline/<AS_OF>/baseline_git_state.json` (git HEAD + status)

**Definition of Done**
Accepted as done only when:
1) `OWNER_PNL.md` and `OWNER_PNL_ASCII.txt` are rendered from `OWNER_PNL.json` (no recomputation).
2) The strict gate chain is GREEN for `AS_OF`.
3) Artifacts exist at the paths above and are deterministic (rerun produces identical numbers).

**Validation / Gates**
Run in this order; stop on first failure:
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
- `bash scripts/lint_docs.sh`
- `python3 scripts/validate_single_truth_system.py`
- `python3 scripts/validate_params.py --strict --as-of <AS_OF>`
- `python3 scripts/system_doctor.py --strict --project-root . --as-of <AS_OF>`
- `python3 scripts/build_owner_pnl_report.py --as-of <AS_OF> --since 2025-06-06 --include-store-breakdown --strict`
- Assert outputs exist:
  - `exports/owner_pnl/<AS_OF>/OWNER_PNL.json`
  - `exports/owner_pnl/<AS_OF>/OWNER_PNL.md`
  - `exports/owner_pnl/<AS_OF>/OWNER_PNL_ASCII.txt`

**Rollback / Backout**
- No DB writes required in P0. If any write is discovered, stop-the-line and revert using latest DB backup.

**Stop-the-line criteria**
- Any strict gate failure.
- Any evidence of recomputation divergence (Markdown/ASCII doesn’t match JSON).
- Any attempt to “temporarily” loosen thresholds or window sizes to force green.

---

### Phase P1 — Owner Truth Autopilot Runner + Scheduling (minimal human)
**Goal (measurable)**
- One command runs the full owner-truth pipeline deterministically for any `AS_OF`:
  - refresh reference (statusdate mapped archive),
  - validate reference freshness,
  - validate identity coverage + external parity,
  - sync ads sidecar (apply-gated, idempotent),
  - run doctor strict,
  - build OWNER_PNL artifacts.

**Inputs**
- Existing scripts used in clearance plan:
  - `scripts/export_sales_archive_statusdate_mapped.py`
  - `scripts/validate_reference_freshness.py`
  - `scripts/import_web_automation_offer_identity.py`
  - `scripts/validate_external_snapshot_parity.py`
  - `scripts/validate_recent_identity_coverage.py`
  - `scripts/validate_ads_sidecar_readiness.py`
  - `scripts/sync_ads_sidecar.py`
  - `scripts/system_doctor.py`
  - `scripts/build_owner_pnl_report.py`
- Config:
  - `config/anchors/kaspi_archive_ui_pack.json`
  - ads env: `AB_ADS_DB_PATH`, `AB_ADS_DB_MAX_AGE_HOURS` (contract)
- Write safety:
  - `scripts/backup_db.py`

**Outputs (exact paths)**
- New orchestrator script:
  - `scripts/run_owner_truth_daily.py` (or integrate into existing daily orchestrator; pick one)
- Daily run evidence:
  - `exports/validation/owner_truth_daily/<AS_OF>/full_run_transcript.md`
  - `exports/daily/<AS_OF>/owner_truth_summary.json` (stopline codes, max dates, ads freshness, identity coverage)

**Definition of Done**
Accepted as done only when:
1) `python3 scripts/run_owner_truth_daily.py --as-of <AS_OF> --strict` exits 0 for at least the last 7 days.
2) The script is fail-closed: if ads/reference/identity is stale, it stops and emits a stopline report (no partial “profit-after-ads”).
3) Any DB write is behind BOTH an env gate AND `--apply` (and a DB backup step is executed first).

**Validation / Gates**
- Unit tests:
  - Add `tests/test_run_owner_truth_daily_contract.py`
- Runtime gates:
  - `python3 scripts/run_owner_truth_daily.py --as-of <AS_OF> --strict` (dry run / validate-only)
  - `ENABLE_OWNER_TRUTH_APPLY=1 python3 scripts/run_owner_truth_daily.py --as-of <AS_OF> --strict --apply` (only if script includes safe apply steps; must backup DB first)

**Rollback / Backout**
- If apply mode is used:
  - Create DB backup: `python3 scripts/backup_db.py --db db/app.db`
  - Rollback by restoring last backup (`backups/app_*.db.gz`) and rerun strict chain to confirm return to GREEN.

**Stop-the-line criteria**
- Any missing backup before apply.
- Any write without env gate + `--apply`.
- Any silent skip of a required step (e.g., ads sync skipped but report still claims profit-after-ads).

---

### Phase P2 — Profit Realism Layer (high ROI)
**Goal (measurable)**
Provide hard evidence against “profits seem too high” by adding two deterministic reconciliations:

1) Returns economics audit:
   - Returned orders must reduce month economics (with delivery fee treatment per contract).
2) Cash/bank reconciliation:
   - Monthly economics should reconcile to cashflow reality within explicit tolerances for months covered by anchors.

**Inputs**
- Cashflow contracts and tables:
  - `docs/validation/CASHFLOW_TRUTH_CONTRACT_2026-01-26.md` (policy)
  - DB tables used by existing cashflow translator/reconciler
- Existing scripts (do not duplicate logic):
  - `scripts/translate_orders_to_cashflow_events.py`
  - `scripts/reconcile_on_delivery_settlement.py`
  - `scripts/build_owner_pnl_report.py`

**Outputs (exact paths)**
- New validators:
  - `scripts/validate_returns_economics_audit.py`
  - `scripts/validate_monthly_cash_reconciliation.py`
- Evidence artifacts:
  - `exports/validation/returns_economics/<AS_OF>/returns_economics_report.json`
  - `exports/validation/cash_reconciliation/<AS_OF>/cash_reconciliation_report.json`

**Definition of Done**
Accepted as done only when:
1) Both validators run in strict mode and produce deterministic JSON reports.
2) Validators are wired into either:
   - `system_doctor --strict` (preferred if this is required for publication), OR
   - `build_owner_pnl_report --strict` as a publication prerequisite.
3) Clear tolerances exist and are documented (no “ignore diff” behavior).

**Validation / Gates**
- Add tests:
  - `tests/test_validate_returns_economics_audit.py`
  - `tests/test_validate_monthly_cash_reconciliation.py`
- Runtime:
  - `python3 scripts/validate_returns_economics_audit.py --as-of <AS_OF> --strict`
  - `python3 scripts/validate_monthly_cash_reconciliation.py --as-of <AS_OF> --strict`

**Rollback / Backout**
- Read-only. If validator is too strict due to missing anchors, do NOT loosen thresholds:
  - Instead gate by “anchor availability” (fail-closed for publication; optionally warn-only for internal ops).

**Stop-the-line criteria**
- Any attempt to change economics formulas outside the owning contracts.
- Any validator that “passes” while reporting missing inputs (must fail if inputs missing for strict scope).

---

### Phase P3 — OPEX Integration into OWNER_PNL (net profit surface)
**Goal (measurable)**
- Add OPEX to owner PnL as:
  - `profit_after_ads_and_opex`
- Fail-closed: if OPEX schedule is missing/stale, that field must lock (`null`/`N/A`) and publication contract must reflect it.

**Inputs**
- OPEX source + existing sync path (if present):
  - `scripts/sync_opex_schedule.py` (existing per task log)
- Current owner PnL builder:
  - `scripts/build_owner_pnl_report.py`
- Contracts:
  - `docs/validation/OWNER_PNL_PUBLICATION_CONTRACT.md`

**Outputs**
- `scripts/validate_opex_readiness.py` (new)
- Updated `scripts/build_owner_pnl_report.py` to emit OPEX fields
- `exports/validation/opex_readiness/<AS_OF>/opex_readiness_report.json`

**Definition of Done**
Accepted as done only when:
1) Owner PnL includes OPEX and profit-after-opex when OPEX readiness is GREEN.
2) If OPEX readiness is RED, profit-after-opex is locked and the report explicitly states why.
3) Doctor strict blocks publication if contract requires OPEX for “net profit” publication mode.

**Validation / Gates**
- `python3 scripts/validate_opex_readiness.py --as-of <AS_OF> --strict`
- `python3 scripts/build_owner_pnl_report.py --as-of <AS_OF> --since 2025-06-06 --include-store-breakdown --strict`
- `python3 scripts/system_doctor.py --strict --as-of <AS_OF>`

**Rollback / Backout**
- OPEX ingestion writes must be apply-gated with DB backup (same policy as ads sync).

**Stop-the-line criteria**
- Any publication of profit-after-opex with missing/stale OPEX.

---

### Phase P4 — Observability + Stopline Triage UX
**Goal (measurable)**
- Make failures actionable in <60 seconds with deterministic stopline codes + “what to do next” hints.

**Inputs**
- Existing stopline/error_code patterns in doctor outputs.
- Existing diagnostics outputs under `exports/diagnostics/<AS_OF>/`.

**Outputs**
- `scripts/triage_owner_truth_stoplines.py` (new)
- `exports/daily/<AS_OF>/owner_truth_summary.json` (if not already present in P1)

**Definition of Done**
Accepted as done only when:
1) A single file lists top blockers (REFERENCE_STALE, ADS_SOURCE_STALE, IDENTITY_COVERAGE_FAIL, etc.)
2) The file links to concrete evidence artifacts.

**Validation / Gates**
- Unit tests for stable JSON schema.
- `python3 scripts/triage_owner_truth_stoplines.py --as-of <AS_OF> --strict` produces output.

**Rollback / Backout**
- Read-only.

**Stop-the-line criteria**
- “Catch and continue” behavior that hides failures.

---

### Phase P5 — Scale/De-risk Sources (UI pack automation + historical replays)
**Goal (measurable)**
- Remove manual fragility in status-date UI packs by automating full-store seed acquisition and refresh.
- Keep shipped-truth and archive truth replayable monthly (bounded windows) and track regressions as explicit remediation tasks.

**Inputs**
- UI pack anchor:
  - `config/anchors/kaspi_archive_ui_pack.json`
- Shipped truth replay backlog indicates need for full-store UI seed automation.

**Outputs**
- `docs/ops/KASPI_ARCHIVE_UI_SEED_AUTOMATION_RUNBOOK.md` (new)
- `scripts/refresh_kaspi_archive_ui_pack.py` (new or refactor existing tooling)
- Replay artifacts:
  - `exports/validation/archive_ui_pack_refresh/<AS_OF>/report.md`
  - `exports/validation/shipped_truth_monthly_replay/<RUN_ID>/window_summary.csv`

**Definition of Done**
Accepted as done only when:
1) UI pack refresh can run for all active stores with a single command.
2) Freshness + integrity validators pass after refresh.
3) Monthly replays generate PASS/FAIL/INCONCLUSIVE artifacts (no silent skips).

**Validation / Gates**
- `python3 scripts/refresh_kaspi_archive_ui_pack.py --as-of <AS_OF> --strict`
- `python3 scripts/export_sales_archive_statusdate_mapped.py --since 2025-06-06 --until <AS_OF> --strict`
- `python3 scripts/validate_reference_freshness.py --as-of <AS_OF> --strict`

**Rollback / Backout**
- Anchors are config files: revert by restoring previous anchor JSON from git if refresh breaks.
- Never delete old packs; keep pack roots immutable.

**Stop-the-line criteria**
- Any approach that unions non-statusdate sources into published truth without contract change.

---

### Phase P6 — Promotion + CI + Release Evidence
**Goal (measurable)**
- Merge changes safely with reproducible evidence and a minimal-human workflow.

**Inputs**
- `docs/ops/PROMOTION_MINIMUM_STANDARD.md` (promotion rules)
- Current working branch state.

**Outputs**
- `docs/OPS_ROLLOUT_EVIDENCE_OWNER_TRUTH_AUTOPILOT_2026-03-XX.md` (new)
- `exports/validation/owner_truth_release/<AS_OF>/full_gates_green_final.md`
- Oracle pack (optional, for external review): `scripts/oracle_pack.sh` output.

**Definition of Done**
Accepted as done only when:
1) Local required gates are GREEN.
2) CI gates are GREEN (or documented exception per promotion minimum standard).
3) Release evidence doc references exact commands, outputs, and commit hash.

**Validation / Gates**
- Full local chain (same as P0)
- CI checks green (if applicable)

**Rollback / Backout**
- Revert PR or roll back to prior tag/commit.
- Restore DB from last known good backup if any apply steps occurred.

**Stop-the-line criteria**
- Any “promote without evidence” attempt.
- Any divergence from single-truth contracts.

---

## If attachments are missing — assumptions policy
- If any required external source (UI pack root, ads DB, OPEX workbook, Web_automation snapshot) is missing or stale:
  - In `--strict` mode: STOP with a deterministic stopline code and write a remediation hint into the phase evidence report.
  - Do NOT fall back to “best effort” dates/sources unless the owning contract explicitly allows it.
- If commit hashes are missing for a change:
  - Record `git rev-parse HEAD` and `git status --short` in the phase transcript; treat that as the authoritative traceability for the run.
## Execution Status (2026-03-05)
- P0: Implemented (owner pnl json/md/ascii generated); strict global gates currently blocked by existing `validate_params` stopline.
- P1: Implemented `scripts/run_owner_truth_daily.py` with fail-closed stopline output; strict run currently RED due upstream `validate_order_entries_freshness` and truth-layer stoplines.
- P2: Implemented and tested:
  - `scripts/validate_returns_economics_audit.py`
  - `scripts/validate_monthly_cash_reconciliation.py`
  - wired into `scripts/system_doctor.py`
- P3: Implemented and tested:
  - `scripts/validate_opex_readiness.py`
  - OPEX integration in `scripts/build_owner_pnl_report.py`
- P4: Implemented and tested:
  - `scripts/triage_owner_truth_stoplines.py`
- P5: Implemented and tested:
  - `scripts/refresh_kaspi_archive_ui_pack.py`
  - `docs/ops/KASPI_ARCHIVE_UI_SEED_AUTOMATION_RUNBOOK.md`
- P6: Evidence artifacts produced; release remains STOP-LINE RED until existing `on_delivery_freeze` backlog is remediated.
