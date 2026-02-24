# docs/PLAN_BOARD_V7_DAILY_OPS_SPEED_PARITY_2026-02-23.md

## Purpose
Increase daily Kaspi ops throughput (fetch → append → assemble → waybill download → bundling) while preserving equal-or-better correctness.
This plan is fail-closed and evidence-first:
- No parity proof → not done.
- No gate replay evidence → not done.
- No explicit write gating → no writes.

Primary outcomes:
1) Measurable runtime improvement with reproducible stage timings.
2) Zero silent correctness regressions (order set, assemble success, PDF presence, bundle grouping).
3) Patch path for wrong `sku_key` / `kaspi_name_core` values (dry-run by default; apply requires explicit gate + backup).

## Global Constraints (Non-negotiable)
- Fail-closed: missing/invalid inputs => STOP.
- Single-truth: do not duplicate business math in UI; DB is operational truth; docs are formula truth.
- No apply writes unless explicitly enabled and logged:
  - must create backup first
  - must record `apply_with_env.md` + rollback proof

## Phases

### V7-T0 — Hotfix Promotion / Baseline Unification
**Goal (measurable)**
- Ensure `main` contains the post-V6 hotfix improvements (or prove it already does).
- Eliminate operator divergence between “hotfix branch behavior” and “main behavior”.

**Inputs**
- Branch (reported): `codex/TASK-import-speed-manual-calc`
- Commits (reported): `d1c84e7`, `ad5e067`, `7d72e1b`
- Files (reported): 
  - `scripts/export_api_orders.py`
  - `scripts/import_orders_to_crm.py`
  - `scripts/backfill_line61_kaspi_core.py`
  - `scripts/download_waybills_api.py`
  - `excel_ui/run_full_import.command`

**Outputs**
- If not already merged:
  - PR: hotfix -> main
  - Evidence: `exports/validation/hotfix_v7t0_<YYYY-MMDD>/full_gates_green_final.md`
  - Oracle pack created under: `<ORACLE_ROOT>/Autonomous_business/<YYYY-MM-DD>/...md`
- If already merged:
  - Evidence: `exports/validation/hotfix_v7t0_<YYYY-MMDD>/already_on_main_proof.md` (git log proof + gate replay)

**Definition of Done**
Accepted as done only when:
- Either (A) PR merged to main OR (B) proven already on main (commit reachability shown).
- Full gate chain is replayed and recorded (see “Validation/Gates”).

**Validation/Gates**
- `python3 scripts/validate_params.py --strict`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
- `python3 scripts/run_contract_suite.py --fixture small`
- `python3 scripts/validate_single_truth_system.py`
- `bash scripts/lint_docs.sh` (if any docs touched)
- `bash scripts/check_no_db_tracked.sh`
- `bash scripts/install_single_truth_ops_scheduler.sh --validate-only`
- `python3 scripts/check_anchor_health.py --project-root <REPO_PATH>`
- `python3 scripts/ops_status.py --project-root <REPO_PATH>`

**Rollback / Backout**
- `git revert -m 1 <merge_sha>`
- If any DB writes happened (should not), restore from `db/backups/app.db.pre_*`.

**Stop-the-line**
- Any gate fails.
- Any “apply” path executed without explicit gating + backup.

---

### V7-C1 — Daily Ops Parity Harness + Baseline Timings
**Goal (measurable)**
- Create deterministic tests that prove “baseline vs optimized” produce identical results for:
  1) selected order IDs
  2) assembled success/failure sets
  3) downloaded/existing PDF sets
  4) bundle grouping outputs (order IDs per bundle + counts)
- Produce stage timing artifacts (not as CI pass/fail; as evidence + regression visibility).

