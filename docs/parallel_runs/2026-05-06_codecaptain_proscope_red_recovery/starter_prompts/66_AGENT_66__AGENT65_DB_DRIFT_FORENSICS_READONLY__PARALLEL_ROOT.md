# Agent 66 - Agent65 DB Drift Forensics Read-Only

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_66_agent65_db_drift_forensics_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_66_evidence/`

## Mission

Explain the Agent65 mid-lane production DB drift.

CodeCaptain confirmed Agent65 is `RED` and requires read-only drift forensics before any new owner-request preflight, current-baseline replay, repair/apply contract, owner phrase request, or production apply.

Your job is to identify what changed between Agent65's initial DB boundary and refreshed DB boundary, and whether the likely writer/process can be explained well enough for the orchestrator to safely plan a frozen current-baseline temp replay.

This is a read-only forensic lane. You are not repairing production and not approving anything.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/CODECAPTAIN_AGENT65_RED_PREFLIGHT_REVIEW_20260507.md`
7. `~/Docs/Oracle/Autonomous_business/2026-05-07/170703_TASK-000_codecaptain-agent65-red-preflight-review/Answer/Code_Captain_2026-05-07_17_50_00.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_65_owner_request_preflight_activation_closeout.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_65_evidence/EVIDENCE_MANIFEST.md`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_65_evidence/FRESH_PRODUCTION_BOUNDARY_REPORT.md`
11. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_65_evidence/BACKUP_ROLLBACK_EVIDENCE.md`
12. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_65_evidence/FRESH_ROW_COUNT_MATRIX.tsv`
13. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_65_evidence/FRESH_ROW_COUNT_MATRIX.initial_855e3c52.tsv`
14. Your assigned starter prompt.

Do not read Agent67's report before publishing your own first-pass closeout.

## Key Evidence Inputs

Agent65 initial byte-identical DB copy:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_65_evidence/backups/app_db_bytecopy_before_owner_request_preflight_20260507_162549.db`

Agent65 refreshed post-drift byte-identical DB copy:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_65_evidence/backups/app_db_bytecopy_before_owner_request_preflight_post_drift_20260507_163602.db`

Initial DB SHA:

`855e3c52442415e69bb161014b3b03d8c848b1bd0de483bca24f05f30f1df33d`

Refreshed DB SHA:

`9a3ec60ec9842d254a5e627133d0b3bfcd89a2254fc04cd610c98bc3e3e954a0`

Observed drift window:

`2026-05-07 16:06:42` to `2026-05-07 16:33:39` Asia/Almaty.

## Write Boundary

Allowed writes:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_66_agent65_db_drift_forensics_closeout.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_66_evidence/**`

Forbidden:

- Do not mutate `~/Docs/Autonomous_business/db/app.db`.
- Do not mutate either Agent65 backup DB.
- Do not edit `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`.
- Do not edit repo files.
- Do not pause, unload, or mutate schedulers.
- Do not call live APIs, web UIs, browser automation, banks, Kaspi, ads platforms, Google, Web_automation, or external systems.
- Do not ask the owner for authorization.
- Do not production-apply.
- Do not use ad hoc SQL mutation.

## Required Analysis

Produce `DRIFT_FORENSICS_REPORT.md` in the assigned evidence folder.

The report must include:

- READCHECK with exact files read.
- Current production DB/workbook SHA, mtime, integrity, sidecar/lsof state at analysis time.
- Table-level schema diff between the initial and refreshed Agent65 DB copies.
- Table-level row-count diff.
- Content-level changed-table report, not only row counts. If practical, compute per-table deterministic hashes or sampled primary-key checksums.
- Recent `fact_runs` or equivalent run table/timestamp evidence if present.
- Recent max/min timestamps for likely operational tables.
- Relevant tmux orchestration manifests/completions around the drift window.
- Relevant launchd/scheduler/process evidence around the drift window.
- Whether the drift appears scheduler-driven, agent-driven, manual, SQLite metadata/page-only, unknown, or mixed.
- Whether a future quiet-window control is required before Agent68 current-baseline temp replay.

## Suggested Read-Only Commands

Adapt safely as needed:

```bash
date '+%Y-%m-%d %H:%M:%S %z %Z'
shasum -a 256 ~/Docs/Autonomous_business/db/app.db ~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx
stat -f '%N\t%Sm\t%z' -t '%Y-%m-%d %H:%M:%S %z' ~/Docs/Autonomous_business/db/app.db ~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx
find ~/Docs/Autonomous_business/db -maxdepth 1 -name 'app.db-*' -print
lsof ~/Docs/Autonomous_business/db/app.db ~/Docs/Autonomous_business/db/app.db-wal ~/Docs/Autonomous_business/db/app.db-shm 2>/dev/null || true
sqlite3 -readonly ~/Docs/Autonomous_business/db/app.db 'PRAGMA integrity_check;'
launchctl list | rg -i 'kaspi|google|stock|cashflow|autonomous|operational|scheduler' || true
find ~/Docs/Autonomous_business/runs/tmux_orchestration -maxdepth 4 -type f -mtime -2 -print
find ~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery -maxdepth 4 -type f -mtime -2 -print
```

If you create a helper script to compare SQLite databases, write it only inside your assigned evidence folder and run it against read-only backup files or copied temp files inside your assigned evidence folder.

## Gate Semantics

`GREEN`:

- The likely drift cause or writer/process is evidence-backed.
- Changed tables/content are identified or the change is convincingly classified as non-semantic SQLite/page metadata.
- Future replay control requirements are explicit.
- No production/workbook/scheduler/external mutation occurred.

`YELLOW`:

- Drift is narrowed but not fully proven, or future quiet-window controls are required before Agent68.

`RED`:

- Active writer risk remains now.
- Drift cause is unknown enough that replay would be unsafe.
- Evidence conflicts or any forbidden mutation occurred.

## Closeout Requirements

The closeout must include:

- standalone `Gate: GREEN/YELLOW/RED` line;
- exact files written;
- exact commands run;
- current boundary summary;
- initial-vs-refreshed DB diff summary;
- likely writer/process classification;
- whether Agent68 may launch now, must wait for quiet-window authorization, or must remain blocked;
- evidence file list;
- plain-English owner clarification needed, if any.
