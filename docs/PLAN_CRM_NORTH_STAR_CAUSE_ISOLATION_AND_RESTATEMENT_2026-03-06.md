# PLAN_CRM_NORTH_STAR_CAUSE_ISOLATION_AND_RESTATEMENT_2026-03-06

## Purpose
Move the CRM North Star rebuild from scaffolded fail-closed RED to decision-grade Jan–Feb truth by:
1. clearing the cross-cutting strict baseline stopline,
2. upgrading sales truth from a ceiling-only check to a bidirectional CRM/reconciled truth band,
3. proving ads completeness and COGS realism rather than only freshness/completeness,
4. publishing a single locked/unlocked North Star owner review surface,
5. applying the minimum safe correction set only after causes are isolated,
6. expanding to automation and full-history replay only after Jan–Feb is green.

This plan is single-agent, sequential, fail-closed, and minimizes human work to login/secrets/copy-paste only.

Risks + likely regressions to watch

Regressing the 2026-03-04 owner-truth green baseline while chasing Jan–Feb North Star fixes. 

DAY_COMPLETE_CONTRACT

Keeping the CRM gate ceiling-only and therefore missing undercount scenarios.

Treating current COGS PASS as proof of realism.

Treating ads freshness / mapping as proof of full spend completeness.

Expanding to full history before Jan–Feb is green.

Any DB write without backup, env gate, --apply, and before/after diff artifacts. 

DAY_COMPLETE_CONTRACT

Automation_Handoff_V16

Biggest unknowns

Assumption: the forensic workbook/CSV comparison already discussed in-session is directionally correct — namely, that Jan–Feb likely still suffer from event-set undercoverage and/or understated COGS/ads despite the current completeness PASS. This plan treats that as unproven but serious and therefore adds explicit realism validators instead of trusting the current surface.

Assumption: the existing downloaded forensic files remain available and stable in the same locations or can be copied into Downloads/repo evidence without schema drift.

Assumption: no parallel worktree is needed; single-agent continuation on the current branch is lower-risk than branching and cherry-picking because the current scaffold and oracle pack already live there. 

DAY_COMPLETE_CONTRACT

## Current Baseline
- Repo: `~/Docs/Autonomous_business`
- Continue on branch/worktree: `codex/TASK-crm-north-star-rebuild-v1`
- Current known recent commit stack includes:
  - `4bd2da2`
  - `6b5ef81`
  - `5ef9a7e`
  - `b620f7c`
  - `f8d3c84`
  - `0d7b0e2`
  - `a099275`
- Existing green rollback anchor:
  - `exports/validation/owner_truth_release/2026-03-04/full_gates_green_final.md`
- Existing North Star artifacts:
  - `exports/validation/crm_north_star_rebuild/2026-03-05/...`
  - `exports/north_star_owner_review/2026-03-05/...`
- Current stoplines:
  - `validate_params --strict --as-of 2026-03-05` FAIL
  - `validate_sales_truth_vs_crm_north_star --strict` FAIL
  - `validate_ads_offer_universe_coverage --strict` FAIL
  - `build_north_star_owner_review --strict` blocked / locked
- No DB writes were executed in the current North Star board run.

## Non-Negotiables
1. Fail-closed always.
2. Single-agent sequential execution in one branch/worktree.
3. Read-only first; DB writes only after root cause isolation, backup-first, env-gated, and `--apply`.
4. No formula/policy-threshold changes without first updating `docs/inventory/Master_Inventory_Rules_v8.md`, then the owning contracts, then validators/tests.
5. Do not claim completion unless all phase gates are green and required artifacts exist.

---

## Phase P0 — Strict Baseline Unblock

### Goal (measurable)
Clear the cross-cutting strict baseline blocker so North Star remediation is not built on a red global chain.

