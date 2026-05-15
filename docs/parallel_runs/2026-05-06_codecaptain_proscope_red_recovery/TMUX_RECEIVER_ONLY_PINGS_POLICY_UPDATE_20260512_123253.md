# Tmux Receiver-Only Pings Policy Update

Generated at: `2026-05-12T12:35:10+0500`

Gate: GREEN

## Decision

Receiver-only tmux completion pings are enabled for future Autonomous_business orchestration runs.

Live chat / human-visible pings remain disabled.

## What Changed

Archived:

`~/Docs/Autonomous_business/config/tmux_orchestrator_pings_disabled.flag.archived_20260512_123253_receiver_only_proof`

Still active:

`~/Docs/Autonomous_business/config/tmux_orchestrator_visibility_disabled.flag`

Added:

`~/Docs/Autonomous_business/config/tmux_orchestrator_receiver_only_pings_enabled.flag`

## Proof

The all-ping flag was first confirmed to block receiver mode:

```text
tmux completion pings are disabled for this repo; use monitor-only routing
```

After archiving the all-ping flag, a dummy non-production receiver proof was run:

- Manifest: `~/Docs/Autonomous_business/runs/tmux_orchestration/tmux_receiver_ping_dummy_proof_20260512_123253/orchestration_manifest.json`
- Completion marker: `~/Docs/Autonomous_business/runs/tmux_orchestration/tmux_receiver_ping_dummy_proof_20260512_123253/completions/root/agent_900.json`
- Sent marker: `~/Docs/Autonomous_business/runs/tmux_orchestration/tmux_receiver_ping_dummy_proof_20260512_123253/completions/root/_orchestrator_ping_sent.json`
- Closeout: `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/TMUX_RECEIVER_PING_DUMMY_PROOF_CLOSEOUT_20260512_123253.md`
- Receiver pane: `%328`
- Receiver command: `cat`
- Visibility panes: none

Observed completion:

```text
sent group root ping to %328
```

Watcher result:

```text
900 done GREEN
```

## Safety Verification

Chat mode still fails closed:

```text
orchestrator_ping_mode=chat is disabled for this repo; use receiver-only or monitor-only routing
```

Therefore future safe launch shape is:

```bash
--orchestrator-ping-mode receiver --orchestrator-pane <attested-inert-receiver-pane>
```

Do not use:

```bash
--orchestrator-ping-mode chat
--visibility-pane LIVE
```

unless a separate live-chat proof is explicitly approved.

## Authority

Closeout files and completion marker JSON remain authority. Receiver pings are only wake-up signals.
