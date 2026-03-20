# PLAN_OWNER_TRUTH_UNIVERSAL_STOPLINE_CLEARANCE_2026-03-10

## Purpose
Clear the last proven live operational stopline on top of the already-cleared truth baseline for `codex/TASK-webui-owner-truth-operationalization-v1`, then convert the branch from blocked evidence into merge-ready live-proof evidence.

This plan supersedes only the still-open part of `docs/PLAN_OWNER_TRUTH_LIVE_OPS_CLEARANCE_2026-03-09.md`.
Already completed and not to be reopened here:
- L0 state freeze/checkpoint
- L1 blocker classification
- L2 daily artifact contract closure

Execution model:
- single-agent
- sequential
- fail-closed
- one worktree / branch only
- no multi-worktree parallelism
- human only for secrets/login refresh if and only if `UNIVERSAL` proves to be auth-gated

Baseline assumptions:
- active repo/worktree: `~/Docs/wt_webui_owner_truth_operationalization_v1`
- active branch: `codex/TASK-webui-owner-truth-operationalization-v1`
- preferred current head: `25b5c1425e7b4a8164b29104362690b4fddbbef7`
- fallback proved head if READCHECK disproves preferred head: `551e2ce7278d55de398af76273c7ab244a4a8078`
- baseline release commit: `86ce447782a005c47ac3d1b61dde8414900320a8`
- rollback anchor: `exports/validation/owner_truth_release/2026-03-04/full_gates_green_final.md`
- no new commit IDs were provided for the latest live-ops-clearance pass; treat the current delta as worktree-local until READCHECK proves otherwise
- no new WebUI scrape
- no source remediation
- no replay-only fallback in live mode
- no new truth-side DB write unless a new truth defect is separately proven

Evidence root for this phase:
- `exports/validation/owner_truth_universal_stopline_clearance/2026-03-10/`

Global non-negotiables:
1. Live mode must not consume replay-only artifacts.
2. `daily_ops_report.json` must never be copied/fabricated manually.
3. Do not change `scripts/run_owner_truth_daily.py` / `scripts/generate_daily_ops_report.py` / `scripts/validate_daily_ops_report.py` unless new evidence proves the current contract is wrong.
4. Prefer canonical operational workflow commands over new helper scripts.
5. No order-state API write commands unless read-only evidence proves they are required and they are already canonical repo entrypoints.
6. No DB write in this plan unless execution halts and a separate write-gated plan is opened.
7. Do not claim completion unless all listed gates are green.

---

## Phase U0 — Freeze Current Delta

### Goal (measurable)
Preserve the current good L1/L2 delta before any additional work.

### Inputs
- current worktree state
- `docs/PLAN_OWNER_TRUTH_LIVE_OPS_CLEARANCE_2026-03-09.md`
- `exports/validation/owner_truth_live_ops_clearance/2026-03-09/root_cause/store_blockers.json`
- `exports/validation/owner_truth_live_ops_clearance/2026-03-09/daily_artifact_contract_report.json`
- `exports/validation/owner_truth_release/2026-03-04/full_gates_green_final.md`

### Outputs
- `exports/validation/owner_truth_universal_stopline_clearance/2026-03-10/readcheck.md`
- `exports/validation/owner_truth_universal_stopline_clearance/2026-03-10/worktree_status.txt`
- `exports/validation/owner_truth_universal_stopline_clearance/2026-03-10/assumptions.md`
- `exports/validation/owner_truth_universal_stopline_clearance/2026-03-10/checkpoint_decision.md`
- one of:
  - narrow checkpoint commit SHA recorded in `checkpoint_decision.md`, or
  - `exports/validation/owner_truth_universal_stopline_clearance/2026-03-10/worktree_checkpoint.patch`

### Definition of Done
Accepted as done only when:
- exact branch and exact head are recorded
- dirty/clean state is recorded
- rollback anchor is recorded
- the current delta is preserved by commit or patch artifact

### Validation / Gates
- `git rev-parse --abbrev-ref HEAD`
- `git rev-parse HEAD`
- `git status --short`
- `bash scripts/check_no_db_tracked.sh`
- `bash scripts/lint_docs.sh`

### Rollback / backout strategy
- revert/drop only U0 artifacts or reset to the checkpoint commit
- no code changes and no DB writes in U0

### Stop-the-line criteria
- unexplained head mismatch vs `25b5...` / `551e2...`
- missing rollback anchor
- tracked/staged `.db` file appears

---

## Phase U1 — UNIVERSAL Stopline Operational Closure

### Goal (measurable)
Clear the last live operational blocker for `UNIVERSAL`, or prove with explicit evidence that it remains an external operational blocker outside repo-code scope.

### Inputs
- `scripts/run_kaspi_daily_ops.py`
- `scripts/preflight_shipment.py`
- `scripts/report_waybill_status.py`
- `docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md`
- `exports/validation/owner_truth_live_ops_clearance/2026-03-09/root_cause/root_cause_decision.md`
- exact order IDs: `849656111`, `850084962`
- current anchors / `.env` / store tokens

