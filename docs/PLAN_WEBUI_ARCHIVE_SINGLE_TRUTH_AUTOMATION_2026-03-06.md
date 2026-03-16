# PLAN_WEBUI_ARCHIVE_SINGLE_TRUTH_AUTOMATION_2026-03-06

## Purpose
Promote Kaspi WebUI archive exports (downloaded in immutable 90-day blocks per store) to the candidate primary historical sales-truth source, then prove and automate that source before cutover.

The target architecture is:

1. **Historical truth**
   - Primary candidate source: WebUI archive packs with status-locked rows and status-change dates.
   - Control anchor: CRM workbook remains the floor/ceiling guardrail for shipped-day reality.
   - Operational system of record remains `db/app.db`.

2. **Future truth**
   - Playwright downloads archive packs on a schedule per store.
   - API sync continues for live/order-entry enrichment and future observed-state snapshots.
   - API status observations are stored with `observed_at`; they do not replace historical WebUI status-change truth.

3. **Publication**
   - Owner publication remains locked until:
     - WebUI archive pack integrity is green,
     - status ledger continuity is green,
     - WebUI truth vs CRM/DB band is green,
     - ads + COGS gates are green on the promoted source,
     - system_doctor governance is green.

This plan is single-agent, sequential, fail-closed, and minimizes human work to login/2FA/session refresh and prompt copy-paste only.

## Current Baseline
- Continue from branch/worktree baseline: `codex/TASK-crm-north-star-rebuild-v1` at `4bd2da2ceacf62aa258da8af100dae6c932176b1`.
- Existing rollback anchor:
  - `exports/validation/owner_truth_release/2026-03-04/full_gates_green_final.md`
- Existing red scaffold:
  - `exports/validation/crm_north_star_restate/2026-03-06/full_execution_transcript.md`
  - `exports/validation/crm_north_star_restate/2026-03-06/open_stopline_items.md`
- Existing red facts:
  - sales truth band red
  - ads offer coverage red
  - owner publication locked
  - doctor governance red

## Non-Negotiables
1. Fail-closed always.
2. DB remains the operational system of record; raw WebUI downloads never bypass DB-backed validation/publication.
3. Read-only first; no DB writes unless:
   - backup exists,
   - env gate is set,
   - `--apply` is present,
   - before/after diffs are emitted,
   - rollback path is documented.
4. No formula or threshold changes without:
   1. updating `docs/inventory/Master_Inventory_Rules_v8.md`,
   2. updating owning contracts,
   3. updating validators/tests.
5. No source cutover until Jan–Feb 2026 is green under the new WebUI-based truth gates.
6. Legacy methods are not retired immediately; they stay in shadow until cutover gates are green.
7. Active docs must avoid absolute personal paths; use variables/placeholders/anchors.

---

## Phase P0 — Source Contract Freeze + Baseline Preservation

### Goal (measurable)
Freeze the current green and red baselines, then explicitly define WebUI archive as the candidate new historical source contract without breaking the current owner-truth green anchor.

### Inputs
- `exports/validation/owner_truth_release/2026-03-04/full_gates_green_final.md`
- `exports/validation/crm_north_star_restate/2026-03-06/full_execution_transcript.md`
- `docs/inventory/Automation_Handoff_V16.md`
- `docs/inventory/Excel_UI_Contract_for_CRM_V1.md`
- `docs/DECISIONS.md`
- `docs/AGENTS.md`
- `claude/journal.md`

### Outputs (exact paths)
- `docs/PLAN_WEBUI_ARCHIVE_SINGLE_TRUTH_AUTOMATION_2026-03-06.md`
- `docs/validation/WEBUI_ARCHIVE_SINGLE_TRUTH_CONTRACT.md`
- `docs/OPS_ROLLOUT_EVIDENCE_WEBUI_ARCHIVE_SINGLE_TRUTH_2026-03-06.md`
- `exports/validation/webui_archive_single_truth/2026-03-06/readcheck.md`
- `exports/validation/webui_archive_single_truth/2026-03-06/baseline_manifest.json`