### Inputs
- `scripts/validate_params.py`
- `exports/validation/owner_truth_release/2026-03-04/open_stopline_items.md`
- `docs/KASPI_ORDER_CASHFLOW_TRACKING.md`
- `db/app.db`
- Existing apply-gated settlement translator/reconciler paths

### Outputs (exact paths)
- `exports/validation/crm_north_star_restate/2026-03-06/p0_readcheck.md`
- `exports/validation/crm_north_star_restate/2026-03-06/p0_baseline_transcript.md`
- `exports/validation/crm_north_star_restate/2026-03-06/p0_stopline_report.md`
- If writes occur:
  - `exports/validation/crm_north_star_restate/2026-03-06/p0_db_write_log.md`

### Definition of Done
Accepted as done only when:
1. `python3 scripts/validate_params.py --strict --as-of 2026-03-05` returns PASS.
2. No regression is introduced to the green `2026-03-04` owner-truth release baseline.
3. Any write is fully logged with backup path, apply command, and post-write validation.

### Validation / Gates
- `python3 scripts/validate_params.py --strict --as-of 2026-03-05`
- `python3 scripts/validate_single_truth_system.py`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
- If code/docs touched: `bash scripts/lint_docs.sh`

### Rollback / Backout
- `python3 scripts/backup_db.py --db db/app.db --dest runtime/backups --keep-days 30`
- Restore the pre-apply backup if any write worsens baseline gates.

### Stop-the-line
- Any apply without backup + env gate + `--apply`
- Any regression to the `2026-03-04` green owner-truth release
- Any attempt to silence the `on_delivery_freeze` stopline without fixing its underlying residuals

---

## Phase P1 — North Star Root-Cause Isolation (CRM Band + Chronology Bridge)

### Goal (measurable)
Replace the current ceiling-only CRM gate with a bidirectional Jan–Feb truth gate that detects:
- DB > CRM ceiling
- DB materially below CRM/reconciled floor
- chronology misplacement vs bridge status
- exact IN_DB_ONLY / IN_CRM_ONLY / bridge-classified gaps

### Inputs
- `scripts/normalize_crm_north_star_inputs.py`
- `scripts/validate_sales_truth_vs_crm_north_star.py`
- `~/Downloads/SALES_KSP_CRM_GPT_Sales_archive.xlsx`
- `~/Downloads/Claude_Reconciled_plus_crm_corrected.xlsx`
- P1 artifacts already generated under `exports/validation/crm_north_star_rebuild/2026-03-05/`

### Outputs
- Updated `scripts/validate_sales_truth_vs_crm_north_star.py`
- `exports/validation/crm_north_star_restate/2026-03-06/sales_truth_vs_crm_by_day_store.csv`
- `exports/validation/crm_north_star_restate/2026-03-06/sales_truth_vs_crm_by_sku.csv`
- `exports/validation/crm_north_star_restate/2026-03-06/sales_truth_vs_crm_gap_classifier.csv`
- `exports/validation/crm_north_star_restate/2026-03-06/sales_truth_vs_crm_floor_gaps.csv`
- `exports/validation/crm_north_star_restate/2026-03-06/sales_truth_vs_crm_root_causes.md`

### Definition of Done
Accepted as done only when:
1. Jan–Feb 2026 validator is PASS with `breach_days=0` and `breach_skus=0`.
2. The validator enforces both ceiling and lower-bound coverage checks.
3. Every unresolved order/day/store/SKU gap is classified into an explicit reason bucket.
4. Strict owner publication cannot bypass this gate when the CRM workbook is present.

### Validation / Gates
- `python3 scripts/validate_sales_truth_vs_crm_north_star.py --start 2026-01-01 --end 2026-02-29 --strict`
- targeted test suite for:
  - ceiling breaches
  - floor gaps
  - chronology bridge classification
  - locked publication on red

### Rollback / Backout
- Read-only by default.
- If any later correction writes are required, defer to P5.

### Stop-the-line
- Leaving the CRM gate optional
- Mixing date grains without explicit bridge logic
- Allowing DB to exceed CRM ceiling or materially undercount without red status

