# Ads Web Automation Source Packet Contract

Status: `REVIEW_ONLY_CONTRACT_PATCH_V2`

Gate: `YELLOW_SOURCE_PACKET_CONTENT_AMENDMENT_IMPLEMENTED_PENDING_CODECAPTAIN_REVIEW`

## Purpose

This contract defines the only safe shape for adopting `~/Docs/Web_automation` Kaspi Marketing ads evidence into Autonomous Business ads freshness proof.

It does not authorize live fetches, browser login, credential use, Web_automation writes, scheduler changes, production `db/app.db` writes, workbook writes, owner publication, external writes, cash movement, PO commitment, ad spend, price changes, or stock changes.

## Required Packet Shape

The input is an immutable reviewed capture packet, not a loose Web_automation DB path.

The packet manifest must validate against:

`scripts/validate_ads_source_packet_contract.py`

Required top-level contract version:

`ads_web_source_packet.v1`

Required packet fields:

- `packet_root`
- `packet_sha256_manifest`
- `file_list`
- `raw_payload_files`
- `source_db_sha256`
- `raw_payload_hash_manifest`
- `redaction_manifest`
- `no_secrets_included=true`
- `capture`
- `store_identity`
- `source_db`
- `status`
- `spend_semantics`
- `adapter_output`
- `validator_replay`
- `warning_cohorts`

## Secret Boundary

The packet must prove `NO_SECRETS_INCLUDED=true`.

Forbidden in AB evidence and Oracle packs:

- `.env`
- cookies
- storage state
- browser profiles
- credentials
- session tokens
- login artifacts
- secret material

The redaction manifest must record `forbidden_artifacts_found=0`.

The validator must parse the redaction manifest file, not only the inline manifest field. The file and inline redaction object must agree on:

- `no_secrets_included=true`
- `forbidden_artifacts_found=0`
- no listed `forbidden_artifacts`

## Packet Immutability

When `--require-existing-files` is used, every `file_list` entry must:

- be relative to `packet_root`
- avoid `..` path traversal
- resolve inside `packet_root`
- exist on disk
- be a regular file

The packet SHA manifest must be parsed and must cover every `file_list` entry exactly once with a valid SHA-256 digest. The validator recalculates hashes for every listed file except the SHA manifest file itself, because self-hashing would make the manifest unstable.

The raw payload hash manifest must be parsed and must contain at least one payload hash. Every `raw_payload_files` entry must be listed in `file_list`, covered by the raw payload hash manifest, and hash-verified when files exist.

## Table, Schema, And Row Identity

The source packet must include source table names, schema hash, expected columns, row counts, uniqueness keys, and duplicate-key counts.

Required source DB SHA rule:

- top-level `source_db_sha256` is required
- nested `source_db.sha256` is required
- both values must be valid SHA-256 hex digests
- both values must match exactly

Required source table logical names:

- `campaign_daily`
- `campaign_product_daily`

Duplicate keys must fail closed. The adapter must reject duplicate keys or materialize them as machine-readable gaps; it must not silently aggregate duplicate rows.

Minimum uniqueness grain:

- campaign daily: `date`, business store identity, access store identity, campaign id
- product daily: `date`, business store identity, access store identity, campaign id, product key

## Timezone And Date Window

The packet must declare:

- `timezone`
- `captured_at`
- `finished_at`
- inclusive `date_start`
- inclusive `date_end`
- AB `as_of`
- AB `max_age_hours`

The packet must show how capture time maps to AB freshness policy. `ADS_SOURCE_STALE` may clear only if the packet is source-fresh under that policy.

## Store Identity Invariant

AB output `store_code` must always be the AB business store code.

For STOREB:

- `business_store_code=STOREB`
- Universal switcher access must be recorded separately as `access_store_code`
- adapter output `store_code` must remain `STOREB`

If access identity is written as business identity, fail closed as:

`ADS_STORE_IDENTITY_CONFLICT`

## Status And Gap Semantics

Allowed statuses:

- `FRESH`
- `STALE`
- `MISSING`
- `PARTIAL`
- `GAP`
- `NO_AUTH`
- `ERROR`
- `BLOCKED`
- `OK`

`allow-stale` may affect command exit severity only. It must never rewrite freshness truth or clear `ADS_SOURCE_STALE`.

Missing source rows are not zero spend. Missing rows must become machine-readable gaps.

Zero spend is valid only when the source packet proves a row or explicit source-backed zero for the exact date/store/campaign/product grain.

## Adapter Output Contract

The adapter proof must run only against a copied/temp DB evidence lane.

Required output tables:

- `ads_campaign_product_daily`
- `ads_source_refresh_runs`

Required `ads_campaign_product_daily` lineage:

- `source_run_id`
- `source_contract_version`
- `captured_at`
- `source_db_sha`
- `payload_hash`
- `coverage_status`

Required `ads_source_refresh_runs` lineage:

- `status`
- `source_freshness_age_hours`
- `max_age_hours`
- `heartbeat_status`
- `gap_status`
- `packet_sha256`

If the production schema cannot store every lineage field, the copied/temp proof must store the missing fields in an evidence sidecar and prove DB rows can be traced back to the packet.

## Validator Replay

Required validators:

- `ads_sidecar_readiness`
- `ads_offer_universe_coverage`

The proof must include a before/after matrix showing whether `ADS_SOURCE_STALE`:

- cleared by a source-fresh packet,
- remained visible,
- or was reclassified to an explicit gap status.

All validator outputs must remain under the lane evidence root. Validators must not fall back to production `db/app.db`.

## Warning Cohorts

These stoplines must remain visible unless a separate reviewed contract changes them:

- `23` product-identity quarantine rows
- `252` header-only source-gap rows
- `ADS_SOURCE_STALE`

The adapter proof must prove these warnings are preserved and not hidden, downgraded, productized, or treated as source truth.

## Production Authority Boundary

Web_automation current tables, SQLite files, or live fetch results are not AB production authority.

They become usable only after:

1. a reviewed immutable source packet exists;
2. the packet passes `scripts/validate_ads_source_packet_contract.py`;
3. the AB adapter proof runs against a copied/temp DB;
4. required validators replay under the evidence root;
5. CodeCaptain/operator review accepts the proof.

## Stoplines

Stop if any of these occur:

- live fetch, browser login, cookie/session/storage-state access, credential use, or Web_automation write without separate authorization
- secret material copied into AB or Oracle evidence
- Web_automation access identity written into AB as business identity
- STOREB replaced by Universal access identity
- missing ads rows treated as zero spend
- `allow-stale` clears or rewrites freshness truth
- `ADS_SOURCE_STALE` hidden while source age exceeds policy
- adapter writes to production `db/app.db`
- protected workbook touched
- scheduler, LaunchAgent, plist, or automation state changed
- validator outputs written outside the lane evidence directory
- validator silently uses production DB instead of copied/temp DB
- `23` or `252` warning cohorts hidden, downgraded, productized, or omitted
- ads-dependent owner publication, profit-after-ads, ad-spend, cash movement, supplier payment, PO commitment, price change, or stock change implied