### Definition of Done
Accepted as done only when:
1. The new source contract is explicit: WebUI archive = candidate historical source, CRM = floor/ceiling cross-check, DB = operational truth.
2. The current `2026-03-04` green owner-truth release remains reproducible.
3. No cutover code is shipped before the contract and baseline manifest exist.

### Validation / Gates
- `git rev-parse --abbrev-ref HEAD`
- `git rev-parse HEAD`
- `git status --short`
- `python3 scripts/validate_single_truth_system.py`
- `python3 scripts/validate_params.py --strict --as-of 2026-03-06`
- `bash scripts/lint_docs.sh`

### Rollback / Backout
- Revert docs only.
- No DB writes allowed in P0.

### Stop-the-line criteria
- Any attempt to treat raw WebUI files as published truth without DB integration.
- Any regression to the `2026-03-04` green owner-truth baseline.
- Any active-doc absolute personal path.

---

## Phase P1 — Manual WebUI Archive Truth Pack (90-day blocks)

### Goal (measurable)
Support manually downloaded 90-day WebUI archive blocks as immutable truth packs for each enabled store.

### Inputs
- Downloads folder archive exports (per store, per 90-day block)
- Current store config / enabled store list
- WebUI archive export schema samples
- Current archive integrity rules around `statusChangeDate`

### Outputs
- `scripts/normalize_kaspi_webui_archive_pack.py`
- `scripts/validate_webui_archive_pack_integrity.py`
- `exports/webui_archive_packs/<PACK_ID>/source_manifest.json`
- `exports/webui_archive_packs/<PACK_ID>/normalized_rows.csv`
- `exports/webui_archive_packs/<PACK_ID>/integrity_report.json`
- `exports/webui_archive_packs/<PACK_ID>/integrity_report.md`

### Required rules
- Pack is immutable once ingested.
- Every row preserves source pack/store/file traceability.
- Delivered/completed rows missing status-change date fail strict integrity.
- Overlap windows are allowed but must not silently duplicate rows.

### Definition of Done
Accepted as done only when:
1. Jan–Feb store coverage exists from manual packs.
2. Strict integrity passes for all required packs.
3. Missing or malformed files produce explicit manifest failures.

### Validation / Gates
- `python3 scripts/validate_webui_archive_pack_integrity.py --pack-root <PACK_ROOT> --strict`
- parser contract tests
- schema drift tests
- duplicate/overlap tests

### Rollback / Backout
- Read-only.
- Delete/rebuild pack outputs only; no DB writes.

### Stop-the-line criteria
- Missing required status/date columns
- Schema drift without explicit parser update
- Duplicate rows caused by overlap merge
- Any pack without immutable manifest/hash

---

## Phase P2 — Historical Status Ledger Merge + Continuity

### Goal (measurable)
Merge overlapping 90-day packs into a single historical status ledger with deterministic continuity.

### Inputs
- normalized WebUI archive packs from P1
- enabled store list
- status normalization rules

### Outputs
- `scripts/build_webui_status_ledger.py`
- `scripts/validate_status_ledger_continuity.py`
- `exports/order_status_ledger/<RUN_ID>/webui_status_ledger.csv`
- `exports/order_status_ledger/<RUN_ID>/ledger_manifest.json`
- `exports/order_status_ledger/<RUN_ID>/continuity_report.json`
- `exports/order_status_ledger/<RUN_ID>/continuity_gaps.csv`

### Ledger grain
At minimum:
- `store_code`
- `order_id`
- `status_internal`
- `status_change_at`
- `created_at`
- `delivered_at` if derivable
- `returned_at` if derivable
- `source_pack_id`
- `source_file`
- `first_seen_pack`
- `last_seen_pack`

### Definition of Done
Accepted as done only when:
1. The ledger is deterministic across reruns.
2. Overlap dedup is stable.
3. No continuity gap exists for the Jan–Feb study window, unless explicitly explained in the gap report.

