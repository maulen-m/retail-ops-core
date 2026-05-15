# Tmux Live Orchestrator Ping Policy

Timestamp: `2026-05-13T12:13:05+0500`

Gate: GREEN

## Decision

The human owner approved live ping-back from execution agents to the current Autonomous Business orchestrator chat so parallel waves and single-agent lanes can continue under orchestrator supervision without manual human polling.

## Registered Orchestrator Chat

Registration command:

```bash
python3 ~/.codex/skills/tmux-agent-orchestrator/scripts/register_orchestrator_chat.py --repo ~/Docs/Autonomous_business --pane %71
```

Registered pane:

- pane id: `%71`
- session: `autonomous_business`
- window index: `1`
- window name: `Autonomous_business_build`
- pane index: `4`
- command: `codex`
- registered at: `2026-05-13T07:13:05Z`
- registry: `~/.codex/tmux-agent-orchestrator/live_orchestrator_pane.json`

## Implementation

The old live-visibility kill switch was removed:

`~/Docs/Autonomous_business/config/tmux_orchestrator_visibility_disabled.flag`

The active repo policy is now:

`~/Docs/Autonomous_business/config/tmux_orchestrator_live_visibility_enabled.md`

Future tmux launches should use:

```bash
--orchestrator-ping-mode receiver --auto-create-orchestrator-receiver --orchestrator-pane AUTO --visibility-pane LIVE
```

This keeps receiver/marker routing durable while forwarding one attested visible wake-up to the registered live orchestrator chat.

For single-agent lanes, use a one-agent parallel group so the completion helper sends the wake-up after that one closeout is written.

## Safety

The ping is not authority. The authority remains:

- assigned closeout file
- standalone `Gate:` line
- completion marker JSON
- watcher output
- validation evidence

Execution should continue autonomously unless the next action requires production mutation, workbook mutation, scheduler restore/mutation, external writes, owner publication, owner approval request, cash movement, PO commitment, ad spend, price changes, stock changes, browser/login automation, or credential/session export.
