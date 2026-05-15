# Agent 740 - Fresh Boundary/Preflight Refresh After Agent739

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_740_fresh_boundary_preflight_refresh_after_739_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_740_evidence/`

Parallel group:

`agent740_fresh_boundary_refresh`

## Mission

Run the fresh boundary/preflight refresh lane required by CodeCaptain after Agent739.

This is a serialized no-owner-ask and no-production-apply lane.

Your job:

- freeze the current live DB/workbook boundary only after quiet-window checks;
- create backup/rollback evidence;
- copy the exact refreshed production DB pre-SHA into staging;
- rerun the reviewed Agent738/Agent734 staging command family on staging only;
- rerun final validators and leakage/cash/warning matrices;
- create a refreshed owner-facing packet candidate with the refreshed DB/workbook SHAs if and only if the proof passes;
- create a CodeCaptain review request for that refreshed packet;
- close with `GREEN`, `YELLOW`, or `RED`.

No owner ask. No production apply. No production DB mutation. No live workbook mutation. No scheduler mutation. No external-system writes. No Option C production authority.

You are not alone in the codebase. Do not revert or overwrite unrelated edits by others.

## Required Context

Read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Oracle/Autonomous_business/2026-05-09/153726_TASK-000_codecaptain-agent739-owner-packet-fix-review/answer/CodeCaptain_2026-05-09_16_35_00.md`
7. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/CODECAPTAIN_AGENT739_PACKET_WORDING_OK_REFRESH_BEFORE_OWNER_20260509.md`
8. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AGENT739_PACKET_FIX_ORCHESTRATOR_REVIEW_20260509.md`
9. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/OWNER_FACING_DB_ONLY_REPAIR_APPLY_REQUEST_DRAFT_AGENT739_REVIEW_REQUIRED_20260509.md`
10. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/OWNER_PACKET_STATIC_REVIEW_MATRIX_AGENT739_20260509.tsv`
11. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AGENT738_ORCHESTRATOR_REVIEW_20260509.md`
12. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_738_fresh_preflight_retry_dynamic_header_control_closeout.md`
13. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_738_evidence/STAGING_COMMAND_FAMILY_REPLAY.md`
14. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_738_evidence/agent738_fresh_preflight_runner.py`
15. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_737_evidence/RECOMMENDED_CONTRACT_DECISION.md`

## Write Boundary

Allowed writes:

- assigned closeout;
- assigned evidence folder;
- copied DBs under assigned evidence folder;
- copied workbook under assigned evidence folder;
- refreshed owner packet candidate:
  `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/OWNER_FACING_DB_ONLY_REPAIR_APPLY_REQUEST_REFRESHED_AGENT740_REVIEW_REQUIRED_20260509.md`
- refreshed static matrix:
  `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/OWNER_PACKET_STATIC_REVIEW_MATRIX_AGENT740_20260509.tsv`
- CodeCaptain refreshed packet review request:
  `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/CODECAPTAIN_AGENT740_REFRESHED_PACKET_REVIEW_REQUEST_20260509.md`

Forbidden:

- Do not mutate `~/Docs/Autonomous_business/db/app.db`.
- Do not mutate `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`.
- Do not pause, kill, restart, or mutate schedulers.
- Do not write to browser, Web_automation, Kaspi/API, ads platforms, Google, banks, external repos, or external systems.
- Do not ask owner for authorization.
- Do not activate Agent64.
- Do not reuse old Agent54.
- Do not production-apply.
- Do not promote Option C beyond validate-only.

## Required Evidence Files

Create under the assigned evidence folder:

1. `READCHECK.md`
2. `QUIET_WINDOW_STABILITY_CHECK.md`
3. `FRESH_PRODUCTION_BOUNDARY_REPORT.md`
4. `DRIFT_STABILITY_REPORT.md`
5. `BACKUP_ROLLBACK_EVIDENCE.md`
6. `STAGING_COMMAND_FAMILY_REPLAY.md`
7. `DYNAMIC_HEADER252_CONTROL_DERIVATION.tsv`
8. `SIMULATE_WRAPPER_SUMMARY.json`
9. `STRICT23_WRAPPER_SUMMARY.json`
10. `HEADER252_DYNAMIC_WRAPPER_SUMMARY.json`
11. `PINNED_VALIDATOR_MATRIX.tsv`
12. `FRESH_ROW_COUNT_MATRIX.tsv`
13. `FRESH_LEAKAGE_MATRIX.tsv`
14. `ORDER_LEVEL_CASH_PRESERVATION_MATRIX.tsv`
15. `WARNING_CLASS_VISIBILITY_MATRIX.tsv`
16. `FINAL_BOUNDARY_STATUS.json`
17. `REFRESHED_OWNER_PACKET_STATUS.md`
18. `CODECAPTAIN_AGENT740_REVIEW_REQUEST_PROMPT.md`
19. `RUN_STATUS.json`

You may reuse/adapt Agent738's evidence runner if helpful, but record exactly what changed and do not hide deviations from the reviewed command family.

## Required Quiet Window Check

Before copying production DB/workbook:

1. Confirm current time is not inside known import windows and not within 15 minutes after them:
   - `11:00`
   - `15:02`
   - `16:01`
   - `17:02`
2. If inside a blocked window or within 15 minutes after one, wait until the next safe interval instead of pausing schedulers.
3. Capture `ps` evidence for import/sync/publish/workbook/DB writer processes.
4. Capture `lsof excel_ui/SALES_KSP_CRM_V3.xlsx` and `lsof db/app.db`.
5. Confirm no SQLite sidecars exist for `db/app.db`.
6. Capture workbook and DB SHA/mtime.
7. Wait 2 to 5 minutes.
8. Capture workbook and DB SHA/mtime again.
9. Close YELLOW/RED before staging if any writer appears or SHA changes unexpectedly.

## Required Replay Work

1. Create timestamped DB backup/copy and workbook copy under the assigned evidence folder only.
2. Record DB backup SHA, backup integrity `ok`, and exact rollback command.
3. Build staging DB from exact frozen production pre-SHA.
4. Run focused tests:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_apply_rebuild_snapshot_production_safe.py tests/test_rebuild_snapshot_negative_active_zero.py tests/test_validate_write_side_gating.py
python3 -m py_compile scripts/apply_rebuild_snapshot_production_safe.py scripts/rebuild_snapshot.py
python3 scripts/validate_write_side_gating.py --manifest config/write_side_gating_manifest.yaml
```

