Biggest unknowns (state assumptions; no questions)

Assumption: origin/main includes PR #21 and the V7 evidence path exists as documented (exports/validation/board_v7_2026-0225/full_gates_green_final.md). 
Assumption: fact_sales_v16 mapping gaps are still non‑zero; V8 should treat them as a correctness stop‑line until explicitly driven to zero with evidence. 
Assumption: Excel workbook size/performance remains a meaningful bottleneck at scale; optimizations must be measured with stage timings and parity gates (not opinions).

ASCII Roadmap Tree (Next Phases)

V8: Daily Ops Autopilot + Sales Truth Closure [Coding Agent] {V8 full gates + daily_report validator PASS}
|
+-- V8-T0: Plan authority + baseline replay [Coding Agent] {tests/test_board_v8_docs_contract.py PASS}
|
+-- V8-C1: fact_sales_v16 mapping gaps -> 0 (strict) [Coding Agent] {build_fact_sales_v16_from_api.py --strict PASS, gaps.json empty}
|
+-- V8-C2: CRM identity repair canary (sku_key/kaspi_name_core) [Coding Agent] {patch tool: DRY-RUN default, apply gated + backup proof}
|
+-- V8-H1: Speed scale w/ checkpointing + cache (opt-in) [Coding Agent] {parity tests PASS + benchmark_timings.json valid}
|
+-- V8-O1: Daily “green/red” decision report artifact [Coding Agent] {python3 scripts/validate_daily_ops_report.py --strict PASS}
|
+-- V8-A1: Scheduler hook for daily report (read-only) [Coding Agent] {plist + contract tests PASS; pinned .venv python}
|
+-- V8-S1: Multi-store resilience (partial outputs, non-zero on any red) [Coding Agent] {tests/test_multi_store_resilience_contract.py PASS}
|
`-- V8-PROMOTE: Evidence + oracle pack + merge [Coding Agent] {CI: gates + headless-gates PASS; evidence doc stamped}.

# docs/PLAN_BOARD_V8_DAILY_OPS_AUTOPILOT_TRUTH_SCALE_2026-02-24.md

## Purpose
Execute the fastest safe next scale step after Board V7 by:
1) closing remaining correctness blockers (fact_sales_v16 mapping gaps; CRM identity mis-IDs),
2) producing a single decision-grade “daily ops green/red” report artifact,
3) wiring a read-only scheduler hook that generates the report autonomously,
while preserving fail-closed behavior and minimizing human time (0–5%).

This board is **sequential, single-agent**, one branch/worktree, one promotion PR (plus optional post-merge stamp).

## Reliability stance
- **Fail-closed**: any ambiguity must stop the line.
- **No writes by default**: any DB or workbook mutation requires explicit env gate + `--apply` + backup + recorded evidence.
- Single-truth: DB is the system of record; Excel/CRM workbook is UI/ops output and must be treated as derived.

## Inputs (authorities / systems)
- Repo: `~/Docs/Autonomous_business`
- Canonical ops schedule authority:
  - `docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md` (import 11:00 + 16:03; waybill deadline 18:30)
- Existing V6/V7 building blocks:
  - `scripts/run_kaspi_daily_ops.py`, `core/stores/roster.py`
  - `scripts/build_fact_sales_v16_from_api.py` (strict mapping-gap output)
  - `scripts/validate_kaspi_parsing_integrity.py`, `scripts/patch_kaspi_parsed_fields.py`
  - Benchmark artifacts approach from V7 (`benchmark_timings.json`)
- Existing global gates (required chain):
  - `python3 scripts/validate_params.py --strict`
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
  - `python3 scripts/run_contract_suite.py --fixture small`
  - `python3 scripts/validate_single_truth_system.py`
  - `bash scripts/lint_docs.sh`
  - `bash scripts/check_no_db_tracked.sh`
  - `bash scripts/install_single_truth_ops_scheduler.sh --validate-only`
  - `python3 scripts/check_anchor_health.py --project-root <REPO_PATH>`
  - `python3 scripts/ops_status.py --project-root <REPO_PATH>`

## Outputs (board-wide)
- Plan doc (this file)
- Evidence doc: `docs/OPS_ROLLOUT_EVIDENCE_BOARD_V8_DAILY_OPS_AUTOPILOT_TRUTH_SCALE_2026-02-24.md`
- Evidence root: `exports/validation/board_v8_<YYYY-MM-DD>/`
- Final gate artifact: `exports/validation/board_v8_<YYYY-MM-DD>/full_gates_green_final.md`

---

## Phase List

### V8-T0 — Plan Authority + Baseline Replay
**Goal (measurable)**
- Establish board authority + fail-first docs contract.
- Produce RED→GREEN evidence proving the board docs are required for promotion.

**Inputs**
- `docs/ops/PROMOTION_MINIMUM_STANDARD.md`
- Prior board doc patterns (V6/V7)

**Outputs**
- `docs/OPS_ROLLOUT_EVIDENCE_BOARD_V8_DAILY_OPS_AUTOPILOT_TRUTH_SCALE_2026-02-24.md`
- `tests/test_board_v8_docs_contract.py`
- Evidence:
  - `exports/validation/board_v8_<YYYY-MM-DD>/V8-T0_PLAN_AUTHORITY/targeted_tests_red.md`
  - `exports/validation/board_v8_<YYYY-MM-DD>/V8-T0_PLAN_AUTHORITY/targeted_tests_green.md`

**Definition of Done**
- Accepted as done only when:
  - `tests/test_board_v8_docs_contract.py` fails before docs exist (RED evidence captured),
  - then passes after docs exist and contain required sections (GREEN evidence captured),
  - docs lint PASS.

**Validation/Gates**
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_board_v8_docs_contract.py`
- `bash scripts/lint_docs.sh`

