# PLAN_OWNER_TRUTH_FULL_RANGE_GATE_AND_OWNER_OUTPUTS_2026-03-12

## Purpose
Clear the current live owner-truth blockers using the real latest blocked-state model, then reconnect the work to visible business value by stabilizing owner-facing outputs in this order:

1. Owner Profit Daily
2. Cash Risk Daily
3. PO / SKU Daily

This plan replaces stale blocker sequencing that focused on:
- ads freshness as the active live blocker,
- ACMEWEAR `832677455`,
- and `validate_recent_identity_coverage` drift.

The current active blocker set is different and narrower:
- full-range WebUI-vs-current-DB hard gate
- direct doctor/runtime-log parity blocker

Execution model:
- single-agent
- sequential
- fail-closed
- one worktree / branch only
- human only for login/secret refresh if explicitly proven necessary

Baseline assumptions:
- active repo/worktree: `~/Docs/wt_webui_owner_truth_operationalization_v1`
- active branch: `codex/TASK-webui-owner-truth-operationalization-v1`
- preferred head: `25b5c1425e7b4a8164b29104362690b4fddbbef7`
- fallback head if READCHECK disproves preferred head: `551e2ce7278d55de398af76273c7ab244a4a8078`
- baseline release commit: `86ce447782a005c47ac3d1b61dde8414900320a8`
- rollback anchor: `exports/validation/owner_truth_release/2026-03-04/full_gates_green_final.md`
- no new commit IDs were created in the latest blocked-state pass; treat the current delta as worktree-local until READCHECK proves otherwise
- no new WebUI scrape
- no replay fallback in live mode
- no DB write unless a read-first case file proves it is required and a write-gated repair phase is opened

Evidence root:
- `exports/validation/owner_truth_full_range_gate_recovery/2026-03-12/`

Global non-negotiables:
1. Do not proceed from stale blocker narratives.
2. `daily_ops_report.json` and `kaspi_import_stdout.log` must never be fabricated manually.
3. Do not touch owner outputs until the live proving chain is green.
4. Do not widen tolerances or quarantine away post-cutover hard-missing orders.
5. No DB write without backup + env gate + `--apply` + before/after diffs + rollback note.
6. Do not claim completion unless all listed gates are green.

---

## Phase B0 — Current-State Checkpoint + Freeze

### Goal (measurable)
Freeze the exact current state and prove the branch really matches the latest blocked-state model.

### Inputs
- current worktree state
- `docs/PLAN_OWNER_TRUTH_ADS_FRESHNESS_AND_OWNER_OUTPUTS_2026-03-11.md`
- latest blocked-state evidence under `exports/validation/owner_truth_ads_freshness_recovery/2026-03-11/`
- rollback anchor `exports/validation/owner_truth_release/2026-03-04/full_gates_green_final.md`

### Outputs
- `exports/validation/owner_truth_full_range_gate_recovery/2026-03-12/readcheck.md`
- `exports/validation/owner_truth_full_range_gate_recovery/2026-03-12/worktree_status.txt`
- `exports/validation/owner_truth_full_range_gate_recovery/2026-03-12/assumptions.md`
- `exports/validation/owner_truth_full_range_gate_recovery/2026-03-12/state_reconciliation.md`
- `exports/validation/owner_truth_full_range_gate_recovery/2026-03-12/checkpoint_decision.md`
- one of:
  - checkpoint commit SHA recorded in `checkpoint_decision.md`
  - or `exports/validation/owner_truth_full_range_gate_recovery/2026-03-12/worktree_checkpoint.patch`

### Definition of Done
Accepted as done only when:
- exact branch and exact head are recorded
- dirty/clean state is recorded
- rollback anchor is recorded
- current blocker set is explicitly documented
- current delta is preserved by commit or patch

### Validation/Gates
- `git rev-parse --abbrev-ref HEAD`
- `git rev-parse HEAD`
- `git status --short`
- `bash scripts/check_no_db_tracked.sh`
- `bash scripts/lint_docs.sh`

### Rollback / backout strategy
- revert/drop B0 artifacts or reset to checkpoint commit
- no DB writes and no code changes in B0

### Stop-the-line criteria
- unexplained head mismatch
- blocker state no longer matches current blocked-state evidence and no new divergence packet is emitted
- tracked/staged `.db` file appears

---

## Phase B1 — Full-Range DB Gate Policy Decision

### Goal (measurable)
Define whether the full-range WebUI-vs-current-DB gate should:
- hard-fail on all historical drift, or
- treat pre-cutover historical drift as diagnostic while keeping post-cutover holes hard-blocking