5. Rerun the corrected Agent738/Agent734 command family on staging only:
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

## Required Refreshed Owner Packet

If and only if the refreshed staging proof passes, write:

`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/OWNER_FACING_DB_ONLY_REPAIR_APPLY_REQUEST_REFRESHED_AGENT740_REVIEW_REQUIRED_20260509.md`

It must be based on Agent739's reviewed wording, but update:

- refreshed DB SHA;
- protected workbook SHA;
- timestamp;
- backup path/SHA;
- staging replay status;
- validator matrix summary;
- warning visibility derivation;
- fresh boundary/preflight status.

It must still be marked `REVIEW_REQUIRED_NOT_SENT_TO_OWNER`.

Do not ask owner and do not make the phrase active.

If proof does not pass, write `REFRESHED_OWNER_PACKET_STATUS.md` explaining why no owner-facing packet is safe.

## Required Final Live Boundary Check

After staging replay completes and before claiming any packet is owner-review-ready:

- recapture production DB SHA and workbook SHA;
- recapture lsof/sidecar state;
- compare to the frozen pre-SHA/pre-workbook SHA;
- close `YELLOW` or `RED` if live boundary drifted during the lane.

## Gate Semantics

`GREEN`:

- quiet-window/stability proof passes;
- production DB/workbook boundary remains stable from freeze through final check;
- backup/rollback evidence complete;
- staging replay uses reviewed command family;
- dynamic header-only control is reproducible;
- final pinned validators pass/GREEN;
- strict `23`, header-only `252`, and combined `275` have zero leakage;
- warning visibility is explicit and matches derived overlap;
- order-level cash is preserved;
- refreshed owner packet is review-required and not sent;
- no forbidden mutation occurred.

`YELLOW`:

- wording/packet can be updated but live boundary drift or review ambiguity prevents owner-facing request.

`RED`:

- active writer or SHA drift appears before copy;
- DB integrity fails;
- backup/rollback missing;
- dynamic derivation fails;
- final validator fails;
- leakage remains;
- warning visibility disappears or is hidden;
- any forbidden mutation occurs.

## Closeout

Write closeout with READCHECK, files written, commands run, quiet-window proof, exact refreshed DB/workbook SHAs, backup/rollback, dynamic-control derivation, replay summary, validator matrix, leakage/cash/warning matrices, refreshed owner-packet status, mutation statement, recommended next step, and standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