**Rollback / backout**
- `git revert` the docs/test commit(s).

**Stop-the-line**
- Any placeholders (`TODO`, `TBD`, “fill later”) in the board plan/evidence docs.
- Any mismatch with `docs/ops/PROMOTION_MINIMUM_STANDARD.md` requirements.

---

### V8-C1 — Close fact_sales_v16 Mapping Gaps to Zero (Strict)
**Goal (measurable)**
- Drive `fact_sales_v16` mapping gaps to **0** under strict mode, producing an empty gaps JSON.
- Make “missing mappings > 0” an unambiguous stop-line in both CI (fixtures) and ops (runtime report).

**Inputs**
- `scripts/build_fact_sales_v16_from_api.py`
- Existing gap output conventions (V6 evidence: `fact_sales_v16_gaps.json`)

**Outputs**
- New/updated scripts (exact names are contract):
  - `scripts/report_fact_sales_v16_gaps.py` (reads builder output; writes Markdown/JSON summary)
  - Optional (if mapping updates require a controlled import):
    - `scripts/apply_fact_sales_v16_mappings.py` (DRY-RUN default; gated apply)
- New/updated tests:
  - `tests/test_fact_sales_v16_mapping_gap_stopline.py`
  - `tests/test_fact_sales_v16_mapping_apply_gating.py` (if apply script is introduced)
- Evidence:
  - `exports/validation/board_v8_<YYYY-MM-DD>/V8-C1_FACT_SALES_MAPPINGS/gaps_before.json`
  - `exports/validation/board_v8_<YYYY-MM-DD>/V8-C1_FACT_SALES_MAPPINGS/gaps_after.json`
  - `exports/validation/board_v8_<YYYY-MM-DD>/V8-C1_FACT_SALES_MAPPINGS/targeted_tests_{red,green}.md`

**Definition of Done**
- Accepted as done only when:
  - Strict build produces `missing_mappings == 0`,
  - `gaps_after.json` is empty (or absent because none generated),
  - tests prove stop-line triggers on non-zero gaps.