### Validation / Gates
- `python3 scripts/validate_status_ledger_continuity.py --ledger-root <RUN_ID> --start 2026-01-01 --end 2026-02-29 --strict`
- ledger determinism tests
- overlap/dedup tests
- status ordering tests

### Rollback / Backout
- Read-only.

### Stop-the-line criteria
- Non-deterministic merge output
- Unexplained overlap conflicts
- Missing store windows for enabled stores

---

## Phase P3 — Truth Promotion Band (WebUI archive vs CRM vs DB)

### Goal (measurable)
Prove that WebUI archive beats the current DB chronology and can sit inside a strict CRM floor/ceiling band for Jan–Feb.

### Inputs
- WebUI status ledger from P2
- CRM workbook / shipped anchor
- current DB sales truth
- existing North Star validators

### Outputs
- `scripts/validate_webui_archive_vs_crm_band.py`
- `scripts/validate_webui_archive_vs_current_db.py`
- `exports/validation/webui_archive_single_truth/2026-03-06/webui_vs_crm_by_day_store.csv`
- `exports/validation/webui_archive_single_truth/2026-03-06/webui_vs_db_by_day_store.csv`
- `exports/validation/webui_archive_single_truth/2026-03-06/webui_vs_crm_gap_classifier.csv`
- `exports/validation/webui_archive_single_truth/2026-03-06/webui_truth_promotion_report.md`

### Required rules
- WebUI truth must not exceed CRM shipped ceiling above tolerance.
- WebUI truth must not materially undercount CRM beyond tolerance.
- WebUI chronology must reduce mismatch counts versus the current DB-based band.
- DB publication remains locked until WebUI source wins this phase.

### Definition of Done
Accepted as done only when:
1. Jan–Feb WebUI-vs-CRM band is PASS.
2. WebUI chronology materially improves on current `chronology_mismatch_orders`.
3. The validator becomes a mandatory promotion gate for source cutover.

### Validation / Gates
- `python3 scripts/validate_webui_archive_vs_crm_band.py --start 2026-01-01 --end 2026-02-29 --strict`
- `python3 scripts/validate_webui_archive_vs_current_db.py --start 2026-01-01 --end 2026-02-29 --strict`
- band/chronology tests
- lock-on-red publication tests

### Rollback / Backout
- Read-only until P7/P8 cutover.

### Stop-the-line criteria
- Leaving CRM band gating optional
- Promoting WebUI source without beating current chronology mismatch
- Any publication unlock while this phase is red

---

## Phase P4 — Playwright Archive Automation (all enabled stores)

### Goal (measurable)
Automate 90-day archive downloads per enabled store with human involvement limited to login/2FA/session refresh.

### Inputs
- validated manual pack schema from P1
- enabled store list / merchant accounts
- local browser / Playwright runtime
- download root config
- session-state storage path

### Outputs
- `scripts/playwright/download_kaspi_archive_webui.py`
- `scripts/validate_playwright_archive_downloads.py`
- `config/anchors/kaspi_webui_archive_downloads.json`
- `exports/webui_archive_download_runs/<RUN_ID>/run_manifest.json`
- `exports/webui_archive_download_runs/<RUN_ID>/download_log.md`
- `exports/webui_archive_download_runs/<RUN_ID>/download_validation.json`

### Required rules
- Dry-run/session-check mode must exist.
- Actual downloads must write immutable file manifests and hashes.
- Session secrets/cookies must not be committed.
- Store failures must be explicit per store.

### Definition of Done
Accepted as done only when:
1. All enabled stores can complete a download run or emit explicit per-store stoplines.
2. Download validation is green for Jan–Feb required blocks.
3. Human action is limited to login/2FA/session refresh only.

### Validation / Gates
- `python3 scripts/playwright/download_kaspi_archive_webui.py --mode session-check --strict`
- `python3 scripts/validate_playwright_archive_downloads.py --run-id <RUN_ID> --strict`
- Playwright smoke tests
- session-state handling tests
- per-store manifest tests