### Inputs
- `scripts/validate_webui_archive_vs_current_db.py`
- current full-range blocked-state evidence
- chronology/workbook authority docs
- latest owner-truth blocked-state evidence

### Outputs
- `docs/validation/WEBUI_CURRENT_DB_FULL_RANGE_POLICY_CONTRACT.md`
- `exports/validation/owner_truth_full_range_gate_recovery/2026-03-12/full_range_policy_decision.md`
- if code/tests touched:
  - updated `scripts/validate_webui_archive_vs_current_db.py`
  - `tests/test_validate_webui_archive_vs_current_db_contract.py`

### Definition of Done
Accepted as done only when:
- the contract explicitly states what is hard-blocking vs diagnostic
- post-cutover missing orders remain hard-blocking
- pre-cutover/historical debt is not silently hidden; it is either still hard-blocking or explicitly diagnostic by contract

### Validation/Gates
- rerun full-range validator in strict mode against the current proving window
- if code changed:
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_validate_webui_archive_vs_current_db_contract.py`

### Rollback / backout strategy
- revert B1 docs/code/tests only
- no DB writes permitted in B1

### Stop-the-line criteria
- any tolerance widening
- any quarantine-only solution for post-cutover holes
- any contract wording that makes current publishable holes informational

---

## Phase B2 — Post-Cutover WebUI-vs-DB Repair

### Goal (measurable)
Repair only the clearly unacceptable post-cutover missing orders:
- `ACMEWEAR` `835039770` on `2026-02-28`
- `UNIVERSAL` `838588815` on `2026-03-01`

### Inputs
- B1 contract decision
- selected canonical repair path
- DB `db/app.db`
- ledger root `exports/order_status_ledger/webui_status_ledger_20260306_full_parse`

### Outputs
- `exports/validation/owner_truth_full_range_gate_recovery/2026-03-12/post_cutover/case_835039770_838588815.json`
- `exports/validation/owner_truth_full_range_gate_recovery/2026-03-12/post_cutover/case_835039770_838588815.md`
- `exports/validation/owner_truth_full_range_gate_recovery/2026-03-12/post_cutover/repair_decision.md`
- if a write is required:
  - `exports/validation/owner_truth_full_range_gate_recovery/2026-03-12/post_cutover/db_backup_path.txt`
  - `exports/validation/owner_truth_full_range_gate_recovery/2026-03-12/post_cutover/db_write_log.md`
  - `exports/validation/owner_truth_full_range_gate_recovery/2026-03-12/post_cutover/before_after_diffs/`
- refreshed strict report:
  - `exports/validation/owner_truth_full_range_gate_recovery/2026-03-12/post_cutover/webui_vs_db_report_after.json`

### Definition of Done
Accepted as done only when:
- both post-cutover missing orders are no longer hard-blocking
- if any write occurred, backup + env gate + `--apply` + before/after diffs + rollback note all exist
- no broad historical cleanup was mixed into this phase

### Validation/Gates
- rerun the chosen strict WebUI-vs-current-DB validator after repair
- rerun targeted contract tests if code changed
- `bash scripts/check_no_db_tracked.sh`

### Rollback / backout strategy
- if read-only fix: revert docs/code/tests only
- if write path used: restore DB from backup, invalidate downstream artifacts, rerun validator to confirm rollback

### Stop-the-line criteria
- any DB write without backup + env gate + `--apply`
- any expansion from 2 named post-cutover holes to broad historical cleanup without separate approval
- any replay fallback introduced to satisfy DB parity

---

## Phase B3 — Ops-Selection Parity Scope Closure

### Goal (measurable)
Resolve whether `validate_ops_selection_parity` belongs inside owner-truth doctor/live proving.

### Inputs
- `scripts/system_doctor.py`
- `scripts/validate_ops_selection_parity.py`
- daily-ops/scheduler contracts
- runtime log path behavior

### Outputs
- `docs/validation/OWNER_TRUTH_OPS_SELECTION_SCOPE_CONTRACT.md`
- `exports/validation/owner_truth_full_range_gate_recovery/2026-03-12/ops_selection/ops_selection_scope_decision.md`
- if code/tests changed:
  - updated `scripts/system_doctor.py`
  - updated `scripts/validate_ops_selection_parity.py` if needed
  - `tests/test_system_doctor_contract.py`
  - `tests/test_validate_ops_selection_parity_contract.py`

### Definition of Done
Accepted as done only when one of the following is true:
1. owner-truth proving now legitimately generates the required canonical import log and parity passes, or
2. ops-selection parity is moved out of owner-truth doctor because owner-truth does not own canonical import scheduling.

### Validation/Gates
- `./.venv/bin/python scripts/system_doctor.py --strict --project-root . --as-of 2026-03-09`
- if code changed:
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_system_doctor_contract.py tests/test_validate_ops_selection_parity_contract.py`

