# Agent 735 - Fresh Owner-Request Preflight, No Apply After Agent734

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_735_fresh_owner_request_preflight_no_apply_after_734_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_735_evidence/`

Parallel group:

`agent735_fresh_owner_request_preflight`

Dependency:

Run only after CodeCaptain Agent734 review returns `GREEN_TO_REOPEN_FRESH_OWNER_REQUEST_PREFLIGHT_ONLY`.

## Mission

Open the fresh owner-request preflight lane authorized by CodeCaptain after Agent734. This is a serialized, no-owner-ask, no-production-mutation lane.

Freeze the current production DB/workbook boundary once, create backup/rollback evidence, build one staging candidate from that exact frozen production pre-SHA, run the corrected Agent734 command family on staging/copies only, rerun pinned `2026-05-04` validators, and produce a review-required owner-request packet candidate.

This lane may prove readiness to prepare an owner request packet for review. It must not ask the owner, activate a phrase, mutate production, mutate workbook, mutate schedulers, write external systems, or promote Option C.

You are not alone in the codebase. Do not revert or overwrite unrelated edits by others.

## Required Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/CODECAPTAIN_AGENT734_GREEN_PREFLIGHT_REOPEN_20260509.md`
7. `~/Docs/Oracle/Autonomous_business/2026-05-08/232546_TASK-000_codecaptain-agent734-green-preflight-review/Answer/Code_Captain_2026-05-09_10_37_00.md`
8. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AGENT734_ORCHESTRATOR_REVIEW_20260508.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_734_simulate_wrapper_full_temp_proof_closeout.md`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_734_evidence/RECOMMENDED_NEXT_STEP.md`
11. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_734_evidence/SIMULATE_WRAPPER_SUMMARY.json`
12. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_734_evidence/STRICT23_PROD_WRAPPER_SUMMARY.json`
13. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_734_evidence/HEADER252_PROD_WRAPPER_SUMMARY.json`
14. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_734_evidence/VALIDATOR_MATRIX.tsv`
15. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_734_evidence/LEAKAGE_MATRIX.tsv`
16. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_734_evidence/ORDER_LEVEL_CASH_PRESERVATION.tsv`
17. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_734_evidence/WARNING_VISIBILITY_MATRIX.tsv`

## Write Boundary

Allowed writes:

- assigned closeout;
- assigned evidence folder;
- staging/copy DBs under assigned evidence folder only;
- copied workbook under assigned evidence folder only;
- review-required owner-request packet candidate under assigned evidence folder only.

Forbidden:

- Do not mutate `~/Docs/Autonomous_business/db/app.db`.
- Do not mutate `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`.
- Do not mutate schedulers.
- Do not write to browser, Web_automation, Kaspi/API, ads platforms, Google, banks, external repos, or external systems.
- Do not ask the owner for authorization.
- Do not production-apply.
- Do not activate Agent64.
- Do not reuse or quote old Agent54 as active.
- Do not use Agent734 copied DB as production truth.
- Do not run direct unsafe production materializers in place of production-safe wrappers.
- Do not use ad hoc SQL against production.
- Do not promote Option C beyond validate-only.

## Required Evidence Files

Create all of these in the assigned evidence folder:

1. `READCHECK.md`
2. `EVIDENCE_MANIFEST.md`
3. `FRESH_PRODUCTION_BOUNDARY_REPORT.md`
4. `DRIFT_STABILITY_REPORT.md`
5. `BACKUP_ROLLBACK_EVIDENCE.md`
6. `STAGING_COMMAND_FAMILY_REPLAY.md`
7. `SIMULATE_WRAPPER_FRESH_PREFLIGHT_SUMMARY.json`
8. `STRICT23_WRAPPER_FRESH_PREFLIGHT_SUMMARY.json`
9. `HEADER252_WRAPPER_FRESH_PREFLIGHT_SUMMARY.json`
10. `PINNED_VALIDATOR_MATRIX.tsv`
11. `FRESH_ROW_COUNT_MATRIX.tsv`
12. `FRESH_LEAKAGE_MATRIX.tsv`
13. `ORDER_LEVEL_CASH_PRESERVATION_MATRIX.tsv`
14. `WARNING_CLASS_VISIBILITY_MATRIX.tsv`
15. `PROTECTED_SURFACE_STATUS.txt`
16. `FINAL_BOUNDARY_STATUS.json`
17. `OWNER_REQUEST_PACKET__REVIEW_REQUIRED_NOT_SENT_TO_OWNER.md`
18. `CODECAPTAIN_AGENT735_REVIEW_REQUEST_PROMPT.md`

## Required Work

1. Capture fresh production DB SHA256, workbook SHA256, mtimes, and protected git status.
2. Run production DB `PRAGMA integrity_check` read-only.
3. Check SQLite sidecars near `db/app.db` and `lsof` holders for DB and sidecars.
4. If sidecar/holder state is unsafe, close RED before copying.
5. Create timestamped DB backup/copy and workbook copy under the assigned evidence folder only. Record SHA256 and DB integrity for the backup/copy.
6. Record exact rollback command using the real DB backup path. This is evidence only; do not execute rollback.
7. Build a staging candidate from the exact frozen production DB pre-SHA. Do not use Agent734's copied DB as the staging target.
8. Run preflight/focused tests that are relevant to the corrected command family, at minimum:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_apply_rebuild_snapshot_production_safe.py tests/test_rebuild_snapshot_negative_active_zero.py tests/test_validate_write_side_gating.py
python3 -m py_compile scripts/apply_rebuild_snapshot_production_safe.py scripts/rebuild_snapshot.py
python3 scripts/validate_write_side_gating.py --manifest config/write_side_gating_manifest.yaml
```