### Outputs
- `exports/validation/owner_truth_universal_stopline_clearance/2026-03-10/universal/waybill_status_before.txt`
- `exports/validation/owner_truth_universal_stopline_clearance/2026-03-10/universal/operational_transcript.md`
- `exports/validation/owner_truth_universal_stopline_clearance/2026-03-10/universal/remediation_decision.md`
- `exports/validation/owner_truth_universal_stopline_clearance/2026-03-10/universal/waybill_status_after.txt`
- `exports/validation/owner_truth_universal_stopline_clearance/2026-03-10/universal/universal_blocker.json`
- `exports/validation/owner_truth_universal_stopline_clearance/2026-03-10/universal/universal_blocker.md`

### Definition of Done
Accepted as done only when one of the following is true:
1. `UNIVERSAL` goes green and both `849656111` and `850084962` disappear from the strict-stopline missing set, or
2. a blocker pack proves that existing canonical operational workflow cannot clear them without external actions outside repo scope.

Additional rule:
- if outcome (2) happens, later green phases do not start; branch remains blocked evidence.

### Validation / Gates
Required reproduction commands:
- `python3 scripts/preflight_shipment.py --project-root . --as-of 2026-03-09`
- `python3 scripts/report_waybill_status.py --date 2026-03-09 --since-days 3 --store UNIVERSAL --include-overdue --strict-stopline`

If code is touched, also run:
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_run_kaspi_daily_ops_contract.py tests/test_live_daily_ops_store_blockers.py tests/test_shipment_preflight.py tests/test_daily_ops_report_contract.py`

### Rollback / backout strategy
- if only read-only operational verification was performed: revert docs/tests only
- if canonical local file-generation steps were run: remove regenerated local artifacts and preserve before/after transcripts
- do not auto-attempt compensating writes

### Stop-the-line criteria
- any replay artifact introduced into live mode
- any new helper script added before proving existing workflow is insufficient
- any order-state API write attempted without explicit evidence that it is necessary and canonical
- any attempt to suppress `UNIVERSAL` failure via `--allow-store-failure`

---

## Phase U2 — Execution-Layer Closure

### Goal (measurable)
Ensure `system_doctor.py` no longer fails at `build_daily_ops_timings` once live daily ops is green; if it still fails, isolate and fix that defect narrowly.

### Inputs
- `scripts/system_doctor.py`
- `scripts/build_daily_ops_timings.py`
- `scripts/validate_daily_ops_timing_artifact.py`
- U1 outputs
- `exports/daily/2026-03-09/daily_ops_report.json`
- `exports/validation/board_v8_runtime/2026-03-09/daily_ops_summary.json`

### Outputs
- `exports/validation/owner_truth_universal_stopline_clearance/2026-03-10/execution/execution_layer_decision.md`
- `exports/validation/owner_truth_universal_stopline_clearance/2026-03-10/execution/build_daily_ops_timings_before.txt`
- `exports/validation/owner_truth_universal_stopline_clearance/2026-03-10/execution/build_daily_ops_timings_after.txt`
- if code changes are required:
  - updated `scripts/build_daily_ops_timings.py`
  - updated `scripts/validate_daily_ops_timing_artifact.py`
  - `tests/test_build_daily_ops_timings_contract.py`

### Definition of Done
Accepted as done only when:
- either `build_daily_ops_timings` passes without code change after U1 green, or
- one narrow execution-layer defect is fixed with tests and verified green

### Validation / Gates
- `python3 scripts/build_daily_ops_timings.py --strict --as-of 2026-03-09 --project-root . --output-root exports/perf`
- `python3 scripts/validate_daily_ops_timing_artifact.py exports/perf/2026-03-09/daily_ops_timings.json --strict`
- if code touched:
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_system_doctor_contract.py tests/test_build_daily_ops_timings_contract.py`

### Rollback / backout strategy
- revert narrow execution-layer code/tests/docs only
- preserve U1 evidence unchanged

### Stop-the-line criteria
- execution-layer fix widens tolerances or reinterprets red daily ops as green
- unrelated runtime/truth/governance logic is changed

---

## Phase U3 — Full Live Green Proving

### Goal (measurable)
Convert current blocked evidence into fully green live evidence for `2026-03-09`.

### Inputs
- U1 and U2 outputs
- `scripts/run_owner_truth_daily.py`
- `scripts/system_doctor.py`
- `scripts/ops_status.py`
- existing anchors/bootstrap state

### Outputs
- `exports/validation/owner_truth_universal_stopline_clearance/2026-03-10/live_green/live_run_summary.json`
- `exports/validation/owner_truth_universal_stopline_clearance/2026-03-10/live_green/live_run_transcript.md`
- `exports/validation/owner_truth_universal_stopline_clearance/2026-03-10/live_green/live_idempotence_report.json`
- `exports/validation/owner_truth_universal_stopline_clearance/2026-03-10/live_green/system_doctor_after_green.json`
- `exports/validation/owner_truth_universal_stopline_clearance/2026-03-10/live_green/system_doctor_after_green.md`
- `docs/OPS_ROLLOUT_EVIDENCE_OWNER_TRUTH_LIVE_GREEN_2026-03-10.md`