**Inputs**
- Orchestrator: `scripts/run_kaspi_daily_ops.py`
- Workflow docs: `docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md`, `docs/ops/KASPI_DAILY_OPS_ORCHESTRATOR_RUNBOOK.md`
- Core steps:
  - `scripts/export_api_orders.py`
  - `scripts/import_orders_to_crm.py`
  - `scripts/ship_orders_api.py` (or `scripts/ship_orders.py` depending on current entrypoint)
  - `scripts/download_waybills_api.py`
  - `scripts/build_waybills_from_crm.py` / `scripts/build_daily_waybills.py`

**Outputs**
- New script (benchmark harness):
  - `scripts/benchmark_kaspi_daily_ops.py`
    - emits `exports/validation/board_v7_<YYYY-MMDD>/V7-C1_PARITY/benchmark_timings.json`
    - emits `exports/validation/board_v7_<YYYY-MMDD>/V7-C1_PARITY/benchmark_timings.md`
- New tests (deterministic; mocks for API + Excel):
  - `tests/test_daily_ops_result_parity.py`
  - `tests/test_daily_ops_api_call_counts_baseline.py` (baseline counts)
  - `tests/test_daily_ops_timing_artifact_shape.py` (ensures timing artifact is produced & structured)

**Definition of Done**
Accepted as done only when:
- Parity test compares baseline vs optimized mode on the same fixture and passes.
- Benchmark harness runs locally and produces artifacts committed under `exports/validation/...`.
- Timing artifact includes per-stage durations for: fetch, append, assemble, download, bundle.

**Validation/Gates**
- Targeted:
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_daily_ops_result_parity.py`
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_daily_ops_api_call_counts_baseline.py`
- Full chain (same as V7-T0).

**Rollback**
- Revert commits.

**Stop-the-line**
- Parity mismatch.
- Tests rely on wall-clock thresholds in CI (must use call-count / structural assertions instead).

---

### V7-C2 — Parsing Correctness + sku_key/kaspi_name_core Patch Tools
**Goal (measurable)**
- Eliminate `sku_key` / `kaspi_name_core` mis-identification for new items.
- Provide a dry-run patch tool that identifies affected rows in DB + CRM exports, with an apply-gated remediation path.

**Inputs**
- Parser + mapping code (likely):
  - `core/parsers/kaspi_parser.py` (or current canonical parse module)
  - any SKU mapping tables used by import/append
- Backfill logic:
  - `scripts/backfill_line61_kaspi_core.py`
- Evidence of mismatch risk from recent runs (use fixture + reproduce mismatches).

**Outputs**
- Parser fixes + unit tests:
  - `tests/test_kaspi_parser_article_cleanup.py`
  - `tests/test_kaspi_name_core_mapping.py`
- Validator + patch tooling:
  - `scripts/validate_kaspi_parsing_integrity.py` (read-only)
  - `scripts/patch_kaspi_parsed_fields.py` (DRY-RUN default; `--apply` requires explicit gating + backup)
- If writes are supported:
  - Add `scripts/patch_kaspi_parsed_fields.py` to `config/write_side_gating_manifest.yaml`

**Definition of Done**
Accepted as done only when:
- New tests reproduce the prior bug and pass after fix (RED→GREEN evidenced).
- Validator can run on fixture and returns zero “hard anomalies”.
- Patch tool produces a deterministic report artifact:
  - `exports/validation/board_v7_<YYYY-MMDD>/V7-C2_PARSING/patch_dry_run_report.md`
- No apply writes executed unless explicitly requested.

