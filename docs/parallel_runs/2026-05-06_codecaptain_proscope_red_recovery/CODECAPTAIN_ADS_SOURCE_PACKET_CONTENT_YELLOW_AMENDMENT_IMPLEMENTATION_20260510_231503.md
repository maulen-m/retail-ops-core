# CodeCaptain Ads Source-Packet Content Yellow Amendment Implementation

Generated at: `2026-05-10T23:15:03+0500`

Status: `ADS_SOURCE_PACKET_CONTENT_YELLOW_AMENDMENT_IMPLEMENTED_REVIEW_ONLY`

## Source Review

CodeCaptain answer:

`~/Docs/Oracle/Autonomous_business/2026-05-10/225538_TASK-000_codecaptain-ads-source-contract-yellow-amendment-rereview/answer/Code Captain_10.05.2026_23_09_40.md`

Decision: `YELLOW_AMEND_SOURCE_PACKET_CONTRACT_BEFORE_PROOF`

## Implemented Amendments

- Added full `file_list` containment checks under `--require-existing-files`.
- Added packet SHA manifest parsing with exact `file_list` coverage and SHA-256 validation.
- Added hash recalculation for listed packet files where possible, excluding the packet SHA manifest file itself to avoid self-hashing instability.
- Added `raw_payload_files` to the packet contract.
- Added raw payload hash manifest parsing, non-empty payload requirement, raw payload coverage, and hash recalculation.
- Added redaction manifest JSON parsing and agreement checks with inline redaction fields.
- Added top-level `source_db_sha256` validation and equality with `source_db.sha256`.
- Added regressions for missing listed files, path traversal, packet SHA coverage gaps, empty raw-payload manifests, redaction contradictions, and source DB SHA mismatch.
- Updated `docs/validation/ADS_WEB_AUTOMATION_SOURCE_PACKET_CONTRACT.md` to document the stricter content checks.

## Scope Boundary

This implementation is review-only. It does not authorize live-readonly Web_automation proof, browser login, credential use, Web_automation writes, production `db/app.db` mutation, workbook mutation, scheduler automation, owner publication, owner approval request, or any external write.

## Verification

- `pytest -q tests/test_ads_source_packet_contract.py` -> `15 passed`
- `pytest -q tests/test_ads_source_packet_contract.py tests/test_ads_canonical_truth.py tests/test_validate_ads_sidecar_readiness.py tests/test_validate_ads_offer_universe_coverage.py` -> `37 passed`
- `python3 -m py_compile core/ads/source_packet_contract.py scripts/validate_ads_source_packet_contract.py` -> PASS
- `git diff --check -- core/ads/source_packet_contract.py scripts/validate_ads_source_packet_contract.py tests/test_ads_source_packet_contract.py docs/validation/ADS_WEB_AUTOMATION_SOURCE_PACKET_CONTRACT.md docs/validation/ADS_ACTIVE_SCOPE_CONTRACT.md docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/CODECAPTAIN_ADS_SOURCE_PACKET_CONTENT_YELLOW_AMENDMENT_IMPLEMENTATION_20260510_231503.md` -> PASS
- `./scripts/lint_docs.sh` -> PASS
- `./scripts/check_no_db_tracked.sh` -> PASS

Next safe gate: package/send the amended content contract to CodeCaptain before any live-readonly Web_automation proof.
