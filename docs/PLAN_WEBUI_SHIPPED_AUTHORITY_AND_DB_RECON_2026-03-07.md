The plan below assumes the current frozen source pack and reseed ledger remain the baseline, the active branch/head is codex/TASK-webui-archive-single-truth-v1 @ fe14ce584326ec8625a9936afc74af33a1653d8d, and the immediate problem is no longer source quality but authority + reconciliation.

# PLAN_WEBUI_SHIPPED_AUTHORITY_AND_DB_RECON_2026-03-07

## Purpose
Close the remaining real promotion blockers after the successful WebUI full-parse and reseed by:
1. proving or disproving a deterministic WebUI-to-CRM shipped-day rule using external shipped-truth authority already in the repo,
2. reconciling the truly absent DB order set,
3. clearing strict governance blockers,
4. only then rebasing economics and owner publication on the promoted truth path.

This plan is single-agent, sequential, fail-closed, and intentionally forbids a new WebUI scrape unless the frozen full-parse pack is later proven defective.

## Current Baseline
- Repo: `~/Docs/Autonomous_business`
- Continue in the same worktree/branch: `codex/TASK-webui-archive-single-truth-v1`
- Current baseline head: `fe14ce584326ec8625a9936afc74af33a1653d8d`
- Frozen source pack:
  - `exports/webui_archive_full_parse_runs/webui_archive_full_parse_2024-06-06_to_2026-03-05_20260306_2211/pack_outputs/webui_archive_full_parse_2024-06-06_to_2026-03-05_20260306_2211_pack`
- Frozen reseed ledger:
  - `exports/order_status_ledger/webui_status_ledger_20260306_full_parse`
- Green rollback anchor:
  - `exports/validation/owner_truth_release/2026-03-04/full_gates_green_final.md`

Current hard blockers:
- CRM promotion still red on shipped projection.
- DB coverage still red on true absence set.
- Downstream ads/COGS/owner publication remain blocked until both are green.

## Non-Negotiables
1. Fail-closed always.
2. No new WebUI scrape in this plan.
3. DB-backed validation/publication cannot be bypassed by raw WebUI files.
4. Read-only first; no DB writes unless:
   - backup exists,
   - env gate is set,
   - `--apply` is present,
   - before/after diff artifacts are written,
   - rollback path is documented.
5. No formula or policy-threshold changes without updating the owning docs/contracts first.
6. Do not claim completion unless every stated phase gate is green.

---

## Phase P0 — Freeze Good Source + Baseline

### Goal (measurable)
Freeze the current successful full-parse source and reseed ledger as the only active source baseline, and prevent accidental source churn.

### Inputs
- Frozen full-parse pack root
- Frozen reseed ledger root
- Current promotion reports
- Rollback anchor

### Outputs
- `exports/validation/webui_shipped_authority_recon/2026-03-07/readcheck.md`
- `exports/validation/webui_shipped_authority_recon/2026-03-07/baseline_manifest.json`
- `exports/validation/webui_shipped_authority_recon/2026-03-07/no_new_scrape_notice.md`

### Definition of Done
Accepted as done only when:
1. Full-parse pack and reseed ledger hashes/manifests are frozen.
2. The plan explicitly states “no new scrape.”
3. The `2026-03-04` rollback anchor is confirmed reproducible.

### Validation / Gates
- `python3 scripts/validate_webui_archive_pack_integrity.py --pack-root <FULL_PARSE_PACK_ROOT> --strict`
- `python3 scripts/validate_status_ledger_continuity.py --ledger-root exports/order_status_ledger/webui_status_ledger_20260306_full_parse --start 2026-01-01 --end 2026-02-29 --strict`
- `python3 scripts/validate_single_truth_system.py`
- `bash scripts/lint_docs.sh`

### Rollback / Backout
- Docs/manifests only. No DB writes allowed in P0.

### Stop-the-line criteria
- Any attempt to start a new scrape
- Any drift in frozen pack/ledger hashes
- Any regression to the rollback anchor

---

## Phase P1 — Shipped-Day Authority Decision

### Goal (measurable)
Answer one binary question using an external shipped-truth authority path already in the repo:
- `RULE_PROVEN`: a deterministic WebUI-to-CRM shipped-day rule exists
- `CRM_REMAINS_CHRONOLOGY_AUTHORITY`: exact CRM shipped-day parity is not derivable from WebUI alone

