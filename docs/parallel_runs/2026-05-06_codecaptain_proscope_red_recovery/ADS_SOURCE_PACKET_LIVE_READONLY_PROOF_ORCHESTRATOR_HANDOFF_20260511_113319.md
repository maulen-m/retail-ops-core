# Ads Source Packet Live-Readonly Proof Orchestrator Handoff

Status: AGENT757_LAUNCHED_MONITOR_ONLY
Created: 2026-05-11 11:33:19 +0500

## Authority

CodeCaptain gate:
`GREEN_ACCEPT_ADS_SOURCE_PACKET_CONTENT_CONTRACT_FOR_LIVE_READONLY_PROOF`

Plan:
`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/ADS_SOURCE_PACKET_LIVE_READONLY_PROOF_PLAN_20260511_113319.md`

Starter folder:
`~/Docs/Autonomous_business/docs/agent_handoffs/ADS_SOURCE_PACKET_LIVE_READONLY_PROOF_STARTERS_20260511_113319`

Evidence root:
`~/Docs/Autonomous_business/exports/validation/ads_source_packet_live_readonly_proof/20260511_113319`

Actual Agent 757 launch record:
`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/ADS_SOURCE_PACKET_LIVE_READONLY_PROOF_AGENT757_LAUNCH_20260511_113748.md`

Actual tmux manifest:
`~/Docs/Autonomous_business/runs/tmux_orchestration/ads_source_packet_live_readonly_proof_20260511_113319/orchestration_manifest.json`

## Launch Sequence

Step 1, launch Agent 757 only:

```bash
python3 ~/.codex/skills/tmux-agent-orchestrator/scripts/launch_tmux_agents.py \
  --repo ~/Docs/Autonomous_business \
  --starter-folder ~/Docs/Autonomous_business/docs/agent_handoffs/ADS_SOURCE_PACKET_LIVE_READONLY_PROOF_STARTERS_20260511_113319 \
  --agents 757 \
  --session autonomous_business \
  --orchestrator-ping-mode monitor-only \
  --orchestrator-pane '%MONITOR'
```

Actual launch used existing Codex pane `%327` because a fresh tmux window failed with `Too many open files`. See the launch record above. Agent 758 remains unlaunched.

Step 2, after Agent 757 closes `Gate: GREEN`, launch Agent 758:

```bash
python3 ~/.codex/skills/tmux-agent-orchestrator/scripts/launch_tmux_agents.py \
  --repo ~/Docs/Autonomous_business \
  --starter-folder ~/Docs/Autonomous_business/docs/agent_handoffs/ADS_SOURCE_PACKET_LIVE_READONLY_PROOF_STARTERS_20260511_113319 \
  --agents 758 \
  --session autonomous_business \
  --orchestrator-ping-mode monitor-only \
  --orchestrator-pane '%MONITOR'
```

Do not use:

- `--visibility-pane LIVE`
- `orchestrator_ping_mode=chat`
- `orchestrator_ping_mode=receiver`
- manual chat pings

Repo flags currently require monitor-only orchestration.

## Closeout Authority

Agent 757 closeout:
`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_757_web_ads_source_packet_builder_closeout.md`

Agent 758 closeout:
`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_758_ab_copied_temp_adapter_replay_closeout.md`

The closeout file plus standalone `Gate:` line is the source of truth. Tmux output is only execution telemetry.

## Gate Logic

`Gate: GREEN` for Agent 757 means:

- Packet manifest exists.
- Strict validator passed.
- Required hashes, raw payload references, redaction manifest, source identity, source row counts, unique keys, duplicate counts, capture metadata, and warning cohorts are present.
- No Web_automation writes, AB production DB writes, browser-login automation, or credential/session export occurred.

`Gate: GREEN` for Agent 758 means:

- Agent 757 was GREEN.
- AB production DB was copied into evidence storage before adaptation.
- Adapter wrote only copied/temp proof storage.
- Both `ads_sidecar_readiness` and `ads_offer_universe_coverage` replay outputs were preserved.
- Final blocker outcome is machine-readable and one of the accepted outcomes in the plan.

Any missing prerequisite is `Gate: YELLOW` or `Gate: RED`, not a partial GREEN.
