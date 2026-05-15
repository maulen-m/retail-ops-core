# Fixed Execution Boundary + C3 Wave Starters

Generated at: `2026-05-12T13:17:02+0500`

## Plan

`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/FIXED_EXECUTION_BOUNDARY_C3_WAVE_PLAN_20260512_131702.md`

## Handoff

`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/FIXED_EXECUTION_BOUNDARY_C3_WAVE_ORCHESTRATOR_HANDOFF_20260512_131702.md`

## Launch Now

- Agent775: boundary freeze and drift forensics.
- Agent776: copied-temp C3 source/policy replay feasibility.
- Agent777: non-ads publication blocker map.

## Gated Later

- Agent778: synthesis after Agents775-777 closeouts are reviewed.

## Receiver-Only Rule

Use an attested inert receiver pane. Do not use live chat visibility.

```bash
python3 ~/.codex/skills/tmux-agent-orchestrator/scripts/launch_tmux_agents.py \
  --repo ~/Docs/Autonomous_business \
  --starter-folder ~/Docs/Autonomous_business/docs/agent_handoffs/FIXED_EXECUTION_BOUNDARY_C3_WAVE_STARTERS_20260512_131702 \
  --session autonomous_business \
  --agents 775,776,777 \
  --reuse-panes %104,%105,%106 \
  --no-start-sessions \
  --run-id fixed_execution_boundary_c3_wave_20260512_131702 \
  --mode hybrid \
  --orchestrator-ping-mode receiver \
  --orchestrator-pane %328 \
  --parallel-groups 775=fixed_boundary_root,776=fixed_boundary_root,777=fixed_boundary_root
```
