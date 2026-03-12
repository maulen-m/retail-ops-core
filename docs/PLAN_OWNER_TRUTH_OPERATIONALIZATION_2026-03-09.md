# PLAN_OWNER_TRUTH_OPERATIONALIZATION_2026-03-09

## Scope

Operationalize the already-green `2026-03-08` WebUI owner-truth baseline into a durable live runtime path without reopening WebUI source acquisition.

## Baseline

- preferred start tip: `25b5c1425e7b4a8164b29104362690b4fddbbef7`
- fallback tip: `551e2ce7278d55de398af76273c7ab244a4a8078`
- baseline release commit: `86ce447782a005c47ac3d1b61dde8414900320a8`
- rollback anchor: `exports/validation/owner_truth_release/2026-03-04/full_gates_green_final.md`
- active clean worktree for this execution: `~/Docs/wt_webui_owner_truth_operationalization_v1`
- source checkout `~/Docs/Autonomous_business` is dirty and is not used for implementation work

## Non-negotiables

1. No new WebUI scrape or source remediation.
2. Live mode must not silently consume replay-only artifacts.
3. No DB write without env gate + `--apply` + backup + before/after diff + rollback note.
4. Scheduler/install assets must be rendered from repo-relative templates.
5. Do not claim completion unless every required gate is green.

## Phases

### R0 — Baseline READCHECK + Tip Freeze

Deliverables:
- `exports/validation/owner_truth_operationalization/2026-03-09/readcheck.md`
- `exports/validation/owner_truth_operationalization/2026-03-09/baseline_manifest.json`
- `exports/validation/owner_truth_operationalization/2026-03-09/baseline_inventory.txt`
- `exports/validation/owner_truth_operationalization/2026-03-09/assumptions.md`

Tests / proof strategy:
- no code change
- verify clean worktree on preferred tip or explicit fallback
- verify required release anchor artifacts exist

### R1 — Runtime Mode Split (Replay vs Live)

Goal:
- make replay behavior explicit
- make live behavior explicit
- fail closed if live mode would consume replay-only inputs

Deliverables:
- `docs/validation/OWNER_TRUTH_RUNTIME_MODE_CONTRACT.md`
- `scripts/resolve_owner_truth_runtime_mode.py`
- updated `scripts/run_owner_truth_daily.py`
- updated `scripts/system_doctor.py`
- updated `scripts/smoke_test_owner_truth_daily.py`
- `tests/test_owner_truth_runtime_mode.py`
- updated `tests/test_run_owner_truth_daily_contract.py`
- updated `tests/test_system_doctor_contract.py`
- `exports/validation/owner_truth_operationalization/2026-03-09/runtime_mode_report.json`

Tests first:
- replay mode permits frozen seed/governance prereqs only when explicitly requested
- live mode rejects replay-only seed usage
- smoke harness uses replay explicitly for historical release proving
- live daily path uses live generation only

### R2 — Scheduler + Install Asset Portability

Goal:
- replace machine-local launchd plists with repo-relative templates + renderer

Deliverables:
- `config/launchd_templates/com.example.kaspi-import.plist.tmpl`
- `config/launchd_templates/com.example.kaspi-waybill-deadline.plist.tmpl`
- `config/launchd_templates/com.example.kaspi-daily-ops-report.plist.tmpl`
- `scripts/render_launchd_plists.py`
- updated `scripts/install_scheduler.sh`
- updated `scripts/install_single_truth_ops_scheduler.sh`
- `tests/test_render_launchd_plists.py`
- `exports/validation/owner_truth_operationalization/2026-03-09/scheduler_portability_report.json`

Tests first:
- render output preserves current schedule/label/runtime semantics
- rendered plists use repo-relative render inputs and resolved project-root outputs
- install scripts call renderer instead of copying hard-coded plists

### R3 — Anchor Bootstrap + Health Contract

Goal:
- one explicit bootstrap/validate path for anchors used by live owner-truth runtime

