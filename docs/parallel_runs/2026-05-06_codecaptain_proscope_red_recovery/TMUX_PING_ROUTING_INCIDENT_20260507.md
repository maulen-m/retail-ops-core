# Tmux Ping Routing Incident - 2026-05-07

## Incident

Agents 66 and 67 completed, but their aggregate completion wake-up did not appear in the live orchestrator chat.

## Evidence

Authoritative run manifest:

`~/Docs/Autonomous_business/runs/tmux_orchestration/codecaptain_agent66_67_readonly_diagnostics_20260507_v2/orchestration_manifest.json`

Completion markers:

- `~/Docs/Autonomous_business/runs/tmux_orchestration/codecaptain_agent66_67_readonly_diagnostics_20260507_v2/completions/agent66_67_diagnostics_root/agent_66.json`
- `~/Docs/Autonomous_business/runs/tmux_orchestration/codecaptain_agent66_67_readonly_diagnostics_20260507_v2/completions/agent66_67_diagnostics_root/agent_67.json`
- `~/Docs/Autonomous_business/runs/tmux_orchestration/codecaptain_agent66_67_readonly_diagnostics_20260507_v2/completions/agent66_67_diagnostics_root/_orchestrator_ping_sent.json`

The ping marker recorded:

- `orchestrator_pane`: `%265`
- `parallel_group`: `agent66_67_diagnostics_root`
- `Agent66`: `YELLOW`
- `Agent67`: `GREEN`

Pane `%265` was an inert `cat` receiver pane, not the live orchestrator chat.

## Root Cause

The launch used receiver-only mode:

`--orchestrator-ping-mode receiver --auto-create-orchestrator-receiver --orchestrator-pane AUTO`

No `--visibility-pane` was provided. Receiver-only mode worked as designed, but it was the wrong mode for a user-facing wave where the expected behavior was "ping our chat."

## Fix Applied

The active tmux orchestrator helper was patched so configured `visibility_panes` receive the same aggregate group-complete wake-up after attestation:

- `~/.codex/skills/tmux-agent-orchestrator/scripts/agent_complete.py`
- `~/.codex/skills/tmux-agent-orchestrator/scripts/launch_tmux_agents.py`
- `~/.codex/skills/tmux-agent-orchestrator/SKILL.md`

## Future Rule

For user-facing orchestration waves, do not use receiver-only mode.

Use one of these:

1. Direct chat ping:

```bash
--orchestrator-ping-mode chat --orchestrator-pane "$TMUX_PANE"
```

2. Receiver plus live chat visibility:

```bash
--orchestrator-ping-mode receiver --auto-create-orchestrator-receiver --orchestrator-pane AUTO --visibility-pane "$TMUX_PANE"
```

Receiver-only is allowed only when a silent receiver log is intentionally desired.

## Current Agent66/67 Status

- Agent66 closeout: `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_66_agent65_db_drift_forensics_closeout.md`
- Agent66 gate: `YELLOW`
- Agent67 closeout: `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_67_source_ads_freshness_root_cause_closeout.md`
- Agent67 gate: `GREEN`

The closeout files remain authority. The missing live-chat ping was a routing issue, not an agent completion issue.
