# Agent773 - STOREB Product-Code Mapping Repair Proof

You are Agent773 for the Autonomous_business STOREB ads mapping repair proof lane.

## Read First

Read these files before taking action:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/STOREB_MAPPING_REPAIR_PROOF_AUTHORIZATION_20260511_195224.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/STOREB_MAPPING_REPAIR_PROOF_PLAN_20260511_195224.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/STOREB_MAPPING_REPAIR_PROOF_ORCHESTRATOR_HANDOFF_20260511_195224.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/current_gate_status_agent750_waiting_codecaptain.json`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/storeb_live_readonly_capture_20260511_170852_agent772_closeout.md`
8. `~/Docs/Autonomous_business/exports/validation/storeb_live_readonly_capture/20260511_170852/final_blocker_classification.json`
9. `~/Docs/Autonomous_business/exports/validation/storeb_live_readonly_capture/20260511_170852/agent772_replay/adapter_lineage_sidecar.json`
10. `~/Docs/Autonomous_business/exports/validation/storeb_live_readonly_capture/20260511_170852/agent772_replay/adapter_apply/storeb_product_code_mapping.csv`
11. `~/Docs/Autonomous_business/exports/validation/storeb_live_readonly_capture/20260511_170852/agent772_replay/adapter_apply/ads_campaign_product_daily_unmapped.csv`
12. `~/Docs/Autonomous_business/scripts/materialize_ads_campaign_product_daily.py`
13. `~/Docs/Autonomous_business/docs/validation/ADS_WEB_AUTOMATION_SOURCE_PACKET_CONTRACT.md`

## Assignment

Repair or classify the Agent772 STOREB product-code mapping blocker using copied/temp evidence only.

Current label to preserve until evidence changes it:

`STOREB_ADS_MAPPING_BLOCKER_VISIBLE`

Your evidence root:

`~/Docs/Autonomous_business/exports/validation/storeb_mapping_repair_proof/20260511_195224`

Expected copied DB:

`~/Docs/Autonomous_business/exports/validation/storeb_mapping_repair_proof/20260511_195224/agent773_replay/app_copy.sqlite`

Closeout path:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/storeb_mapping_repair_proof_20260511_195224_agent773_closeout.md`

## Blocked Product Codes

Agent772 blocked these seven product codes:

- `11391140b` - Комплект ALPIKA черный - source rows `7`, source cost `0`
- `11391205b` - Комплект Antec черный - source rows `7`, source cost `5351.33`
- `11391711b` - Комплект S SPORT серый - source rows `7`, source cost `3565.47`
- `11869884b` - Спортивный костюм PRO COMBAT черный - source rows `7`, source cost `0`
- `11956144b` - Спортивный костюм черный - source rows `7`, source cost `1290.00`
- `12071269b` - Спортивный костюм Fashion черный - source rows `7`, source cost `0`
- `12236047b` - Спортивный костюм IMPERIAL черный - source rows `7`, source cost `0`

Already mapped product codes:

- `11120372b` -> `CL_OC_MEN_LINE52_BLACK`
- `11122298b` -> `CL_OC_MEN_LINE52_BLACK`
- `11942309b` -> `CL_OC_MEN_LINE52_BLACK`

## Allowed

- Read `~/Docs/Autonomous_business`.
- Read Agent772 evidence under `~/Docs/Autonomous_business/exports/validation/storeb_live_readonly_capture/20260511_170852`.
- Write only under your evidence root and assigned closeout path.
- Copy `~/Docs/Autonomous_business/db/app.db` into your evidence root for copied/temp replay.
- Create evidence-local candidate mapping CSV/JSON files.
- Run adapter and validators against copied/temp DB only, with outputs under your evidence root.
- Run focused read-only inspection queries against production DB.
- Run tests if you make any focused repo-code change.

## Forbidden

- Do not write `~/Docs/Autonomous_business/db/app.db`.
- Do not mutate any workbook.
- Do not write inside `~/Docs/Web_automation`.
- Do not perform browser-login automation or live web capture.
- Do not export, copy, package, hash into evidence, reveal, or depend on cookies, credentials, tokens, `.env`, browser profiles, storage state, or sessions as deliverable evidence.
- Do not perform external writes, Kaspi/API merchant writes, ad spend, bid/budget/campaign/product mutation, cash movement, supplier payment, PO commitment, price changes, stock changes, owner publication, owner send, or owner approval request.
- Do not map by fuzzy product name alone.
- Do not convert unmapped rows or missing rows into zero spend.
- Do not treat copied/temp proof as production truth.
- Do not hide, clear, downgrade, productize, or use `product_identity_quarantine=23`, `header_only_source_gap=252`, validator-visible `249`, or combined `275` as SKU, stock, COGS, profit, or profit-after-ads truth.

## Required Work

1. Verify Agent772 closeout is `Gate: GREEN`.
2. Refresh current production DB/workbook SHA and DB integrity for awareness only. Do not treat this as production apply authority.
3. Copy production DB to your expected copied DB path and record before/copy SHA and integrity.
4. Build a mapping evidence matrix for all ten STOREB product codes.
5. For each blocked product code, search deterministic evidence only:
   - exact Kaspi product-code/order-entry joins;
   - exact related-order product article mapping;
   - existing article/catalog/map truth in DB;
   - current source packet rows and `related_order_products`;
   - no fuzzy product-name-only matching.
6. Create an evidence-local mapping decision table with columns:
   - `kaspi_product_code`
   - `product_name`
   - `decision`
   - `sku_key`
   - `evidence_type`
   - `evidence_path_or_query`
   - `confidence`
   - `remaining_blocker`
7. If deterministic candidate mappings exist, replay against copied/temp DB only. Use an evidence-local mapping sidecar or copied-DB-only staging table if needed.
8. Rerun:

```bash
python3 scripts/validate_ads_sidecar_readiness.py --help
python3 scripts/validate_ads_offer_universe_coverage.py --help
```

Then run the actual validators against copied/temp DB only with outputs inside your evidence root.

9. Write final blocker classification JSON under your evidence root.

## Acceptable Final Labels

Use exactly one if evidence supports it:

- `STOREB_ADS_MAPPING_REPAIRED_IN_COPIED_TEMP_REPLAY`
- `STOREB_ADS_PARTIAL_MAPPING_REPAIR_WITH_RESIDUAL_BLOCKER_VISIBLE`
- `STOREB_ADS_MAPPING_BLOCKER_VISIBLE`

## Closeout Requirements

Write a concise closeout with:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- exact copied DB path and before/after SHA evidence;
- mapping decision table path;
- deterministic evidence used per product code;
- adapter command(s) and results;
- validator command(s) and results;
- warning cohort `23`, `252`, `249`, and `275` handling;
- final STOREB label;
- explicit statement of any residual unmapped rows/cost;
- explicit confirmation that no production DB writes, workbook writes, Web_automation writes, browser-login automation, credential/session export, scheduler mutation, external writes, owner publication, cash/PO/ad/price/stock actions, or owner approval request occurred.

Use `Gate: GREEN` only if copied/temp replay and validation are complete and every newly mapped product code is deterministically supported.

Do not manually ping tmux or any orchestrator pane. The launcher footer will provide the monitor-only completion command.
