# C3 Read-Only Wave Orchestrator Handoff

Run: `2026-05-03_c3-source-truth-readonly-wave`

Repo: `~/Docs/Autonomous_business`

Starter folder: `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_c3-source-truth-readonly-wave`

Shared handoff folder: `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-truth-readonly-wave`

## Launch Decision

Option B is selected.

Start only Agents 1-6 in parallel. Agents 7-8 are present as blocked future prompts and must not be launched until the orchestrator reviews all six read-only closeouts.

## Launch Command Shape

Use tmux hybrid mode:

```bash
python3 ~/.codex/skills/tmux-agent-orchestrator/scripts/launch_tmux_agents.py \
  --repo ~/Docs/Autonomous_business \
  --starter-folder ~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_c3-source-truth-readonly-wave \
  --session <session> \
  --orchestrator-pane <pane> \
  --agents 1,2,3,4,5,6 \
  --agent-command codex \
  --mode hybrid \
  --window-name c3-readonly-wave
```

The launcher should start fresh Codex sessions and send `/approvals` option `3` before each prompt, per owner-approved tmux orchestrator workflow.

## Monitor Command

```bash
python3 ~/.codex/skills/tmux-agent-orchestrator/scripts/watch_tmux_agents.py \
  --manifest ~/Docs/Autonomous_business/runs/tmux_orchestration/<run_id>/orchestration_manifest.json \
  --agents 1,2,3,4,5,6 \
  --once
```

## Stopline

Do not launch Agent 7 or Agent 8 if any Wave 1 closeout is missing, has no gate line, leaks secrets, modifies repo/DB/external systems, or leaves source ownership unresolved.
