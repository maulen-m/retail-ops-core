# PLAN_CRM_NORTH_STAR_OWNER_TRUTH_REBUILD_2026-03-05

## Context
- Repo: `~/Docs/Autonomous_business`
- Branch/worktree: `codex/TASK-crm-north-star-rebuild-v1`
- As-of: `2026-03-05`
- Inputs:
  - CRM workbook: `~/Downloads/SALES_KSP_CRM_GPT_Sales_archive.xlsx`
  - Reconciled workbook: `~/Downloads/Claude_Reconciled_plus_crm_corrected.xlsx`

## North Star Objective
Use the downloaded CRM workbook as mandatory North Star ceiling for reviewed periods, use reconciled workbook as status bridge, prove COGS completeness and ads offer-universe completeness, and block owner profit publication until those gates are green.

## Non-Negotiables
1. Single-agent sequential execution in one branch/worktree.
2. Fail-closed always.
3. Read-only first; no DB writes unless root cause is isolated and write path is explicit, backup-first, env-gated, and applied with `--apply`.
4. No formula/policy-threshold changes without first updating `docs/inventory/Master_Inventory_Rules_v8.md`, then contracts, then validators/tests.
5. No completion claim unless all stated gates are green and all required artifacts exist.

## Phases

### P0 — Input Provenance + Manifest
- Build download artifact manifest first.
- Required outputs:
  - `exports/validation/crm_north_star_rebuild/2026-03-05/readcheck.md`
  - `exports/validation/crm_north_star_rebuild/2026-03-05/input_manifest.json`
  - `exports/validation/crm_north_star_rebuild/2026-03-05/input_manifest.sha256.txt`
- Stop immediately if CRM/reconciled workbook is missing.

### P1 — Comparable-Grain Normalization
- Normalize CRM workbook, reconciled workbook, and DB truth to comparable grain.
- Required outputs:
  - `crm_workbook_normalized.csv`
  - `reconciled_workbook_normalized.csv`
  - `db_truth_normalized.csv`
  - `normalization_schema.json`
  - `normalization_report.md`

### P2 — CRM Ceiling Validator
- Extend validator(s) so CRM workbook is mandatory ceiling in strict owner publication when workbook is available.
- Initial focus: Jan-Feb 2026.
- Required outputs:
  - `sales_truth_vs_crm_by_day_store.csv`
  - `sales_truth_vs_crm_by_sku.csv`
  - `sales_truth_vs_crm_gap_classifier.csv`
  - `sales_truth_vs_crm_report.md`

### P3 — COGS Completeness Audit (Jan-Feb)
- Validate unresolved/partial/base-only COGS, weight drift impact, identity-related landed COGS gaps.
- Required outputs:
  - `cogs_completeness_by_month.csv`
  - `cogs_unresolved_lines.csv`
  - `cogs_base_only_lines.csv`
  - `weight_drift_impact_report.csv`
  - `cogs_completeness_report.md`

### P4 — Ads Offer-Universe Coverage (Jan-Feb)
- Validate sold current offers vs ads mapped universe.
- Required outputs:
  - `ads_offer_universe_coverage.csv`
  - `ads_missing_sold_offers.csv`
  - `ads_coverage_by_month_store.csv`
  - `ads_offer_universe_report.md`

### P5 — North Star Owner Review Surface
- Build canonical review JSON and derived outputs.
- Profit fields locked whenever P2/P3/P4 not green.
- Required outputs:
  - `exports/north_star_owner_review/2026-03-05/NORTH_STAR_OWNER_REVIEW.json`
  - `exports/north_star_owner_review/2026-03-05/NORTH_STAR_OWNER_REVIEW.md`
  - `exports/north_star_owner_review/2026-03-05/monthly_totals_review.csv`
  - `exports/north_star_owner_review/2026-03-05/daily_profit_by_day_store.csv`
  - `exports/north_star_owner_review/2026-03-05/sku_profit_table.csv`
  - `exports/north_star_owner_review/2026-03-05/top_gainers_by_sku.csv`
  - `exports/north_star_owner_review/2026-03-05/top_losers_by_sku.csv`
  - `exports/north_star_owner_review/2026-03-05/locked_flags_monthly.csv`
  - `exports/north_star_owner_review/2026-03-05/locked_flags_monthly_by_store.csv`
  - `exports/north_star_owner_review/2026-03-05/publication_readiness.json`

### P6 — Minimum Safe Correction Set (Post-Cause Isolation Only)
- Only after P2/P3/P4 isolate real causes.
- Any DB write requires:
  - `python3 scripts/backup_db.py --db db/app.db`
  - explicit env gate
  - `--apply`
  - before/after diff artifacts
  - `db_write_log.md`
- Do not expand from Jan-Feb to full history until Jan-Feb evidence is green.

## Required Tests
- workbook parser contract tests for both downloaded workbooks
- sales truth vs CRM North Star validator tests
- COGS completeness tests
- ads offer-universe coverage tests
- North Star review builder tests
- regression tests ensuring locked months never expose numeric profit

## Required Gates
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
- `python3 scripts/validate_single_truth_system.py`
- `python3 scripts/validate_params.py --strict --as-of 2026-03-05`
- `bash scripts/lint_docs.sh`
- `python3 scripts/validate_sales_truth_vs_crm_north_star.py --start 2026-01-01 --end 2026-02-29 --strict`
- `python3 scripts/validate_cogs_completeness_by_month.py --start 2026-01-01 --end 2026-02-29 --strict`
- `python3 scripts/validate_ads_offer_universe_coverage.py --start 2026-01-01 --end 2026-02-29 --strict`
- `python3 scripts/build_north_star_owner_review.py --as-of 2026-03-05 --strict`

## Required Evidence Artifacts
- `exports/validation/crm_north_star_rebuild/2026-03-05/full_execution_transcript.md`
- `exports/validation/crm_north_star_rebuild/2026-03-05/open_stopline_items.md` (if any gate is red)
- `docs/OPS_ROLLOUT_EVIDENCE_CRM_NORTH_STAR_REBUILD_2026-03-05.md`
- Final journal entry in `claude/journal.md` summarizing proof, reds, profit lock status, and next inspection files.

## Absolute Stop Conditions
- missing CRM workbook or reconciled workbook
- silent schema drift in downloaded workbooks
- leaving CRM ceiling gate optional for owner publication
- coercing missing ads to zero
- publishing profit for locked months
- DB write without backup + env gate + `--apply` + rollback path
I'll provide Oracle Pack with these changes.