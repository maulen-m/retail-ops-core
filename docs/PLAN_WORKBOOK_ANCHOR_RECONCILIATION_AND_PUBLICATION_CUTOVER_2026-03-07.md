# PLAN_WORKBOOK_ANCHOR_RECONCILIATION_AND_PUBLICATION_CUTOVER_2026-03-07

## Purpose
Finish the WebUI archive single-truth migration by clearing the only remaining hard blocker in this rollout path:
`validate_sales_against_workbook.py --strict`.

The source pack is good, the chronology authority decision is already locked as workbook/CRM, and DB absence is already cleared. The next work is to:
1. classify every workbook overage day/order by source lineage,
2. apply the minimum safe correction to published truth / OCEAN_DROP / overlap logic,
3. rerun strict governance,
4. only then rebase economics and owner publication,
5. only then resume daily automation and full-history replay.

This plan is single-agent, sequential, fail-closed, and forbids a new WebUI scrape.

## Current Baseline
- Repo: `~/Docs/Autonomous_business`
- Continue in the same worktree/branch: `codex/TASK-webui-archive-single-truth-v1`
- Authoritative READCHECK head for this pass: `4124c14836366871b94a1dd785604f5b58b54912`
- Frozen source:
  - `exports/webui_archive_full_parse_runs/webui_archive_full_parse_2024-06-06_to_2026-03-05_20260306_2211/...`
- Frozen reseed ledger:
  - `exports/order_status_ledger/webui_status_ledger_20260306_full_parse`
- Green rollback anchor:
  - `exports/validation/owner_truth_release/2026-03-04/full_gates_green_final.md`

Current facts:
- WebUI pack integrity: PASS
- Ledger continuity: PASS
- Shipped-day authority decision: `CRM_REMAINS_CHRONOLOGY_AUTHORITY`
- DB coverage gate: PASS after a 102-row write-gated `sales_fact_v2` rebuild
- Remaining blocker:
  - `validate_sales_against_workbook.py --start 2026-01-01 --end 2026-02-29 --strict`
  - `overlap_days = 54`
  - `53` overage errors across `37` unique failing dates

Observed read-only diagnosis for this pass:
- every current published Jan-Feb order is present in the workbook order set
- only `53` published orders currently land on the same workbook day
- `2,786` published orders are present in workbook but on a different day
- current `sales_fact_v2` Jan-Feb rows are dominated by `OCEAN_DROP_ANCHOR`
- current publication overages are therefore a lineage/chronology selection problem, not a missing-source or missing-order problem

## Non-Negotiables
1. Fail-closed always.
2. No new WebUI scrape in this plan.
3. Raw WebUI files are not publication sources; DB-backed validation/publication remains mandatory.
4. Read-only first. No DB writes unless:
   - backup exists,
   - env gate is set,
   - `--apply` is present,
   - before/after diffs are emitted,
   - rollback path is documented.
5. No formula or threshold changes without updating the owning docs/contracts first.
6. Do not claim completion unless every stated phase gate is green.

---

## Phase P0 — Freeze Good Source + Baseline

### Goal (measurable)
Freeze the successful full-parse pack, reseed ledger, chronology authority contract, and rollback anchor as the baseline for the workbook-reconciliation pass.

### Inputs
- frozen full-parse pack root
- frozen reseed ledger root
- current chronology contract
- current workbook gate report
- rollback anchor

### Outputs (exact paths)
- `exports/validation/workbook_anchor_recon/2026-03-07/readcheck.md`
- `exports/validation/workbook_anchor_recon/2026-03-07/baseline_manifest.json`
- `exports/validation/workbook_anchor_recon/2026-03-07/no_new_scrape_notice.md`

### Definition of Done
Accepted as done only when:
1. Frozen source/ledger hashes are recorded.
2. No-new-scrape policy is explicit.
3. The 2026-03-04 rollback anchor is confirmed available.

### Validation / Gates
- `python3 scripts/validate_webui_archive_pack_integrity.py --pack-root <FULL_PARSE_PACK_ROOT> --strict`
- `python3 scripts/validate_status_ledger_continuity.py --ledger-root exports/order_status_ledger/webui_status_ledger_20260306_full_parse --start 2026-01-01 --end 2026-02-29 --strict`
- `python3 scripts/validate_single_truth_system.py`
- `bash scripts/lint_docs.sh`

### Rollback / Backout
- Docs/manifests only. No DB writes.

### Stop-the-line criteria
- Any attempt to start a new scrape
- Any drift in frozen pack/ledger hashes
- Any regression to the rollback anchor

---

## Phase P1 — Workbook Overage Taxonomy

### Goal (measurable)
Classify 100% of the 53 failing workbook-overage days and all contributing overage orders/rows into deterministic source-lineage buckets.

