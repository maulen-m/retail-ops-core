# CodeCaptain Review Prompt - Phase31 Ads Packet Acceptance Audit

Please review the Phase31 ads packet acceptance audit for the `2026-05-22` MVOS current boundary.

No production DB writes, workbook writes, source-pointer writes, scheduler/LaunchAgent/cron changes, Web_automation writes, external writes, Kaspi/API/WebUI mutations, ad-platform writes, ad spend, cash movement, PO commitment, stock changes, price changes, owner publication, production preflight, or production apply were requested or performed.

## What Phase31 Proved

Phase31 audited local ads evidence candidates and found `0` accepted current candidates:

- `src_facebook_ads_external_ads`: `7` local candidates, `0` accepted for `2026-05-22`.
- `src_web_automation_kaspi_marketing_directapi`: `1` local candidate, `0` accepted for `2026-05-22`.

The May19/20 Meta files are readonly summaries, not AB source-freshness packets:

- filename `meta_readonly_summary.json`;
- under `exports`, not `runs/ab_source_freshness_*`;
- gates `YELLOW` or `RED`;
- missing required packet fields and write-safety booleans;
- older than the 24-hour source window for `2026-05-22`;
- include Ads Manager draft/edit unknowns;
- latest owner-manual budget verification is `RED`.

The only `GREEN` Meta AB packet covers only through `2026-05-04`.

The only Kaspi Marketing DirectAPI packet is structurally `GREEN`, but only for `as_of=2026-05-04`, with STOREB/ACMEWEAR coverage through `2026-05-04`, not `2026-05-22`.

## Review Questions

1. Do you agree Phase31 should retain `ads_source_truth` and `source_freshness` as yellow until accepted current-as-of packets are produced?
2. Is a new read-only source acquisition lane sufficient before the next copied-temp rerun, or do you require review of packet-construction rules first?
3. For Meta/Facebook, is the accepted packet shape still the current `meta_live_refresh_summary.json` / `meta_source_freshness_summary.json` contract, or should it be revised for May19/20 operator summaries?
4. For Kaspi Marketing DirectAPI, confirm the current minimum accepted packet requirements: `schema_version=kaspi_marketing_source_freshness_packet.v1`, `as_of=2026-05-22`, `STOREB` and `ACMEWEAR` coverage through `2026-05-22`, zero-write proofs, source SQLite/evidence summary paths, and closeout no-write checks.
