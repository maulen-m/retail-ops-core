# Agent 731 - Fresh Owner-Request Preflight, No Apply

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_731_fresh_owner_request_preflight_no_apply_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_731_evidence/`

Parallel group:

`agent731_fresh_owner_request_preflight`

Dependency:

Run only after Agent730 is reviewed GREEN and CodeCaptain returns `GREEN_TO_OPEN_FRESH_OWNER_REQUEST_PREFLIGHT_ONLY`.

## Mission

Open the fresh owner-request preflight lane authorized by CodeCaptain. This is a no-owner-ask and no-production-mutation lane.

Freeze the current production DB/workbook boundary, create backup/rollback evidence, build a staging candidate from that exact frozen pre-SHA, run the hardened command family on staging/copies only, rerun pinned `2026-05-04` validators, and produce a review-required owner-request packet candidate.

The owner has broadly approved doing required safe changes to achieve final success, but that broad approval is not the later exact reviewed production-apply phrase. Do not ask for, infer, activate, or reuse any authorization phrase in this lane.

You are not alone in the codebase. Do not revert or overwrite unrelated edits by others.

## Required Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/CODECAPTAIN_AGENT72G_GREEN_PREFLIGHT_ONLY_20260508.md`
7. `~/Docs/Oracle/Autonomous_business/2026-05-08/213828_AGENT72G_codecaptain_review_pack_after_write_gate_integration/asnwer/Code_Captain_2026-05-08_22_22_00.md`
8. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AGENT729_ORCHESTRATOR_REVIEW_20260508.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_72g_codecaptain_review_pack_closeout.md`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_72f_write_gate_integration_temp_proof_closeout.md`
11. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_72f_evidence/TEMP_PROOF_SUMMARY.json`
12. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_72f_evidence/temp_proof/snapshot_wrapper_apply_20260504_after_orchestrator_fix/summary.json`

## Write Boundary

Allowed writes:

- assigned closeout;
- assigned evidence folder;
- staging/copy DBs under assigned evidence folder only;
- review-required owner-request packet candidate under assigned evidence folder only.

Forbidden:

- Do not mutate `~/Docs/Autonomous_business/db/app.db`.
- Do not mutate `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`.
- Do not mutate schedulers.
- Do not write to browser, Web_automation, Kaspi/API, ads platforms, Google, banks, or external systems.
- Do not ask the owner for authorization.
- Do not production-apply.
- Do not activate Agent64.
- Do not reuse or quote old Agent54 as active.
- Do not run direct unsafe production materializers in place of wrappers.
- Do not use ad hoc SQL against production.

## Required Evidence Files

Create all of these in the assigned evidence folder:

1. `EVIDENCE_MANIFEST.md`
2. `FRESH_PRODUCTION_BOUNDARY_REPORT.md`
3. `DRIFT_STABILITY_REPORT.md`
4. `BACKUP_ROLLBACK_EVIDENCE.md`
5. `STAGING_COMMAND_FAMILY_REPLAY.md`
6. `PINNED_VALIDATOR_MATRIX.tsv`
7. `FRESH_ROW_COUNT_MATRIX.tsv`
8. `FRESH_LEAKAGE_MATRIX.tsv`
9. `ORDER_LEVEL_CASH_PRESERVATION_MATRIX.tsv`
10. `WARNING_CLASS_VISIBILITY_MATRIX.tsv`
11. `OWNER_REQUEST_PACKET__REVIEW_REQUIRED_NOT_SENT_TO_OWNER.md`
12. `CODECAPTAIN_AGENT731_REVIEW_REQUEST_PROMPT.md`

## Required Work

1. Capture fresh production DB SHA256, workbook SHA256, mtimes, and protected git status.
2. Run production DB `PRAGMA integrity_check` read-only.
3. Check SQLite sidecars near `db/app.db` and `lsof` holders for DB and sidecars.
4. If sidecar/holder state is unsafe, close RED before copying.
5. Create timestamped DB backup/copy and workbook copy under the assigned evidence folder only. Record SHA256 and DB integrity for the backup/copy.
6. Record exact rollback command using the real DB backup path. This is evidence only; do not execute rollback.
7. Build a staging candidate from the exact frozen production DB pre-SHA.
8. Run the hardened command family on staging/copies only. Use final wrappers/commands and env gates where the script requires `--apply` against staging. Never target production DB.
9. Rerun pinned `2026-05-04` validators on the staging candidate.
10. Produce row-count, leakage, order-level cash preservation, validator, and warning-class matrices.
11. Prove `ORDER_ENTRY_PRODUCT_IDENTITY_QUARANTINED=23`, `ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_QUARANTINED=252`, and combined `275` remain visible and do not leak into product truth.
12. Capture DB/workbook SHA again before closeout. Any unexplained production DB/workbook drift closes RED.
13. Draft owner-request packet candidate only as `REVIEW_REQUIRED_NOT_SENT_TO_OWNER`.

## Gate Semantics

`GREEN`:

- fresh boundary proof is complete;
- DB integrity is `ok`;
- sidecar/lsof state is safe;
- backup/copy SHA, backup integrity, and rollback command are complete;
- staging candidate is tied to the exact frozen pre-SHA;
- hardened command family replay completes on staging only;
- pinned `2026-05-04` validators pass or have only reviewed-safe warnings;
- row-count, leakage, cash-preservation, and warning matrices are present;
- `23`, `252`, and combined `275` remain visible as warning/quarantine classes and do not become product truth;
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
- direct unsafe script used instead of wrapper;
- Option C promoted beyond validate-only.

## Closeout

Write closeout with READCHECK, files written, commands run, exact DB/workbook SHAs, integrity, sidecar/lsof, backup/rollback, staging replay, validator summary, row/leakage/cash/warning matrices, mutation statement, recommended next step, and standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