**Validation/Gates**
- Targeted:
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_fact_sales_v16_mapping_gap_stopline.py`
- Runtime reproduction (fixture or local safe DB):
  - `python3 scripts/build_fact_sales_v16_from_api.py --strict --since-days 14`
  - `python3 scripts/report_fact_sales_v16_gaps.py --strict`

**Rollback / backout**
- Revert mapping updates (code/config) and restore DB from backup if any apply was executed.

**Stop-the-line**
- Any attempt to “auto-map” ambiguous items without a deterministic rule + explicit evidence.
- Any apply path that does not require env gate + `--apply` + backup.

---

### V8-C2 — CRM Identity Repair Canary (sku_key + kaspi_name_core)
**Goal (measurable)**
- Produce a deterministic report of identity anomalies (strict mode).
- Provide a safe, write-gated remediation that:
  - is **DRY-RUN by default**,
  - requires explicit env gate + `--apply`,
  - creates a backup before modifying the workbook,
  - is idempotent (second run makes 0 changes).

**Inputs**
- `scripts/validate_kaspi_parsing_integrity.py`
- `scripts/patch_kaspi_parsed_fields.py`
- `scripts/patch_crm_identity_columns.py`
- Excel UI contract (do not mutate outside explicitly allowed columns without justification + tests)

**Outputs**
- Strengthened patch/apply evidence artifacts:
  - `exports/validation/board_v8_<YYYY-MM-DD>/V8-C2_CRM_IDENTITY_REPAIR/apply_without_env_block.md`
  - `exports/validation/board_v8_<YYYY-MM-DD>/V8-C2_CRM_IDENTITY_REPAIR/apply_with_env_success.md`
  - `exports/validation/board_v8_<YYYY-MM-DD>/V8-C2_CRM_IDENTITY_REPAIR/patch_report.json`
- New/updated tests:
  - `tests/test_validate_kaspi_parsing_integrity_contract.py` (output schema + stopline semantics)
  - `tests/test_patch_kaspi_parsed_fields_apply_writes_and_creates_backup.py`

**Definition of Done**
- Accepted as done only when:
  - validator emits a machine-readable report and fails closed on anomalies in strict mode,
  - patch tool in DRY-RUN mode produces a report but does not write,
  - patch tool in APPLY mode (with env gate) writes and creates a backup,
  - apply is bounded (supports `--max-rows` or equivalent) and records which rows were changed.

**Validation/Gates**
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_validate_kaspi_parsing_integrity_contract.py tests/test_patch_kaspi_parsed_fields_apply_writes_and_creates_backup.py`

**Rollback / backout**
- Restore workbook from created backup.
- Revert code changes.

**Stop-the-line**
- Any workbook write without:
  - backup created first,
  - explicit env gate,
  - `--apply`,
  - deterministic patch report.

---

### V8-H1 — Speed Scale: Checkpointing + Cache (Opt-in, Parity-Proven)
**Goal (measurable)**
- Make daily runs faster at high order counts by enabling **resume/retry without redoing completed stages** and by reducing redundant API calls.
- Preserve equal-or-better results with parity tests.

**Inputs**
- Existing V7 benchmark framework:
  - `scripts/benchmark_kaspi_daily_ops.py`
  - `docs/ops/DAILY_OPS_TIMING_SLO_POLICY.md`
- Existing deterministic selection trace patterns (e.g., `_waybill_selection_orders.json`)

**Outputs**
- New/updated code:
  - `scripts/daily_ops_checkpoint.py` (or equivalent module): reads/writes stage status JSON.
  - Updates to orchestrator or benchmark runner to honor checkpoints.
- New/updated tests:
  - `tests/test_daily_ops_checkpoint_resume_contract.py`
  - `tests/test_daily_ops_result_parity.py` extended to cover checkpoint mode
- Evidence:
  - `exports/validation/board_v8_<YYYY-MM-DD>/V8-H1_SPEED/checkpoint_resume_parity.md`
  - `exports/validation/board_v8_<YYYY-MM-DD>/V8-H1_SPEED/benchmark_timings.json`

**Definition of Done**
- Accepted as done only when:
  - parity tests pass for baseline vs checkpoint/resume path,
  - benchmark artifacts produced and validated by schema test,
  - checkpoint mode is **opt-in** (cannot silently change production behavior).

**Validation/Gates**
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_daily_ops_checkpoint_resume_contract.py tests/test_daily_ops_result_parity.py`
- `python3 scripts/benchmark_kaspi_daily_ops.py --profile today-fast --emit-json <path>`

**Rollback / backout**
- Revert checkpoint feature (no data migration should occur).

**Stop-the-line**
- Any change that makes checkpointing default ON without explicit plan update and new safety gates.

---

### V8-O1 — Daily “Green/Red” Decision Report Artifact
**Goal (measurable)**
- Generate a single artifact that an operator can trust in <60 seconds:
  - status for each gate (green/red),
  - per-stage timings,
  - counts (orders fetched/assembled/PDFs/bundles),
  - links to the exact evidence directory.
- Report generation must be deterministic and validated by a strict contract.

**Inputs**
- Existing gate chain commands and outputs
- Timing policy: `docs/ops/DAILY_OPS_TIMING_SLO_POLICY.md`

**Outputs**
- New script:
  - `scripts/generate_daily_ops_report.py`
  - `scripts/validate_daily_ops_report.py` (strict schema validator; fail-closed)
- Report output path contract:
  - `exports/daily/<YYYY-MM-DD>/daily_ops_report.md`
  - `exports/daily/<YYYY-MM-DD>/daily_ops_report.json`
- Tests:
  - `tests/test_daily_ops_report_schema_contract.py`

**Definition of Done**
- Accepted as done only when:
  - report generation creates both `.md` and `.json`,
  - strict validator passes,
  - a negative fixture fails validator (fail-first evidence included).

**Validation/Gates**
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_daily_ops_report_schema_contract.py`
- `python3 scripts/validate_daily_ops_report.py --strict --path exports/daily/<date>/daily_ops_report.json`