**Validation/Gates**
- Targeted tests:
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_kaspi_parser_article_cleanup.py tests/test_kaspi_name_core_mapping.py`
- Re-run parity test from V7-C1.
- Full chain.

**Rollback**
- Revert commits.
- If apply is ever executed (only with explicit instruction):
  - restore DB from `db/backups/app.db.pre_patch_<timestamp>.sqlite`

**Stop-the-line**
- Any parser change not covered by tests.
- Any patch apply without backup + `apply_with_env.md` evidence.

---

### V7-H1 — API Efficiency: Selective Refetch + Single-Pass Assemble/Waybill
**Goal (measurable)**
- Reduce avoidable API calls without changing results:
  - No unconditional “detail refetch for every order”
  - No repeated “fetch pending” per store when the selection is already known
- Preserve assemble state-transition verification.

**Inputs**
- `scripts/export_api_orders.py`
- `scripts/ship_orders_api.py` / `core/integrations/kaspi_api_client.py`
- `scripts/download_waybills_api.py`
- Existing selection trace behavior:
  - `_waybill_selection_orders.json` (determinism)

**Outputs**
- Code changes implementing:
  1) selective refetch only when required fields missing
  2) single-pass selection + per-store subsetting
  3) cached selection reused across assemble + download steps
- Deterministic contract tests:
  - `tests/test_export_api_orders_refetch_policy.py`
  - `tests/test_ship_orders_single_pass_assemble.py`
  - `tests/test_waybill_download_uses_selection_trace.py`

**Definition of Done**
Accepted as done only when:
- New call-count tests prove fewer API calls (or at minimum: forbid the known wasteful patterns).
- Parity test remains green.
- Selection trace is present and stable (same IDs across stages).

**Validation/Gates**
- Targeted:
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_export_api_orders_refetch_policy.py tests/test_ship_orders_single_pass_assemble.py tests/test_waybill_download_uses_selection_trace.py`
- Full chain.

**Rollback**
- Revert commits.

**Stop-the-line**
- Any parity mismatch.
- Any assemble call treated as success without state-transition verification.

---

### V7-H2 — Excel Append Speed Hardening
**Goal (measurable)**
- Reduce Excel append runtime and AppleEvent timeouts while preserving workbook integrity.

**Inputs**
- `scripts/import_orders_to_crm.py`
- `excel_ui/run_full_import.command`
- Excel UI safety contract: `docs/inventory/Excel_UI_Contract_for_CRM_V1.md`

**Outputs**
- Safer/faster append strategy (batching writes; manual calc guard; minimal screen updates).
- Deterministic tests via mocking:
  - `tests/test_import_orders_to_crm_calc_mode_and_batching.py`
- Benchmark artifact:
  - `exports/validation/board_v7_<YYYY-MMDD>/V7-H2_EXCEL/append_benchmark.md`

**Definition of Done**
Accepted as done only when:
- Tests ensure Excel calc mode is set/restored and write batching is used.
- Benchmark artifacts show measurable improvement on the same dataset.
- No structural workbook changes outside approved ranges.

**Validation/Gates**
- Targeted test + parity test + full chain.

**Rollback**
- Revert commits.
- Restore workbook backups created by the script (must be logged in evidence).

**Stop-the-line**
- Any evidence of workbook corruption or sheet structure modification.
- Any Excel automation that removes fail-closed behavior (timeouts must STOP, not “continue”).

---

### V7-A1 — Workflow Mode Split: “today-fast” vs “catch-up”
**Goal (measurable)**
- Provide two explicit operational profiles with deterministic behavior:
  - **today-fast**: minimal lookback, no overdue, fastest safe runtime
  - **catch-up**: includes overdue, broader lookback

**Inputs**
- `scripts/run_kaspi_daily_ops.py`
- `docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md`
- `docs/DAILY_SOP.md`
- Selection logic inside `scripts/download_waybills_api.py`

**Outputs**
- CLI flags or env vars with contract tests:
  - `tests/test_daily_ops_profile_contract.py`
- Docs updates:
  - `docs/ops/KASPI_DAILY_OPS_ORCHESTRATOR_RUNBOOK.md`
  - `docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md`

**Definition of Done**
Accepted as done only when:
- Running the orchestrator in each profile produces a selection trace file and does not drift the intended selection policy.
- Docs + tests agree on defaults and schedule references.

**Validation/Gates**
- Targeted profile test + parity test + full chain.

**Rollback**
- Revert commits.

**Stop-the-line**
- Any “implicit” behavior based on hidden defaults (must be explicit and tested).

---