### Rollback / backout strategy
- revert B3 code/docs/tests only
- no DB writes permitted in B3

### Stop-the-line criteria
- log fabrication
- governance downgrade from hard-block to informational without explicit contract
- changing unrelated doctor checks in the same phase

---

## Phase B4 — Full Live Green Proving

### Goal (measurable)
Convert the branch from blocked evidence into fully green live evidence for `2026-03-09`.

### Inputs
- B2 and B3 outputs
- `scripts/run_owner_truth_daily.py`
- `scripts/system_doctor.py`
- `scripts/ops_status.py`

### Outputs
- `exports/validation/owner_truth_full_range_gate_recovery/2026-03-12/live_green/live_run_summary.json`
- `exports/validation/owner_truth_full_range_gate_recovery/2026-03-12/live_green/live_run_transcript.md`
- `exports/validation/owner_truth_full_range_gate_recovery/2026-03-12/live_green/live_idempotence_report.json`
- `exports/validation/owner_truth_full_range_gate_recovery/2026-03-12/live_green/system_health.json`
- `exports/validation/owner_truth_full_range_gate_recovery/2026-03-12/live_green/system_health.md`
- `docs/OPS_ROLLOUT_EVIDENCE_OWNER_TRUTH_LIVE_GREEN_2026-03-12.md`

### Definition of Done
Accepted as done only when:
- `./.venv/bin/python scripts/run_owner_truth_daily.py --mode live --as-of 2026-03-09 --strict` exits `0`
- `./.venv/bin/python scripts/system_doctor.py --strict --project-root . --as-of 2026-03-09` is `GREEN`
- second rerun is semantically identical except approved volatile fields
- no new blocker appears

### Validation/Gates
- `bash scripts/check_no_db_tracked.sh`
- `bash scripts/lint_docs.sh`
- `python3 scripts/check_release_hygiene.py --strict --project-root .`
- `bash scripts/install_single_truth_ops_scheduler.sh --validate-only`
- `python3 scripts/check_anchor_health.py --project-root .`
- `./.venv/bin/python scripts/ops_status.py --project-root .`
- `AB_CRM_WORKBOOK_PATH=config/anchors/SALES_KSP_CRM_LATEST.xlsx python3 scripts/validate_params.py --strict --as-of 2026-03-09`
- `./.venv/bin/python scripts/run_owner_truth_daily.py --mode live --as-of 2026-03-09 --strict`
- `./.venv/bin/python scripts/system_doctor.py --strict --project-root . --as-of 2026-03-09`

### Rollback / backout strategy
- revert B2/B3/B4 code only if green proof regresses
- if any unexpected write path appeared, stop and open a separate write-gated rollback step

### Stop-the-line criteria
- one green run followed by a red rerun
- hidden manual artifact dependency between reruns
- new truth/governance blocker appears without separate classification

---

## Phase O1 — Owner Profit Daily

### Goal (measurable)
Produce one trustworthy owner profit file for the proving date with a visible trust banner.

### Inputs
- B4 live-green chain
- current economics / ads / OPEX publication paths
- `OWNER_PROGRESS_SCORECARD_2026-03-11.md`

### Outputs
- `exports/owner/2026-03-09/owner_profit_daily.json`
- `exports/owner/2026-03-09/owner_profit_daily.md`
- `exports/validation/owner_profit_daily/2026-03-09/trust_report.json`

### Definition of Done
Accepted as done only when the file truthfully answers:
- revenue
- COGS
- ads
- OPEX
- profit
- confidence / trust banner

### Validation/Gates
- strict owner-truth chain still green
- economics/publication validators required by the chosen output
- docs lint if docs touched

### Rollback / backout strategy
- revert owner-output code/docs only
- do not weaken publication gates

### Stop-the-line criteria
- output exists but lacks trust/confidence state
- output is built from mixed/stale sources

---

## Phase O2 — Cash Risk Daily

### Goal (measurable)
Produce one trustworthy near-term cash-risk file from the stabilized truth chain.

### Inputs
- B4 green owner-truth chain
- cashflow truth contract and current cashflow engine entrypoints
- `OWNER_PROGRESS_SCORECARD_2026-03-11.md`

### Outputs
- `exports/owner/2026-03-09/cash_risk_daily.json`
- `exports/owner/2026-03-09/cash_risk_daily.md`
- `exports/validation/cash_risk_daily/2026-03-09/trust_report.json`

### Definition of Done
Accepted as done only when the file truthfully answers:
- current usable cash
- expected receipts
- expected commitments
- projected low-cash dates
- conservative cash floor

