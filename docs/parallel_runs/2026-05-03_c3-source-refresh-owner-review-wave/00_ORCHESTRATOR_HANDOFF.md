# C3 Source Refresh Wave Orchestrator Handoff

Run: `2026-05-03_c3-source-refresh-owner-review-wave`

Repo: `~/Docs/Autonomous_business`

Starter folder: `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_c3-source-refresh-owner-review-wave`

Shared handoff folder: `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-refresh-owner-review-wave`

## Launch Decision

Launch Agents 1-5 in parallel now.

Agents 1-5 are read-only analysts. They do not mutate repo files, DB rows, external repos, workbooks, browser sessions, APIs, ads platforms, payment systems, or supplier communication state.

Agent 6 remains blocked until Agents 1-5 are reviewed.

Agent 7 remains blocked until Agent 6 is reviewed.

## Tmux Launch Command Shape

Use tmux hybrid mode:

```bash
python3 ~/.codex/skills/tmux-agent-orchestrator/scripts/launch_tmux_agents.py \
  --repo ~/Docs/Autonomous_business \
  --starter-folder ~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_c3-source-refresh-owner-review-wave \
  --session ab_c3_readonly_20260503 \
  --orchestrator-pane %4 \
  --agents 1,2,3,4,5 \
  --agent-command codex \
  --mode hybrid \
  --window-name c3-source-refresh-wave
```

## Monitor Command

```bash
python3 ~/.codex/skills/tmux-agent-orchestrator/scripts/watch_tmux_agents.py \
  --manifest ~/Docs/Autonomous_business/runs/tmux_orchestration/<run_id>/orchestration_manifest.json \
  --agents 1,2,3,4,5 \
  --once
```

## Expected Agent Closeouts

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-refresh-owner-review-wave/agent_1_ab_operational_source_refresh_closeout.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-refresh-owner-review-wave/agent_2_ads_source_refresh_closeout.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-refresh-owner-review-wave/agent_3_cashflow_bank_obligations_closeout.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-refresh-owner-review-wave/agent_4_po_inbound_refresh_closeout.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-refresh-owner-review-wave/agent_5_owner_exception_review_pack_closeout.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-refresh-owner-review-wave/agent_6_source_refresh_execution_closeout.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-refresh-owner-review-wave/agent_7_c3_rematerialize_owner_brief_closeout.md`

## Stopline

Do not launch Agent 6 if any Agent 1-5 closeout is missing, has no standalone gate line, modified forbidden surfaces, or leaves source ownership unresolved.