### V7-O1 — Observability: Timing Policy + Reporting
**Goal (measurable)**
- Make runtime improvements measurable and reviewable:
  - stage timing JSON emitted every run
  - a simple SLO policy doc that defines “what we measure” and “what we alert on”
- CI should not fail on wall-clock; use structural + call-count gates.

**Inputs**
- `scripts/run_kaspi_daily_ops.py`
- Drift pack policy hooks: `docs/ops/DRIFT_PACK_SLO_POLICY.md`

**Outputs**
- Doc: `docs/ops/DAILY_OPS_TIMING_SLO_POLICY.md`
- Validator: `scripts/validate_daily_ops_timing_artifact.py`
- Tests:
  - `tests/test_daily_ops_timing_artifact_shape.py` (if not already)

**Definition of Done**
Accepted as done only when:
- Timing artifacts are produced and validated.
- Evidence includes before/after comparison in `benchmark_timings.md`.

**Validation/Gates**
- Targeted + full chain.

**Rollback**
- Revert commits.

**Stop-the-line**
- Any attempt to make CI depend on fragile wall-clock thresholds.

---

### V7-S1 — Optional bounded concurrency (default OFF)
**Goal (measurable)**
- Add bounded concurrency to per-order detail fetch / waybill download where safe,
  without changing results and without rate-limit regressions.
- Default remains OFF (single-thread) until proven.

**Inputs**
- `core/integrations/kaspi_api_client.py`
- `scripts/export_api_orders.py`
- `scripts/download_waybills_api.py`

**Outputs**
- Feature-flagged concurrency:
  - env `KASPI_CONCURRENCY=1` default
- Tests:
  - `tests/test_kaspi_concurrency_flag_contract.py`
  - `tests/test_kaspi_rate_limit_backoff_mocked.py`

**Definition of Done**
Accepted as done only when:
- Flagged behavior is tested and defaults to OFF.
- Parity remains green in both modes on fixture.

**Validation/Gates**
- Targeted + parity + full chain.

**Rollback**
- Revert commits.

**Stop-the-line**
- Any concurrency enabled by default.
- Any uncontrolled retry loop.

---

### V7-PROMOTE — Promotion + Evidence
**Goal**
- Promote Board V7 with decision-grade evidence and rollback instructions.

**Outputs**
- Plan: `docs/PLAN_BOARD_V7_DAILY_OPS_SPEED_PARITY_2026-02-23.md`
- Evidence: `docs/OPS_ROLLOUT_EVIDENCE_BOARD_V7_DAILY_OPS_SPEED_PARITY_2026-02-23.md`
- Evidence directory:
  - `exports/validation/board_v7_<YYYY-MMDD>/full_gates_green_final.md`
  - Per-phase subfolders with `targeted_tests_{red,green}.md`
  - `benchmark_timings.{json,md}`
- Tracking updated:
  - `.claude/TASKS.md`, `.claude/PROGRESS.md`, `.claude/DECISIONS.md`, `.claude/ISSUES.md`, `.claude/SESSION_LOG.md`, `.claude/GOALS.md`
  - `claude/journal.md` (append-only)
- Oracle pack created (offline) including all touched files and evidence.

**Definition of Done**
Accepted as done only when:
- CI green on promotion PR (gates + headless-gates).
- Evidence paths exist and are referenced from the evidence doc.
- Rollback is explicit (git revert + DB restore path if applicable).

**Stop-the-line**
- Any missing evidence artifact.
- Any claim of “speed improvement” without benchmark artifacts + parity proof.

## If attachments are missing — assumptions policy
- If any referenced file/contract is missing in the repo:
  1) STOP and create a minimal stub doc (title + purpose + links to canonical source).
  2) Commit the stub and record in `.claude/SESSION_LOG.md`.
- If any conflict between docs and code:
  - Docs win; update owning doc first, then code.
- If “already merged vs not merged” is unclear:
  - Treat as NOT merged until proven by `git` reachability evidence recorded in `exports/validation/...`.
