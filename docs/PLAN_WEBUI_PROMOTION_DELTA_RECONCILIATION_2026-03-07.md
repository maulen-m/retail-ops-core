# PLAN_WEBUI_PROMOTION_DELTA_RECONCILIATION_2026-03-07

## Purpose
Take the now-valid WebUI archive source and close the remaining promotion gap between:
1. WebUI historical truth,
2. CRM shipped-day anchor,
3. DB operational truth.

The source acquisition problem is solved. The remaining work is:
- classify all remaining promotion deltas,
- correct the event/date projection used for CRM comparison,
- reconcile missing/extra DB coverage,
- clear remaining strict governance blockers,
- only then rebase economics and cut owner publication over to the promoted WebUI truth.

This plan is single-agent, sequential, fail-closed, and keeps human time near zero. No new scrape is allowed unless the current full-parse pack is later proven defective.

Risks + likely regressions to watch

Running another scrape now would likely waste time and muddy evidence, because the current source pack is already valid. The active problem is promotion logic and reconciliation, not pack integrity.

A likely regression is using the wrong lifecycle event from the WebUI ledger for the CRM comparison. If the validator is comparing a delivered-event projection to a CRM shipped-day anchor, chronology can worsen even with a valid source. The evidence supports this as a plausible root cause because chronology mismatch increased while source quality improved. This is an inference, not yet a proven fact, and the next phase should test it explicitly.

Another likely regression is pushing DB writes too early. The repo’s architecture keeps the DB as operational truth and requires explicit, gated writes with rollback. The next plan therefore keeps P1/P2 read-only and only allows writes after delta classes are fully explained.

Biggest unknowns

What share of the remaining 2553 chronology mismatches comes from event-basis mismatch (shipped vs delivered vs another lifecycle point), versus date truncation, store-specific lag, or returned/cancelled treatment.

What exactly explains the 382 missing-in-DB and 143 WebUI-only orders: missed imports, identity/store mapping, status filters, or legitimate exclusions.

Whether the post-reseed global strict chain (validate_params --strict, system_doctor --strict, ads readiness, identity freshness) will still have independent reds after source promotion is fixed. The reseed run intentionally stopped before those reruns, so this is currently an explicit assumption from db_main context rather than a verified green/red state.

## Current Baseline
- Repo: `~/Docs/Autonomous_business`
- Continue in the same worktree/branch: `codex/TASK-webui-archive-single-truth-v1`
- Latest reseed transcript branch/head:
  - branch: `codex/TASK-webui-archive-single-truth-v1`
  - head: `fe14ce584326ec8625a9936afc74af33a1653d8d`
- Successful full-parse source run (previously reported in db_main context):
  - commit: `0e2e255172b6c302abbdafde469e550951966649` (assumption from provided context)
  - run_id: `webui_archive_full_parse_2024-06-06_to_2026-03-05_20260306_2211`
- Current good source artifacts:
  - `exports/webui_archive_full_parse_runs/webui_archive_full_parse_2024-06-06_to_2026-03-05_20260306_2211/...`
- Current reseed ledger:
  - `exports/order_status_ledger/webui_status_ledger_20260306_full_parse`
- Green rollback anchor:
  - `exports/validation/owner_truth_release/2026-03-04/full_gates_green_final.md`
- Current red promotion artifacts:
  - `exports/validation/webui_archive_single_truth/2026-03-06/webui_truth_promotion_report_full_parse.json`
  - `exports/validation/webui_archive_single_truth/2026-03-06/webui_vs_db_report_full_parse.json`
  - `exports/validation/webui_archive_single_truth/2026-03-06/open_stopline_items_full_parse_reseed.md`

## Non-Negotiables
1. Fail-closed always.
2. No new WebUI scrape in this plan unless the current full-parse pack is explicitly proven defective.
3. DB remains the operational system of record; WebUI truth must flow through DB-backed validation/publication, not around it.
4. Read-only first. No DB writes unless:
   - backup exists,
   - env gate is set,
   - `--apply` is present,
   - before/after diff artifacts are emitted,
   - rollback path is documented.
5. No formula/threshold changes without updating owning docs/contracts first.
6. Do not claim completion unless all listed phase gates are green.

---

## Phase P0 — Freeze Good Source + Baseline

### Goal (measurable)
Freeze the current valid full-parse pack and reseed ledger as the source baseline, and prevent accidental new-scrape churn.

### Inputs
- `exports/webui_archive_full_parse_runs/webui_archive_full_parse_2024-06-06_to_2026-03-05_20260306_2211/...`
- `exports/order_status_ledger/webui_status_ledger_20260306_full_parse/...`
- `exports/validation/webui_archive_single_truth/2026-03-06/...`
- `exports/validation/owner_truth_release/2026-03-04/full_gates_green_final.md`

