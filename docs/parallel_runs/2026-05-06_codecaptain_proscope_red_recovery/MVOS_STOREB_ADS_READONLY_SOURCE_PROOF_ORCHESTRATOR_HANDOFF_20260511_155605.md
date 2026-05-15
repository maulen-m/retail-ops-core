# MVOS STOREB Ads Read-Only Source Proof Orchestrator Handoff

Generated at: `2026-05-11T15:56:05+0500`

## Launch Decision

Launch Agent771 in monitor-only tmux mode.

Do not use chat pings, receiver pings, visibility panes, or stale pane routing. This repo has active tmux visibility and completion-ping kill switches.

## Starter Folder

`~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_STOREB_ADS_READONLY_SOURCE_PROOF_STARTERS_20260511_155605`

## Agent

| Agent | Prompt | Gate |
|---|---|---|
| `771` | `01_AGENT_771__STOREB_ADS_READONLY_SOURCE_PACKET_AND_COPIED_TEMP_REPLAY__ROOT.md` | root |

## Expected Outputs

Agent771 closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/mvos_storeb_ads_readonly_source_20260511_155605_agent771_closeout.md`

Evidence root:

`~/Docs/Autonomous_business/exports/validation/storeb_ads_readonly_source_packet/20260511_155605`

Expected packet manifest, if created:

`~/Docs/Autonomous_business/exports/validation/storeb_ads_readonly_source_packet/20260511_155605/agent771_packet/packet_manifest.json`

Expected copied DB, if replay runs:

`~/Docs/Autonomous_business/exports/validation/storeb_ads_readonly_source_packet/20260511_155605/agent771_replay/app_copy.sqlite`

## Boundaries

Allowed:

- read `~/Docs/Autonomous_business`;
- read `~/Docs/Web_automation`;
- write under Agent771 evidence root;
- write Agent771 closeout path;
- copy production DB only into the evidence root for copied/temp replay;
- run validators only against the copied/temp DB and evidence-root outputs.

Forbidden:

- production DB writes;
- protected workbook writes;
- Web_automation writes;
- browser-login automation;
- credential/session/cookie/token/storage-state export, copy, reveal, or packaging;
- scheduler/LaunchAgent/plist/launchctl/install mutation;
- owner publication/send/approval request;
- external-system writes;
- Kaspi/API merchant writes;
- ad spend, bid, budget, campaign mutation;
- cash movement, supplier payment, PO commitment;
- price or stock change.

## Launch Command Shape

Use a reused idle Codex pane only after confirming it is not running and clearing any staged prompt input.

```bash
python3 ~/.codex/skills/tmux-agent-orchestrator/scripts/launch_tmux_agents.py \
  --repo ~/Docs/Autonomous_business \
  --starter-folder ~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_STOREB_ADS_READONLY_SOURCE_PROOF_STARTERS_20260511_155605 \
  --session autonomous_business \
  --orchestrator-pane %MONITOR \
  --agents 771 \
  --reuse-panes <IDLE_CODEX_PANE> \
  --no-start-sessions \
  --mode monitor \
  --orchestrator-ping-mode monitor-only \
  --window-name mvos_storeb_ads_readonly_20260511_155605
```

## Completion Rule

The closeout path and standalone `Gate:` line are the authority. Tmux pane text is only transport evidence.