### Validation/Gates
- relevant cashflow validators
- strict owner-truth chain still green
- docs lint if docs touched

### Rollback / backout strategy
- revert cash-risk code/docs only

### Stop-the-line criteria
- output exists but is not trust-labeled
- output depends on unresolved owner-truth drift

---

## Phase O3 — PO / SKU Daily

### Goal (measurable)
Produce one trustworthy reorder/freeze/kill file from the stabilized truth chain.

### Inputs
- B4 green owner-truth chain
- PO / inventory contracts and validators
- `OWNER_PROGRESS_SCORECARD_2026-03-11.md`

### Outputs
- `exports/owner/2026-03-09/po_sku_daily.json`
- `exports/owner/2026-03-09/po_sku_daily.md`
- `exports/validation/po_sku_daily/2026-03-09/trust_report.json`

### Definition of Done
Accepted as done only when the file truthfully answers:
- reorder list
- freeze list
- kill list
- expected ROIC
- capital tied in stock / inbound / on-delivery

### Validation/Gates
- relevant PO/inventory validators
- strict owner-truth chain still green
- docs lint if docs touched

### Rollback / backout strategy
- revert PO/SKU code/docs only

### Stop-the-line criteria
- output is produced without trust banner
- formula drift is introduced instead of updating canonical docs first

---

## Phase R1 — Merge / Release / Oracle Refresh

### Goal (measurable)
Publish merge-ready release/evidence only after B4 and O1 are green.

### Inputs
- B4 live-green evidence
- O1 owner output
- current merge manifest
- Oracle pack structure

### Outputs
- `exports/validation/owner_truth_operationalization/2026-03-09/merge_manifest.json`
- `exports/validation/owner_truth_operationalization/2026-03-09/merge_manifest.md`
- `exports/validation/owner_truth_release/2026-03-09/full_gates_green_live_ops.md`
- `Oracle_listings/packs/owner_truth_live_green_2026-03-09/PACK_SUMMARY.md`
- `Oracle_listings/packs/owner_truth_live_green_2026-03-09/bundle.md`
- `Oracle_listings/packs/owner_truth_live_green_2026-03-09/oracle_files_manifest.txt`
- `Oracle_listings/packs/owner_truth_live_green_2026-03-09/ArchiveOrders_WEBUI_MERGED_ALL_STORES.csv`

### Definition of Done
Accepted as done only when:
- merge manifest status is `GREEN`
- exact commits, commands, rollback, and scope-out are documented
- Oracle pack contains the canonical full-range merged orders CSV required by the refreshed pack contract
- rollback mapping is explicit

### Validation/Gates
- `bash scripts/lint_docs.sh`
- `bash scripts/check_no_db_tracked.sh`
- `python3 scripts/check_release_hygiene.py --strict --project-root .`

### Rollback / backout strategy
- revert R1 docs/manifest/pack refresh only
- preserve B4/O1 evidence

### Stop-the-line criteria
- merge manifest still says `DEFER`
- wrong canonical CSV packed
- rollback mapping missing

---

## Phase S1 — Deferred Scale Queue Lock

### Goal (measurable)
Keep non-owner-output scale work visible but out of this merge.

### Inputs
- current operationalization backlog
- merge manifest
- owner output status

### Outputs
- `exports/validation/owner_truth_full_range_gate_recovery/2026-03-12/deferred_scale_backlog.md`

### Definition of Done
Accepted as done only when:
- scale items are explicitly marked out-of-scope
- no WebUI source work enters this branch
- no unrelated docs cleanup or broad architecture detours enter this branch

### Validation/Gates
- `bash scripts/lint_docs.sh`

### Rollback / backout strategy
- revert S1 backlog doc only

### Stop-the-line criteria
- source remediation re-enters scope
- parallel worktrees are introduced without necessity

---

## If attachments are missing — assumptions policy
- If older bundles conflict with the latest 2026-03-11 blocked-state docs, prefer the latest blocked-state docs and document the conflict in B0.
- If no new commit IDs exist for the latest pass, treat the pass as worktree-local on top of `25b5c1425e7b4a8164b29104362690b4fddbbef7`.
- If `25b5...` is not available locally, fail closed to `551e2ce7278d55de398af76273c7ab244a4a8078` and record that fallback in `readcheck.md`.
- If `validate_ops_selection_parity` cannot be satisfied because owner-truth proving does not own canonical import scheduling, emit a scope-closure artifact and stop rather than fabricating a log.
- If any DB write becomes necessary in B2, backup + env gate + `--apply` + before/after diffs + rollback note are mandatory before execution.
- If B4 cannot go fully green after B2/B3, emit a fresh blocker pack and do not claim merge readiness.