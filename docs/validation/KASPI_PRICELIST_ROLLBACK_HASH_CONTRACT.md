# Kaspi Pricelist Rollback Hash Contract

## Purpose
`G-WA-02` prevents price-lane uploads from becoming one-way doors. Every Kaspi
pricelist upload must have a staged rollback workbook before upload and a
verified readback hash after upload.

## Authority
- Gate: `G-WA-02`
- AB verifier: `scripts/verify_kaspi_pricelist_hash.py`
- Manifest: `config/validation/kaspi_pricelist_hash_manifest.csv`
- Supporting WA verifier: `inventory/verify_pricelist_snapshots_and_uploads.py`

## Manifest Columns
- `upload_id`
- `upload_stage`: `planned` or `applied`
- `store_name`
- `upload_file`
- `rollback_file`
- `post_readback_file`
- `expected_upload_sha256`
- `expected_rollback_sha256`
- `expected_post_readback_sha256`
- `upload_applied_at`
- `owner_decision_id`
- `gate_id`
- `notes`

## Rules
- `planned` rows must include the intended upload workbook, rollback workbook,
  and expected SHA-256 for both before any upload is allowed.
- `applied` rows must additionally include the post-upload readback workbook and
  expected readback SHA-256.
- `gate_id` must be `G-WA-02`.
- `upload_file`, `rollback_file`, and readback files are resolved relative to
  the manifest parent first, then relative to the Web_automation repo root.
- `ARMED` means the contract and verifier are usable but no applied upload row
  has yet proved rollback plus post-readback hashes.
- `GREEN` means at least one applied row has all required hashes verified and
  every manifest row passes.
- `RED` means any required file/hash/column check fails.

## Safety
This verifier is read-only. It does not upload files, edit workbooks, write
prices, change stock, message operators/customers, or call external systems.
