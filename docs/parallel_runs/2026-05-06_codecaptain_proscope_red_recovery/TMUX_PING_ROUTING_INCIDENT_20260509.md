# Tmux Ping Routing Incident - 2026-05-09

Status: `LIVE_VISIBILITY_DISABLED_FOR_THIS_ROLLOUT`

## Summary

Agents743 and 744 completed their assigned root group and recorded the aggregate completion marker, but the human-visible wake-up was forwarded to the wrong tmux chat pane.

The closeout files remain authoritative. The wrong-pane ping does not change the agent gate results.

Follow-up owner report on 2026-05-09: later agents also did not wake the intended orchestrator chat. The later manifests were safer than the original incident because they used receiver-only pings to `%328`, but that still failed the human workflow: the completion signal landed in an inert receiver pane instead of the active orchestrator conversation.

## Evidence

- Run manifest: `~/Docs/Autonomous_business/runs/tmux_orchestration/codecaptain_agent743_744_release_anchor_20260509/orchestration_manifest.json`
- Completion evidence: `~/Docs/Autonomous_business/runs/tmux_orchestration/codecaptain_agent743_744_release_anchor_20260509/completions/agent743_744_release_anchor_root/_orchestrator_ping_sent.json`
- Receiver pane used: `%328`
- Human-visible pane copied from stale `LIVE` registry: `%76`

The `_orchestrator_ping_sent.json` file records:

```json
"orchestrator_pane": "%328",
"visibility_panes": ["%76"]
```

## Root Cause

`--visibility-pane LIVE` resolved from `~/.codex/tmux-agent-orchestrator/live_orchestrator_pane.json`.

That registry pointed to a stale Codex pane. Pane-token attestation proved that pane identity existed at send time, but it did not prove that the pane was the current intended human/orchestrator chat.

## Immediate Control

The stale live registry was invalidated by moving it to:

`~/.codex/tmux-agent-orchestrator/live_orchestrator_pane.json.stale_wrong_pane_20260509_215910_+0500`

Outside this rollout, future `--visibility-pane LIVE` launches should fail closed until a fresh live orchestrator chat is explicitly registered again. Inside the Agent751-753 rollout, `LIVE` remains disabled even if a chat is re-registered.

Fresh live orchestrator chat was re-registered after the follow-up owner report:

```bash
python3 ~/.codex/skills/tmux-agent-orchestrator/scripts/register_orchestrator_chat.py \
  --repo ~/Docs/Autonomous_business \
  --pane %71
```

Registered live pane:

- Pane: `%71`
- Location: `autonomous_business:1.4`
- Command: `codex`
- Role: `orchestrator_live_chat`
- Registered at: `2026-05-09T18:04:29Z`
- Registry: `~/.codex/tmux-agent-orchestrator/live_orchestrator_pane.json`

Follow-up owner report after this re-registration: two later execution agents still pinged the wrong pane. That means dynamic `LIVE` visibility is no longer acceptable for this rollout. For the Agent751-753 path, human-visible chat pinging is disabled, and primary chat-mode pinging is also disabled. Closeout files, completion markers, and watcher output are the authority.

Repeat owner report on 2026-05-10: both follow-up agents again pinged the wrong pane from the human workflow perspective. Current manifest review shows the later paired run used receiver `%328` and no visibility pane, so the transport was safer than stale `LIVE` chat forwarding but still failed the intended operator workflow because the wake-up was not delivered to the active orchestrator conversation. This confirms that execution agents must not be asked to manually ping any chat pane for this rollout, and Agent751-753 must use monitor-only completion rather than receiver wake-ups.

Mechanical control added after the repeat report:

`~/Docs/Autonomous_business/config/tmux_orchestrator_visibility_disabled.flag`

The final repeat report on 2026-05-10 showed receiver-only was still not acceptable for this operator workflow. A stricter control was added:

`~/Docs/Autonomous_business/config/tmux_orchestrator_pings_disabled.flag`

The canonical tmux-agent-orchestrator launcher now refuses `--visibility-pane` routing, primary `orchestrator_ping_mode=chat` routing, and receiver-mode completion pings for repos with the strict ping-disabled flag. For Agent751-753 specifically, use monitor-only only.

## Forward Rule

For this rollout, do not use `--visibility-pane LIVE`. A stale-but-attestable Codex pane can still be the wrong human target, and the repeated wrong-pane report proves that chat wake-ups are less reliable than artifact-based watching for this lane.

Safe default for Agent751-753:

```bash
--orchestrator-ping-mode monitor-only
```

Then the orchestrator reviews status through:

```bash
python3 ~/.codex/skills/tmux-agent-orchestrator/scripts/watch_tmux_agents.py \
  --manifest <manifest> \
  --once
```

If a human-visible wake-up is needed later, it must be treated as a separate repaired feature and tested on a non-production dummy run before re-enabling it for Autonomous Business execution agents.

Do not ask execution agents to manually ping any chat pane. They should write their closeout with a standalone `Gate:` line and rely on the guarded `agent_complete.py` marker flow that the launcher appends. The orchestrator must use closeout files, completion markers, and watcher output as the authority.

## Current Business Gate Impact

No production state decision should depend on the pane ping.

Agents743 and 744 are both `RED` because the production DB SHA drifted from the Agent742 protected boundary. The next safe step is DB drift forensics / re-anchor proof, not Agent745.
