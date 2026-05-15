# Agent 55 - Drift Forensics Read-Only

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_55_drift_forensics_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_55_evidence/`

## Mission

Explain the May 6 production drift that made Agent 54A return RED.

You are not approving production apply. You are not repairing production. You are building an evidence-backed drift dossier that tells the orchestrator whether the current production/workbook state should be preserved, restored, merged, or kept RED pending more evidence.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Oracle/Autonomous_business/2026-05-06/120135_TASK-000_codecaptain-proscope-system-review/answer/Code_Captain_2026-05-06_12_32_00_GMT+5.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_54a_may6_freshness_asof_preflight_closeout.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_53_option_b_agent31_production_safe_wrapper_temp_proof_after_52_green_closeout.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_53_evidence/AGENT54_PRODUCTION_APPLY_READINESS_CONTRACT.md`

## Write Boundary

Allowed writes:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_55_drift_forensics_closeout.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_55_evidence/**`

Forbidden:

- Do not mutate `~/Docs/Autonomous_business/db/app.db`.
- Do not edit `excel_ui/SALES_KSP_CRM_V3.xlsx`.
- Do not edit repo files.
- Do not run write-enabled scripts.
- Do not ask owner for Agent 54 authorization.
- Do not launch Agent 54.
- Do not call external/live systems.
- Do not copy full production DB unless explicitly justified in closeout; prefer read-only queries and small evidence files.

## Required Analysis

Build a read-only timeline and drift dossier covering:

- current production DB SHA, workbook SHA, mtimes, sidecars, lsof status, and integrity;
- protected Agent 54 contract DB/workbook SHAs;
- Agent 53 temp DB SHA and row matrix;
- current production row matrix for key tables;
- table-level row deltas versus Agent 53 temp;
- max observed dates/run IDs where available;
- recent DB backup files and their mtimes/SHAs;
- recent run folders, tmux manifests, completion records, launchd jobs, shell-visible scripts, and evidence trails that may explain drift;
- whether production drift looks legitimate, accidental, partial, scheduler-driven, manual workbook save, or unknown;
- whether current production should be preserved, restored, merged, or kept RED pending more evidence.

## Suggested Read-Only Evidence Commands

Use only as appropriate:

```bash
date '+%Y-%m-%d %H:%M:%S %z %Z'
git -C ~/Docs/Autonomous_business status --short -- db/app.db excel_ui/SALES_KSP_CRM_V3.xlsx
ls -l ~/Docs/Autonomous_business/db/app.db*
shasum -a 256 ~/Docs/Autonomous_business/db/app.db ~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx
sqlite3 -readonly ~/Docs/Autonomous_business/db/app.db 'PRAGMA integrity_check;'
lsof ~/Docs/Autonomous_business/db/app.db
find ~/Docs/Autonomous_business_agent_handoffs -path '*agent_5*evidence*' -o -path '*agent_53_evidence*' -o -path '*db_backups*'
find ~/Docs/Autonomous_business/runs/tmux_orchestration -maxdepth 3 -type f -mtime -3
```

Do not use destructive shell commands.

## Success Criteria

Closeout must include:

- standalone `Gate: GREEN/YELLOW/RED`;
- READCHECK with files read;
- exact current SHAs and protected expected SHAs;
- drift timeline;
- row-count/delta summary;
- likely root cause classification;
- preserve/restore/merge/keep-RED recommendation;
- evidence file list;
- what, if anything, needs owner clarification in plain English.

## Gate Semantics

`GREEN`:

- drift cause is evidence-backed enough to choose the next baseline action safely.

`YELLOW`:

- evidence narrows the likely cause, but owner/operator clarification or a second read-only pass is needed.

`RED`:

- active writer risk, hidden mutation risk, evidence contradiction, or no safe baseline recommendation.
