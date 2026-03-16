# PLAN_ADS_SCOPE_SOURCE_REFRESH_AND_GOVERNANCE_CLOSEOUT_2026-03-08

## Purpose
Finish the currently blocked rollout after the workbook catalog sync by clearing the only remaining real blockers:
1. active-ads scope must be encoded explicitly by store and effective date,
2. the real ads sidecar DB must be rebuilt from a fresh marketing source using the already-tested `assisted_products` fix,
3. the remaining ACMEWEAR `HUS` ads gap must be either recovered from source or formally quarantined by contract,
4. the stale forensic COGS comparator must be refreshed or explicitly superseded,
5. the missing daily ops artifact must be generated so `system_doctor` can go green,
6. only then resume economics, owner publication, and daily automation.

This plan is single-agent, sequential, fail-closed, and assumes minimal human time:
- login / secret refresh for the external marketing source if needed,
- prompt / plan copy-paste only.

## Current Baseline
- Branch/worktree: `codex/TASK-webui-archive-single-truth-v1`
- Latest evidenced head from prior phase: `4124c14836366871b94a1dd785604f5b58b54912`
- Current authoritative READCHECK head for this phase: `86ce447782a005c47ac3d1b61dde8414900320a8`
- Workbook catalog sync already applied:
  - `exports/validation/workbook_catalog_offer_map_sync/2026-03-08/workbook_catalog_offer_map_sync.json`
- Current green gates already proven:
  - `validate_sales_against_workbook.py --strict`
  - `validate_webui_archive_vs_current_db.py --strict`
  - `validate_params.py --strict --as-of 2026-03-07`
  - `validate_single_truth_system.py`
  - `validate_monthly_economics_parity.py --since 2025-06-06 --until 2026-03-07 --strict`
  - `audit_cogs_realism.py --as-of 2026-03-07 --days 60 --strict`
- Remaining blockers:
  - ads source freshness is stale for real sidecar apply,
  - one real ACMEWEAR/HUS Jan ads-source gap remains,
  - legacy forensic COGS comparator is stale,
  - `exports/daily/2026-03-07/daily_ops_report.json` is missing,
  - `system_doctor.py --strict --project-root . --as-of 2026-03-07` remains red.

## Assumption Locked From Operator Note
- Current active Kaspi ads stores:
  - `STOREB` = active
  - `ACMEWEAR` = active
  - `UNIVERSAL` = inactive since approximately `2026-02-22`
- This assumption must be encoded as an effective-dated contract/config, not left as tribal knowledge.
- Historical periods before the stop date must still validate according to the store’s historical ads activity.

## Non-Negotiables
1. Fail-closed always.
2. No new WebUI scrape in this plan.
3. DB-backed validation/publication remains mandatory.
4. Read-only first; no DB writes unless:
   - backup exists,
   - env gate is set,
   - `--apply` is present,
   - before/after diffs are emitted,
   - rollback path is documented.
5. No silent tolerance widening.
6. No silent relaxation of the stale forensic comparator.
7. Do not claim completion unless every stated gate is green.

---
Risks + likely regressions to watch

Wrong ads scope assumptions for current/future runs. Your operator note changes the current ads-state model: STOREB and ACMEWEAR are actively running Kaspi ads now; UNIVERSAL stopped around two weeks before 2026-03-08. If this is not encoded as an effective-dated ads-scope contract, future validations may keep treating UNIVERSAL as an active ads store when it should be “off,” or may incorrectly skip historical windows when it was still active. The plan therefore introduces an explicit store/date scope contract rather than hardcoded store lists.

Applying the sidecar fix to the real DB without refreshing the ads source. The current evidence explicitly says the live sidecar was built before the assisted_products fix and real apply is blocked by stale marketing DB freshness. Doing a write without a fresh source would violate the current fail-closed contract.

Silently relaxing the stale forensic comparator. The current evidence says not to do that. Any comparator refresh must be explicit, documented, and tested, because internal audits are green while the legacy external file is stale.

Skipping daily artifact generation while expecting doctor green. The repo’s governance layer fails closed on missing/as-of-inconsistent daily artifacts. Until exports/daily/<as_of>/daily_ops_report.json exists for the target as-of, system_doctor can legitimately stay red even if truth is otherwise fixed.

Biggest unknowns

Whether the HUS gap can be recovered from refreshed marketing source tables/details after a real source refresh, or whether it will remain a true source-untrackable order that needs explicit quarantine by contract.

Whether the stale forensic comparator should be replaced, refreshed, or formally demoted in favor of the already-green internal checks (audit_cogs_realism, monthly economics parity). The evidence only proves it is stale; it does not yet define the new canonical external comparator policy.