### Outputs (exact paths)
- `exports/validation/webui_promotion_delta_recon/2026-03-07/readcheck.md`
- `exports/validation/webui_promotion_delta_recon/2026-03-07/baseline_manifest.json`
- `exports/validation/webui_promotion_delta_recon/2026-03-07/freeze_source_notice.md`

### Definition of Done
Accepted as done only when:
1. The successful full-parse pack and reseed ledger are hashed/manifests frozen.
2. The plan explicitly states “no new scrape.”
3. The `2026-03-04` green owner-truth release remains reproducible as rollback anchor.

### Validation / Gates
- `python3 scripts/validate_webui_archive_pack_integrity.py --pack-root <FULL_PARSE_PACK_ROOT> --strict`
- `python3 scripts/validate_status_ledger_continuity.py --ledger-root exports/order_status_ledger/webui_status_ledger_20260306_full_parse --start 2026-01-01 --end 2026-02-29 --strict`
- `python3 scripts/validate_single_truth_system.py`
- `bash scripts/lint_docs.sh`

### Rollback / Backout
- Revert docs/manifests only. No DB writes allowed in P0.

### Stop-the-line criteria
- Any attempt to start a new scrape before P1/P2 are complete
- Any drift in the frozen pack/ledger hashes
- Any regression to the `2026-03-04` rollback anchor

---

## Phase P1 — Promotion Delta Taxonomy

### Goal (measurable)
Classify 100% of the remaining Phase-2 deltas into deterministic root-cause buckets.

Current target deltas:
- `breach_days = 104`
- `floor_days = 119`
- `chronology_mismatch_orders = 2553`
- `missing_in_db_orders = 382`
- `webui_only_orders = 143`
- `db_only_orders = 12`

### Inputs
- `exports/validation/webui_archive_single_truth/2026-03-06/webui_vs_crm_by_day_store_full_parse.csv`
- `exports/validation/webui_archive_single_truth/2026-03-06/webui_vs_crm_by_day_store_sku_full_parse.csv`
- `exports/validation/webui_archive_single_truth/2026-03-06/webui_vs_crm_gap_classifier_full_parse.csv`
- `exports/validation/webui_archive_single_truth/2026-03-06/webui_vs_db_by_day_store_full_parse.csv`
- `exports/validation/webui_archive_single_truth/2026-03-06/webui_vs_db_by_day_store_sku_full_parse.csv`
- `exports/validation/webui_archive_single_truth/2026-03-06/webui_vs_db_order_compare_full_parse.csv`

### Outputs
- `scripts/classify_webui_promotion_deltas.py`
- `exports/validation/webui_promotion_delta_recon/2026-03-07/promotion_delta_buckets.csv`
- `exports/validation/webui_promotion_delta_recon/2026-03-07/promotion_delta_orders.csv`
- `exports/validation/webui_promotion_delta_recon/2026-03-07/promotion_delta_unresolved.csv`
- `exports/validation/webui_promotion_delta_recon/2026-03-07/promotion_root_causes.md`

### Required bucket examples
At minimum classify into:
- event-basis mismatch (shipped vs delivered / other lifecycle point)
- date truncation / timezone / day-boundary mismatch
- return/cancel inclusion mismatch
- missing-in-DB import gap
- WebUI-only non-promotable row
- DB-only legacy row
- store/identity alias mismatch
- unresolved/manual-review

### Definition of Done
Accepted as done only when:
1. 100% of delta orders are assigned to a bucket.
2. Top root-cause buckets explain at least 95% of delta volume.
3. Unresolved bucket is <= 5% of total delta orders.

### Validation / Gates
- `python3 scripts/classify_webui_promotion_deltas.py --start 2026-01-01 --end 2026-02-29 --strict`
- Deterministic tests for bucket assignment
- Reconciliation check: bucket totals must match current validator totals exactly

### Rollback / Backout
- Read-only.

### Stop-the-line criteria
- Bucket counts not reconciling to validator totals
- >5% unresolved after classification
- Any silent exclusion of delta rows

---

## Phase P2 — Event Projection / Chronology Correction

### Goal (measurable)
Correct the WebUI event/date projection used for CRM comparison so the WebUI source is compared against the correct CRM-shipped equivalent event.

### Inputs
- WebUI status ledger:
  - `exports/order_status_ledger/webui_status_ledger_20260306_full_parse/webui_status_ledger.csv`
