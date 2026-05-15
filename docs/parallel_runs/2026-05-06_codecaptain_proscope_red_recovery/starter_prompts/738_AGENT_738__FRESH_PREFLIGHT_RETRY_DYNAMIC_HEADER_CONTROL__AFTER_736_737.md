# Agent 738 - Fresh Preflight Retry With Dynamic Header-Only Control

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_738_fresh_preflight_retry_dynamic_header_control_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_738_evidence/`

Parallel group:

`agent738_fresh_preflight_retry`

## Mission

Retry the fresh owner-request preflight as a serialized no-apply lane after Agents736/737 cleared the Agent735 RED causes.

This lane must:

- first prove the current live DB/workbook window is quiet and stable;
- freeze one fresh production boundary;
- create backup/rollback evidence;
- build one staging candidate from the exact frozen production pre-SHA;
- rerun the corrected Agent734 command family on staging only;
- use Agent737's dynamic header-only expected-control derivation instead of stale static `251`;
- produce review-required owner-request evidence only if all gates pass.

No owner ask. No production apply. No workbook mutation. No scheduler mutation. No external-system writes. No Option C production authority.

You are not alone in the codebase. Do not revert or overwrite unrelated edits by others.

## Required Context

Read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AGENT735_ORCHESTRATOR_REVIEW_20260509.md`
7. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AGENT736_737_ORCHESTRATOR_REVIEW_20260509.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_736_workbook_drift_scheduler_forensics_closeout.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_736_evidence/QUIET_WINDOW_RETRY_RECOMMENDATION.md`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_737_header252_249_control_reproof_closeout.md`
11. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_737_evidence/RECOMMENDED_CONTRACT_DECISION.md`
12. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_737_evidence/FINAL_VALIDATOR_MATRIX.tsv`
13. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_737_evidence/FINAL_LEAKAGE_MATRIX.tsv`
14. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_737_evidence/FINAL_WARNING_VISIBILITY_MATRIX.tsv`

## Write Boundary

Allowed writes:

- assigned closeout;
- assigned evidence folder;
- copied DBs under assigned evidence folder;
- copied workbook under assigned evidence folder;
- review-required owner-request packet candidate under assigned evidence folder.

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

Create:

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
17. `OWNER_REQUEST_PACKET__REVIEW_REQUIRED_NOT_SENT_TO_OWNER.md`
18. `CODECAPTAIN_AGENT738_REVIEW_REQUEST_PROMPT.md`

## Required Quiet Window Check

Before copying production DB/workbook:

1. Confirm current time is not inside known import windows and not within 15 minutes after them:
   - `11:00`
   - `15:02`
   - `16:01`
   - `17:02`
2. Capture `ps` evidence for import/sync/publish/workbook/DB writer processes.
3. Capture `lsof excel_ui/SALES_KSP_CRM_V3.xlsx` and `lsof db/app.db`.
4. Confirm no SQLite sidecars exist for `db/app.db`.
5. Capture workbook and DB SHA/mtime.
6. Wait 2 to 5 minutes.
7. Capture workbook and DB SHA/mtime again.
8. Close YELLOW/RED before staging if any writer appears or SHA changes unexpectedly.

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

5. Rerun the corrected Agent734 command family on staging only:
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
   - expected stock-ledger delete rows = distinct/row overlap between candidate order IDs and pre-header `stock_ledger.reference_id`;
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

## Gate Semantics

`GREEN`:

- quiet-window/stability proof passes;
- production DB/workbook boundary remains stable;
- backup/rollback evidence complete;
- staging replay uses corrected command family;
- dynamic header-only control is reproducible;
- final pinned validators pass/GREEN;
- strict `23`, header-only `252`, and combined `275` have zero leakage;
- warning visibility is explicit and matches derived overlap;
- owner-request packet is review-required and not sent;
- no forbidden mutation occurred.

`YELLOW`:

- evidence is useful but a review decision is needed before owner-facing review.

`RED`:

- active writer or SHA drift appears;
- DB integrity fails;
- backup/rollback missing;
- dynamic derivation fails;
- final validator fails;
- leakage remains;
- warning visibility disappears or is hidden;
- any forbidden mutation occurs.

## Closeout

Write closeout with READCHECK, files written, commands run, quiet-window proof, exact DB/workbook SHAs, backup/rollback, dynamic-control derivation, replay summary, validator matrix, leakage/cash/warning matrices, mutation statement, recommended next step, and standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
