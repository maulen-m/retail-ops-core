# Green Path Phase 2 Post-Rebaseline Scouts

Purpose: classify the remaining non-green Phase-2 and standing-observation gates after the 2026-06-14 order/status/quarantine rebaseline.

Launch order:
1. Launch agents 19-22 in parallel.
2. All agents are read-only scouts. They may write only their assigned closeout under `~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_post_rebaseline_scouts/`.
3. The orchestrator reads all closeouts, reruns the required gates, and decides the next single writer lane, if any.

Starter folder:
`~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_PHASE2_POST_REBASELINE_SCOUTS_20260614_STARTERS`

Shared closeout folder:
`~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_post_rebaseline_scouts`

Current boundary:
- Production DB SHA before this scout wave: `bcd6befdc985c91e2d76066efe902c65e58e9266893778f004e886942f40b0e1`.
- Current strict `validate_params.py --strict --as-of 2026-06-14` passes.
- G-ORD-01/02/03 and G-QUAR-02/03 are green as of `20260614_1641`.
- Daily business automations remain paused except the read-only weekly cash cadence monitor.

