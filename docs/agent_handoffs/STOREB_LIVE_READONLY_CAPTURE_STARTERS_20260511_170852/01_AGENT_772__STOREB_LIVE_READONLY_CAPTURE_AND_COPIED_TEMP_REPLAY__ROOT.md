# Agent772 - STOREB Live-Readonly Capture And Copied-Temp Replay

You are Agent772 for the Autonomous_business STOREB live-readonly ads source lane.

## Read First

Read these files before taking action:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/STOREB_LIVE_READONLY_CAPTURE_AUTHORIZATION_20260511_170852.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/STOREB_LIVE_READONLY_CAPTURE_PLAN_20260511_170852.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/STOREB_LIVE_READONLY_CAPTURE_ORCHESTRATOR_HANDOFF_20260511_170852.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/current_gate_status_agent750_waiting_codecaptain.json`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/mvos_storeb_ads_readonly_source_20260511_155605_agent771_closeout.md`
8. `~/Docs/Autonomous_business/exports/validation/storeb_ads_readonly_source_packet/20260511_155605/final_blocker_classification.json`
9. `~/Docs/Autonomous_business/docs/validation/ADS_WEB_AUTOMATION_SOURCE_PACKET_CONTRACT.md`
10. `~/Docs/Oracle/Autonomous_business/2026-05-10/231609_TASK-000_codecaptain-ads-source-packet-content-rereview/Answer/Code Captain_11.05.2026_11_27_43.md`
11. `~/Docs/Web_automation/Docs/kaspi_marketing_storeb_readonly_capture.md`
12. `~/Docs/Web_automation/Docs/experiments/storeb_ads/storeb_bid_change_automation_plan.md`
13. `~/Docs/Web_automation/config/experiments/storeb_ads_tracking.yaml`

## Assignment

Perform the separately owner-approved bounded live-readonly STOREB ads capture and then run copied/temp replay only if the source packet strictly validates.

Current label to preserve until evidence changes it:

`STOREB_ADS_SOURCE_GAP_STILL_VISIBLE`

Your evidence root:

`~/Docs/Autonomous_business/exports/validation/storeb_live_readonly_capture/20260511_170852`

Expected packet manifest, if created:

`~/Docs/Autonomous_business/exports/validation/storeb_live_readonly_capture/20260511_170852/agent772_packet/packet_manifest.json`

Expected copied DB, if replay runs:

`~/Docs/Autonomous_business/exports/validation/storeb_live_readonly_capture/20260511_170852/agent772_replay/app_copy.sqlite`