### Inputs
- `exports/validation/webui_archive_single_truth/2026-03-07/sales_against_workbook_report.json`
- `view_sales_line_truth`
- `view_sales_daily_truth`
- `sales_fact_v2`
- `fact_sales`
- `source_file` / lineage fields including `OCEAN_DROP_ANCHOR`
- current chronology contract
- workbook anchor file/path used by `validate_sales_against_workbook.py`

### Outputs
- `scripts/classify_workbook_anchor_overages.py`
- `exports/validation/workbook_anchor_recon/2026-03-07/workbook_overage_days.csv`
- `exports/validation/workbook_anchor_recon/2026-03-07/workbook_overage_source_mix.csv`
- `exports/validation/workbook_anchor_recon/2026-03-07/workbook_overage_order_lineage.csv`
- `exports/validation/workbook_anchor_recon/2026-03-07/workbook_overage_unresolved.csv`
- `exports/validation/workbook_anchor_recon/2026-03-07/workbook_overage_root_causes.md`

### Required bucket examples
At minimum:
- `FACT_SALES_OVERLAP_AFTER_V2_START`
- `OCEAN_DROP_ANCHOR_OVERAGE`
- `SALES_FACT_V2_DUPLICATE_LINEAGE`
- `UNKNOWN_COMPLETED_HEADER_FALLBACK_DUPLICATION`
- `RETURN_CANCEL_FILTER_MISMATCH`
- `WORKBOOK_PARSE_OR_AGGREGATION_MISMATCH`
- `STORE_ALIAS_OR_IDENTITY_SPLIT`
- `UNRESOLVED_MANUAL_REVIEW`

### Definition of Done
Accepted as done only when:
1. 100% of failing workbook days are classified.
2. 100% of overage units/net_rev are assigned to buckets.
3. `UNRESOLVED_MANUAL_REVIEW` is <= 5% of total overage.

### Validation / Gates
- `python3 scripts/classify_workbook_anchor_overages.py --start 2026-01-01 --end 2026-02-29 --strict`
- Unit tests for bucket assignment.
- Reconciliation check:
  - sum of classified overage must equal the validator’s day-level overage totals.

### Rollback / Backout
- Read-only.

### Stop-the-line criteria
- Bucket totals do not reconcile exactly to workbook overage totals.
- More than 5% unresolved.
- Any silent drop of rows from lineage analysis.

---

## Phase P2 — Published Truth / OCEAN_DROP Reconciliation

### Goal (measurable)
Apply the minimum safe correction so published truth no longer exceeds the workbook anchor for Jan–Feb.

### Inputs
- P1 workbook-overage taxonomy
- `docs/DECISIONS.md` workbook-anchored published-sales policy
- `scripts/validate_sales_against_workbook.py`
- `view_sales_line_truth`
- `view_sales_daily_truth`
- `sales_fact_v2`
- `fact_sales`
- `exports/validation/webui_shipped_authority_recon/2026-03-07/db_write_log.md` (for prior write context)

### Outputs
- `docs/validation/PUBLISHED_TRUTH_WORKBOOK_RECON_CONTRACT.md` (new, if needed)
- updated code in the minimal required path(s), likely among:
  - `scripts/validate_sales_against_workbook.py`
  - source selection / rebuild paths
  - published truth view generation logic
- `exports/validation/workbook_anchor_recon/2026-03-07/published_truth_correction_plan.md`
- `exports/validation/workbook_anchor_recon/2026-03-07/workbook_gate_replay.json`
- `exports/validation/workbook_anchor_recon/2026-03-07/workbook_gate_replay.md`
- if writes occur:
  - `exports/validation/workbook_anchor_recon/2026-03-07/db_write_log.md`
  - `exports/validation/workbook_anchor_recon/2026-03-07/before_after_diffs/`

### Definition of Done
Accepted as done only when:
1. `validate_sales_against_workbook.py --strict` passes for `2026-01-01..2026-02-29`.
2. The correction is explainable by the P1 buckets.
3. No regression is introduced to:
   - WebUI pack integrity,
   - ledger continuity,
   - chronology authority contract,
   - DB coverage gate.

### Validation / Gates
- `python3 scripts/validate_sales_against_workbook.py --start 2026-01-01 --end 2026-02-29 --strict`
- `python3 scripts/validate_webui_archive_vs_current_db.py --start 2026-01-01 --end 2026-02-29 --ledger-root exports/order_status_ledger/webui_status_ledger_20260306_full_parse --strict`
- regression tests preserving:
  - chronology authority contract
  - DB coverage pass
  - rollback anchor

### Rollback / Backout
- If any DB write is required:
  - `python3 scripts/backup_db.py --db db/app.db`
  - explicit env gate + `--apply`
  - restore backup on failure
- If view/source logic changes regress other gates, revert that patch.