Deliverables:
- `scripts/bootstrap_owner_truth_anchors.py`
- `docs/ops/OWNER_TRUTH_ANCHOR_BOOTSTRAP.md`
- `tests/test_bootstrap_owner_truth_anchors.py`
- `exports/validation/owner_truth_operationalization/2026-03-09/anchor_bootstrap_report.json`

Tests first:
- bootstrap creates/refreshes required anchor pointers from explicit source args
- validate mode fails closed on missing inputs
- check_anchor_health remains authoritative after bootstrap

### R4 — Fresh-Date Live Proving

Goal:
- prove live mode on `2026-03-09` or first available date after it
- no replay-only artifact consumption

Deliverables:
- `exports/validation/owner_truth_operationalization/2026-03-09/live_proving/live_run_summary.json`
- `exports/validation/owner_truth_operationalization/2026-03-09/live_proving/live_run_transcript.md`
- `exports/validation/owner_truth_operationalization/2026-03-09/live_proving/live_idempotence_report.json`
- `exports/validation/owner_truth_operationalization/2026-03-09/live_proving/blocked_inputs.json`
- `exports/validation/owner_truth_operationalization/2026-03-09/live_proving/blocked_inputs.md`
- `docs/OPS_ROLLOUT_EVIDENCE_OWNER_TRUTH_LIVE_PROVING_2026-03-09.md`

Tests / proof strategy:
- execute `run_owner_truth_daily.py --mode live`
- execute twice and compare semantic outputs ignoring approved volatile fields
- if blocked, emit blocker pack and stop

### R5 — Observability + Merge / Oracle Refresh

Deliverables:
- `exports/validation/owner_truth_operationalization/2026-03-09/merge_manifest.json`
- `exports/validation/owner_truth_operationalization/2026-03-09/merge_manifest.md`
- `Oracle_listings/packs/owner_truth_operationalization_2026-03-09/PACK_SUMMARY.md`
- `Oracle_listings/packs/owner_truth_operationalization_2026-03-09/bundle.md`
- `Oracle_listings/packs/owner_truth_operationalization_2026-03-09/oracle_files_manifest.txt`
- `Oracle_listings/packs/owner_truth_operationalization_2026-03-09/ArchiveSales_ALL_STORES_statusdate_mapped.csv`

Tests / proof strategy:
- artifact presence and pack content validation
- merge manifest must name exact commit(s), commands, rollback, and exclusion scope

### R6 — Deferred Scale Queue Lock

Deliverables:
- `exports/validation/owner_truth_operationalization/2026-03-09/deferred_scale_backlog.md`

Tests / proof strategy:
- document non-merge scope explicitly
- ensure no deferred scale item is silently pulled into live cutover

## Required gate chain

1. `bash scripts/lint_docs.sh`
2. `bash scripts/check_no_db_tracked.sh`
3. `python3 scripts/check_release_hygiene.py --strict --project-root .`
4. `bash scripts/install_single_truth_ops_scheduler.sh --validate-only`
5. `python3 scripts/check_anchor_health.py --project-root .`
6. `./.venv/bin/python scripts/ops_status.py --project-root .`
7. `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_owner_truth_runtime_mode.py tests/test_run_owner_truth_daily_contract.py tests/test_system_doctor_contract.py tests/test_render_launchd_plists.py tests/test_bootstrap_owner_truth_anchors.py tests/test_kaspi_import_scheduler_contract.py tests/test_kaspi_waybill_deadline_scheduler_contract.py tests/test_kaspi_daily_ops_report_scheduler_contract.py tests/test_kaspi_daily_ops_workflow_contract_doc.py`
8. `./.venv/bin/python scripts/smoke_test_owner_truth_daily.py --as-of 2026-03-08 --strict`
9. `./.venv/bin/python scripts/run_owner_truth_daily.py --mode live --as-of 2026-03-09 --strict`
10. `./.venv/bin/python scripts/system_doctor.py --strict --project-root . --as-of 2026-03-09`

## Rollback

1. revert new commits newest-to-oldest
2. restore operator baseline to `exports/validation/owner_truth_release/2026-03-04/full_gates_green_final.md`
3. if any write path is introduced later, rollback must cite backup + before/after diff artifacts before execution
