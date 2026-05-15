# Agent771 - STOREB Ads Read-Only Source Packet And Copied-Temp Replay

You are Agent771 for the Autonomous_business MVOS STOREB ads proof lane.

## Read First

Read these files before taking action:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/MVOS_STOREB_ADS_READONLY_SOURCE_PROOF_PLAN_20260511_155605.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/MVOS_STOREB_ADS_READONLY_SOURCE_PROOF_ORCHESTRATOR_HANDOFF_20260511_155605.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/MVOS_PHASE_C_PLUS_SYNTHESIS_20260511_154019.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/mvos_phase_c_plus_20260511_154019_agent770_synthesis_closeout.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/mvos_phase_c_plus_20260511_154019_agent767_storeb_ads_gap_closeout.md`
8. `~/Docs/Autonomous_business/docs/validation/ADS_WEB_AUTOMATION_SOURCE_PACKET_CONTRACT.md`
9. `~/Docs/Oracle/Autonomous_business/2026-05-10/231609_TASK-000_codecaptain-ads-source-packet-content-rereview/Answer/Code Captain_11.05.2026_11_27_43.md`

## Assignment

Resolve or classify the current STOREB ads source gap using only a bounded read-only source packet and copied/temp AB replay.

Current label to preserve until evidence changes it:

`STOREB_ADS_SOURCE_GAP_VISIBLE_NOT_ZERO_SPEND`

Your evidence root:

`~/Docs/Autonomous_business/exports/validation/storeb_ads_readonly_source_packet/20260511_155605`

Expected packet manifest, if created:

`~/Docs/Autonomous_business/exports/validation/storeb_ads_readonly_source_packet/20260511_155605/agent771_packet/packet_manifest.json`

Expected copied DB, if replay runs:

`~/Docs/Autonomous_business/exports/validation/storeb_ads_readonly_source_packet/20260511_155605/agent771_replay/app_copy.sqlite`

Closeout path:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/mvos_storeb_ads_readonly_source_20260511_155605_agent771_closeout.md`

## Allowed

- Read `~/Docs/Autonomous_business`.
- Read `~/Docs/Web_automation`.
- Use Web_automation code only if all generated outputs can be redirected to your Autonomous_business evidence root and no Web_automation files are written.
- Write only under your evidence root and your closeout path.
- Copy `~/Docs/Autonomous_business/db/app.db` into your evidence root only for copied/temp replay.
- Inspect command help before running any source, adapter, or validator command.
- Stop `YELLOW` if a safe packet/replay cannot be produced from current evidence.

## Forbidden

- Do not write inside `~/Docs/Web_automation`.
- Do not write `~/Docs/Autonomous_business/db/app.db`.
- Do not mutate any workbook.
- Do not run scheduler automation, launchctl, installers, LaunchAgent changes, or plist changes.
- Do not perform browser-login automation.
- Do not export, copy, package, hash, reveal, or depend on cookies, credentials, tokens, `.env`, browser profiles, storage state, or sessions.
- Do not perform external writes, Kaspi/API merchant writes, ad spend, bid/budget/campaign mutation, cash movement, supplier payment, PO commitment, price changes, stock changes, owner publication, owner send, or owner approval request.
- Do not treat missing STOREB rows as zero spend.
- Do not treat Universal access identity as STOREB business identity.
- Do not treat copied/temp replay as production truth.
- Do not hide, clear, downgrade, productize, or use `product_identity_quarantine=23`, `header_only_source_gap=252`, validator-visible `249`, or combined `275` as SKU, stock, COGS, profit, or profit-after-ads truth.

## Required Work

1. Verify Agent770 closeout is `Gate: GREEN`.
2. Verify Agent767 closeout is `Gate: YELLOW` and preserve its STOREB gap rules.
3. Search for safe existing STOREB source evidence and safe Web_automation capture methods.
4. If a safe STOREB packet can be built, build an immutable `ads_web_source_packet.v1` under:
   `~/Docs/Autonomous_business/exports/validation/storeb_ads_readonly_source_packet/20260511_155605/agent771_packet`
5. Validate the packet from `~/Docs/Autonomous_business`:

```bash
python3 scripts/validate_ads_source_packet_contract.py \
  --manifest ~/Docs/Autonomous_business/exports/validation/storeb_ads_readonly_source_packet/20260511_155605/agent771_packet/packet_manifest.json \
  --require-existing-files \
  --strict \
  --json
```

6. Save validator stdout/stderr/exit code under your evidence root.
7. If strict packet validation fails, stop and close `YELLOW` or `RED` with exact reason. Do not run replay.
8. If strict packet validation passes, copy production DB to the expected copied DB path, record before/copy SHA and integrity, and replay only against that copied/temp DB.
9. Run ads sidecar readiness and ads offer-universe coverage validators against the copied/temp DB only, with outputs under your evidence root.
10. Write a final blocker classification JSON under your evidence root.

## Required Identity And Window

Packet identity must keep:

- `business_store_code=STOREB`
- Universal switcher or shared login only as access identity, never business identity

Minimum window:

- `2026-05-05..2026-05-11`

If the available evidence cannot cover that window, stop `YELLOW` and state the exact missing dates.

## Acceptable Final Labels

Use exactly one if evidence supports it:

- `STOREB_ADS_SOURCE_FRESH_IN_COPIED_TEMP_REPLAY`
- `STOREB_ADS_SOURCE_BACKED_NO_SPEND_IN_COPIED_TEMP_REPLAY`
- `STOREB_ADS_MAPPING_BLOCKER_VISIBLE`
- `STOREB_ADS_SOURCE_GAP_STILL_VISIBLE`

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
- explicit confirmation that no production DB writes, workbook writes, Web_automation writes, browser-login automation, credential/session export, scheduler mutation, external writes, owner publication, cash/PO/ad/price/stock actions, or owner approval request occurred.

Use `Gate: GREEN` only if all proof requirements are satisfied and all writes stayed inside the copied/temp proof boundary.
