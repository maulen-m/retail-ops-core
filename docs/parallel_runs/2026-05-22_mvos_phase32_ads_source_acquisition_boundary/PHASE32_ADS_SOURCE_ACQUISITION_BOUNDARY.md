# PHASE32_ADS_SOURCE_ACQUISITION_BOUNDARY

Status: `YELLOW_BOUNDARY_PREPARED_NO_LIVE_FETCH`
Created: `2026-05-22`

This Phase32 document turns the Phase31 retained ads packet blocker into an executable next route without pretending that source truth is already green.

No production DB writes, workbook writes, source-pointer writes, scheduler/LaunchAgent/cron changes, Web_automation writes, Business_3/Facebook_ads writes, external writes, Kaspi/API/WebUI mutations, ad-platform writes, ad spend, cash movement, PO commitment, stock or price changes, owner publication, production preflight, or production apply were performed.

## Why Phase32 Exists

Phase31 proved that local evidence is not enough to clear the current `2026-05-22` ads source boundary:

| source_id | local candidates | accepted current candidates | retained reason |
| --- | ---: | ---: | --- |
| `src_facebook_ads_external_ads` | `7` | `0` | May19/20 files are readonly summaries, not accepted AB source-freshness packets; old accepted packet covers only through `2026-05-04`. |
| `src_web_automation_kaspi_marketing_directapi` | `1` | `0` | The only packet is structurally green but only for `as_of=2026-05-04`, not `2026-05-22`. |

The next real closure step is current read-only ads source acquisition, but the output boundary is not clean under the current approval:

- Web_automation has usable `kaspi-marketing fetch-campaigns` tooling with `--run-dir` and `--db-path`.
- Web_automation `AGENTS.md` says that repo must not write into `~/Docs/Autonomous_business`.
- The active Autonomous_business owner envelope forbids Web_automation writes.
- Facebook_ads has prior `ab_source_freshness_*` packet tooling, but the active Autonomous_business envelope did not explicitly authorize new Business_3/Facebook_ads run writes.

Therefore Phase32 does not launch live fetches. It prepares the exact acquisition contract, starter prompts, and approval phrase needed to run the next wave safely.

## Required Accepted Outputs

### Kaspi Marketing DirectAPI

The next accepted packet must satisfy the current `core/ops/policy_materialization_c3.py` observer contract:

- `schema_version=kaspi_marketing_source_freshness_packet.v1`
- `source_policy_key=src_web_automation_kaspi_marketing_directapi`
- `gate=GREEN`
- `ab_can_clear_src_web_automation_kaspi_marketing_directapi=true`
- `as_of=2026-05-22`
- `strict_requirements.date_coverage_through >= 2026-05-22`
- `strict_requirements.date_coverage_through_2026_05_22=true`
- `stores_required` and `stores_covered` include `STOREB` and `ACMEWEAR`
- each store has `latest_covered_date >= 2026-05-22`
- each store has `date_coverage_through_2026_05_22=true`
- source SQLite files, evidence summaries, and closeout files exist, hash-check, and remain parseable
- no-write fields are all zero, and `read_only_external_operations=true`
- closeout no-write checks prove no WebUI/API/Kaspi mutation, no ad-platform mutation, no budget/bid/status/campaign changes, and no secret values stored

### Meta/Facebook

The next accepted packet must satisfy the current Meta observer contract:

- filename is `meta_live_refresh_summary.json` or `meta_source_freshness_summary.json`
- packet is under an accepted `runs/ab_source_freshness_*` run folder
- `gate=GREEN`
- `ab_can_clear_src_facebook_ads_external_ads=true`
- `dates_requested` covers the requested current window through `2026-05-22`
- `dates_successfully_fetched` exactly matches `dates_requested`
- every `date_results` row has `source_status=SUCCESS` and `clears_source_freshness=true`
- `source_freshness_cleared_by_date[date]=true` for every requested date
- raw evidence paths exist under the same packet run
- `platform_writes_occurred=false`
- `budget_status_campaign_adset_ad_writes_occurred=false`
- `autonomous_business_writes_performed=false`
- `deterministic_purchase_attribution_claimed=false`
- `any_spend_found=false`, or if spend is found, the lane must stop before treating it as source freshness clearance and route to a reviewed external-ads ingestion contract

## Starter Pack Prepared

Starter folder:

`~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_PHASE32_ADS_SOURCE_ACQUISITION_BOUNDARY_20260522_STARTERS`

Launch order after exact owner approval:

1. Agent 32A: Kaspi Marketing DirectAPI current packet acquisition and no-write proof.
2. Agent 32B: Meta/Facebook current packet acquisition and no-write proof.
3. Agent 32C: copied-temp Autonomous_business source-freshness materialization and ads gate rerun, only after both 32A and 32B are `GREEN`.

Agents 32A and 32B may run in parallel after the approval phrase below is pasted. Agent 32C must not run if either source packet is `YELLOW` or `RED`.

## Approval Phrase Required Before Live Read-Only Fetch

The current owner envelope does not resolve the cross-repo evidence-output conflict. Paste this exact phrase before launching Phase32 live-readonly acquisition:

```text
I approve Phase32 read-only ads source acquisition for Autonomous_business. Agents may use existing Web_automation Kaspi Marketing read-only tooling and Business_3/Facebook_ads Meta read-only tooling to fetch current ads source evidence through 2026-05-22 for STOREB and ACMEWEAR, writing only dedicated local run/evidence artifacts under clearly labeled Phase32 run folders in the owning source repo and/or copied redacted hashed evidence under ~/Docs/Autonomous_business/exports/validation/mvos_phase32_ads_source_acquisition_boundary. This narrowly overrides the prior no-Web_automation-writes/no-Facebook_ads-writes boundary only for generated Phase32 local evidence artifacts, not for code, config, schedulers, source pointers, production DB, workbooks, prices, stock, cash, PO, owner publication, external writes, Kaspi/API/WebUI mutations, ad-platform writes, ad spend, bid/budget/status/campaign changes, or secret/cookie/storage-state copying. Agents must stop YELLOW if packet shape, no-write proof, source coverage, secret redaction, or protected-surface checks fail.
```

## CodeCaptain Review Questions

1. Is the Phase32 approval phrase sufficient to resolve the cross-repo evidence-output boundary, or should current source acquisition wait until CodeCaptain reviews a stricter AB-native wrapper?
2. For Kaspi Marketing, is a Web_automation-owned run folder plus copied redacted/hashed AB evidence acceptable, or must all accepted artifacts live only in Autonomous_business?
3. For Meta/Facebook, may the accepted packet be generated under `Business_3/Facebook_ads/runs/ab_source_freshness_*` and consumed by Autonomous_business, matching the May5 precedent?
4. If either source produces positive spend, should Phase32 stop before source-freshness clearance and route to an external-ads ingestion contract, or can source freshness clear while spend ingestion remains a separate visible blocker?

## Current Decision

Gate remains `YELLOW`.

No live fetch was launched. No copied-temp materialization was attempted because accepted current packets still do not exist.