### Rollback / Backout
- Delete failed download run outputs.
- Revoke stored session state if compromised.

### Stop-the-line criteria
- Any credential/session secret written into repo
- Any download run without immutable manifest
- Silent partial-store success

---

## Phase P5 — Future Observation Ledger (API observed_at + WebUI snapshots)

### Goal (measurable)
Capture future status evolution between WebUI archive downloads without pretending API has historical status-change timestamps.

### Inputs
- current Kaspi API sync engine
- WebUI status ledger contract
- order-entry enrichment paths
- API status detection logic

### Outputs
- `scripts/capture_order_status_observations.py`
- `scripts/validate_order_status_audit_history.py`
- new DB table / migration:
  - `fact_order_status_observations`
- `exports/validation/webui_archive_single_truth/2026-03-06/order_status_audit_report.json`

### Required rules
- Each observation stores:
  - `order_id`
  - `store_code`
  - `status_internal`
  - `observed_at`
  - `source` (`API` / `WEBUI`)
- API observations are provisional/current-state observations only.
- WebUI status ledger remains primary historical status source after cutover.
- Order-entry enrichment remains optional and must not break core sync.

### Definition of Done
Accepted as done only when:
1. Future observed-state audit history exists and is queryable.
2. API observations never overwrite WebUI historical status dates.
3. Core API sync remains strict even if optional enrichment is degraded.

### Validation / Gates
- `python3 scripts/validate_order_status_audit_history.py --as-of <AS_OF> --strict`
- migration tests
- observation idempotency tests
- source precedence tests

### Rollback / Backout
- DB backup before migration/apply.
- Drop/revert new table only through migration rollback.

### Stop-the-line criteria
- API observed timestamps replacing WebUI historical dates
- Core sync blocked by optional enrichment failure
- Any write without backup + env gate + `--apply`

---

## Phase P6 — Ads + COGS Rebase onto Archive Truth

### Goal (measurable)
Re-run ads offer-universe coverage, ads spend realism, COGS completeness, and COGS realism on the promoted WebUI-based truth candidate rather than the current chronology.

### Inputs
- WebUI truth candidate
- current ads sidecar
- current COGS validators and forensic comparison
- SKU/weight master data

### Outputs
- updated:
  - `scripts/validate_ads_offer_universe_coverage.py`
  - `scripts/validate_ads_spend_reality.py`
  - `scripts/validate_cogs_completeness_by_month.py`
  - `scripts/validate_cogs_realism_vs_forensic.py`
- `exports/validation/webui_archive_single_truth/2026-03-06/ads_offer_universe_report.json`
- `exports/validation/webui_archive_single_truth/2026-03-06/ads_spend_reality_report.json`
- `exports/validation/webui_archive_single_truth/2026-03-06/cogs_completeness_report.json`
- `exports/validation/webui_archive_single_truth/2026-03-06/cogs_realism_report.json`

### Definition of Done
Accepted as done only when:
1. Ads coverage and spend realism are green on the WebUI-based truth source.
2. COGS completeness and realism are green on the WebUI-based truth source.
3. Any remaining red economics gate keeps owner publication locked.

### Validation / Gates
- `python3 scripts/validate_ads_offer_universe_coverage.py --start 2026-01-01 --end 2026-02-29 --truth-source webui_archive --strict`
- `python3 scripts/validate_ads_spend_reality.py --start 2026-01-01 --end 2026-02-29 --truth-source webui_archive --strict`
- `python3 scripts/validate_cogs_completeness_by_month.py --start 2026-01-01 --end 2026-02-29 --truth-source webui_archive --strict`
- `python3 scripts/validate_cogs_realism_vs_forensic.py --start 2026-01-01 --end 2026-02-29 --truth-source webui_archive --strict`

### Rollback / Backout
- Read-only unless a later mapping/identity repair is applied.

### Stop-the-line criteria
- Publishing profit while any economics gate is red
- Treating partial ads as full
- Treating completeness PASS as realism PASS

---

