# CodeCaptain Ads Source-Contract Yellow Amendment Implementation

Generated at: `2026-05-10T22:51:08+0500`

Status: `ADS_SOURCE_CONTRACT_YELLOW_AMENDMENT_REREVIEW_PACK_READY`

## Source Review

CodeCaptain answer:

`~/Docs/Oracle/Autonomous_business/2026-05-10/222851_TASK-000_codecaptain-ads-source-contract-review/Answer/Code_Captain_10.05.2026_22_41_58.md`

Decision: `YELLOW_AMEND_ADS_SOURCE_CONTRACT_BEFORE_LIVE_READONLY`

## Implemented Amendments

- Added an immutable Web_automation ads source-packet contract and validator:
  - `core/ads/source_packet_contract.py`
  - `scripts/validate_ads_source_packet_contract.py`
- Added regression coverage:
  - `tests/test_ads_source_packet_contract.py`
- Added review-only contract documentation:
  - `docs/validation/ADS_WEB_AUTOMATION_SOURCE_PACKET_CONTRACT.md`
- Updated the active ads scope contract to point to the source-packet contract and state that Web_automation current tables, SQLite files, and live fetch results are not AB production authority until packet-contract and copied/temp adapter proof gates pass:
  - `docs/validation/ADS_ACTIVE_SCOPE_CONTRACT.md`

## Contract Coverage

The implemented guard now fails closed on:

- missing packet root, file list, packet SHA manifest, raw payload hash manifest, redaction manifest, or `NO_SECRETS_INCLUDED=true`;
- secret-like artifacts such as `.env`, cookies, storage state, browser profiles, credentials, sessions, tokens, or secrets;
- missing table/schema/row identity, duplicate keys, or malformed numeric fields;
- access-store versus business-store identity conflicts via `ADS_STORE_IDENTITY_CONFLICT`;
- unsupported freshness/gap statuses or `allow-stale` attempts to clear `ADS_SOURCE_STALE`;
- missing rows being treated as zero spend;
- adapter output targeting production DB instead of copied/temp DB evidence;
- missing lineage fields for `ads_campaign_product_daily` and `ads_source_refresh_runs`;
- missing validator replay matrix or hidden `23` / `252` warning cohorts.

## Verification

- `pytest -q tests/test_ads_source_packet_contract.py` -> `8 passed`
- `pytest -q tests/test_ads_source_packet_contract.py tests/test_ads_canonical_truth.py tests/test_validate_ads_sidecar_readiness.py tests/test_validate_ads_offer_universe_coverage.py` -> `30 passed`
- `python3 -m py_compile core/ads/source_packet_contract.py scripts/validate_ads_source_packet_contract.py` -> PASS
- `git diff --check -- core/ads/source_packet_contract.py scripts/validate_ads_source_packet_contract.py tests/test_ads_source_packet_contract.py docs/validation/ADS_WEB_AUTOMATION_SOURCE_PACKET_CONTRACT.md docs/validation/ADS_ACTIVE_SCOPE_CONTRACT.md` -> PASS
- `./scripts/check_no_db_tracked.sh` -> PASS, no tracked/staged `.db` files

## Scope Boundary

This implementation is review-only. It does not authorize live-readonly Web_automation proof, browser login, credential use, Web_automation writes, production `db/app.db` mutation, workbook mutation, scheduler automation, owner publication, owner approval request, or any external write.

## Re-Review Pack

CodeCaptain amended source-contract re-review pack:

`~/Docs/Oracle/Autonomous_business/2026-05-10/225538_TASK-000_codecaptain-ads-source-contract-yellow-amendment-rereview`

Pack facts:

- file count `4`;
- bundle SHA `10d414d9723819590acd87bf4739a1c1f8ec51526fb9685d912f0aaf7a5e59f0`;
- mandatory CSV SHA `e5f4ba4e5cdcf152bf01d7364fbca4d5f213ca83275cbe344cf04052e162db99`.

Next safe gate: send the re-review pack to CodeCaptain and import the answer before any live-readonly Web_automation proof.