---

## Phase P2 — Ads Offer-Universe + Spend Realism

### Goal (measurable)
Prove that sold current offers are covered by the ads-mapped universe and that monthly ads spend is not being understated by mapping-only completeness.

### Inputs
- `scripts/validate_ads_offer_universe_coverage.py`
- ads sidecar tables in `db/app.db`
- sold truth from `view_sales_line_truth`
- downloaded forensic/review artifacts if present

### Outputs
- Updated `scripts/validate_ads_offer_universe_coverage.py`
- New `scripts/validate_ads_spend_reality.py`
- `exports/validation/crm_north_star_restate/2026-03-06/ads_offer_universe_coverage.csv`
- `exports/validation/crm_north_star_restate/2026-03-06/ads_missing_sold_offers.csv`
- `exports/validation/crm_north_star_restate/2026-03-06/ads_coverage_by_month_store.csv`
- `exports/validation/crm_north_star_restate/2026-03-06/ads_spend_reality_by_month_store.csv`
- `exports/validation/crm_north_star_restate/2026-03-06/ads_offer_universe_report.md`

### Definition of Done
Accepted as done only when:
1. `failing_month_store_pairs = 0`.
2. Ads completeness is labeled FULL/PARTIAL/UNKNOWN by month/store.
3. `profit_after_ads` stays locked whenever coverage or spend realism is red.
4. Missing sold offers are fully enumerated.

### Validation / Gates
- `python3 scripts/validate_ads_offer_universe_coverage.py --start 2026-01-01 --end 2026-02-29 --strict`
- `python3 scripts/validate_ads_spend_reality.py --start 2026-01-01 --end 2026-02-29 --strict`
- tests for:
  - coverage failure
  - partial spend labeling
  - locked output behavior

### Rollback / Backout
- Read-only unless a later mapping repair is deliberately applied in P5.

### Stop-the-line
- Coercing missing ads to zero
- Publishing profit-after-ads while coverage/spend realism is red
- Silent use of partial ads as if they were full

---

## Phase P3 — COGS Realism + Landed-Cost Sanity Band

### Goal (measurable)
Extend beyond completeness and prove whether current COGS is economically plausible for Jan–Feb against the forensic workbook / SKU priors / weight-based landed-cost expectations.

### Inputs
- `scripts/validate_cogs_completeness_by_month.py`
- current COGS artifacts under `exports/validation/crm_north_star_rebuild/2026-03-05/`
- downloaded forensic workbook(s)
- `dim_sku` / weight alignment paths
- existing COGS integrity contract/tests

### Outputs
- New `scripts/validate_cogs_realism_vs_forensic.py`
- `exports/validation/crm_north_star_restate/2026-03-06/cogs_realism_by_month.csv`
- `exports/validation/crm_north_star_restate/2026-03-06/cogs_realism_by_sku.csv`
- `exports/validation/crm_north_star_restate/2026-03-06/cogs_profit_at_risk.csv`
- `exports/validation/crm_north_star_restate/2026-03-06/cogs_restatement_scope.md`

### Definition of Done
Accepted as done only when:
1. Jan–Feb COGS has both completeness PASS and realism PASS.
2. Any month/store/SKU outside the allowed band is enumerated with profit-at-risk.
3. Owner publication locks profit when COGS realism is red.

### Validation / Gates
- `python3 scripts/validate_cogs_completeness_by_month.py --start 2026-01-01 --end 2026-02-29 --strict`
- `python3 scripts/validate_cogs_realism_vs_forensic.py --start 2026-01-01 --end 2026-02-29 --strict`
- targeted tests for:
  - unrealistically low landed COGS
  - weight drift impact
  - base-only masquerading as full landed COGS
  - lock-on-red publication behavior

### Rollback / Backout
- Read-only unless a later COGS/weight correction is deliberately applied in P5.