Closeout path:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/storeb_live_readonly_capture_20260511_170852_agent772_closeout.md`

## Required Identity And Window

Packet identity must keep:

- `business_store_code=STOREB`
- `access_store_code=UNIVERSAL_SWITCHER_FOR_STOREB`
- selected account label freshly confirmed as `ИП STORE-B`, `STORE-B`, or `STOREB`
- campaign `2609342`
- campaign name `Line52_storeb_26.2.2026`
- merchant/API id `1065684` when freshly confirmed
- seller/store UID `30000002` only as expected/preserved UID unless freshly visible

Minimum window:

- `2026-05-05..2026-05-11`

If available source evidence cannot cover that window, stop `YELLOW` and state the exact missing dates.

## Allowed

- Read `~/Docs/Autonomous_business`.
- Read `~/Docs/Web_automation`.
- Use existing Web_automation read-only capture/report methods only if generated outputs can be redirected to your Autonomous_business evidence root and no Web_automation files are written.
- Use existing authenticated read-only access only if it does not require browser-login automation and does not export, copy, reveal, package, hash, or persist credential/session material in AB evidence.
- Write only under your evidence root and your closeout path.
- Copy `~/Docs/Autonomous_business/db/app.db` into your evidence root only for copied/temp replay, after strict packet validation passes.
- Inspect command help before running any source, adapter, or validator command.
- Stop `YELLOW` if a safe live-readonly capture, packet, or replay cannot be produced within this boundary.

## Forbidden

- Do not write inside `~/Docs/Web_automation`.
- Do not write `~/Docs/Autonomous_business/db/app.db`.
- Do not mutate any workbook.
- Do not run scheduler automation, launchctl, installers, LaunchAgent changes, or plist changes.
- Do not perform browser-login automation.
- Do not export, copy, package, hash into evidence, reveal, or depend on cookies, credentials, tokens, `.env`, browser profiles, storage state, or sessions as deliverable evidence.
- Do not perform external writes, Kaspi/API merchant writes, ad spend, bid/budget/campaign/product mutation, cash movement, supplier payment, PO commitment, price changes, stock changes, owner publication, owner send, or owner approval request.
- Do not treat missing STOREB rows as zero spend.
- Do not treat Universal access identity as STOREB business identity.
- Do not treat copied/temp replay as production truth.
- Do not hide, clear, downgrade, productize, or use `product_identity_quarantine=23`, `header_only_source_gap=252`, validator-visible `249`, or combined `275` as SKU, stock, COGS, profit, or profit-after-ads truth.

## Required Work

1. Verify Agent771 closeout is `Gate: YELLOW` and preserve its exact STOREB missing-date classification.
2. Refresh current production DB/workbook SHA and DB integrity for awareness only. Do not treat this as production apply authority.
3. Search/inspect the existing Web_automation STOREB read-only method and available commands.
4. Perform the narrow live-readonly STOREB source capture only if it stays within the allowed boundary.
5. If a safe STOREB packet can be built, build immutable `ads_web_source_packet.v1` under:
   `~/Docs/Autonomous_business/exports/validation/storeb_live_readonly_capture/20260511_170852/agent772_packet`
6. Validate the packet from `~/Docs/Autonomous_business`:

```bash
python3 scripts/validate_ads_source_packet_contract.py \
  --manifest ~/Docs/Autonomous_business/exports/validation/storeb_live_readonly_capture/20260511_170852/agent772_packet/packet_manifest.json \
  --require-existing-files \
  --strict \
  --json
```

7. Save validator stdout/stderr/exit code under your evidence root.
8. If strict packet validation fails, stop and close `YELLOW` or `RED` with the exact reason. Do not run replay.
9. If strict packet validation passes, copy production DB to the expected copied DB path, record before/copy SHA and integrity, and replay only against that copied/temp DB.
10. Run ads sidecar readiness and ads offer-universe coverage validators against the copied/temp DB only, with outputs under your evidence root.
11. Write a final blocker classification JSON under your evidence root.

## Rate-Limit And Source Caution

The prior STOREB Web_automation work observed direct product endpoint `429` risk. Prefer stable campaign-product report CSV sources when available. Record exact capture timestamps and do not retry aggressively.

## Acceptable Final Labels

Use exactly one if evidence supports it:

- `STOREB_ADS_SOURCE_FRESH_IN_COPIED_TEMP_REPLAY`
- `STOREB_ADS_SOURCE_BACKED_NO_SPEND_IN_COPIED_TEMP_REPLAY`
- `STOREB_ADS_MAPPING_BLOCKER_VISIBLE`
- `STOREB_ADS_SOURCE_GAP_STILL_VISIBLE`
- `NO_SAFE_STOREB_LIVE_READONLY_AUTH_AVAILABLE`

Do not invent a green STOREB status from absence.

## Closeout Requirements

Write a concise closeout with:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- exact packet manifest path, if created;
- exact strict validator command and result;
- source surfaces used;
- date window and as-of semantics;
- business identity and access identity;
- copied DB path and before/after SHA evidence, if replay ran;
- adapter and validator command results, if replay ran;
- warning cohort `23`, `252`, `249`, and `275` handling;
- final STOREB label;
- exact reason if live-readonly capture was unavailable or forbidden;
- explicit confirmation that no production DB writes, workbook writes, Web_automation writes, browser-login automation, credential/session export, scheduler mutation, external writes, owner publication, cash/PO/ad/price/stock actions, or owner approval request occurred.

Use `Gate: GREEN` only if all proof requirements are satisfied and all writes stayed inside the copied/temp proof boundary.

Do not manually ping tmux or any orchestrator pane. The launcher footer will provide the monitor-only completion command.
