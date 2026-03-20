# PLAN_POST_OCEAN_DROP_HIGH_ROI_NEXT_PHASES_2026-02-28

## Purpose
Convert the closure-v3 sales truth state into decision-grade daily operations by closing three high-ROI gaps:
1. BUSINESS_INSIDES economics completeness (COGS/profit/ads) with strict fail-closed publication.
2. Import/waybill/ship selector parity so overdue/pending order selection cannot drift silently.
3. Scheduler heartbeat + proving-run autopilot so daily red/green state is deterministic and low-touch.

## Baseline
- Closure-v3 commits present:
  - `2eca780`
  - `ebe6063`
  - `ebeb2fd`
  - `98f2344`
- Reference oracle packs:
  - `~/Docs/Oracle/Autonomous_business/2026-02-28/080459_TASK-000_sales-ocean-drop-engine-closure-v3-primary-db-schemas.md`
  - `~/Docs/Oracle/Autonomous_business/2026-02-28/085842_TASK-000_sales-ocean-drop-daily-ops-reliability-delta-primary-db-schemas-v2.md`

## Scope And Phases

### P0 — Consolidate + Promotion Safety Lock
Goal:
- Normalize this plan doc and establish a reproducible baseline on branch `codex/TASK-post-ocean-drop-high-roi-economics-dailyops-v1`.

DoD:
- Plan doc exists at this path and is committed.
- READCHECK evidence recorded in `claude/journal.md`.
- Baseline strict gates transcript exists:
  - `exports/validation/board_post_ocean_drop_high_roi_2026-02-28/full_gates_green_final.md`

### P1 — BUSINESS_INSIDES Economics Completion (Fail-Closed)
Goal:
- Prevent decision-grade economics output when cost/identity coverage is incomplete.

Deliverables:
- `scripts/validate_business_insides_economics_ready.py`
- tests:
  - `tests/test_validate_business_insides_economics_ready.py`
- artifacts:
  - `exports/validation/business_insides_economics/<AS_OF>/economics_ready_report.json`
  - `exports/validation/business_insides_economics/<AS_OF>/economics_ready_report.md`

DoD:
- `python3 scripts/validate_business_insides_economics_ready.py --as-of <AS_OF> --strict` PASS.
- Report explicitly fails on nonvolatile missing economics coverage.

### P2 — Daily Ops Selector Contract Unification (Import ↔ Waybill ↔ Ship)
Goal:
- One parity validator checks selected order IDs across import/waybill selection surfaces and fails on mismatch.

Deliverables:
- `scripts/validate_ops_selection_parity.py`
- tests:
  - `tests/test_validate_ops_selection_parity.py`
- artifacts:
  - `exports/validation/ops_selection_parity/<AS_OF>/parity_report.json`
  - `exports/validation/ops_selection_parity/<AS_OF>/parity_report.md`
  - `exports/validation/ops_selection_parity/<AS_OF>/missing_order_ids.csv`
  - `exports/validation/ops_selection_parity/<AS_OF>/extra_order_ids.csv`

DoD:
- `python3 scripts/validate_ops_selection_parity.py --as-of <AS_OF> --strict` PASS.
- Any mismatch produces CSV diffs + non-zero exit.

### P3 — Scheduler Heartbeat + Drift Alerts
Goal:
- Verify expected schedules and runtime heartbeat evidence fail-closed.

Deliverables:
- `scripts/validate_scheduler_heartbeat.py`
- tests:
  - `tests/test_validate_scheduler_heartbeat.py`
- artifacts:
  - `exports/daily/<AS_OF>/scheduler_heartbeat.json`
  - `exports/daily/<AS_OF>/scheduler_heartbeat.md`

DoD:
- `python3 scripts/validate_scheduler_heartbeat.py --as-of <AS_OF> --strict` PASS.
- Drift between plist/doc contract and expected schedule fails closed.

### P4 — Proving-Run Autopilot Wiring
Goal:
- Wire P1/P2/P3 gates into proving-run flow so decision outputs are only green when all checks pass.

Deliverables:
- `scripts/run_h5_proving_day.py` updated to call new validators (strict mode).
- `scripts/validate_h5_artifact_set.py` updated if needed for new artifact checks.

DoD:
- Proving day run emits deterministic manifest and reflects new gate results.

### P5 — Continuous Drift Monitoring
Goal:
- Ensure sales drift + economics + selection + scheduler checks are part of final strict evidence chain.

Deliverables:
- Final gate transcript:
  - `exports/validation/board_post_ocean_drop_high_roi_2026-02-28/full_gates_green_final.md`

DoD:
- Mandatory gates + new gates PASS and are captured in transcript.
- No truth contamination: published sales views do not use ocean-drop reference override.

## Mandatory Gates
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
- `python3 scripts/validate_params.py --strict`
- `python3 scripts/validate_single_truth_system.py`
- `python3 scripts/system_doctor.py --strict --project-root . --as-of 2026-02-26`
- `bash scripts/lint_docs.sh`

## New Gates
- `python3 scripts/validate_business_insides_economics_ready.py --as-of 2026-02-26 --strict`
- `python3 scripts/validate_ops_selection_parity.py --as-of 2026-02-26 --strict`
- `python3 scripts/validate_scheduler_heartbeat.py --as-of 2026-02-26 --strict`

## Stop-The-Line
- Any gate fails or is skipped.
- Any economics output is produced when required identity/cost coverage is incomplete.
- Any selector mismatch lacks explicit diff artifacts.
- Any schedule drift exists between plist/docs/tests without intentional documented change.
- Any attempt to reintroduce reference override into published truth views.
