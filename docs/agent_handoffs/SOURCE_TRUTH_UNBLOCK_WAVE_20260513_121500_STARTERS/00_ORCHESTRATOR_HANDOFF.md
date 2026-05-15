# Source Truth Unblock Wave Orchestrator Handoff

Workflow: `source_truth_unblock_wave_20260513_121500`

Purpose: attack the remaining source-truth blockers after Agents781-787 completed on the accepted `7cfe...` DB / `4e7...` workbook boundary.

## Control Artifacts

- Repo: `~/Docs/Autonomous_business`
- Current gate tracker: `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/current_gate_status_agent750_waiting_codecaptain.json`
- Accepted-boundary recheck: `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/ACCEPTED_BOUNDARY_PROOF_WAVE_RECHECK_20260513_103706.md`
- Live ping policy: `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/TMUX_LIVE_ORCHESTRATOR_PING_POLICY_20260513_121305.md`
- Live ping repo policy: `~/Docs/Autonomous_business/config/tmux_orchestrator_live_visibility_enabled.md`
- Starter folder: `~/Docs/Autonomous_business/docs/agent_handoffs/SOURCE_TRUTH_UNBLOCK_WAVE_20260513_121500_STARTERS`

## Accepted Boundary

- DB SHA-256: `7cfe3ebc5df4867e28c57b4ed392f665dfa8143c44db4d54dde11fdb41f889d6`
- DB mtime: `2026-05-12T19:11:05+0500`
- Workbook SHA-256: `4e7d18e16d2c16779de5f1f91eadea231c92143c1da29cdee9d0441c7592444c`
- Workbook mtime: `2026-05-12T17:06:10+0500`

## Sequence And Parallelism

All five agents are parallel siblings under group `source_truth_unblock_wave`.

- Agent788: cashflow copied-temp replay for `2026-05-05..2026-05-11`.
- Agent789: stock/order identity-bearing source evidence discovery and copied-temp route.
- Agent790: ads source-readiness packet for bounded live-readonly approval and local proof finalization.
- Agent791: PO inbound source decision packet and replacement-source feasibility.
- Agent792: exception owner-decision packet for 9 open `STOCK/HIGH` controls.

## Live Ping Rule

This wave must use tmux group-last completion. Each agent writes its closeout first, then runs `agent_complete.py`. The last completed agent pings the registered live orchestrator chat through the manifest's receiver plus `LIVE` visibility route.

Ping is only a wake-up signal. Closeout files, standalone `Gate:` lines, marker JSON, watcher output, and validation evidence are the authority.

## Shared Stop Conditions

Stop and close out instead of improvising if the task would require:

- production DB mutation
- workbook mutation
- scheduler restore or mutation
- external writes
- owner publication
- owner approval request
- cash movement
- PO commitment
- ad spend
- price changes
- stock changes
- browser/login automation
- credential/session export

Gate: GREEN
