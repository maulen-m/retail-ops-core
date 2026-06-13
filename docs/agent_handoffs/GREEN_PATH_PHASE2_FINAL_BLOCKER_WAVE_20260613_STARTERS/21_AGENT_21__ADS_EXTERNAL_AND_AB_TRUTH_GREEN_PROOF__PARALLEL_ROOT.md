# Agent 21 - Ads External And AB Truth Green Proof

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-06-13_green_path_resume/agent_21_ads_external_and_ab_truth_green_proof_closeout.md`

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/validation/ADS_WEB_AUTOMATION_SOURCE_PACKET_CONTRACT.md`
4. `~/Docs/Autonomous_business/docs/validation/ADS_ACTIVE_SCOPE_CONTRACT.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_PHASE2_CASHFLOW_PROD_APPLY_20260613.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-06-13_green_path_resume/agent_19_ads_truth_temp_proof_closeout.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-06-13_green_path_resume/agent_16_wa_kaspi_marketing_packet_closeout.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-06-13_green_path_resume/agent_17_meta_source_packet_boundary_closeout.md`
9. This starter prompt.

Role: produce the minimum honest green path for ads truth after cashflow is fixed. You must clear or precisely preserve each ads source independently:

- `src_ab_db_ads_truth`
- `src_web_automation_kaspi_marketing_directapi`
- `src_facebook_ads_external_ads`

Hard boundary:

- Do not mutate production `db/app.db`.
- Do not perform Meta, Instagram, Facebook, Kaspi merchant, Kaspi ads, pricing, Telegram, LaunchAgent, workbook, customer, or operator-message writes.
- Do not turn true spend into a no-spend packet.
- You may create copied DBs using SQLite online backup and apply only to those copies.

Allowed writes:

- Evidence under `~/Docs/Autonomous_business/exports/validation/agent21_ads_external_and_ab_truth_green_proof_20260613/`
- Copied DBs under that evidence folder.
- Assigned closeout.
- A focused code/test patch only if a repo bug blocks the copied-DB proof. If you patch code, keep it lane-local and say exactly which tests prove it.

Known current evidence:

- Agent 19 closeout: `~/Docs/Autonomous_business_agent_handoffs/2026-06-13_green_path_resume/agent_19_ads_truth_temp_proof_closeout.md`
- Web Automation accepted packet: `~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_source_packet_standardization/kaspi_marketing_source_freshness_packet.json`
- Agent 16 run copy: `~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260613_agent16_wa_kaspi_marketing_packet/kaspi_marketing_source_freshness_packet.json`
- Agent 17 Meta packet: `~/Docs/Business_3/Facebook_ads/runs/ab_source_freshness_20260613_acmewear_meta_spend_boundary/meta_live_refresh_summary.json`

Current production after cashflow apply:

- `cashflow_source_truth`: `PASS`
- strict gate errors: `ads_source_truth`, `source_freshness`, `stock_source_truth`
- strict source errors: `src_ab_db_ads_truth` stale, `src_ab_db_stock_truth` stale, `src_facebook_ads_external_ads` blocked.

Tasks:

1. Reproduce the ads blockers read-only on production:

```bash
PYTHONPATH=. .venv/bin/python scripts/validate_policy_source_freshness.py --db db/app.db --strict --json
PYTHONPATH=. .venv/bin/python scripts/validate_policy_gate_results.py --db db/app.db --strict --json
PYTHONPATH=. .venv/bin/python scripts/validate_ads_offer_universe_coverage.py --db db/app.db --as-of 2026-06-13 --strict --json
```

2. Identify the minimum honest path for each retained ads blocker:

- If `src_ab_db_ads_truth` can clear by applying the existing Kaspi marketing materializer to a copied DB, prove it and include exact production apply commands.
- If Agent 16's packet must be wrapped or regenerated to satisfy strict `ads_web_source_packet.v1`, create or propose the smallest deterministic wrapper and validate it.
- Resolve `ACMEWEAR/LINE-31-TS` for 2026-06-13 as mapped, no-spend with explicit evidence, or quarantined with a policy-backed reason. Do not silently drop it.
- For `src_facebook_ads_external_ads`, use Agent 17's real spend truth. Either prove the existing contract can represent the real-spend packet as fresh, or stop `YELLOW` with the exact missing ingestion contract/table/script. Do not mark it green by pretending spend is zero.

3. Create copied DB:

```bash
sqlite3 db/app.db ".backup 'exports/validation/agent21_ads_external_and_ab_truth_green_proof_20260613/agent21_ads_probe.db'"
```

4. On the copied DB only, perform the minimum materialization/proof sequence. Use documented env gates for any apply.

5. Materialize C3 source freshness and gates on the copied DB, then run:

```bash
sqlite3 -readonly exports/validation/agent21_ads_external_and_ab_truth_green_proof_20260613/agent21_ads_probe.db 'PRAGMA integrity_check;'
PYTHONPATH=. .venv/bin/python scripts/validate_policy_source_freshness.py --db exports/validation/agent21_ads_external_and_ab_truth_green_proof_20260613/agent21_ads_probe.db --strict --json
PYTHONPATH=. .venv/bin/python scripts/validate_policy_gate_results.py --db exports/validation/agent21_ads_external_and_ab_truth_green_proof_20260613/agent21_ads_probe.db --strict --json
PYTHONPATH=. .venv/bin/python scripts/validate_ads_offer_universe_coverage.py --db exports/validation/agent21_ads_external_and_ab_truth_green_proof_20260613/agent21_ads_probe.db --as-of 2026-06-13 --strict --json
```

Closeout requirements:

- Standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
- Before/after copied-DB row counts and max dates for every ads table you touch.
- Explicit status for `src_ab_db_ads_truth`, `src_web_automation_kaspi_marketing_directapi`, and `src_facebook_ads_external_ads`.
- Explicit status for `ACMEWEAR/LINE-31-TS` on 2026-06-13.
- If `GREEN`, include exact serialized production apply proposal with backup command, env gates, expected row deltas, validators, and rollback path. Do not run it.
- If `YELLOW`, state the missing source/contract/code gap and the smallest next action.

