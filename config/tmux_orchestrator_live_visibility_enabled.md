# Tmux Orchestrator Live Visibility Policy

Timestamp: `2026-05-13T12:13:05+0500`

Status: `LIVE_VISIBILITY_ENABLED_FOR_REGISTERED_ORCHESTRATOR_CHAT`

## Human Decision

The human owner approved using real live ping-back from execution agents to the current orchestrator chat so the Autonomous Business build can continue under orchestrator supervision without human polling.

Approved live orchestrator target:

- tmux session: `autonomous_business`
- window index: `1`
- window name: `Autonomous_business_build`
- pane index: `4`
- pane id at registration: `%71`
- command: `codex`
- registry: `~/.codex/tmux-agent-orchestrator/live_orchestrator_pane.json`

## Required Rules

- Execution agents must write their assigned closeout first.
- Each closeout must include a standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED` line.
- The completion helper must record completion marker JSON.
- For parallel waves, only the last completed agent in the parallel group pings the orchestrator.
- For single-agent execution, the agent pings the orchestrator after its closeout and marker are written.
- Ping text is only a wake-up signal; closeout files, marker JSON, watcher output, and validation evidence remain authoritative.
- Pane identity and token attestation must pass before any live ping is sent.
- If live pane attestation fails, the helper must write blocked/skip evidence and not send to a stale or wrong pane.

## Pause Conditions

Agents may proceed without human intervention unless the next action requires one of these high-risk authorities:

- production DB mutation
- protected workbook mutation
- scheduler restore or mutation
- external write
- owner publication
- owner approval request
- cash movement
- PO commitment
- ad spend
- price change
- stock change
- browser/login automation or credential/session export

Those authorities still require separate explicit approval.

Gate: GREEN
