# Agent 758 Starter: AB Copied-Temp Adapter Replay

You are Agent 758 for the Autonomous_business ads source packet live-readonly proof lane.

Do not start unless Agent 757 has already written a closeout with a standalone:

`Gate: GREEN`

Agent 757 closeout:
`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_757_web_ads_source_packet_builder_closeout.md`

## Read First

Read these files before taking action:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/ADS_SOURCE_PACKET_LIVE_READONLY_PROOF_PLAN_20260511_113319.md`
4. `~/Docs/Autonomous_business/docs/validation/ADS_WEB_AUTOMATION_SOURCE_PACKET_CONTRACT.md`
5. `~/Docs/Oracle/Autonomous_business/2026-05-10/231609_TASK-000_codecaptain-ads-source-packet-content-rereview/Answer/Code Captain_11.05.2026_11_27_43.md`
6. Agent 757 closeout listed above.

## Assignment

Use the validated Agent 757 packet manifest to adapt ads source truth only into copied/temp Autonomous_business proof storage, then replay the ads validators.

Your evidence root:
`~/Docs/Autonomous_business/exports/validation/ads_source_packet_live_readonly_proof/20260511_113319/agent758_replay`

Expected copied DB:
`~/Docs/Autonomous_business/exports/validation/ads_source_packet_live_readonly_proof/20260511_113319/agent758_replay/app_copy.sqlite`

Closeout path:
`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_758_ab_copied_temp_adapter_replay_closeout.md`

## Allowed

- Read `~/Docs/Autonomous_business`.
- Read Agent 757 packet files.
- Copy `~/Docs/Autonomous_business/db/app.db` into your evidence root.
- Write only under your evidence root and your closeout path.
- Inspect command help before running adapter or validator commands.
- Stop `YELLOW` if no safe copied/temp adapter path exists.

## Forbidden

- Do not start if Agent 757 is not `Gate: GREEN`.
- Do not write `~/Docs/Autonomous_business/db/app.db`.
- Do not mutate any workbook.
- Do not write inside `~/Docs/Web_automation`.
- Do not run scheduler automation or LaunchAgent changes.
- Do not perform browser-login automation.
- Do not export, copy, package, hash, or reveal cookies, credentials, tokens, `.env`, browser profiles, or sessions.
- Do not perform external writes, ad spend, cash movement, price changes, stock changes, or owner publication.
- Do not hide warning cohorts `23` or `252`.

## Required Replay Shape

1. Verify Agent 757 closeout is `Gate: GREEN`.
2. Re-run or inspect the saved strict packet validation result.
3. Hash production DB before copy.
4. Copy production DB to:
   `~/Docs/Autonomous_business/exports/validation/ads_source_packet_live_readonly_proof/20260511_113319/agent758_replay/app_copy.sqlite`
5. Hash copied DB after copy.
6. Adapt only into copied/temp proof storage.
7. Replay:
   - `ads_sidecar_readiness`
   - `ads_offer_universe_coverage`
8. Save commands, stdout/stderr, JSON outputs, before/after DB SHA, table counts, and final blocker classification under your evidence root.

Expected accepted outcomes:

- `ADS_SOURCE_STALE` clears by source-fresh packet.
- `ADS_SOURCE_STALE` remains visible with exact reason.
- The blocker is reclassified to a machine-readable source/coverage gap.

## Closeout Requirements

Write a concise closeout with:

- Standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
- Agent 757 closeout status and packet manifest used.
- Copied DB path and before/after SHA evidence.
- Adapter command(s), validator command(s), and results.
- Validator output paths.
- Warning cohort `23` and `252` visibility.
- Final blocker outcome.
- Explicit confirmation that no production DB writes, workbook writes, Web_automation writes, browser-login automation, or credential/session export occurred.

Only use `Gate: GREEN` if all replay requirements are satisfied and all writes stayed inside the copied/temp proof boundary.
