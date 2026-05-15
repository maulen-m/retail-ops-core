# Agent793 Starter - Boundary Reanchor And Quiet Proof

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-13_autonomous_phase0_3_source_truth_wave/agent793_boundary_reanchor_20260513_192243_closeout.md`

## Bootstrap

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AUTONOMOUS_PHASE0_3_SOURCE_TRUTH_WAVE_PLAN_20260513_192243.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AUTONOMOUS_PHASE0_3_SOURCE_TRUTH_WAVE_HANDOFF_20260513_192243.md`
5. this starter prompt

## Mission

Create the current accepted boundary packet for the autonomous Phase 0-3 source-truth wave.

## Scope

Read-only only.

Allowed writes:

- evidence under `~/Docs/Autonomous_business/exports/validation/autonomous_phase0_3_source_truth_wave/20260513_192243/agent793_boundary_reanchor/`
- assigned closeout only.

Forbidden:

- production DB mutation;
- workbook mutation;
- scheduler/LaunchAgent mutation;
- source pointer changes;
- owner publication;
- external writes.

## Required Work

1. Record current timestamp.
2. Record current git status summary without modifying unrelated changes.
3. Record production DB SHA-256, mtime, size, `PRAGMA integrity_check`, SQLite sidecar state, and `lsof` holder state for `~/Docs/Autonomous_business/db/app.db`.
4. Record protected workbook SHA-256, mtime, size, and `lsof` holder state for `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`.
5. Run read-only daily automation checks:
   - `python3 scripts/manage_business_automation.py status --scope daily-ops --output-json <evidence>/daily_ops_status.json`
   - `python3 scripts/manage_business_automation.py verify --scope daily-ops --expect running --output-json <evidence>/daily_ops_verify_running.json`
6. If a DB/workbook holder is present, identify the process and decide if it is a hard boundary stopline.
7. Write a closeout with:
   - standalone `Gate: GREEN` only if the current boundary was captured safely and no active holder/sidecar stopline blocks downstream copied-temp work;
   - `Domain Status: BOUNDARY_GREEN` or exact blocker;
   - exact accepted DB/workbook SHA pair;
   - evidence paths;
   - explicit non-mutation statement.

Remember: `Gate` is assignment health. If you cannot safely establish the boundary, use `Gate: RED`.
