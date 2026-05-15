# Agent 747 - Current `dec77` Boundary Release Anchor

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_747_current_dec77_release_anchor_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_747_current_dec77_release_anchor_evidence/`

Assigned release-anchor folder:

`~/Docs/Autonomous_business/exports/validation/db_only_repair_release/2026-05-09_current_dec77_reanchor/`

Parallel group:

`agent747_748_current_dec77_reanchor_root`

## Mission

Create a durable release anchor for the current production DB boundary after Agent746 forensics showed the old Agent742 SHA boundary is stale.

This is a release/evidence artifact only. It is not an owner-truth publication and not Option C production automation approval.

## Required Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/TMUX_PING_ROUTING_INCIDENT_20260509.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_746_orchestrator_db_drift_forensics_closeout.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_746_orchestrator_db_drift_forensics_evidence/01_current_sha.out`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_746_orchestrator_db_drift_forensics_evidence/05_key_table_counts.tsv`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_742_db_only_repair_apply_closeout.md`
11. `~/Docs/Oracle/Autonomous_business/2026-05-09/192420_TASK-000_codecaptain-option-c-preprod-review-after-agent742/answer/Code_Captain_09.05.2026_20_38_06.md`

## Current Boundary

Expected current production DB SHA:

`dec77f37cc63147e54e9085a6a0f9564d9ead9e57aea0d8483dc0473886bee64`

Expected workbook SHA:

`3ad4b81c39b125c48b34c02afb8a30eafd348658e07afd27c11f628b8987025c`

Expected current status:

- DB integrity: `ok`
- key table counts match Agent746 evidence
- source freshness strict passes
- operational stock integration gate is `GREEN` with warning-only findings
- order/cashflow coverage pinned to `2026-05-04` passes
- cashflow actual/model separation pinned to `2026-05-04` passes
- cashflow invariants pass

## Write Boundary

Allowed writes:

- assigned closeout;
- assigned evidence folder;
- assigned release-anchor folder;
- optional short pointer note under `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/` if needed.

Forbidden:

- Do not mutate `~/Docs/Autonomous_business/db/app.db`.
- Do not mutate `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`.
- Do not mutate schedulers or LaunchAgents.
- Do not write to external systems, Kaspi/API, ads platforms, Google, banks, browser automation, Web_automation, or external repos.
- Do not install or enable Option C automation.
- Do not ask owner for approval.
- Do not reuse old Agent54 phrase or activate Agent64.

## Required Release Anchor Artifacts

Create at minimum:

- `CURRENT_DEC77_RELEASE_ANCHOR.md`
- `current_dec77_release_anchor.json`
- `CURRENT_BOUNDARY_BACKUP_POINTER.md`
- `GIT_STATE.txt`
- `EVIDENCE_FILE_INDEX.tsv`

Create a current-boundary backup copy only after `lsof` shows no DB/workbook holders:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_747_current_dec77_release_anchor_evidence/backups/app_current_dec77_release_anchor_<timestamp>.db`

Record backup SHA and `PRAGMA integrity_check`.

## Required Checks

Run these read-only checks and record outputs:

```bash
date '+%Y-%m-%dT%H:%M:%S%z'
shasum -a 256 db/app.db excel_ui/SALES_KSP_CRM_V3.xlsx
stat -f '%N\t%z\t%m\t%Sm' db/app.db excel_ui/SALES_KSP_CRM_V3.xlsx
sqlite3 -readonly db/app.db 'PRAGMA integrity_check; PRAGMA schema_version; PRAGMA page_count; PRAGMA freelist_count;'
lsof db/app.db excel_ui/SALES_KSP_CRM_V3.xlsx || true
ls db/app.db-wal db/app.db-shm db/app.db-journal 2>/dev/null || true
python3 scripts/validate_policy_source_freshness.py --strict --json
python3 scripts/validate_operational_stock_integration_gates.py --json
python3 scripts/validate_order_cashflow_coverage.py --as-of 2026-05-04 --strict --json
python3 scripts/validate_cashflow_actual_model_separation.py --anchor-date 2026-05-04 --strict --json
python3 scripts/validate_cashflow_invariants.py
git rev-parse HEAD
git rev-parse --abbrev-ref HEAD
git status --short
```

Also save key count, warning visibility, leakage, and cash preservation matrices using the Agent746/Agent742 expected values as the target. Do not hide the `23` product-identity warnings, the `252` header-only table rows, or the validator-visible header-only warning count.

## Gate Semantics

`GREEN`:

- release anchor exists and is internally consistent;
- current DB SHA equals `dec77...ee64` at start and final sample;
- workbook SHA equals protected value;
- DB integrity is `ok`;
- current-boundary backup exists, SHA is recorded, and backup integrity is `ok`;
- required validators pass;
- warning/leakage/cash matrices remain visible and preserved;
- no forbidden mutation occurred.

`YELLOW`:

- validators pass but evidence needs orchestrator review for dirty-state ambiguity, harmless holder ambiguity, or non-critical context gaps.

`RED`:

- current DB SHA differs from `dec77...ee64` without reviewed explanation;
- workbook SHA differs from protected value;
- DB integrity fails;
- required validator fails;
- backup pointer is missing/invalid;
- warning cohorts become hidden/productized;
- leakage or cash preservation mismatch appears;
- any forbidden mutation occurs.

## Closeout

Write the closeout with READCHECK, files written, commands run, release-anchor path, current DB/workbook SHAs, integrity result, backup pointer, gate rationale, and standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
