# Agent 23 - Meta Positive Spend Ingestion Boundary

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-06-13_green_path_resume/agent_23_meta_positive_spend_ingestion_boundary_closeout.md`

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_PHASE2_ADS_PARTIAL_PROD_APPLY_20260613.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_PHASE2_ADS_LINE31TS_QUARANTINE_20260613.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-06-13_green_path_resume/agent_21_ads_external_and_ab_truth_green_proof_closeout.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-06-13_green_path_resume/agent_17_meta_source_packet_boundary_closeout.md`
7. This starter prompt.

Role: determine the minimum honest route to clear `src_facebook_ads_external_ads` when the Meta packet contains real positive spend. Do not convert real spend into a no-spend packet.

Hard boundary:

- Do not mutate production `db/app.db`.
- Do not edit repo files.
- Do not call live Meta/Facebook/Instagram write APIs.
- Do not perform Kaspi merchant, pricing, Telegram, LaunchAgent, workbook, customer, or operator-message writes.
- You may create copied DBs and evidence files only.

Allowed writes:

- Evidence under `~/Docs/Autonomous_business/exports/validation/agent23_meta_positive_spend_ingestion_boundary_20260613/`
- Copied DBs under that evidence folder.
- Assigned closeout.

Tasks:

1. Reproduce the current retained source/gate blockers read-only on production after commit `8cb0b1f`:

```bash
PYTHONPATH=. .venv/bin/python scripts/validate_policy_source_freshness.py --db db/app.db --as-of 2026-06-13 --strict --json
PYTHONPATH=. .venv/bin/python scripts/validate_policy_gate_results.py --db db/app.db --strict --json
PYTHONPATH=. .venv/bin/python scripts/validate_ads_offer_universe_coverage.py --db-path db/app.db --as-of 2026-06-13 --start 2026-06-13 --end 2026-06-13 --strict --output-dir exports/validation/agent23_meta_positive_spend_ingestion_boundary_20260613/prod_ads_offer_coverage
```

2. Inspect the Meta packet and current C3/policy code:

- `~/Docs/Business_3/Facebook_ads/runs/ab_source_freshness_20260613_acmewear_meta_spend_boundary/meta_live_refresh_summary.json`
- `~/Docs/Autonomous_business/core/ops/policy_materialization_c3.py`
- `~/Docs/Autonomous_business/scripts/materialize_policy_source_freshness.py`
- `~/Docs/Autonomous_business/scripts/materialize_policy_gate_results.py`
- `~/Docs/Autonomous_business/tests/test_policy_materialization_c3.py`

3. Answer these exactly:

- What positive spend amount/date/account/campaign/adset evidence exists in the Meta packet?
- Which current code path blocks it, and what exact reason code is emitted?
- Is there an existing production table/contract that can ingest positive external Meta spend without inventing product attribution?
- If yes, prove it on a copied DB and include exact serialized production apply commands, expected row deltas, validators, and rollback.
- If no, specify the smallest code/schema/contract change needed. Include table names, grain, required fields, source packet hash/provenance fields, source-freshness semantics, and the validator/test updates required.

4. If a copied DB proof is possible, create it with SQLite online backup only:

```bash
sqlite3 db/app.db ".backup 'exports/validation/agent23_meta_positive_spend_ingestion_boundary_20260613/agent23_meta_probe.db'"
```

Then materialize only on the copied DB with documented env gates and rerun:

```bash
sqlite3 -readonly exports/validation/agent23_meta_positive_spend_ingestion_boundary_20260613/agent23_meta_probe.db 'PRAGMA integrity_check;'
PYTHONPATH=. .venv/bin/python scripts/validate_policy_source_freshness.py --db exports/validation/agent23_meta_positive_spend_ingestion_boundary_20260613/agent23_meta_probe.db --as-of 2026-06-13 --strict --json
PYTHONPATH=. .venv/bin/python scripts/validate_policy_gate_results.py --db exports/validation/agent23_meta_positive_spend_ingestion_boundary_20260613/agent23_meta_probe.db --strict --json
```

Closeout requirements:

- Standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
- Explicit status for `src_facebook_ads_external_ads`.
- Exact positive-spend evidence from the Meta packet.
- Exact current blocker reason code(s).
- Existing path proof or missing contract/schema/code details.
- If owner approval is needed, provide one copy-paste approval phrase with exact allowed scope and explicit no-live-write boundaries.

Success bias: prefer a small source-freshness ingestion contract that records real external spend provenance over any attempt to map spend to product-level ads unless the existing repo contract already requires that mapping.
