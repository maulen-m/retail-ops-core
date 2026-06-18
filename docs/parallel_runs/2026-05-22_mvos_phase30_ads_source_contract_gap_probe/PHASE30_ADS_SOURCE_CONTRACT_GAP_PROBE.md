# PHASE30_ADS_SOURCE_CONTRACT_GAP_PROBE

Status: `YELLOW_ADS_SOURCE_CONTRACT_GAP_RETAINED`
Created: `2026-05-22`

This probe is copied-temp/evidence-only. It does not authorize production DB writes, workbook writes, source-pointer writes, scheduler/LaunchAgent/cron changes, Web_automation writes, external writes, Kaspi/API/WebUI mutations, ad-platform writes, ad spend, cash movement, PO commitment, stock or price changes, owner publication, production preflight, or production apply.

## Boundary

- Source DB: Phase29 copied DB.
- Probe DB: `exports/validation/mvos_phase30_ads_source_contract_gap_probe/20260522_0455/app_phase30_ads_probe.sqlite`
- Evidence root: `exports/validation/mvos_phase30_ads_source_contract_gap_probe/20260522_0455`
- Source rows materialized: `src_facebook_ads_external_ads`, `src_web_automation_kaspi_marketing_directapi`.
- Production DB SHA stayed `726a6bc45a4811423390e28698a63e39f5d9400057fb2671ca68c255468371b5`.

## Result

Phase30 did not clear ads source truth. It made the retained ads source gap exact:

| source_id | status | max_observed_at | row_count | blocks_publication |
| --- | --- | --- | ---: | ---: |
| `src_facebook_ads_external_ads` | `STALE` | `2026-05-04T23:59:59+05:00` | `18` | `1` |
| `src_web_automation_kaspi_marketing_directapi` | `BLOCKED` | `2026-05-04T23:59:59+05:00` | `15` | `1` |

The accepted Meta packet is structurally green for its old requested dates, but it only covers through `2026-05-04`. Local May19/20 Meta readonly summary files exist under `Business_3/Facebook_ads/exports`, but they are not accepted Autonomous Business source-freshness packets for `2026-05-22`.

The accepted Kaspi Marketing DirectAPI packet is structurally green for its old boundary, but fails the current boundary:

- `DATE_COVERAGE_BEFORE_AS_OF:2026-05-04`
- `DATE_COVERAGE_FLAG_NOT_TRUE:date_coverage_through_2026_05_22`
- `PACKET_AS_OF_MISMATCH:2026-05-04`
- `STORE_DATE_COVERAGE_BEFORE_AS_OF:STOREB:2026-05-04`
- `STORE_DATE_COVERAGE_BEFORE_AS_OF:ACMEWEAR:2026-05-04`
- `STORE_DATE_COVERAGE_FLAG_NOT_TRUE:STOREB:date_coverage_through_2026_05_22`
- `STORE_DATE_COVERAGE_FLAG_NOT_TRUE:ACMEWEAR:date_coverage_through_2026_05_22`

Strict source freshness remains at four retained errors:

- `src_ab_db_operational_truth` remains `BLOCKED`.
- `src_bank_manual_ingest` remains `STALE`.
- `src_facebook_ads_external_ads` remains `STALE`.
- `src_web_automation_kaspi_marketing_directapi` remains `BLOCKED`.

Policy gates remain unchanged at four blockers:

- `ads_source_truth`
- `cashflow_source_truth`
- `source_freshness`
- `stock_source_truth`

## Evidence

- `local_meta_readonly_summary_candidates.txt`: local May19/20 Meta readonly summary candidates found, not accepted as current AB source-freshness packet.
- `local_webautomation_kaspi_marketing_packet_candidates.txt`: accepted Kaspi Marketing packet candidate found, but old boundary only.
- `materialize_ads_sources_dryrun.json`: source-filtered dry-run for the two ads sources.
- `materialize_ads_sources_apply.json`: copied-temp source materialization applied only to the copied DB.
- `ads_source_rows_after_apply.csv`: exact source rows and evidence JSON after materialization.
- `validate_policy_source_freshness_20260522_after_ads_probe.json`: strict source freshness still fails with four errors.
- `validate_policy_gate_results_strict_after_ads_probe.json`: strict C3 policy gates still fail with four blocked gates.
- `materialize_c3_policy_state_ads_sources_dryrun.json`: source-filtered C3 dry-run remains `1` stale and `1` blocked ads source.
- `v_source_freshness_current_after_ads_probe.csv`: current source view after copied-temp materialization.
- `v_policy_gate_latest_after_ads_probe.csv`: current gate view after copied-temp materialization.

## Route Decision

The fastest safe route is a current accepted ads source packet, not a production apply. The next agent should either:

1. Build accepted `2026-05-22` source-freshness packets for Meta and Kaspi Marketing DirectAPI from read-only source evidence, then rerun copied-temp materialization and strict validators.
2. If fresh evidence cannot be acquired, keep `ads_source_truth` and `source_freshness` yellow with these exact packet-boundary reasons.

No ad spend, bid, budget, campaign, external source, source-pointer, production DB, workbook, scheduler, or owner-publication action is authorized by this probe.
