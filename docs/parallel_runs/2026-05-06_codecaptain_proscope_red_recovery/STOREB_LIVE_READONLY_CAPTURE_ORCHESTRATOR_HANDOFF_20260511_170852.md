# STOREB Live-Readonly Capture Orchestrator Handoff

Generated at: `2026-05-11T17:08:52+0500`

Gate: `READY_TO_LAUNCH_AGENT772_MONITOR_ONLY`

## Launch Shape

Launch one execution agent:

- Agent: `772`
- Starter folder: `~/Docs/Autonomous_business/docs/agent_handoffs/STOREB_LIVE_READONLY_CAPTURE_STARTERS_20260511_170852`
- Prompt: `01_AGENT_772__STOREB_LIVE_READONLY_CAPTURE_AND_COPIED_TEMP_REPLAY__ROOT.md`
- Evidence root: `~/Docs/Autonomous_business/exports/validation/storeb_live_readonly_capture/20260511_170852`
- Closeout: `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/storeb_live_readonly_capture_20260511_170852_agent772_closeout.md`

Use monitor-only routing. Do not use chat pings, receiver pings, `LIVE`, or hard-coded stale orchestrator panes. Repo-local tmux visibility and completion ping kill switches remain active.

## Recommended Command

Use a verified idle Codex/Claude pane only. Do not paste into `zsh`.

```bash
python3 ~/.codex/skills/tmux-agent-orchestrator/scripts/launch_tmux_agents.py \
  --repo ~/Docs/Autonomous_business \
  --starter-folder ~/Docs/Autonomous_business/docs/agent_handoffs/STOREB_LIVE_READONLY_CAPTURE_STARTERS_20260511_170852 \
  --session autonomous_business \
  --orchestrator-pane %MONITOR \
  --agents 772 \
  --reuse-panes <VERIFIED_CODEX_OR_CLAUDE_PANE> \
  --no-start-sessions \
  --run-id storeb_live_readonly_capture_20260511_170852 \
  --window-name storeb_live_readonly_capture_20260511_170852 \
  --mode monitor \
  --orchestrator-ping-mode monitor-only \
  --clear-line
```

## Watch Command

```bash
python3 ~/.codex/skills/tmux-agent-orchestrator/scripts/watch_tmux_agents.py \
  --manifest ~/Docs/Autonomous_business/runs/tmux_orchestration/storeb_live_readonly_capture_20260511_170852/orchestration_manifest.json \
  --once
```

## Stopline

If no verified idle Codex/Claude pane is available, create or start one first and verify `pane_current_command` is an agent client before launch. Do not repeat the superseded Agent771 shell-paste incident.