### Inputs
- `exports/webui_projection/webui_shipped_projection_20260307/webui_shipped_projection.csv`
- `exports/validation/webui_promotion_delta_recon/2026-03-07/webui_vs_crm_gap_classifier_reprojected.csv`
- `exports/validation/webui_promotion_delta_recon/2026-03-07/promotion_delta_orders.csv`
- Existing shipped-truth evidence:
  - `exports/validation/shipped_vs_waybill_crm/2026-02-27/...`
  - historical API shipped-vs-CRM artifacts
- Existing shipped-truth validators and contracts

### Outputs
- `scripts/validate_webui_crm_shipped_day_authority.py`
- `exports/validation/webui_shipped_authority_recon/2026-03-07/shipped_day_authority_sample.csv`
- `exports/validation/webui_shipped_authority_recon/2026-03-07/shipped_day_rule_candidates.csv`
- `exports/validation/webui_shipped_authority_recon/2026-03-07/shipped_day_authority_report.md`
- `exports/validation/webui_shipped_authority_recon/2026-03-07/shipped_day_authority_decision.json`

### Definition of Done
Accepted as done only when:
1. 100% of the current chronology residual is mapped to an authority-backed decision.
2. The decision JSON ends with exactly one of:
   - `RULE_PROVEN`
   - `CRM_REMAINS_CHRONOLOGY_AUTHORITY`
3. The decision is backed by concrete order/day evidence, not heuristic date math alone.

### Validation / Gates
- `python3 scripts/validate_webui_crm_shipped_day_authority.py --start 2026-01-01 --end 2026-02-29 --strict`
- Targeted tests for:
  - waybill/API/CRM authority matching
  - binary decision output
  - fail-closed behavior on insufficient authority

### Rollback / Backout
- Read-only.

### Stop-the-line criteria
- Any new heuristic rule without shipped-truth / waybill / API authority evidence
- Using delivered-at as a shipped proxy without contract evidence
- Any ambiguous decision state

---

## Phase P2 — CRM Chronology Contract Path

### Goal (measurable)
Implement the outcome of P1, with exactly one valid path:

### Path A — RULE_PROVEN
Update the WebUI shipped-event projection contract and validators so CRM promotion goes green.

### Path B — CRM_REMAINS_CHRONOLOGY_AUTHORITY
Do not force WebUI-only exact day parity. Update contracts so:
- WebUI remains historical status truth,
- CRM workbook remains the mandatory chronology anchor for shipped-day publication,
- owner publication stays workbook-anchored for chronology until a better authority exists.

### Inputs
- P1 decision artifacts
- `docs/validation/WEBUI_SHIPPED_EVENT_PROJECTION_CONTRACT.md`
- `scripts/build_webui_shipped_projection.py`
- `scripts/validate_webui_archive_vs_crm_band.py`
- workbook-anchor policy / validators already in repo

### Outputs
- Updated contract(s):
  - `docs/validation/WEBUI_SHIPPED_EVENT_PROJECTION_CONTRACT.md`
  - and/or `docs/validation/WEBUI_CRM_CHRONOLOGY_AUTHORITY_CONTRACT.md`
- Updated code:
  - `scripts/build_webui_shipped_projection.py`
  - `scripts/validate_webui_archive_vs_crm_band.py`
- Artifacts:
  - `exports/validation/webui_shipped_authority_recon/2026-03-07/webui_truth_promotion_report_authority.json`
  - `exports/validation/webui_shipped_authority_recon/2026-03-07/webui_vs_crm_by_day_store_authority.csv`
  - `exports/validation/webui_shipped_authority_recon/2026-03-07/chronology_contract_decision.md`

### Definition of Done
Accepted as done only when:
- Path A: `validate_webui_archive_vs_crm_band.py --strict` passes, OR
- Path B: the fallback contract is explicit, tested, and owner publication still requires the CRM/workbook chronology gate.

### Validation / Gates
- Path A:
  - `python3 scripts/validate_webui_archive_vs_crm_band.py --start 2026-01-01 --end 2026-02-29 --ledger-root exports/order_status_ledger/webui_status_ledger_20260306_full_parse --truth-event authority_projection --strict`
- Path B:
  - `python3 scripts/validate_sales_against_workbook.py --start 2026-01-01 --end 2026-02-29 --strict`
  - plus publication-lock regression tests
- In both paths:
  - projection contract tests
  - day-boundary / return / cancel regression tests

### Rollback / Backout
- Revert contract + projection changes if they do not improve the gate or if Path B fallback is not fully documented.

