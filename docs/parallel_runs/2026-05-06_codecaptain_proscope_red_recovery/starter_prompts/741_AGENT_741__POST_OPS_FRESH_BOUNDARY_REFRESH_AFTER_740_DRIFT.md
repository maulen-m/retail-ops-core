# Agent 741 - Post-Ops Fresh Boundary Refresh After Agent740 Drift

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_741_post_ops_fresh_boundary_refresh_after_740_drift_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_741_evidence/`

Parallel group:

`agent741_post_ops_refresh`

## Mission

Run one narrow post-ops fresh boundary/preflight refresh after Agent740.

Agent740 completed `GREEN`, but an orchestrator sample at `2026-05-09T16:59:48+05:00` showed live `db/app.db` drifted to:

`a8fd14ef61c882d551f6ad6bac63cf58fbfa5eb11436f0724298256865ea3ffe`

while the workbook remained:

`5c42b36f07f2c537cca2f4ff3388197047b4516afdfc54479e274c1f5229dc51`

Active ops/shipping processes were visible around that sample. Your job is to wait for a safe post-ops quiet window, then re-run the same no-production-apply refresh from the exact current DB pre-SHA.

This is serialized, no-owner-ask, no-production-apply, no-production-mutation.

## Required Context

Read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AGENT740_ORCHESTRATOR_REVIEW_20260509.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_740_fresh_boundary_preflight_refresh_after_739_closeout.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_740_evidence/STAGING_COMMAND_FAMILY_REPLAY.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_740_evidence/agent740_fresh_boundary_runner.py`
10. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/OWNER_FACING_DB_ONLY_REPAIR_APPLY_REQUEST_REFRESHED_AGENT740_REVIEW_REQUIRED_20260509.md`
11. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/CODECAPTAIN_AGENT740_REFRESHED_PACKET_REVIEW_REQUEST_20260509.md`

## Write Boundary

Allowed writes:

- assigned closeout;
- assigned evidence folder;
- copied DBs under assigned evidence folder;
- copied workbook under assigned evidence folder;
- refreshed owner packet candidate:
  `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/OWNER_FACING_DB_ONLY_REPAIR_APPLY_REQUEST_REFRESHED_AGENT741_REVIEW_REQUIRED_20260509.md`
- refreshed static matrix:
  `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/OWNER_PACKET_STATIC_REVIEW_MATRIX_AGENT741_20260509.tsv`
- refreshed CodeCaptain review request:
  `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/CODECAPTAIN_AGENT741_REFRESHED_PACKET_REVIEW_REQUEST_20260509.md`

Forbidden:

- Do not mutate `~/Docs/Autonomous_business/db/app.db`.
- Do not mutate `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`.
- Do not pause, kill, restart, or mutate schedulers or daily shipping processes.
- Do not write to browser, Web_automation, Kaspi/API, ads platforms, Google, banks, external repos, or external systems.
- Do not ask owner for authorization.
- Do not activate Agent64.
- Do not reuse old Agent54.
- Do not production-apply.
- Do not promote Option C beyond validate-only.

## Safe Window Requirement

Before copying production DB/workbook:

1. Wait until outside the `17:02` import window plus at least a 15-minute buffer.
2. Confirm no active daily ops writers are running, especially:
   - `run_google_ops_board_closeout_scheduler.py`
   - `run_google_ops_board_closeout.py`
   - `ship_orders_api.py`
   - Kaspi import/write scripts
   - workbook/Excel automation writers
3. Capture `ps` evidence for import/sync/publish/workbook/DB writer processes.
4. Capture `lsof db/app.db` and `lsof excel_ui/SALES_KSP_CRM_V3.xlsx`.
5. Confirm no SQLite sidecars exist for `db/app.db`.
6. Capture workbook and DB SHA/mtime.
7. Wait 2 to 5 minutes.
8. Capture workbook and DB SHA/mtime again.
9. Close `YELLOW` before staging if active writers persist, if the DB/workbook SHA changes during the quiet sample, or if the quiet window cannot be established.

Do not pause or kill the writers. If they are still running, wait or close YELLOW with evidence.

## Required Replay Work

If the quiet window is stable:

