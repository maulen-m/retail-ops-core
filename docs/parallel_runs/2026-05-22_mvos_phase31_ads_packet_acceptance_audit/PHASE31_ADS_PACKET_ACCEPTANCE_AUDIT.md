# PHASE31_ADS_PACKET_ACCEPTANCE_AUDIT

Status: `YELLOW_RETAINED_NO_ACCEPTED_CURRENT_ADS_PACKET`
Created: `2026-05-22`

This audit is read-only/evidence-only. It does not authorize production DB writes, workbook writes, source-pointer writes, scheduler/LaunchAgent/cron changes, Web_automation writes, external writes, Kaspi/API/WebUI mutations, ad-platform writes, ad spend, cash movement, PO commitment, stock or price changes, owner publication, production preflight, or production apply.

## Boundary

- Requested as-of date: `2026-05-22`
- Evidence root: `exports/validation/mvos_phase31_ads_packet_acceptance_audit/20260522_0505`
- Candidate matrix: `ads_packet_acceptance_matrix.csv`
- Candidate audit JSON: `ads_packet_acceptance_audit.json`
- DB materialization: not attempted, because accepted current candidate count is `0`.

## Result

Phase31 checked all local Meta/Facebook and Kaspi Marketing source packet candidates relevant to the current ads source blockers:

| source_id | candidate_count | accepted_current_candidate_count | result |
| --- | ---: | ---: | --- |
| `src_facebook_ads_external_ads` | `7` | `0` | retained stale |
| `src_web_automation_kaspi_marketing_directapi` | `1` | `0` | retained blocked |

No candidate can safely clear the `2026-05-22` source-freshness boundary.

## Meta/Facebook Findings

Phase31 found `7` local Meta candidates:

- `5` May19/20 files under `Business_3/Facebook_ads/exports/.../meta_readonly_summary.json`.
- `2` older AB source-freshness packet files under `Business_3/Facebook_ads/runs/ab_source_freshness_*`.

The May19/20 files are useful operator evidence but are not accepted AB source-freshness packets:

- filename is `meta_readonly_summary.json`, not `meta_live_refresh_summary.json` or `meta_source_freshness_summary.json`;
- path is under `exports`, not a `runs/ab_source_freshness_*` run folder;
- gates are `YELLOW` or `RED`;
- required AB packet fields are missing, including `ab_can_clear_src_facebook_ads_external_ads`, `dates_requested`, `dates_successfully_fetched`, `date_results`, write-safety booleans, and `any_spend_found=false`;
- files are older than the current 24-hour source window for `2026-05-22`;
- readonly summaries retain unknowns about Ads Manager unpublished draft/edit state;
- the latest May20 owner-manual budget verification file is `RED` because actual product adset budgets were `[2500, 2500]` minor units instead of the expected `[2000, 2000]`.

The only local Meta AB packet with `gate=GREEN` is:

`~/Docs/Business_3/Facebook_ads/runs/ab_source_freshness_20260505_acmewear_meta_live_refresh/meta_live_refresh_summary.json`

It remains valid for the old May4 boundary only. It covers requested dates through `2026-05-04`, not `2026-05-22`.

## Kaspi Marketing DirectAPI Findings

Phase31 found exactly `1` local Kaspi Marketing source-freshness packet:

`~/Docs/Web_automation/runs/ab_ads_source_refresh_data_gathering/20260505_source_packet_standardization/kaspi_marketing_source_freshness_packet.json`

It is structurally `GREEN`, but only for the old boundary:

- packet `as_of=2026-05-04`;
- strict `date_coverage_through=2026-05-04`;
- no `date_coverage_through_2026_05_22` flag;
- `STOREB` latest covered date is `2026-05-04`;
- `ACMEWEAR` latest covered date is `2026-05-04`.

## Route Decision

Do not bridge or materialize these candidates as current green source truth.

The next safe autonomous action, if permitted by the owner, is a read-only source acquisition lane that produces accepted current-as-of packets:

- Meta/Facebook packet under the accepted AB source-freshness shape, with `gate=GREEN`, exact requested dates through `2026-05-22`, raw evidence paths, write-safety booleans, and no deterministic attribution claim.
- Kaspi Marketing DirectAPI packet under `kaspi_marketing_source_freshness_packet.v1`, with `as_of=2026-05-22`, `STOREB` and `ACMEWEAR` coverage through `2026-05-22`, store coverage flags, zero-write proofs, source SQLite/evidence summaries, and closeout no-write checks.

If fresh read-only source acquisition is not authorized or cannot prove the accepted packet shape, keep `ads_source_truth` and `source_freshness` yellow.