### Stop-the-line criteria
- Contract change without docs/tests
- Any projection improvement that hides rows
- Unlocking publication without a defensible chronology authority

---

## Phase P3 — DB Absence Reconciliation

### Goal (measurable)
Resolve the remaining true DB coverage blocker set after chronology policy is decided.

Target residuals:
- `missing_in_db_orders = 382`
- `db_only_orders = 1`
- `window_drift_orders = 143` (already explanatory, not missing coverage)
- `db_only_returned_orders = 11` (already explanatory)

### Inputs
- `exports/validation/webui_promotion_delta_recon/2026-03-07/db_missing_order_candidates.csv`
- `exports/validation/webui_promotion_delta_recon/2026-03-07/db_only_order_explanations.csv`
- `exports/validation/webui_promotion_delta_recon/2026-03-07/db_reconciliation_plan.md`
- Current import / backfill / order-entry paths
- `db/app.db`

### Outputs
- `exports/validation/webui_shipped_authority_recon/2026-03-07/db_absence_root_causes.csv`
- `exports/validation/webui_shipped_authority_recon/2026-03-07/db_backfill_candidates.csv`
- `exports/validation/webui_shipped_authority_recon/2026-03-07/db_quarantine_candidates.csv`
- If writes are required:
  - `exports/validation/webui_shipped_authority_recon/2026-03-07/db_write_log.md`
  - `exports/validation/webui_shipped_authority_recon/2026-03-07/before_after_diffs/`

### Definition of Done
Accepted as done only when:
1. `validate_webui_archive_vs_current_db.py --strict` passes, OR
2. every residual order is explicitly explained and contract-quarantined.

### Validation / Gates
- Read-only first:
  - `python3 scripts/validate_webui_archive_vs_current_db.py --start 2026-01-01 --end 2026-02-29 --ledger-root exports/order_status_ledger/webui_status_ledger_20260306_full_parse --strict`
- If writes are required:
  - `python3 scripts/backup_db.py --db db/app.db`
  - explicit env gate + `--apply`
  - rerun the DB validator after every write batch

### Rollback / Backout
- Restore the specific pre-apply DB backup.
- Revert code changes for the write batch.

### Stop-the-line criteria
- Any DB write before read-only classification is complete
- Any DB write without backup + env gate + `--apply`
- Any reconciliation without before/after diffs

---

## Phase P4 — Governance + Global Strict Cleanup

### Goal (measurable)
Clear remaining global strict blockers once chronology and DB coverage are no longer red.

### Inputs
- `scripts/validate_params.py`
- `scripts/system_doctor.py`
- current stopline docs
- rollback anchor

### Outputs
- `exports/validation/webui_shipped_authority_recon/2026-03-07/governance_stopline_closeout.md`
- `exports/validation/webui_shipped_authority_recon/2026-03-07/system_doctor_after_cleanup.md`
- if writes are needed:
  - `exports/validation/webui_shipped_authority_recon/2026-03-07/governance_db_write_log.md`

### Definition of Done
Accepted as done only when:
1. `python3 scripts/validate_params.py --strict --as-of 2026-03-07` passes.
2. `python3 scripts/system_doctor.py --strict --project-root . --as-of 2026-03-07` is green, or only fails on still-open economics gates from P5.
3. The `2026-03-04` rollback anchor still reproduces.

### Validation / Gates
- `python3 scripts/validate_params.py --strict --as-of 2026-03-07`
- `python3 scripts/system_doctor.py --strict --project-root . --as-of 2026-03-07`
- `python3 scripts/validate_single_truth_system.py`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
- `bash scripts/lint_docs.sh`

### Rollback / Backout
- DB backup + restore if any apply-gated repair is needed.

### Stop-the-line criteria
- Silencing generic strict blockers without evidence
- Regressing the rollback anchor
- Continuing to publication while governance is red

---

## Phase P5 — Economics / Publication Rebase

### Goal (measurable)
Re-run downstream economics and owner publication only after P2/P3/P4 are green under the chosen chronology contract.

### Inputs
- promoted truth path from P2
- DB coverage state from P3
- existing ads / COGS validators
- owner publication builders

### Outputs
- Updated or rerun:
  - `scripts/validate_ads_offer_universe_coverage.py`
  - `scripts/validate_ads_spend_reality.py`
  - `scripts/validate_cogs_completeness_by_month.py`
  - `scripts/validate_cogs_realism_vs_forensic.py`
  - `scripts/build_north_star_owner_review.py`
  - `scripts/build_owner_pnl_report.py`