- CRM workbook anchor
- P1 bucket outputs
- Existing `scripts/validate_webui_archive_vs_crm_band.py`

### Outputs
- New or extended:
  - `docs/validation/WEBUI_SHIPPED_EVENT_PROJECTION_CONTRACT.md`
  - `scripts/build_webui_shipped_projection.py`
  - `scripts/validate_webui_archive_vs_crm_band.py` (updated if safer than a new validator)
- Artifacts:
  - `exports/webui_projection/webui_shipped_projection_20260307/projection_manifest.json`
  - `exports/webui_projection/webui_shipped_projection_20260307/webui_shipped_projection.csv`
  - `exports/validation/webui_promotion_delta_recon/2026-03-07/webui_truth_promotion_report_reprojected.json`
  - `exports/validation/webui_promotion_delta_recon/2026-03-07/webui_vs_crm_by_day_store_reprojected.csv`
  - `exports/validation/webui_promotion_delta_recon/2026-03-07/webui_vs_crm_gap_classifier_reprojected.csv`

### Definition of Done
Accepted as done only when:
1. `validate_webui_archive_vs_crm_band.py --strict` passes on the corrected projection.
2. `chronology_mismatch_orders` is better than the current baseline and no longer worse by 55.
3. `breach_days` and `floor_days` are reduced to zero, or explicit contract-approved tolerances if the contract is changed first.

### Validation / Gates
- `python3 scripts/validate_webui_archive_vs_crm_band.py --start 2026-01-01 --end 2026-02-29 --ledger-root exports/order_status_ledger/webui_status_ledger_20260306_full_parse --truth-event shipped_projection --strict`
- Projection contract tests
- Day-boundary / returned / cancelled regression tests

### Rollback / Backout
- Revert projection logic and contract if it fails to improve the band.

### Stop-the-line criteria
- Using delivered-at as a shipped proxy without an explicit contract
- Any contract change without docs/tests
- Any projection that improves one metric by silently hiding rows

---

## Phase P3 — DB Coverage Reconciliation

### Goal (measurable)
Resolve the remaining DB coverage deltas against the promoted WebUI truth:
- `missing_in_db_orders = 382`
- `webui_only_orders = 143`
- `db_only_orders = 12`

### Inputs
- `exports/validation/webui_archive_single_truth/2026-03-06/webui_vs_db_report_full_parse.json`
- `exports/validation/webui_archive_single_truth/2026-03-06/webui_vs_db_order_compare_full_parse.csv`
- P1 bucket outputs
- Current DB import / backfill / reconciliation paths

### Outputs
- `exports/validation/webui_promotion_delta_recon/2026-03-07/db_coverage_root_causes.csv`
- `exports/validation/webui_promotion_delta_recon/2026-03-07/db_missing_order_candidates.csv`
- `exports/validation/webui_promotion_delta_recon/2026-03-07/db_only_order_explanations.csv`
- `exports/validation/webui_promotion_delta_recon/2026-03-07/db_reconciliation_plan.md`
- If writes are required:
  - `exports/validation/webui_promotion_delta_recon/2026-03-07/db_write_log.md`
  - `exports/validation/webui_promotion_delta_recon/2026-03-07/before_after_diffs/`

### Definition of Done
Accepted as done only when:
1. `validate_webui_archive_vs_current_db.py --strict` passes.
2. All 382/143/12 residual orders are either reconciled or explicitly quarantined by contract.
3. Any DB writes are fully backed up, gated, and diffed.

### Validation / Gates
- Read-only classification first:
  - `python3 scripts/validate_webui_archive_vs_current_db.py --start 2026-01-01 --end 2026-02-29 --ledger-root exports/order_status_ledger/webui_status_ledger_20260306_full_parse --strict`
- If writes are required:
  - `python3 scripts/backup_db.py --db db/app.db`
  - env gate + `--apply`
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
Clear remaining global strict blockers that are independent of the WebUI source pack itself.

### Inputs
- `scripts/validate_params.py`
- `scripts/system_doctor.py`
- Prior stopline docs for `on_delivery_freeze`, mapping freshness, identity freshness, ads readiness, and cashflow/returns artifacts
- Current green rollback anchor

### Outputs
- `exports/validation/webui_promotion_delta_recon/2026-03-07/governance_stopline_closeout.md`
- `exports/validation/webui_promotion_delta_recon/2026-03-07/system_doctor_after_cleanup.md`
- If writes are needed:
  - `exports/validation/webui_promotion_delta_recon/2026-03-07/governance_db_write_log.md`