### Stop-the-line
- Treating completeness PASS as proof of realism
- Any month with numeric profit while realism is red
- Any silent overwrite of weight/COGS master data

---

## Phase P4 — Locked North Star Owner Review Surface

### Goal (measurable)
Publish one canonical review surface that the owner can inspect visually without mistaking provisional or red metrics for real profit.

### Inputs
- `scripts/build_north_star_owner_review.py`
- outputs from P1/P2/P3
- `docs/validation/OWNER_PNL_PUBLICATION_CONTRACT.md`

### Outputs
- Updated `scripts/build_north_star_owner_review.py`
- `exports/north_star_owner_review/2026-03-06/NORTH_STAR_OWNER_REVIEW.json`
- `exports/north_star_owner_review/2026-03-06/NORTH_STAR_OWNER_REVIEW.md`
- `exports/north_star_owner_review/2026-03-06/monthly_totals_review.csv`
- `exports/north_star_owner_review/2026-03-06/daily_profit_by_day_store.csv`
- `exports/north_star_owner_review/2026-03-06/sku_profit_table.csv`
- `exports/north_star_owner_review/2026-03-06/top_gainers_by_sku.csv`
- `exports/north_star_owner_review/2026-03-06/top_losers_by_sku.csv`
- `exports/north_star_owner_review/2026-03-06/locked_flags_monthly.csv`
- `exports/north_star_owner_review/2026-03-06/locked_flags_monthly_by_store.csv`
- `exports/north_star_owner_review/2026-03-06/publication_readiness.json`

### Definition of Done
Accepted as done only when:
1. All rendered files derive from one canonical JSON.
2. Locked months show `N/A` profitability plus `locked_reason`.
3. The review surface includes CRM ceiling/current DB/bridge status/ads completeness/COGS realism context.
4. Legacy noncanonical review surfaces are clearly marked diagnostic-only.

### Validation / Gates
- `python3 scripts/build_north_star_owner_review.py --as-of 2026-03-06 --strict`
- builder regression tests
- output consistency check (JSON -> Markdown/CSV parity)

### Rollback / Backout
- Read-only. Keep prior diagnostic surfaces until replacement is verified.

### Stop-the-line
- Numeric profit on locked months
- Multiple competing math paths for the same owner review
- Owner-grade labeling on a noncanonical surface

---

## Phase P5 — Minimum Safe Jan–Feb Correction Set

### Goal (measurable)
Apply only the smallest necessary correction set to make Jan–Feb decision-grade green after root causes are isolated.

### Inputs
- P0–P4 red reports
- existing repair/write scripts
- `db/app.db`
- `scripts/backup_db.py`

### Outputs
- `exports/validation/crm_north_star_restate/2026-03-06/restatement_plan.md`
- `exports/validation/crm_north_star_restate/2026-03-06/db_write_log.md`
- `exports/validation/crm_north_star_restate/2026-03-06/before_after_diffs/`
- refreshed P1–P4 artifacts

### Definition of Done
Accepted as done only when:
1. Jan–Feb P1/P2/P3/P4 are GREEN.
2. Every write is backed up, env-gated, `--apply`, and followed by explicit before/after diffs.
3. No fix expands beyond Jan–Feb until Jan–Feb is green.

### Validation / Gates
At minimum after each write batch:
- `python3 scripts/backup_db.py --db db/app.db`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
- `python3 scripts/validate_single_truth_system.py`
- `python3 scripts/validate_params.py --strict --as-of 2026-03-06`
- `bash scripts/lint_docs.sh`
- `python3 scripts/validate_sales_truth_vs_crm_north_star.py --start 2026-01-01 --end 2026-02-29 --strict`
- `python3 scripts/validate_ads_offer_universe_coverage.py --start 2026-01-01 --end 2026-02-29 --strict`
- `python3 scripts/validate_ads_spend_reality.py --start 2026-01-01 --end 2026-02-29 --strict`
- `python3 scripts/validate_cogs_realism_vs_forensic.py --start 2026-01-01 --end 2026-02-29 --strict`
- `python3 scripts/build_north_star_owner_review.py --as-of 2026-03-06 --strict`

