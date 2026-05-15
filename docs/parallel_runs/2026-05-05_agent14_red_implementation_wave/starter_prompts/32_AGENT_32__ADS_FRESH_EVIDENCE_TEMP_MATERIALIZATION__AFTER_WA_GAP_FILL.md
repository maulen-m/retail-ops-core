# Agent 32 - Ads Fresh Evidence Temp Materialization

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_32_ads_fresh_evidence_temp_materialization_closeout.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/ORCHESTRATOR_REVIEW_AFTER_WA_ADS_GAP_FILL.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_28_ads_canonical_reader_bridge_closeout.md`
6. `~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_acmewear_post_0415_and_historical_daily_readonly/WA_ACMEWEAR_GAP_FILL_CLOSEOUT.md`
7. `~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_storeb_post_0415_mapping_readonly/WA_STOREB_POST0415_MAPPING_CLOSEOUT.md`
8. this starter prompt

## Mission

Materialize the fresh Web_automation Kaspi Marketing evidence into a fresh Autonomous_business temp DB, using canonical ads truth. Do not write production `db/app.db`.

The goal is to prove exactly how much the fresh ACMEWEAR and STOREB evidence reduces `ADS_REFRESH_MISSING` and `ADS_COVERAGE_MISSING`, while preserving unresolved Meta/Facebook and STOREB mapping blockers.

## Write Boundary

Allowed:

- ads materializer code/tests if needed to support the new Web_automation evidence DB/CSV formats;
- temp DB and evidence under `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_32_evidence/`;
- assigned closeout.

Forbidden:

- production `db/app.db` writes;
- workbook edits;
- external-system writes;
- ad-platform writes;
- Web_automation writes;
- non-ads code changes;
- fuzzy-name mapping;
- weakening ads/source publication gates.

## Source Evidence To Consume

ACMEWEAR fresh evidence:

- closeout: `~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_acmewear_post_0415_and_historical_daily_readonly/WA_ACMEWEAR_GAP_FILL_CLOSEOUT.md`
- SQLite: `~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_acmewear_post_0415_and_historical_daily_readonly/kaspi_marketing_gap_fill.sqlite`
- summary: `~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_acmewear_post_0415_and_historical_daily_readonly/source_evidence_summary.json`

STOREB fresh evidence:

- closeout: `~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_storeb_post_0415_mapping_readonly/WA_STOREB_POST0415_MAPPING_CLOSEOUT.md`
- SQLite: `~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_storeb_post_0415_mapping_readonly/kaspi_marketing.sqlite`
- summary: `~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_storeb_post_0415_mapping_readonly/source_evidence_summary.json`

Prior baseline sources may still be needed for historical periods:

- `~/Documents/useful tables/Main crm spreadsheets/main tables/External_database/Kaspi_marketing/db/kaspi_marketing.db`
- `~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_acmewear_readonly/kaspi_marketing_readonly.sqlite`
- `~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_storeb_universal_switcher_readonly/kaspi_marketing.sqlite`

## Required Work

1. Write tests first if materializer support for `kaspi_marketing_gap_fill.sqlite` or its table names is missing.
2. Copy production `db/app.db` to a fresh temp DB.
3. Replay the necessary source materializers on the temp DB through `2026-05-04`.
4. Materialize ads using prior and fresh evidence sources.
5. Preserve unresolved STOREB product-code mapping blockers:
   - `11122298b`
   - `11391711b`
   - `11942309b`
   - `12071269b`
   - `12236047b`
6. Preserve ACMEWEAR Meta/Facebook source freshness as blocked/stale unless a separate Facebook_ads source-freshness artifact already proves freshness or no-spend scope.
7. Run canonical validators:
   - `scripts/validate_ads_sidecar_readiness.py`
   - `scripts/validate_ads_offer_universe_coverage.py`
   - `scripts/validate_ads_spend_reality.py`
   - `scripts/validate_operational_stock_integration_gates.py`
   - policy source/gate validators if C3 state is materialized.
8. Produce a before/after residual table for ads blockers.

## Stoplines

- No production DB apply.
- No live source fetches.
- No external writes.
- No product-name/fuzzy mapping.
- Do not clear Meta/Facebook source freshness from Kaspi Marketing evidence.
- Do not claim production publication green unless every strict source gate passes.

## Closeout Requirements

Include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- files changed;
- tests written first;
- commands run with pass/fail;
- temp DB path;
- before/after ads residual counts;
- validator matrix;
- remaining blocker list;
- explicit production apply status.
