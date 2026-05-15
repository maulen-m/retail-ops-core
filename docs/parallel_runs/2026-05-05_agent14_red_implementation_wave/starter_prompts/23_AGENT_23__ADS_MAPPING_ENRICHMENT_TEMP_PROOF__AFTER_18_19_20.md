# Agent 23 - Ads Mapping Enrichment Temp Proof

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_23_ads_mapping_enrichment_temp_proof_closeout.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-05_agent14_red_implementation_wave/PLAN.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/README.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/ORCHESTRATOR_REVIEW_AFTER_AGENTS_18_20.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_20_ads_materializer_temp_proof_closeout.md`
8. `~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_storeb_universal_switcher_readonly/WA2_STOREB_CLOSEOUT.md`
9. this starter prompt

## Mission

Continue Agent 20's ads materialization lane by adding stable mapping/enrichment proof for STOREB Kaspi advertised product codes, while keeping ads coverage fail-closed.

You are not alone in the codebase. Do not revert edits made by others. Touch only your owned files. If an owned file has unexpected concurrent edits beyond Agent 20's accepted baseline, stop and close out YELLOW/RED with evidence.

## Owned Write Set

Primary:

- `~/Docs/Autonomous_business/scripts/materialize_ads_campaign_product_daily.py`
- `~/Docs/Autonomous_business/tests/test_materialize_ads_campaign_product_daily.py`

Optional only if strictly needed:

- fixture files under `~/Docs/Autonomous_business/tests/fixtures/`;
- generated temp/evidence files under your handoff evidence folder.

Forbidden:

- production `db/app.db` writes;
- Web_automation repo writes;
- live Kaspi Marketing calls;
- ad-platform writes;
- derived-table files owned by Agent 22;
- C3 policy files owned by Agent 19.

## Evidence Inputs

STOREB Web_automation evidence:

- `~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_storeb_universal_switcher_readonly/kaspi_marketing.sqlite`
- `~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_storeb_universal_switcher_readonly/campaign_product_daily_live_chrome.csv`
- `~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_storeb_universal_switcher_readonly/campaign_product_window_live_chrome.csv`
- `~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_storeb_universal_switcher_readonly/live_chrome_product_report_summary.json`

Agent 20 temp state:

- before: `ADS_REFRESH_MISSING=1016`, `ADS_COVERAGE_MISSING=1016`;
- after Agent 20 temp proof: `ADS_REFRESH_MISSING=0`, `ADS_COVERAGE_MISSING=247`;
- remaining coverage blockers: `ACMEWEAR=22`, `STOREB=225`.

## Mapping Rules

Allowed mapping evidence:

- exact Kaspi advertised product code if AB has a stable product-code mapping table or source;
- exact article strings from `related_order_products` only when they match AB SKU keys/articles deterministically;
- exact joins to order-entry/sales facts when a stable code/article/order relation exists;
- explicit generated sidecar mapping with confidence/provenance, if tests prove it is deterministic and non-fuzzy.

Forbidden mapping evidence:

- fuzzy product-name matching as the only basis;
- assuming every STOREB campaign row maps to LINE52 without exact provenance;
- marking STOREB as covered/no-spend from campaign-level spend alone;
- converting positive aggregate spend to daily SKU-level `COVERED` without daily product evidence.

## Required Implementation

Write tests first, then code.

Required behavior:

1. Materializer can consume a stable STOREB product-code mapping/enrichment source if available or generated deterministically.
2. Unmapped STOREB product codes remain blocked and visible.
3. Mapped STOREB daily product-code rows can create `COVERED` or `NO_SPEND_VERIFIED` rows only at supported source grain.
4. Business store remains `STOREB`; Universal is access provenance only.
5. Remaining ACMEWEAR `CL_OC_MEN_LINE51_WHITE` positive-aggregate blockers stay blocked unless exact daily product evidence exists.
6. Dry-run remains default; apply remains env-gated with `ENABLE_C3_ADS_SOURCE_WRITE=1`.

## Required Temp Proof

Use a copied temp DB, not production:

`/private/tmp/agent23_ads_mapping_enrichment_temp_proof_20260504.db`

Run dry-run and temp apply only against that DB.

## Required Gates

Run focused tests for your changed files.

Run:

- `python3 scripts/validate_operational_stock_integration_gates.py --db <temp_db> --as-of 2026-05-04 --json`
- `python3 scripts/validate_ads_sidecar_readiness.py --db <temp_db> --as-of 2026-05-04 --output-root <evidence_dir>/sidecar --strict`
- `python3 scripts/validate_ads_offer_universe_coverage.py --db-path <temp_db> --as-of 2026-05-04 --start 2026-01-01 --end 2026-05-04 --output-dir <evidence_dir>/offer --strict`
- `python3 scripts/validate_ads_spend_reality.py --db-path <temp_db> --as-of 2026-05-04 --start 2026-01-01 --end 2026-05-04 --output-dir <evidence_dir>/spend --strict`
- `sqlite3 <temp_db> 'PRAGMA integrity_check;'`

## Closeout Requirements

Include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- files changed;
- tests written first;
- exact product-code mapping result for all 10 STOREB codes;
- blocker counts before and after temp materialization;
- whether remaining ACMEWEAR blockers require a Web_automation daily-evidence retry;
- production apply stoplines.
