# Agent 19 - Ads Truth Temp Proof

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-06-13_green_path_resume/agent_19_ads_truth_temp_proof_closeout.md`

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/validation/ADS_WEB_AUTOMATION_SOURCE_PACKET_CONTRACT.md`
4. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/handoff/ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_REMAINING_BLOCKERS_20260613_STARTERS/RUN_CLOSEOUT.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-06-13_green_path_resume/agent_16_wa_kaspi_marketing_packet_closeout.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-06-13_green_path_resume/agent_17_meta_source_packet_boundary_closeout.md`
8. This starter prompt.

Role: prove the minimum safe path to refresh AB-local Kaspi ads truth (`src_ab_db_ads_truth`) and precisely preserve the Meta/Facebook boundary (`src_facebook_ads_external_ads`) without hiding real spend.

Hard boundary:

- Do not mutate production `db/app.db`.
- Do not perform Meta/Instagram/Facebook ad platform writes of any kind.
- Do not perform Kaspi merchant/ad writes, pricing uploads, Telegram, LaunchAgents, workbooks, or customer/operator messages.
- You may read existing local evidence and create copied DBs via `sqlite3 .backup`.
- You may use Web_automation runtime SQLite evidence read-only.

Allowed writes:

- Evidence under `~/Docs/Autonomous_business/exports/validation/agent19_ads_truth_temp_proof_20260613/`
- Copied DBs under that evidence folder or `exports/validation/`
- Assigned closeout.
- Focused code/test patch only if the ads materializer or source parser has a bug that blocks copied-DB proof. Do not apply production DB writes.

Known current evidence:

- Web Automation accepted packet:
  `~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_source_packet_standardization/kaspi_marketing_source_freshness_packet.json`
- Agent 16 run copy:
  `~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260613_agent16_wa_kaspi_marketing_packet/kaspi_marketing_source_freshness_packet.json`
- Agent 17 Meta packet:
  `~/Docs/Business_3/Facebook_ads/runs/ab_source_freshness_20260613_acmewear_meta_spend_boundary/meta_live_refresh_summary.json`

Tasks:

1. Reproduce the ads blockers read-only:

```bash
PYTHONPATH=. .venv/bin/python scripts/validate_policy_source_freshness.py --db db/app.db --as-of 2026-06-13 --strict --json
PYTHONPATH=. .venv/bin/python scripts/validate_policy_gate_results.py --db db/app.db --strict --json
```

2. Inspect `scripts/materialize_ads_campaign_product_daily.py --help`, `tests/test_materialize_ads_campaign_product_daily.py`, and the Agent 16 packet to determine whether current accepted Kaspi Marketing evidence can populate `ads_source_refresh_runs` and `ads_campaign_product_daily` through `2026-06-13` for required stores.
3. Create copied DB:

```bash
sqlite3 db/app.db ".backup 'exports/validation/agent19_ads_truth_temp_proof_20260613/agent19_ads_probe.db'"
```

4. On the copied DB only, run the ads materializer dry-run using existing accepted Web_automation SQLite evidence. If it is scoped and sane, run copied-DB apply only with the documented env gates.
5. Materialize C3 source freshness/gates on the copied DB and verify whether `src_ab_db_ads_truth` clears. Keep `src_facebook_ads_external_ads` BLOCKED if the true current Meta packet still has spend and the contract requires ingestion rather than no-spend clearance.
6. Validate on copied DB:

```bash
sqlite3 -readonly exports/validation/agent19_ads_truth_temp_proof_20260613/agent19_ads_probe.db 'PRAGMA integrity_check;'
PYTHONPATH=. .venv/bin/python scripts/validate_policy_source_freshness.py --db exports/validation/agent19_ads_truth_temp_proof_20260613/agent19_ads_probe.db --as-of 2026-06-13 --strict --json
PYTHONPATH=. .venv/bin/python scripts/validate_policy_gate_results.py --db exports/validation/agent19_ads_truth_temp_proof_20260613/agent19_ads_probe.db --strict --json
PYTHONPATH=. .venv/bin/python scripts/validate_ads_spend_reality.py --db exports/validation/agent19_ads_truth_temp_proof_20260613/agent19_ads_probe.db --as-of 2026-06-13 --strict
```

Closeout requirements:

- Standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
- Before/after copied-DB row counts and max dates for `ads_source_refresh_runs`, `ads_campaign_product_daily`, `ads_campaign_daily_current`, `ads_campaign_product_daily_current`, `ads_spend_sidecar_daily`, and `ads_spend_sidecar_daily_sku`.
- State whether `src_ab_db_ads_truth` clears on copied DB.
- State why `src_facebook_ads_external_ads` remains blocked or how it can be cleared without lying about spend.
- If `GREEN`, include exact serialized production apply proposal with backup command, env gates, source DB paths, expected row deltas, and rollback path. Do not run it.
- If `YELLOW`, state the missing source/contract/code gap and the smallest next action.

