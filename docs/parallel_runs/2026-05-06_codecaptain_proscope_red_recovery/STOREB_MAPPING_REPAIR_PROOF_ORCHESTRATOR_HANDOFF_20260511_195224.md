# STOREB Mapping Repair Proof Orchestrator Handoff

Generated at: `2026-05-11T19:52:24+0500`

Gate: `READY_TO_LAUNCH_AGENT773_MONITOR_ONLY`

## Launch Shape

Launch one execution agent:

- Agent: `773`
- Starter folder: `~/Docs/Autonomous_business/docs/agent_handoffs/STOREB_MAPPING_REPAIR_PROOF_STARTERS_20260511_195224`
- Prompt: `01_AGENT_773__STOREB_MAPPING_REPAIR_PROOF__ROOT.md`
- Evidence root: `~/Docs/Autonomous_business/exports/validation/storeb_mapping_repair_proof/20260511_195224`
- Closeout: `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/storeb_mapping_repair_proof_20260511_195224_agent773_closeout.md`

Use monitor-only routing. Do not use chat pings, receiver pings, `LIVE`, or stale orchestrator panes. Repo-local tmux visibility and completion ping kill switches remain active.

## Recommended Command

Use a verified idle Codex/Claude pane only. Do not paste into `zsh`.

```bash
python3 ~/.codex/skills/tmux-agent-orchestrator/scripts/launch_tmux_agents.py \
  --repo ~/Docs/Autonomous_business \
  --starter-folder ~/Docs/Autonomous_business/docs/agent_handoffs/STOREB_MAPPING_REPAIR_PROOF_STARTERS_20260511_195224 \
  --session autonomous_business \
  --orchestrator-pane %MONITOR \
  --agents 773 \
  --reuse-panes <VERIFIED_CODEX_OR_CLAUDE_PANE> \
  --no-start-sessions \
  --run-id storeb_mapping_repair_proof_20260511_195224 \
  --window-name storeb_mapping_repair_proof_20260511_195224 \
  --mode monitor \
  --orchestrator-ping-mode monitor-only \
  --clear-line
```

## Watch Command

```bash
python3 ~/.codex/skills/tmux-agent-orchestrator/scripts/watch_tmux_agents.py \
  --manifest ~/Docs/Autonomous_business/runs/tmux_orchestration/storeb_mapping_repair_proof_20260511_195224/orchestration_manifest.json \
  --once
```

## Stopline

If no verified idle Codex/Claude pane is available, create or start one first and verify `pane_current_command` is an agent client before launch. Do not paste a starter prompt into a shell.
