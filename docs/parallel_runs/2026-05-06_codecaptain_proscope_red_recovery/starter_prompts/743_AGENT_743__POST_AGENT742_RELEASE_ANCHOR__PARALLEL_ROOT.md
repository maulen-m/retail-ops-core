# Agent 743 - Post-Agent742 Release Anchor

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_743_post_agent742_release_anchor_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_743_release_anchor_evidence/`

Assigned release-anchor folder:

`~/Docs/Autonomous_business/exports/validation/db_only_repair_release/2026-05-09_agent742/`

Parallel group:

`agent743_744_release_anchor_root`

## Mission

Create a durable post-Agent742 DB-only repair release anchor. This is an audit/release artifact for the successful DB-only apply, not an owner-truth publication and not Option C production automation approval.

## Required Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/CODECAPTAIN_POST_AGENT742_OPTION_C_PREPROD_REVIEW_20260509.md`
7. `~/Docs/Oracle/Autonomous_business/2026-05-09/192420_TASK-000_codecaptain-option-c-preprod-review-after-agent742/answer/Code_Captain_09.05.2026_20_38_06.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_742_db_only_repair_apply_closeout.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_742_db_only_repair_apply_evidence/production_dynamic_apply_with_all_prod_gates/status.txt`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_742_db_only_repair_apply_evidence/production_dynamic_apply_with_all_prod_gates/final_db_sha.out`
11. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_742_db_only_repair_apply_evidence/production_dynamic_apply_with_all_prod_gates/final_db_integrity.out`
12. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_742_db_only_repair_apply_evidence/production_dynamic_apply_with_all_prod_gates/POST_APPLY_KEY_TABLE_COUNTS.tsv`
13. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_742_db_only_repair_apply_evidence/production_dynamic_apply_with_all_prod_gates/POST_APPLY_LEAKAGE_MATRIX.tsv`
14. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_742_db_only_repair_apply_evidence/production_dynamic_apply_with_all_prod_gates/POST_APPLY_CASH_PRESERVATION_MATRIX.tsv`
15. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_742_db_only_repair_apply_evidence/production_dynamic_apply_with_all_prod_gates/POST_APPLY_WARNING_CLASS_VISIBILITY_MATRIX.tsv`

## Write Boundary

Allowed writes:

- assigned closeout;
- assigned evidence folder;
- release-anchor folder:
  `~/Docs/Autonomous_business/exports/validation/db_only_repair_release/2026-05-09_agent742/`
- optional repo run note under:
  `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/`
  if needed to point to the release anchor.

Forbidden:

- Do not mutate `~/Docs/Autonomous_business/db/app.db`.
- Do not mutate `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`.
- Do not mutate schedulers.
- Do not write to external systems, Kaspi/API, ads platforms, Google, banks, browser automation, Web_automation, or external repos.
- Do not install or enable Option C automation.
- Do not ask owner for approval.
- Do not reuse old Agent54 phrase or activate Agent64.

## Required Release Anchor Artifacts

Create at minimum:

- `POST_AGENT742_RELEASE_ANCHOR.md`
- `post_agent742_release_anchor.json`
- `ROLLBACK_POINTER.md`
- `GIT_STATE.txt`
- `EVIDENCE_FILE_INDEX.tsv`

The release anchor must include:

- production DB path;
- pre-apply DB SHA;
- final DB SHA `9c51a7fd5654379e10232176e922661709481caa5752a9fc6fffd09d24c5ee53`;
- protected workbook path;
- protected workbook SHA `3ad4b81c39b125c48b34c02afb8a30eafd348658e07afd27c11f628b8987025c`;
- final DB integrity `ok`;
- final holder/sidecar status from Agent742 evidence and, if cheap, a fresh read-only sample;
- final backup path, backup SHA, backup integrity, and rollback command;
- owner authorization boundary and exclusions;
- exact command-family/source evidence references;
- final validator family;
- post-apply key table counts;
- warning visibility matrix;
- leakage matrix;
- cash preservation matrix;
- git branch, HEAD, and focused dirty status;
- explicit statement that Option C production remains blocked.

## Required Checks

Run these read-only checks and record outputs:

```bash
shasum -a 256 db/app.db excel_ui/SALES_KSP_CRM_V3.xlsx
sqlite3 -readonly db/app.db 'PRAGMA integrity_check;'
lsof db/app.db excel_ui/SALES_KSP_CRM_V3.xlsx || true
ls db/app.db-wal db/app.db-shm db/app.db-journal 2>/dev/null || true
git rev-parse HEAD
git rev-parse --abbrev-ref HEAD
git status --short
```

Do not fail solely because the working tree is dirty; record the dirty state and make clear that true Option C production requires a later clean/reviewed release split.

## Gate Semantics

`GREEN`:

- release anchor exists and is internally consistent;
- DB/workbook SHAs match Agent742 values;
- DB integrity is `ok`;
- rollback pointer resolves to a real backup path;
- warning/leakage/cash matrices are referenced and preserved;
- no forbidden mutation occurred.

`YELLOW`:

- anchor is written but needs orchestrator review for dirty-state ambiguity, evidence mismatch, or missing non-critical context.

`RED`:

- current DB SHA differs from Agent742 final SHA without reviewed explanation;
- workbook SHA differs from protected value without authorization;
- DB integrity fails;
- rollback pointer is missing or invalid;
- any forbidden mutation occurs.

## Closeout

Write the closeout with READCHECK, files written, commands run, release-anchor path, current DB/workbook SHAs, integrity result, rollback pointer, gate rationale, and standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
