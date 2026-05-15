# Source Truth Unblock Reanchored Wave Orchestrator Handoff

Workflow: `source_truth_unblock_reanchored_wave_20260513_140535`

Purpose: relaunch the source-truth unblock work after the `7cfe...` to `04c764...` DB drift was proven to be header-only SQLite metadata drift and dry-run policy paths were hardened to readonly.

## Control Artifacts

- Repo: `~/Docs/Autonomous_business`
- Plan: `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/SOURCE_TRUTH_UNBLOCK_REANCHORED_WAVE_PLAN_20260513_140535.md`
- Boundary/hardening memo: `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/BOUNDARY_DRIFT_FORENSICS_AND_READONLY_HARDENING_20260513_140535.md`
- Current gate tracker: `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/current_gate_status_agent750_waiting_codecaptain.json`
- Previous source-truth wave recheck: `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/SOURCE_TRUTH_UNBLOCK_WAVE_RECHECK_20260513_124526.md`
- Starter folder: `~/Docs/Autonomous_business/docs/agent_handoffs/SOURCE_TRUTH_UNBLOCK_REANCHORED_WAVE_20260513_140535_STARTERS`

## Active Review-Only Boundary

- DB SHA256: `04c76434399eb7e146037271fa121d69f71ae64195ac5a3436ccfed080b18f99`
- DB mtime: `2026-05-13T12:21:48+0500`
- DB integrity: `ok`
- Workbook SHA256: `4e7d18e16d2c16779de5f1f91eadea231c92143c1da29cdee9d0441c7592444c`
- Workbook mtime: `2026-05-12T17:06:10+0500`

## Sequence And Parallelism

All five agents are parallel siblings under group `source_truth_reanchored_wave`.

- Agent793: cashflow source truth and missing-cost unblock packet.
- Agent794: stock/order identity-bearing order-entry source capture/proof packet.
- Agent795: ads source capture/adoption packet.
- Agent796: PO inbound fresh source decision and copied-temp feasibility packet.
- Agent797: exception owner/source fact resolution packet.

## Ping Rule

This wave must use tmux group-last completion. Each agent writes its closeout first, then runs the manifest-specific `agent_complete.py` command appended by the launcher.

The ping is only a wake-up signal. The closeout files, standalone `Gate:` lines, marker JSON, watcher output, and validation evidence are the authority.

## Shared Stop Conditions

Stop and close out instead of improvising if the task would require:

- production DB mutation
- workbook mutation
- scheduler restore or mutation
- external writes
- owner publication
- owner approval request
- cash movement
- supplier payment
- PO commitment
- ad spend
- price changes
- stock changes
- credential/session export

Gate: GREEN