9. Run the corrected Agent734 command family on staging/copies only.
10. The snapshot step must use `scripts/apply_rebuild_snapshot_production_safe.py --mode simulate` on the staging DB only.
11. Use the same control family as Agent734: expected pre-SHA, expected existing rows, expected row delta, expected current stock total, expected inbound stock total, backup, staging, integrity checks, and rollback metadata.
12. Because this is a fresh production boundary, do not blindly hard-code Agent734's old row totals. Derive exact expected controls from the fresh staging plan/copy, compare them to Agent734 evidence, and close YELLOW/RED if differences are not explained by the fresh boundary.
13. Strict `23` quarantine must use the production-safe wrapper on staging only.
14. Header-only `252` quarantine must use the production-safe wrapper on staging only.
15. Rerun pinned `2026-05-04` validators on the staging candidate:

```bash
python3 scripts/validate_policy_source_freshness.py --db <staging_db> --as-of 2026-05-04 --strict --json
python3 scripts/validate_operational_stock_integration_gates.py --db <staging_db> --as-of 2026-05-04 --json
python3 scripts/validate_order_cashflow_coverage.py --db <staging_db> --as-of 2026-05-04 --strict --json
python3 scripts/validate_cashflow_actual_model_separation.py --db <staging_db> --anchor-date 2026-05-04 --strict --json
python3 scripts/validate_cashflow_invariants.py --db <staging_db>
```

16. Produce row-count, leakage, order-level cash preservation, validator, and warning-class matrices.
17. Prove these warning/quarantine semantics exactly:
    - strict product-identity quarantine table: `23` rows unless there is reviewed fresh-boundary evidence for a different value;
    - header-only source-gap quarantine table: `252` rows unless there is reviewed fresh-boundary evidence for a different value;
    - operational validator warning visibility: `23` product-identity and `251` header-only unless there is reviewed fresh-boundary evidence for a different value;
    - combined cohort: `275` rows unless there is reviewed fresh-boundary evidence for a different value.
18. Prove no strict/header/combined cohort leaks into product truth: fact entries, stock rows, product cashflow, product profit, or published SKU sales truth.
19. Prove order-level `CASH_IN` is preserved, or close YELLOW/RED with exact differences and source evidence.
20. Capture production DB/workbook SHA again before closeout. Any unexplained production DB/workbook drift closes RED.
21. Draft owner-request packet candidate only as `REVIEW_REQUIRED_NOT_SENT_TO_OWNER`.
22. Draft a CodeCaptain review request prompt for the Agent735 evidence. Do not create an Oracle pack unless the orchestrator asks later.

## Gate Semantics

`GREEN`:

- fresh boundary proof is complete;
- production DB integrity is `ok`;
- sidecar/lsof state is safe;
- backup/copy SHA, backup integrity, and rollback command are complete;
- staging candidate is tied to the exact frozen pre-SHA;
- corrected Agent734 command family replay completes on staging only;
- pinned `2026-05-04` validators pass or have only reviewed-safe warnings;
- row-count, leakage, cash-preservation, and warning matrices are present;
- `23`, `252`, `251`, and combined `275` semantics remain visible and do not become product truth;
- no production/workbook/scheduler/external mutation occurred;
- owner-request packet remains review-required and not sent.

`YELLOW`:

- evidence is useful but one non-mutating review item remains ambiguous or needs CodeCaptain/orchestrator curation before owner-facing review.

`RED`:

- any forbidden mutation;
- owner authorization requested;
- old Agent54 reused or Agent64 activated;
- DB integrity not `ok`;
- unsafe sidecar/holder state;
- missing backup/rollback proof;
- unexplained DB/workbook drift;
- failed pinned validator;
- missing or changed warning class without reviewed explanation;
- header-only or strict quarantine rows leak into product truth;
- ledger-only wrapper used where simulate wrapper is required;
- direct unsafe script used instead of wrapper;
- Option C promoted beyond validate-only.

## Closeout

Write closeout with READCHECK, files written, commands run, exact DB/workbook SHAs, integrity, sidecar/lsof, backup/rollback, staging replay, validator summary, row/leakage/cash/warning matrices, mutation statement, recommended next step, and standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