Whether any additional system_doctor truth/governance blockers remain after ads and the comparator are resolved. The current evidence bundle stops at status=RED blocked_layer=truth and the missing daily artifact, but does not show the full post-fix doctor trace yet.

----
## Phase P0 — Freeze Baseline + Ads Scope Contract

### Goal (measurable)
Freeze the current 2026-03-08 baseline and encode the effective-dated active ads scope.

### Inputs
- `exports/validation/workbook_catalog_offer_map_sync/2026-03-08/workbook_catalog_offer_map_sync.json`
- `exports/validation/workbook_catalog_offer_map_sync/2026-03-08/resume_replay_status.md`
- `exports/validation/workbook_catalog_offer_map_sync/2026-03-08/open_stopline_items.md`
- operator note:
  - STOREB active
  - ACMEWEAR active
  - UNIVERSAL off since ~2026-02-22

### Outputs (exact paths)
- `docs/validation/ADS_ACTIVE_SCOPE_CONTRACT.md`
- `config/ads_active_scope.yaml`
- `exports/validation/ads_scope_closeout/2026-03-08/readcheck.md`
- `exports/validation/ads_scope_closeout/2026-03-08/baseline_manifest.json`

### Definition of Done
Accepted as done only when:
1. Ads-active scope is encoded with effective dates.
2. Historical windows still preserve prior-store activity when applicable.
3. Active docs remain free of absolute personal paths.

### Validation / Gates
- `python3 scripts/validate_single_truth_system.py`
- `bash scripts/lint_docs.sh`
- new tests for scope resolution:
  - current-day scope
  - historical-window scope
  - UNIVERSAL off after the configured stop date

### Rollback / Backout
- Revert docs/config only. No DB writes in P0.

### Stop-the-line criteria
- Any hardcoded forever-active / forever-inactive store rule
- Any active doc with absolute `/Users/...` path
- Any scope rule that erases historical activity incorrectly

---

## Phase P1 — Real Ads Source Refresh + Sidecar Apply

### Goal (measurable)
Refresh the external marketing DB/source and apply the already-tested `assisted_products` sync path to the real DB sidecar tables.

### Inputs
- `scripts/sync_ads_sidecar.py`
- current real DB `db/app.db`
- refreshed external marketing DB/source
- `config/ads_active_scope.yaml`

### Outputs
- `exports/validation/ads_scope_closeout/2026-03-08/ads_source_refresh_report.md`
- `exports/validation/ads_scope_closeout/2026-03-08/ads_sidecar_apply_report.json`
- `exports/validation/ads_scope_closeout/2026-03-08/ads_sidecar_apply_report.md`
- if writes occur:
  - `exports/validation/ads_scope_closeout/2026-03-08/db_write_log.md`
  - `exports/validation/ads_scope_closeout/2026-03-08/before_after_diffs/`

### Definition of Done
Accepted as done only when:
1. Source freshness is green for real apply.
2. `sync_ads_sidecar.py` apply succeeds on the real DB.
3. The assisted-products fix is now actually present in the live sidecar tables, not just in temp replay.

### Validation / Gates
- dry-run or readiness proof for the source freshness path
- `ENABLE_CASHFLOW_WRITE=1 python3 scripts/sync_ads_sidecar.py --since 2026-01-01 --until 2026-02-29 --apply`
- post-apply targeted checks proving `LINE52` is no longer missing because of parser/ingestion loss

### Rollback / Backout
- `python3 scripts/backup_db.py --db db/app.db`
- restore the pre-apply backup if apply fails or worsens coverage

### Stop-the-line criteria
- Any apply without fresh source
- Any DB write without backup + env gate + `--apply`
- Any mismatch between temp replay and real DB apply artifacts

---

## Phase P2 — ACMEWEAR HUS Resolution / Quarantine Decision

### Goal (measurable)
Resolve the last remaining ACMEWEAR Jan ads gap at:
- `order_id=776936815`
- `sale_date=2026-01-06`
- `sku_key=CL_NEW-CLO2_MEN_HUS_GREEN`

### Inputs
- refreshed real ads source
- real sidecar tables after P1
- `ads_offer_universe_report.json`
- `ads_offer_universe_report_assisted_probe.json`
- `ads_missing_sold_offers.csv`
- `ads_missing_sold_offers_assisted_probe.csv`

### Outputs
- `exports/validation/ads_scope_closeout/2026-03-08/hus_root_cause_report.md`
- one of:
  - `exports/validation/ads_scope_closeout/2026-03-08/hus_source_recovery_evidence.json`
  - or `docs/validation/ADS_SOURCE_GAP_QUARANTINE_CONTRACT.md`
  - and `config/ads_source_gap_quarantine.yaml`
