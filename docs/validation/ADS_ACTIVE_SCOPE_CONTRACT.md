# Ads Active Scope Contract

## Purpose
- Encode which stores are expected to have Kaspi ads coverage by effective date.
- Prevent validators from treating intentionally inactive stores as missing-ads failures.
- Distinguish full sold-SKU ads coverage from advertised-product-only coverage.
- Keep the rule explicit, versioned, and auditable.

## Source Of Truth
- Config file: `config/ads_active_scope.yaml`
- Web_automation source-packet adoption contract: `docs/validation/ADS_WEB_AUTOMATION_SOURCE_PACKET_CONTRACT.md`

## Rules
- Resolution is store-by-store and date-by-date.
- If a store/date falls inside an active window, ads coverage and spend-reality gates apply.
- If a store/date falls inside an inactive window, ads coverage is not required for those sold rows.
- If a store has no matching window, `default_active` from the config applies.
- Inactive scope suppresses false missing-ads failures only. It does not fabricate ads spend or relax unrelated gates.
- The config is date-level, not timestamp-level. If a manual stop occurs during a day, preserve the exact event timestamp in an event record and keep same-day source truth explicit instead of silently inferring zero spend.
- Active windows must declare a `coverage_mode`.
- `all_sold_skus` means every sold SKU in the active store/date scope must have product-level ads coverage or exact no-spend evidence.
- `advertised_products_only` means product-level coverage is required only for SKU/product codes represented by exact mapped ads evidence. Sold SKUs that were never advertised are outside the coverage universe and must not create false `ADS_COVERAGE_MISSING` findings.
- `advertised_products_only` does not treat missing source as zero. Store/month spend-reality still fails when the active store/month has sales but neither positive spend nor verified no-spend ads rows.
- Positive-spend advertised product/code rows that cannot be exactly mapped remain blockers. Mapping conflicts must stay fail-closed until exact evidence resolves them.
- Web_automation current tables, SQLite files, or live fetch results are not AB production authority until they pass the immutable source-packet contract and a copied/temp AB adapter proof.

## Current Effective Policy
- `ACMEWEAR`: active from `2025-01-01` through `2026-05-04` with `all_sold_skus` coverage where the accepted historical source evidence supports full sold-SKU coverage or exact no-spend rows.
- `ACMEWEAR`: active from `2026-05-05` forward with `advertised_products_only` coverage because the accepted post-`2026-05-04` Kaspi Marketing evidence is exact campaign-product/day source evidence plus refresh proof, not a full-store absence/no-spend proof for every sold SKU.
- `STOREB`: active from `2026-03-08` through `2026-05-20` for Kaspi internal generic advertised product offers with `advertised_products_only` coverage; Jan-Feb 2026 is not ads-required.
- `STOREB`: manually stopped by the human owner at exact timestamp `2026-05-20 09:46:41 +05`; because the active-scope resolver is date-level, `2026-05-20` remains the final same-day source-refresh day and the inactive date-level window begins `2026-05-21`.
- `UNIVERSAL`: explicitly inactive from `2026-02-22`; no historical Jan-Feb 2026 active window is encoded without source evidence
- Unlisted stores default to inactive until explicitly added

## Evidence Basis
- Active scope is not inferred from sales volume.
- Historical windows must be backed by marketing-source evidence or an explicit operator decision with a concrete effective date.
- Fresh Jan-Feb 2026 source refreshes for `STOREB` and `UNIVERSAL` returned zero campaigns/products, so those stores are not treated as ads-required for that historical window.
- Owner clarification recorded `2026-05-04`: Meta/Facebook funnel ads are ACMEWEAR scoped; STOREB is scoped to Kaspi internal marketing for generic LINE52-like advertised product offers, not the entire STOREB sold SKU universe.
- Post-`2026-05-04` ACMEWEAR Kaspi Marketing imports are exact advertised campaign-product evidence. They prove the advertised product rows and daily refresh coverage, but they do not prove that unrelated sold SKUs had zero Kaspi ads; therefore unrelated sold SKUs must not emit false `ADS_COVERAGE_MISSING` findings under this window.
- Owner manual external action recorded `2026-05-20`: STOREB ads campaign was fully stopped manually at `2026-05-20 09:46:41 +05`; canonical event record is `docs/marketing/STOREB_ADS_CAMPAIGN_MANUAL_STOP_20260520_094641.md`.
- Current unresolved STOREB mapping conflicts, including `11391711b`, `11942309b`, and `11391205b`, are not cleared by this scope contract.

## Change Management
- Update this contract first.
- Then update `config/ads_active_scope.yaml`.
- Then update tests and validators.
- Broad or retrospective quarantine is not allowed without explicit documented rationale.