**Rollback / backout**
- Revert report scripts; does not affect truth state.

**Stop-the-line**
- Any “report” that is not validated or does not include evidence root pointers.

---

### V8-A1 — Scheduler Hook (Read-only by default; pinned runtime)
**Goal (measurable)**
- Add a launchd job that generates the daily report on schedule with pinned `.venv/bin/python`.
- Must be safe-by-default: no apply writes; no network mutation; exits non-zero on any red.

**Inputs**
- Existing scheduler patterns:
  - `config/com.example.kaspi-import.plist`
  - `scripts/install_single_truth_ops_scheduler.sh` (or scheduler installer in repo)
- Runtime pinning requirements from earlier ops rollout (venv pin)

**Outputs**
- New plist:
  - `config/com.example.kaspi-daily-ops-report.plist`
- Installer updates (if required):
  - `scripts/install_scheduler.sh` or the canonical installer
- Tests:
  - `tests/test_kaspi_daily_ops_report_scheduler_contract.py`

**Definition of Done**
- Accepted as done only when:
  - plist is pinned to `.venv/bin/python`,
  - schedule times are documented and consistent with workflow contract ownership,
  - validate-only install path proves it would load cleanly,
  - contract tests pass.

**Validation/Gates**
- `bash scripts/install_single_truth_ops_scheduler.sh --validate-only`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_kaspi_daily_ops_report_scheduler_contract.py`

**Rollback / backout**
- Unload launchd job; revert plist and installer changes.

**Stop-the-line**
- Any scheduler job that runs “apply” modes or can mutate without env+flag gating.

---

### V8-S1 — Multi-store Resilience (Fail Closed; Partial Artifacts Allowed)
**Goal (measurable)**
- When running against multiple stores:
  - collect per-store outcomes,
  - still emit a single report artifact,
  - return a **non-zero exit code** if ANY store is red,
  - keep partial artifacts to minimize operator time diagnosing.

**Inputs**
- `core/stores/roster.py`
- Daily report artifact

**Outputs**
- Updated orchestration/report aggregation logic
- Tests:
  - `tests/test_multi_store_resilience_contract.py` (simulated 1-store failure)

**Definition of Done**
- Accepted as done only when:
  - report includes per-store section and overall summary,
  - exit code behavior is contract-tested (0 only when all green).

**Validation/Gates**
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_multi_store_resilience_contract.py`

**Rollback / backout**
- Revert aggregation changes.

**Stop-the-line**
- Any behavior that hides store failure behind overall green.

---

### V8-PROMOTE — Promotion + Evidence
**Goal (measurable)**
- Merge into `main` only when CI is green and evidence is stamped.

**Outputs**
- Evidence root:
  - `exports/validation/board_v8_<YYYY-MM-DD>/full_gates_green_final.md`
- Evidence doc stamped with:
  - PR link(s)
  - merge SHA
  - CI run links
- Offline oracle pack path recorded in:
  - `.claude/SESSION_LOG.md`

**Definition of Done**
- Accepted as done only when:
  - `gates` and `headless-gates` are PASS,
  - evidence doc contains final merge metadata,
  - oracle pack created and path recorded.

**Validation/Gates**
- Full required chain (listed in Inputs)
- CI: `gates` + `headless-gates` PASS

**Rollback / backout**
- `git revert -m 1 <merge_sha>` (and revert post-merge stamp PR if used)
- Restore workbook/DB from backups if apply was executed.

**Stop-the-line**
- Any claim of completion without the full gates artifact and stamped evidence doc.

---

## If attachments are missing — assumptions policy
- Proceed without questions unless truly blocking.
- If a required referenced file does not exist:
  1) Create a minimal stub with an explicit “MISSING AT START” banner,
  2) Add a fail-first contract test that would have caught the absence earlier,
  3) Record the assumption + file creation in `claude/journal.md`,
  4) Treat missing authority docs as a stop-line if they affect operator safety or truth integrity.