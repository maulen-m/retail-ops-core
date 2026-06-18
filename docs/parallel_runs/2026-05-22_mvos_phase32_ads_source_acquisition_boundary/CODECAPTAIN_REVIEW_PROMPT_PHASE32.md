# CodeCaptain Review Prompt - Phase32 Ads Source Acquisition Boundary

Please review the Phase32 ads source acquisition boundary for the `2026-05-22` Autonomous_business MVOS current boundary.

Phase31 proved that local ads evidence cannot clear current source freshness:

- `src_facebook_ads_external_ads`: `7` local candidates, `0` accepted current candidates.
- `src_web_automation_kaspi_marketing_directapi`: `1` local candidate, `0` accepted current candidates.

Phase32 did not perform live fetches. It prepares the exact boundary and starter prompts for the next read-only source acquisition wave.

## Why Review Is Needed

The next real closure step is read-only ads source acquisition, but the output boundary needs explicit review:

- Web_automation can fetch Kaspi Marketing data with `--run-dir` and `--db-path`.
- Web_automation repo contract says it must not write into Autonomous_business.
- The active Autonomous_business owner envelope forbids Web_automation writes.
- Facebook_ads has a prior accepted `ab_source_freshness_*` Meta packet precedent, but the current envelope does not explicitly authorize new Business_3/Facebook_ads run writes.

## Review Questions

1. Do you agree Phase32 should stay `YELLOW_BOUNDARY_PREPARED_NO_LIVE_FETCH` until the owner pastes a narrow source-acquisition approval phrase or CodeCaptain approves a stricter route?
2. Is the proposed approval phrase sufficient to allow generated local evidence in Web_automation / Facebook_ads source repos plus copied redacted/hash evidence in Autonomous_business?
3. Should Kaspi Marketing accepted packets be generated in Web_automation and consumed by AB, or should AB own a wrapper that writes only under `exports/validation/`?
4. Should a Meta `meta_live_refresh_summary.json` generated under `Business_3/Facebook_ads/runs/ab_source_freshness_*` remain acceptable for AB `src_facebook_ads_external_ads` materialization?
5. If positive spend appears in Meta or Kaspi Marketing current source, should source freshness stop and route to reviewed spend ingestion, or may source freshness clear while spend ingestion remains an explicit separate blocker?

## Proposed Approval Phrase

```text
I approve Phase32 read-only ads source acquisition for Autonomous_business. Agents may use existing Web_automation Kaspi Marketing read-only tooling and Business_3/Facebook_ads Meta read-only tooling to fetch current ads source evidence through 2026-05-22 for STOREB and ACMEWEAR, writing only dedicated local run/evidence artifacts under clearly labeled Phase32 run folders in the owning source repo and/or copied redacted hashed evidence under ~/Docs/Autonomous_business/exports/validation/mvos_phase32_ads_source_acquisition_boundary. This narrowly overrides the prior no-Web_automation-writes/no-Facebook_ads-writes boundary only for generated Phase32 local evidence artifacts, not for code, config, schedulers, source pointers, production DB, workbooks, prices, stock, cash, PO, owner publication, external writes, Kaspi/API/WebUI mutations, ad-platform writes, ad spend, bid/budget/status/campaign changes, or secret/cookie/storage-state copying. Agents must stop YELLOW if packet shape, no-write proof, source coverage, secret redaction, or protected-surface checks fail.
```

## Included Context

- Phase31 acceptance audit result.
- Current blocker board and current source truth map.
- Phase32 boundary and starter plan.
- Ads source packet contract.
- Current packet observer requirements from `core/ops/policy_materialization_c3.py`.