- refreshed:
  - `ads_offer_universe_report.json`
  - `ads_spend_reality_report.json`

### Definition of Done
Accepted as done only when:
1. Exactly one path is chosen:
   - source recovered, or
   - formally quarantined by contract.
2. `validate_ads_offer_universe_coverage.py --strict` passes under the chosen path.
3. `validate_ads_spend_reality.py --strict` still passes.

### Validation / Gates
- `python3 scripts/validate_ads_offer_universe_coverage.py --start 2026-01-01 --end 2026-02-29 --truth-source webui_archive --strict`
- `python3 scripts/validate_ads_spend_reality.py --start 2026-01-01 --end 2026-02-29 --truth-source webui_archive --strict`
- tests for:
  - recovered source path
  - quarantine path
  - lock-on-red behavior

### Rollback / Backout
- Revert quarantine contract/config if source recovery supersedes it later.
- Restore DB backup if any sidecar write batch caused regressions.

### Stop-the-line criteria
- Treating missing HUS ads as zero without explicit contract
- Broad quarantine that hides unrelated missing ads
- Relaxing ads coverage thresholds silently

---

## Phase P3 — Forensic Comparator Refresh Decision

### Goal (measurable)
Resolve the stale `validate_cogs_realism_vs_forensic.py` blocker explicitly.

### Inputs
- `exports/validation/workbook_catalog_offer_map_sync/2026-03-08/cogs_realism_report.json`
- `exports/validation/workbook_catalog_offer_map_sync/2026-03-08/validate_monthly_economics_parity_2026-03-07.txt`
- `exports/validation/workbook_catalog_offer_map_sync/2026-03-08/audit_cogs_realism_2026-03-07.txt`
- frozen forensic file currently used by `validate_cogs_realism_vs_forensic.py`

### Outputs
- one of:
  - `docs/validation/COGS_FORENSIC_REFERENCE_REFRESH_CONTRACT.md`
  - refreshed comparator artifact(s) with manifest + hash
  - updated `validate_cogs_realism_vs_forensic.py`
- or
  - `docs/validation/COGS_FORENSIC_REFERENCE_SUPERSESSION_DECISION.md`
  - validator/contract update replacing the stale comparator with the approved refreshed source
- evidence:
  - `exports/validation/ads_scope_closeout/2026-03-08/cogs_comparator_decision.md`

### Definition of Done
Accepted as done only when:
1. The stale comparator is either refreshed or explicitly superseded by contract.
2. `validate_cogs_realism_vs_forensic.py --strict` passes on the approved comparator path.
3. Internal green checks remain green.

### Validation / Gates
- `python3 scripts/validate_cogs_realism_vs_forensic.py --start 2026-01-01 --end 2026-02-29 --truth-source webui_archive --strict`
- `python3 scripts/validate_monthly_economics_parity.py --since 2025-06-06 --until 2026-03-07 --strict`
- `python3 scripts/audit_cogs_realism.py --as-of 2026-03-07 --days 60 --strict`

### Rollback / Backout
- Revert comparator/contract changes if the refreshed reference introduces new unexplained red states.

### Stop-the-line criteria
- Silent relaxation of the stale comparator
- Comparator replacement without manifest/provenance
- Internal green checks regressing after comparator change

---

## Phase P4 — Daily Ops Artifact + Doctor Replay

### Goal (measurable)
Generate the missing daily ops artifact and rerun the governance path after ads/comparator blockers are green.

### Inputs
- current truth/economics state after P1–P3
- `scripts/system_doctor.py`
- `scripts/run_owner_truth_daily.py`
- as-of target closeout date (`2026-03-07` first, then `2026-03-08` for fresh daily run)

### Outputs
- `exports/daily/2026-03-07/daily_ops_report.json`
- `exports/daily/2026-03-07/daily_ops_report.md`
- `exports/validation/ads_scope_closeout/2026-03-08/system_doctor_after_closeout.md`
- `exports/validation/ads_scope_closeout/2026-03-08/validate_params_after_closeout.txt`

### Definition of Done
Accepted as done only when:
1. `daily_ops_report.json` exists for the target as-of.
2. `validate_params.py --strict --as-of 2026-03-07` passes.
3. `system_doctor.py --strict --project-root . --as-of 2026-03-07` passes.

### Validation / Gates
- `python3 scripts/validate_params.py --strict --as-of 2026-03-07`
- `python3 scripts/system_doctor.py --strict --project-root . --as-of 2026-03-07`
- `python3 scripts/validate_single_truth_system.py`
- `bash scripts/lint_docs.sh`