## Phase P7 — North Star Owner Publication Cutover

### Goal (measurable)
Cut owner publication from current chronology to WebUI-based truth only after all Jan–Feb truth and economics gates are green.

### Inputs
- P0–P6 green artifacts
- `scripts/build_north_star_owner_review.py`
- `scripts/build_owner_pnl_report.py`
- `scripts/system_doctor.py`

### Outputs
- updated:
  - `scripts/build_north_star_owner_review.py`
  - `scripts/build_owner_pnl_report.py` (only if source contract changes for owner publication)
  - `scripts/system_doctor.py`
- `exports/north_star_owner_review/<AS_OF>/...`
- `exports/owner_pnl/<AS_OF>/...`
- `exports/validation/webui_archive_single_truth/<AS_OF>/publication_cutover_report.md`

### Definition of Done
Accepted as done only when:
1. North Star owner review strict is green on WebUI source.
2. Any locked month still shows `N/A` + `locked_reason`.
3. Current legacy owner/report surfaces are clearly labeled shadow/diagnostic until superseded.

### Validation / Gates
- `python3 scripts/build_north_star_owner_review.py --as-of <AS_OF> --truth-source webui_archive --strict`
- `python3 scripts/build_owner_pnl_report.py --as-of <AS_OF> --truth-source webui_archive --strict`
- `python3 scripts/system_doctor.py --strict --project-root . --as-of <AS_OF>`

### Rollback / Backout
- Revert cutover commit.
- Restore pre-cutover DB backup if any source-promotion write occurred.
- Re-enable prior owner-truth source path.

### Stop-the-line criteria
- Unlocking owner publication while governance is red
- Cutover without before/after comparison artifacts
- Removing legacy shadow path before cutover is proven

---

## Phase P8 — Daily Automation + Full-History Replay + Promotion

### Goal (measurable)
Operationalize daily archive truth capture and then replay the full history only after Jan–Feb is green.

### Inputs
- Playwright downloader
- WebUI truth pack/ledger builder
- owner-truth daily runner
- promotion/runbook contracts

### Outputs
- updated:
  - `scripts/run_owner_truth_daily.py`
  - `scripts/triage_owner_truth_stoplines.py`
- `exports/daily/<AS_OF>/owner_truth_summary.json`
- `exports/validation/webui_archive_single_truth/full_history_<RUN_ID>/...`
- `docs/OPS_ROLLOUT_EVIDENCE_WEBUI_ARCHIVE_SINGLE_TRUTH_2026-03-XX.md`
- new Oracle pack

### Definition of Done
Accepted as done only when:
1. One daily command can run source-refresh -> ledger-build -> gates -> owner outputs.
2. Full-history replay is deterministic.
3. Promotion evidence references exact commit SHA, commands, manifests, and rollback.

### Validation / Gates
- `python3 scripts/run_owner_truth_daily.py --as-of <AS_OF> --strict`
- `python3 scripts/triage_owner_truth_stoplines.py --as-of <AS_OF> --strict`
- full-history replay command(s)
- complete strict gate chain
- promotion evidence check

### Rollback / Backout
- Revert promotion commit
- Restore DB backup if any historical apply step occurred
- Restore previous scheduler config/session state if automation rollout fails

### Stop-the-line criteria
- Promotion without evidence
- Full-history replay before Jan–Feb green
- Any automation path that hides a failed prerequisite

---

## If attachments are missing — assumptions policy
- Default repo root is repo-relative.
- Default downloads root is provided at runtime, not hardcoded in active docs.
- If required WebUI archive packs or CRM workbook are missing:
  - fail strict mode,
  - emit a missing-input manifest,
  - do not continue with placeholder data.
- If filenames differ but contents are clearly the same:
  - record the substituted path + SHA256 in the manifest,
  - continue only when traceability is explicit.
- If WebUI schema drifts:
  - fail closed with a schema mismatch report.
- If current HEAD differs from the assumed baseline:
  - record actual branch + SHA in READCHECK and treat that as authoritative.