- Artifacts:
  - `exports/validation/webui_shipped_authority_recon/2026-03-07/ads_offer_universe_report.json`
  - `exports/validation/webui_shipped_authority_recon/2026-03-07/ads_spend_reality_report.json`
  - `exports/validation/webui_shipped_authority_recon/2026-03-07/cogs_completeness_report.json`
  - `exports/validation/webui_shipped_authority_recon/2026-03-07/cogs_realism_report.json`
  - `exports/north_star_owner_review/2026-03-07/...`
  - `exports/owner_pnl/2026-03-07/...`

### Definition of Done
Accepted as done only when:
1. Ads and COGS gates pass on the chosen truth path.
2. `build_north_star_owner_review.py --strict` passes.
3. Any locked month still shows `N/A` + `locked_reason`.
4. `build_owner_pnl_report.py --strict` no longer blocks on unresolved promotion issues.

### Validation / Gates
- `python3 scripts/validate_ads_offer_universe_coverage.py --start 2026-01-01 --end 2026-02-29 --truth-source webui_archive --strict`
- `python3 scripts/validate_ads_spend_reality.py --start 2026-01-01 --end 2026-02-29 --truth-source webui_archive --strict`
- `python3 scripts/validate_cogs_completeness_by_month.py --start 2026-01-01 --end 2026-02-29 --truth-source webui_archive --strict`
- `python3 scripts/validate_cogs_realism_vs_forensic.py --start 2026-01-01 --end 2026-02-29 --truth-source webui_archive --strict`
- `python3 scripts/build_north_star_owner_review.py --as-of 2026-03-07 --truth-source webui_archive --strict`
- `python3 scripts/build_owner_pnl_report.py --as-of 2026-03-07 --truth-source webui_archive --strict`

### Rollback / Backout
- Revert publication changes if any month unlocks incorrectly or metrics regress.

### Stop-the-line criteria
- Publishing numeric profit for locked months
- Treating partial ads as full
- Treating completeness PASS as realism PASS
- Unlocking owner publication before P2/P3/P4 are green

---

## Phase P6 — Daily Automation + Full-History Replay + Promotion

### Goal (measurable)
Operationalize daily truth refresh and then replay the full history only after Jan–Feb is green.

### Inputs
- successful P0–P5 artifacts
- existing daily runner / stopline triage paths
- current Playwright downloader only as session-check / maintenance path

### Outputs
- Updated:
  - `scripts/run_owner_truth_daily.py`
  - `scripts/triage_owner_truth_stoplines.py`
- Artifacts:
  - `exports/daily/<AS_OF>/owner_truth_summary.json`
  - `exports/validation/webui_shipped_authority_recon/full_history_<RUN_ID>/...`
  - `docs/OPS_ROLLOUT_EVIDENCE_WEBUI_SHIPPED_AUTHORITY_AND_DB_RECON_2026-03-07.md`
  - updated Oracle pack

### Definition of Done
Accepted as done only when:
1. `run_owner_truth_daily.py --strict` succeeds on the promoted truth path.
2. Full-history replay is deterministic.
3. Promotion evidence references exact commit SHA, commands, outputs, and rollback path.

### Validation / Gates
- `python3 scripts/run_owner_truth_daily.py --as-of 2026-03-07 --strict`
- `python3 scripts/triage_owner_truth_stoplines.py --as-of 2026-03-07 --strict`
- complete strict chain rerun
- full-history replay command(s)

### Rollback / Backout
- Revert promotion commit.
- Restore DB backup if any apply step occurred.
- Restore previous scheduler/session configuration if needed.

### Stop-the-line criteria
- Promotion without evidence
- Full-history replay before Jan–Feb is green
- Any automation path that hides a failed prerequisite

---

## If attachments are missing — assumptions policy
- Default repo root is repo-relative.
- Default workbook/download roots are runtime variables, not hardcoded in active docs.
- If any required full-parse pack, ledger, CRM workbook, shipped-truth artifact, or delta CSV is missing:
  - fail strict mode,
  - emit a missing-input manifest,
  - do not continue with placeholder data.
- If filenames differ but contents are clearly the same:
  - record exact substituted path + SHA256 in the manifest,
  - continue only when traceability is explicit.
- If current HEAD differs from the assumed baseline:
  - record actual branch + SHA in READCHECK and treat that as authoritative.