### Rollback / Backout
- Restore the specific pre-apply DB backup.
- Revert code changes for the write batch.
- Rerun strict gates to confirm rollback integrity.

### Stop-the-line
- Any DB write without backup + env gate + `--apply`
- Any restatement without before/after diff artifacts
- Expanding from Jan–Feb to full history before Jan–Feb is green

---

## Phase P6 — Observability + Daily Automation

### Goal (measurable)
Make future failures obvious and daily owner-truth runs deterministic.

### Inputs
- prior owner-truth autopilot plan artifacts
- stopline patterns already used by doctor
- P1–P5 gates

### Outputs
- updated `scripts/triage_owner_truth_stoplines.py`
- updated `scripts/run_owner_truth_daily.py`
- `exports/daily/<AS_OF>/owner_truth_summary.json`
- `exports/validation/crm_north_star_restate/<AS_OF>/automation_smoke.md`

### Definition of Done
Accepted as done only when:
1. One command emits a clear red/green owner-truth summary.
2. The summary links to exact blocker artifacts.
3. No catch-and-continue behavior hides a failed gate.

### Validation / Gates
- `python3 scripts/triage_owner_truth_stoplines.py --as-of <AS_OF> --strict`
- `python3 scripts/run_owner_truth_daily.py --as-of <AS_OF> --strict`
- JSON schema tests for the summary artifact

### Rollback / Backout
- Read-only unless an existing sync step is intentionally run in apply mode.

### Stop-the-line
- Any automation path that silently skips a failed prerequisite
- Any summary that claims ready while publication remains locked

---

## Phase P7 — Full-History Replay + Promotion Evidence

### Goal (measurable)
Only after Jan–Feb is green, expand the same proven logic to full history and prepare promotion evidence.

### Inputs
- Jan–Feb green artifacts
- prior automation / UI-pack refresh / replay plans
- `docs/ops/PROMOTION_MINIMUM_STANDARD.md`

### Outputs
- `exports/validation/crm_north_star_restate/full_history_<RUN_ID>/...`
- `docs/OPS_ROLLOUT_EVIDENCE_CRM_NORTH_STAR_RESTATE_2026-03-XX.md`
- new Oracle pack
- commit-stamped release metadata

### Definition of Done
Accepted as done only when:
1. Full-history replay artifacts exist and are deterministic.
2. Local required gates are GREEN.
3. Promotion evidence references exact commit SHA, commands, and outputs.

### Validation / Gates
- all P0–P6 required gates
- full-history replay command(s)
- promotion evidence completeness check

### Rollback / Backout
- Revert promotion commit or restore prior release state.
- Restore DB backup if any historical apply step occurred.

### Stop-the-line
- Promotion without evidence
- Full-history expansion before Jan–Feb green
- Any divergence from single-truth contracts

---

## If attachments are missing — assumptions policy
- Default repo: `~/Docs/Autonomous_business`
- Default downloads root: `~/Downloads`
- If a required workbook/forensic attachment is missing:
  - fail strict mode,
  - emit a missing-input manifest,
  - do not continue with placeholder data.
- If filenames differ but contents are clearly the same:
  - record the exact substituted path in the manifest,
  - continue only when SHA256 + traceability are explicit.
- If workbook schema drifts:
  - fail closed with a schema mismatch report.
- If current HEAD differs from the assumed branch/commit context:
  - record actual branch + SHA in READCHECK and treat that as authoritative.

This plan intentionally extends the current board with two missing proof layers that the current scaffold does not provide: bidirectional sales-truth coverage and COGS/ads realism. That recommendation follows directly from the current validator shapes: sales truth is ceiling-only, COGS PASS is completeness-only, and ads PASS/FAIL is coverage-only. 