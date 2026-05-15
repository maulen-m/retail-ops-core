# Ads Source Packet Live-Readonly Proof Starter Index

Created: 2026-05-11 11:33:19 Asia/Almaty

Plan:
`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/ADS_SOURCE_PACKET_LIVE_READONLY_PROOF_PLAN_20260511_113319.md`

Orchestrator handoff:
`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/ADS_SOURCE_PACKET_LIVE_READONLY_PROOF_ORCHESTRATOR_HANDOFF_20260511_113319.md`

## Agents

- Agent 757, `01_AGENT_757__WEB_ADS_SOURCE_PACKET_BUILDER__SEQUENTIAL.md`, launch first.
- Agent 758, `02_AGENT_758__AB_COPIED_TEMP_ADAPTER_REPLAY__AFTER_757_GREEN.md`, launch only after Agent 757 closes `Gate: GREEN`.

## Copy-Paste Launch Lines

Launch Agent 757 now:

```bash
python3 ~/.codex/skills/tmux-agent-orchestrator/scripts/launch_tmux_agents.py --repo ~/Docs/Autonomous_business --starter-folder ~/Docs/Autonomous_business/docs/agent_handoffs/ADS_SOURCE_PACKET_LIVE_READONLY_PROOF_STARTERS_20260511_113319 --agents 757 --session autonomous_business --orchestrator-ping-mode monitor-only --orchestrator-pane '%MONITOR'
```

Launch Agent 758 later, only after Agent 757 GREEN:

```bash
python3 ~/.codex/skills/tmux-agent-orchestrator/scripts/launch_tmux_agents.py --repo ~/Docs/Autonomous_business --starter-folder ~/Docs/Autonomous_business/docs/agent_handoffs/ADS_SOURCE_PACKET_LIVE_READONLY_PROOF_STARTERS_20260511_113319 --agents 758 --session autonomous_business --orchestrator-ping-mode monitor-only --orchestrator-pane '%MONITOR'
```