### Stop-the-line criteria
- Any fix that hides rows rather than classifying/correcting them
- Any regression to DB coverage PASS
- Any regression to rollback anchor
- Any contract change without docs/tests

---

## Phase P3 — Governance Replay

### Goal (measurable)
Once workbook chronology is green, clear the remaining global strict chain.

### Inputs
- `scripts/validate_params.py`
- `scripts/system_doctor.py`
- prior stopline docs
- rollback anchor

### Outputs
- `exports/validation/workbook_anchor_recon/2026-03-07/governance_stopline_closeout.md`
- `exports/validation/workbook_anchor_recon/2026-03-07/system_doctor_after_cleanup.md`
- if writes are needed:
  - `exports/validation/workbook_anchor_recon/2026-03-07/governance_db_write_log.md`

### Definition of Done
Accepted as done only when:
1. `python3 scripts/validate_params.py --strict --as-of 2026-03-07` passes.
2. `python3 scripts/system_doctor.py --strict --project-root . --as-of 2026-03-07` is green, or only fails on still-open economics gates from P4.
3. The 2026-03-04 rollback anchor still reproduces.

### Validation / Gates
- `python3 scripts/validate_params.py --strict --as-of 2026-03-07`
- `python3 scripts/system_doctor.py --strict --project-root . --as-of 2026-03-07`
- `python3 scripts/validate_single_truth_system.py`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
- `bash scripts/lint_docs.sh`

### Rollback / Backout
- DB backup + restore if any governance repair is write-gated.

### Stop-the-line criteria
- Silencing strict blockers without evidence
- Regressing rollback anchor
- Proceeding to publication while governance is red

---

## Phase P4 — Economics / Publication Rebase

### Goal (measurable)
Re-run downstream economics and owner publication once workbook chronology, DB coverage, and governance are green.

### Inputs
- promoted truth path from P2
- governance-green state from P3
- existing ads / COGS validators
- owner publication builders

### Outputs
- rerun/update:
  - `scripts/validate_ads_offer_universe_coverage.py`
  - `scripts/validate_ads_spend_reality.py`
  - `scripts/validate_cogs_completeness_by_month.py`
  - `scripts/validate_cogs_realism_vs_forensic.py`
  - `scripts/build_north_star_owner_review.py`
  - `scripts/build_owner_pnl_report.py`
- artifacts:
  - `exports/validation/workbook_anchor_recon/2026-03-07/ads_offer_universe_report.json`
  - `exports/validation/workbook_anchor_recon/2026-03-07/ads_spend_reality_report.json`
  - `exports/validation/workbook_anchor_recon/2026-03-07/cogs_completeness_report.json`
  - `exports/validation/workbook_anchor_recon/2026-03-07/cogs_realism_report.json`
  - `exports/north_star_owner_review/2026-03-07/...`
  - `exports/owner_pnl/2026-03-07/...`

### Definition of Done
Accepted as done only when:
1. Ads and COGS gates pass.
2. `build_north_star_owner_review.py --strict` passes.
3. Locked months still show `N/A` + `locked_reason`.
4. `build_owner_pnl_report.py --strict` passes.

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
- Numeric profit on locked months
- Partial ads treated as full
- Completeness PASS treated as realism PASS
- Publication unlock before P2/P3 are green

---

## Phase P5 — Daily Automation + Full-History Replay + Promotion

### Goal (measurable)
Operationalize daily truth refresh and then replay full history only after Jan–Feb is green.

### Inputs
- successful P0–P4 artifacts
- `scripts/run_owner_truth_daily.py`
- `scripts/triage_owner_truth_stoplines.py`
- current Playwright downloader only as session-check / maintenance path

### Outputs
- updated:
  - `scripts/run_owner_truth_daily.py`
  - `scripts/triage_owner_truth_stoplines.py`
- artifacts:
  - `exports/daily/<AS_OF>/owner_truth_summary.json`
  - `exports/validation/workbook_anchor_recon/full_history_<RUN_ID>/...`
  - `docs/OPS_ROLLOUT_EVIDENCE_WORKBOOK_ANCHOR_RECONCILIATION_2026-03-07.md`
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
- Restore previous scheduler/session config if needed.

### Stop-the-line criteria
- Promotion without evidence
- Full-history replay before Jan–Feb is green
- Any automation path that hides a failed prerequisite

---

## If attachments are missing — assumptions policy
- Default repo root is repo-relative.
- Workbook/download roots are runtime variables, not hardcoded in active docs.
- If any required full-parse pack, reseed ledger, workbook anchor, or overage artifact is missing:
  - fail strict mode,
  - emit a missing-input manifest,
  - do not continue with placeholder data.
- If filenames differ but contents are clearly the same:
  - record exact substituted path + SHA256 in the manifest,
  - continue only when traceability is explicit.
- If current HEAD differs from the assumed baseline:
  - record actual branch + SHA in READCHECK and treat that as authoritative.