### Definition of Done
Accepted as done only when:
1. `python3 scripts/validate_params.py --strict --as-of 2026-03-07` passes.
2. `python3 scripts/system_doctor.py --strict --project-root . --as-of 2026-03-07` is green or only fails on still-open economics gates from P5.
3. No regression to `2026-03-04` rollback anchor.

### Validation / Gates
- `python3 scripts/validate_params.py --strict --as-of 2026-03-07`
- `python3 scripts/system_doctor.py --strict --project-root . --as-of 2026-03-07`
- `python3 scripts/validate_single_truth_system.py`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
- `bash scripts/lint_docs.sh`

### Rollback / Backout
- DB backup + restore if apply-gated governance repair is needed.

### Stop-the-line criteria
- Silencing generic strict blockers without root-cause evidence
- Regressing current rollback anchor
- Continuing to publication while governance is red

---

## Phase P5 — Economics Rebase on Promoted WebUI Truth

### Goal (measurable)
Re-run downstream economics and publication on the promoted WebUI truth **only after P2/P3 pass**.

### Inputs
- promoted WebUI ledger / projection
- existing ads and COGS validators
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
  - `exports/validation/webui_promotion_delta_recon/2026-03-07/ads_offer_universe_report.json`
  - `exports/validation/webui_promotion_delta_recon/2026-03-07/ads_spend_reality_report.json`
  - `exports/validation/webui_promotion_delta_recon/2026-03-07/cogs_completeness_report.json`
  - `exports/validation/webui_promotion_delta_recon/2026-03-07/cogs_realism_report.json`
  - `exports/north_star_owner_review/2026-03-07/...`
  - `exports/owner_pnl/2026-03-07/...`

### Definition of Done
Accepted as done only when:
1. Ads coverage / spend realism and COGS completeness / realism all pass on `truth_source=webui_archive`.
2. `build_north_star_owner_review.py --strict` passes.
3. Any locked month still shows `N/A` + `locked_reason`.
4. `build_owner_pnl_report.py --strict` no longer blocks on WebUI promotion.

### Validation / Gates
- `python3 scripts/validate_ads_offer_universe_coverage.py --start 2026-01-01 --end 2026-02-29 --truth-source webui_archive --strict`
- `python3 scripts/validate_ads_spend_reality.py --start 2026-01-01 --end 2026-02-29 --truth-source webui_archive --strict`
- `python3 scripts/validate_cogs_completeness_by_month.py --start 2026-01-01 --end 2026-02-29 --truth-source webui_archive --strict`
- `python3 scripts/validate_cogs_realism_vs_forensic.py --start 2026-01-01 --end 2026-02-29 --truth-source webui_archive --strict`
- `python3 scripts/build_north_star_owner_review.py --as-of 2026-03-07 --truth-source webui_archive --strict`
- `python3 scripts/build_owner_pnl_report.py --as-of 2026-03-07 --truth-source webui_archive --strict`

### Rollback / Backout
- Revert publication cutover logic if owner outputs regress or unlock incorrectly.

### Stop-the-line criteria
- Publishing numeric profit for locked months
- Treating partial ads as full
- Treating COGS completeness PASS as realism PASS
- Any owner publication unlock before P2/P3 are green

---

## Phase P6 — Daily Automation + Full-History Replay + Promotion

### Goal (measurable)
Operationalize daily truth refresh and then run a full-history replay on the promoted source.

### Inputs
- successful P0–P5 artifacts
- existing daily runner / stopline triage paths
- Playwright downloader (only session-check unless future refresh needed)

### Outputs
- Updated:
  - `scripts/run_owner_truth_daily.py`
  - `scripts/triage_owner_truth_stoplines.py`
- Artifacts:
  - `exports/daily/<AS_OF>/owner_truth_summary.json`
  - `exports/validation/webui_promotion_delta_recon/full_history_<RUN_ID>/...`
  - `docs/OPS_ROLLOUT_EVIDENCE_WEBUI_PROMOTION_DELTA_RECONCILIATION_2026-03-07.md`
  - updated Oracle pack

### Definition of Done
Accepted as done only when:
1. `run_owner_truth_daily.py --strict` succeeds on the promoted source.
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
- Default downloads/workbook roots are runtime variables, not hardcoded in active docs.
- If any required full-parse pack, ledger, CRM workbook, or delta CSV is missing:
  - fail strict mode,
  - emit a missing-input manifest,
  - do not continue with placeholder data.
- If filenames differ but contents are clearly the same:
  - record exact substituted path + SHA256 in the manifest,
  - continue only when traceability is explicit.
- If current HEAD differs from the assumed baseline:
  - record actual branch + SHA in READCHECK and treat that as authoritative.