### Definition of Done
Accepted as done only when:
- `./.venv/bin/python scripts/run_owner_truth_daily.py --mode live --as-of 2026-03-09 --strict` exits `0`
- `./.venv/bin/python scripts/system_doctor.py --strict --project-root . --as-of 2026-03-09` is `GREEN`
- second rerun is semantically identical except approved volatile fields
- no new truth blocker appears

### Validation / Gates
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
- revert U2/U3 code only if green proof regresses
- if any unexpected write path appeared, stop and restore latest DB backup before any further attempt

### Stop-the-line criteria
- one green live run followed by a red rerun
- hidden manual artifact dependency between reruns
- any new truth drift requiring write-side repair

---

## Phase U4 — Merge / Release / Oracle Refresh

### Goal (measurable)
Publish merge-ready release/evidence only after U3 is fully green.

### Inputs
- U3 live-green evidence
- current merge manifest
- release anchor
- Oracle pack structure

### Outputs
- `exports/validation/owner_truth_operationalization/2026-03-09/merge_manifest.json`
- `exports/validation/owner_truth_operationalization/2026-03-09/merge_manifest.md`
- `exports/validation/owner_truth_release/2026-03-09/full_gates_green_live_ops.md`
- `Oracle_listings/packs/owner_truth_live_green_2026-03-09/PACK_SUMMARY.md`
- `Oracle_listings/packs/owner_truth_live_green_2026-03-09/bundle.md`
- `Oracle_listings/packs/owner_truth_live_green_2026-03-09/oracle_files_manifest.txt`
- `Oracle_listings/packs/owner_truth_live_green_2026-03-09/ArchiveSales_ALL_STORES_statusdate_mapped.csv`

### Definition of Done
Accepted as done only when:
- merge manifest status is `GREEN`
- exact commit(s), commands, rollback, and scope-out are documented
- Oracle pack contains `ArchiveSales_ALL_STORES_statusdate_mapped.csv`
- Oracle pack does not substitute `ArchiveOrders_WEBUI_MERGED_ALL_STORES.csv`

### Validation / Gates
- `bash scripts/lint_docs.sh`
- `bash scripts/check_no_db_tracked.sh`
- `python3 scripts/check_release_hygiene.py --strict --project-root .`
- manifest content checks for the Oracle pack

### Rollback / backout strategy
- revert U4 docs/manifest/pack refresh only
- preserve U3 live-green evidence

### Stop-the-line criteria
- merge manifest still says `DEFER`
- wrong CSV packed
- rollback mapping missing

---

## Phase U5 — Automation Hardening

### Goal (measurable)
Make future live stoplines immediately diagnosable without weakening fail-closed behavior.

### Inputs
- `docs/DAILY_SOP.md`
- `docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md`
- U1 blocker taxonomy
- U3 live-green evidence

### Outputs
- updated `docs/DAILY_SOP.md`
- updated `docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md`
- `exports/validation/owner_truth_universal_stopline_clearance/2026-03-10/automation_hardening_report.md`
- if code-level failure classification is added:
  - `tests/test_kaspi_daily_ops_failure_classification.py`

### Definition of Done
Accepted as done only when:
- docs point to exact blocker classes and remediation path
- docs stay consistent with live-vs-replay contract
- no fail-open behavior is introduced

### Validation / Gates
- `bash scripts/lint_docs.sh`
- `bash scripts/install_single_truth_ops_scheduler.sh --validate-only`
- relevant targeted pytest if code/tests changed

### Rollback / backout strategy
- revert U5 docs/tests/scripts only

### Stop-the-line criteria
- docs contradict runtime-mode or workflow contracts
- docs hide that live red is still a hard blocker

---

## Phase U6 — Deferred Scale Queue Lock

### Goal (measurable)
Keep scale work visible but out of this merge.

### Inputs
- current operationalization backlog
- merge manifest
- live-green evidence or blocker pack

### Outputs
- `exports/validation/owner_truth_universal_stopline_clearance/2026-03-10/deferred_scale_backlog.md`

### Definition of Done
Accepted as done only when:
- scale items are explicitly marked out-of-scope for this merge
- no WebUI source work enters this branch
- no unrelated docs-plan or archive-cleanup work enters this branch

### Validation / Gates
- `bash scripts/lint_docs.sh`

### Rollback / backout strategy
- revert U6 backlog doc only

### Stop-the-line criteria
- source remediation re-enters scope
- parallel worktrees are introduced without necessity

---

## If attachments are missing — assumptions policy

- If no new commit IDs exist for the live-ops-clearance pass, treat it as worktree-local on top of `25b5c1425e7b4a8164b29104362690b4fddbbef7`.
- If `25b5...` is not available locally, fail closed to `551e2ce7278d55de398af76273c7ab244a4a8078` and record that fallback in `readcheck.md`.
- If the exact `UNIVERSAL` missing IDs are absent from local evidence, use the last attached blocker artifacts (`849656111`, `850084962`) as the authoritative target set and do not widen scope.
- If `UNIVERSAL` cannot be cleared because of external live operational state, emit blocker artifacts and do not claim green.
- If any new truth defect appears, stop this plan and create a separate write-gated follow-up before any DB write is attempted.