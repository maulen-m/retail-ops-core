# Copied-Temp Source-Freshness Bridge Contract

Contract id: `COPIED_TEMP_SOURCE_FRESHNESS_BRIDGE_ONLY`

Status: active for copied-temp MVOS proof replay only.

## Contract

Accepted source packets and source contracts may be materialized into the copied validation DB as `source_freshness_result` rows for proof replay only.

This does not update production `db/app.db`, does not authorize owner publication, and does not convert copied-temp source freshness into production source freshness.

## Required Row Fields

Every bridge row must include:

- `source_id`
- `source_packet_path`
- `source_packet_sha`
- `captured_at`
- `as_of`
- `status`
- `blocks_publication`
- `proof_scope="copied_temp"`
- `production_authority=false`

## Apply Boundary

The bridge materializer:

- refuses `--apply` against production `db/app.db`;
- requires `ENABLE_C3_POLICY_MATERIALIZATION_WRITE=1` and `--apply` before mutating any copied DB;
- validates that `source_packet_path` is a real file and that `source_packet_sha` matches the current bytes;
- validates that `source_id` is an active `policy_source_registry` row;
- fails closed on missing fields, hash mismatch, non-`copied_temp` scope, or `production_authority=true`.

## Non-Authority

Bridge rows are proof replay inputs only. They must not be used to:

- change production source pointers;
- mutate workbooks, schedulers, Web_automation, Kaspi/API/WebUI, ad platforms, cash, PO, stock, or prices;
- approve owner publication;
- claim production source freshness;
- hide retained blockers in policy gates or downstream validators.

Owner-publication readiness can be claimed only if all required validators genuinely pass on the copied proof and no retained blocker remains visible.