1. Create timestamped DB backup/copy and workbook copy under the assigned evidence folder only.
2. Record DB backup SHA, backup integrity `ok`, and exact rollback command.
3. Build staging DB from exact frozen production pre-SHA.
4. Run focused tests:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_apply_rebuild_snapshot_production_safe.py tests/test_rebuild_snapshot_negative_active_zero.py tests/test_validate_write_side_gating.py
python3 -m py_compile scripts/apply_rebuild_snapshot_production_safe.py scripts/rebuild_snapshot.py
python3 scripts/validate_write_side_gating.py --manifest config/write_side_gating_manifest.yaml
```

5. Rerun the corrected Agent740/Agent738/Agent734 command family on staging only:
   - sales fact rebuild;
   - stock ledger sales replay;
   - simulate snapshot production-safe wrapper;
   - order-status materialization;
   - cashflow translation/calendar;
   - policy source freshness;
   - ads materialization using existing evidence DBs;
   - order-entry recovery;
   - cashflow refresh;
   - strict `23` wrapper;
   - dynamic header-only `252` wrapper;
   - final policy source freshness.
6. Derive the expected header-only stock-ledger delete count from current pre-header overlap:
   - source classification: Agent69E `RESIDUAL_275_ROW_CLASSIFICATION.tsv`;
   - candidate set: `recommended_action=HEADER_ONLY_BLOCKER`;
   - expected candidate rows must remain `252`;
   - expected stock-ledger delete rows = overlap between candidate order IDs and pre-header `stock_ledger.reference_id`;
   - expected product cashflow delete rows = product-level `fact_cashflow_events.ref_id` overlap for those IDs;
   - expected warning visibility should match final product-truth overlap after wrapper.
7. Do not hard-code `251`.
8. Do not hard-code `249` unless the fresh derivation proves `249` for this boundary.
9. Stop RED if derivation cannot be reproduced or if candidate rows differ from `252` without reviewed evidence.

## Required Final Validators

Run on final staging DB:

```bash
python3 scripts/validate_policy_source_freshness.py --db <staging_db> --as-of 2026-05-04 --strict --json
python3 scripts/validate_operational_stock_integration_gates.py --db <staging_db> --as-of 2026-05-04 --json
python3 scripts/validate_order_cashflow_coverage.py --db <staging_db> --as-of 2026-05-04 --strict --json
python3 scripts/validate_cashflow_actual_model_separation.py --db <staging_db> --anchor-date 2026-05-04 --strict --json
python3 scripts/validate_cashflow_invariants.py --db <staging_db>
```

## Required Evidence

Create the same evidence set as Agent740, adjusted for Agent741 names:

- `READCHECK.md`
- `QUIET_WINDOW_STABILITY_CHECK.md`
- `FRESH_PRODUCTION_BOUNDARY_REPORT.md`
- `DRIFT_STABILITY_REPORT.md`
- `BACKUP_ROLLBACK_EVIDENCE.md`
- `STAGING_COMMAND_FAMILY_REPLAY.md`
- `DYNAMIC_HEADER252_CONTROL_DERIVATION.tsv`
- `SIMULATE_WRAPPER_SUMMARY.json`
- `STRICT23_WRAPPER_SUMMARY.json`
- `HEADER252_DYNAMIC_WRAPPER_SUMMARY.json`
- `PINNED_VALIDATOR_MATRIX.tsv`
- `FRESH_ROW_COUNT_MATRIX.tsv`
- `FRESH_LEAKAGE_MATRIX.tsv`
- `ORDER_LEVEL_CASH_PRESERVATION_MATRIX.tsv`
- `WARNING_CLASS_VISIBILITY_MATRIX.tsv`
- `FINAL_BOUNDARY_STATUS.json`
- `REFRESHED_OWNER_PACKET_STATUS.md`
- `CODECAPTAIN_AGENT741_REVIEW_REQUEST_PROMPT.md`
- `RUN_STATUS.json`

If proof passes, update the refreshed owner packet and review request under the repo run folder.

## Gate Semantics

`GREEN`:

- quiet post-ops window is proven;
- production DB/workbook boundary remains stable from freeze through final check;
- backup/rollback evidence complete;
- staging replay uses reviewed command family;
- final validators pass/GREEN;
- strict `23`, header-only `252`, and combined `275` have zero leakage;
- warning visibility is explicit and matches derived overlap;
- order-level cash is preserved;
- refreshed owner packet is review-required and not sent;
- no forbidden mutation occurred.

`YELLOW`:

- active ops writers persist, boundary cannot be stabilized, or review ambiguity remains.

`RED`:

- DB integrity fails;
- backup/rollback missing;
- dynamic derivation fails;
- final validator fails;
- leakage remains;
- warning visibility disappears or is hidden;
- any forbidden mutation occurs.

## Closeout

Write closeout with READCHECK, files written, commands run, quiet-window proof, exact refreshed DB/workbook SHAs, backup/rollback, dynamic-control derivation, replay summary, validator matrix, leakage/cash/warning matrices, refreshed owner-packet status, mutation statement, recommended next step, and standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