### Rollback / Backout
- If any write-gated repair is needed before doctor passes, back up DB first and restore on regression.

### Stop-the-line criteria
- Proceeding to owner publication while doctor is red
- Missing daily artifact
- Any as-of mismatch between artifacts

---

## Phase P5 — Economics / Owner Publication Resume

### Goal (measurable)
Resume the blocked economics/publication path only after P1–P4 are green.

### Inputs
- green ads gates
- green COGS gates
- green doctor
- owner publication builders

### Outputs
- `exports/validation/ads_scope_closeout/2026-03-08/ads_offer_universe_report.json`
- `exports/validation/ads_scope_closeout/2026-03-08/ads_spend_reality_report.json`
- `exports/validation/ads_scope_closeout/2026-03-08/cogs_completeness_report.json`
- `exports/validation/ads_scope_closeout/2026-03-08/cogs_realism_report.json`
- `exports/north_star_owner_review/2026-03-08/...`
- `exports/owner_pnl/2026-03-08/...`

### Definition of Done
Accepted as done only when:
1. `build_north_star_owner_review.py --strict` passes.
2. `build_owner_pnl_report.py --strict` passes.
3. Locked months still show `N/A` + `locked_reason`.
4. Ads current-store scope is honored for current/future windows.

### Validation / Gates
- `python3 scripts/validate_ads_offer_universe_coverage.py --start 2026-01-01 --end 2026-02-29 --truth-source webui_archive --strict`
- `python3 scripts/validate_ads_spend_reality.py --start 2026-01-01 --end 2026-02-29 --truth-source webui_archive --strict`
- `python3 scripts/validate_cogs_completeness_by_month.py --start 2026-01-01 --end 2026-02-29 --truth-source webui_archive --strict`
- `python3 scripts/validate_cogs_realism_vs_forensic.py --start 2026-01-01 --end 2026-02-29 --truth-source webui_archive --strict`
- `python3 scripts/build_north_star_owner_review.py --as-of 2026-03-08 --truth-source webui_archive --strict`
- `python3 scripts/build_owner_pnl_report.py --as-of 2026-03-08 --truth-source webui_archive --strict`

### Rollback / Backout
- Revert publication changes if any month unlocks incorrectly.
- Restore DB backup if apply-gated sidecar or reconciliation changes regress.

### Stop-the-line criteria
- Numeric profit on locked months
- Partial ads treated as full without contract
- Publication unlock while any upstream gate is red

---

## Phase P6 — Daily Automation + Full-History Replay + Promotion

### Goal (measurable)
Operationalize the corrected path after closeout.

### Inputs
- successful P0–P5 artifacts
- `scripts/run_owner_truth_daily.py`
- `scripts/triage_owner_truth_stoplines.py`

### Outputs
- `exports/daily/2026-03-08/owner_truth_summary.json`
- `exports/validation/ads_scope_closeout/full_history_<RUN_ID>/...`
- `docs/OPS_ROLLOUT_EVIDENCE_ADS_SCOPE_SOURCE_REFRESH_AND_GOVERNANCE_CLOSEOUT_2026-03-08.md`
- refreshed Oracle pack

### Definition of Done
Accepted as done only when:
1. `run_owner_truth_daily.py --strict` succeeds with the new ads-scope-aware path.
2. Full-history replay is deterministic.
3. Promotion evidence references exact commit SHA, commands, outputs, and rollback path.

### Validation / Gates
- `python3 scripts/run_owner_truth_daily.py --as-of 2026-03-08 --strict`
- `python3 scripts/triage_owner_truth_stoplines.py --as-of 2026-03-08 --strict`
- complete strict chain rerun
- full-history replay command(s)

### Rollback / Backout
- Revert promotion commit.
- Restore DB backup if any apply step occurred.
- Restore prior scheduler/session config if needed.

### Stop-the-line criteria
- Promotion without evidence
- Full-history replay before Jan–Feb / governance / ads / comparator are green
- Any automation path hiding a failed prerequisite

---

## If attachments are missing — assumptions policy
- Use repo-relative paths inside active docs.
- If required marketing DB refresh artifacts, workbook anchor artifacts, or comparator inputs are missing:
  - fail strict mode,
  - emit a missing-input manifest,
  - do not continue with placeholder data.
- If the exact UNIVERSAL stop date is still approximate:
  - encode `2026-02-22` as operator-authority provisional,
  - replace it only if refreshed source evidence proves a more exact date,
  - do not silently move the stop date.
- If current HEAD differs from the assumed baseline:
  - record actual branch + SHA in READCHECK and treat that as authoritative.
