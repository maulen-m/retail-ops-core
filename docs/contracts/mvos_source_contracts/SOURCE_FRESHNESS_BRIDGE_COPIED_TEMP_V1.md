# SOURCE_FRESHNESS_BRIDGE_COPIED_TEMP_V1

Status: active copied-temp contract.

Accepted at: `2026-05-18T21:23:26+05:00`

Accepted by: CodeCaptain `2026-05-18 21:23:26` review, under the existing owner-approved accepted-packets-only C3 bridge rule.

Supersedes: `COPIED_TEMP_SOURCE_FRESHNESS_BRIDGE_ONLY`.

## Purpose

This contract allows accepted May 18 source evidence to be materialized into `source_freshness_result` rows on a copied validation DB only. It is a proof bridge, not production source freshness.

## Scope

Allowed scope:

- copied validation DB only;
- accepted source packets and active copied-temp contracts only;
- `source_freshness_result` materialization with `proof_scope=copied_temp`;
- `production_authority=false`;
- retained-blocker board proof.

Forbidden scope:

- production `db/app.db` mutation;
- source-pointer mutation;
- workbook mutation;
- scheduler mutation;
- Web_automation mutation;
- external writes;
- owner publication;
- treating missing ads spend as zero;
- bridging unaccepted source packets.

## Required Row Fields

Every bridge row must include:

- `source_id`;
- `source_packet_path`;
- `source_packet_sha`;
- `captured_at`;
- `as_of`;
- `status`;
- `blocks_publication`;
- `proof_scope="copied_temp"`;
- `production_authority=false`;
- active contract id or accepted source packet id.

## Accepted Bridge Behavior

The bridge may materialize only source evidence that is already accepted by:

- `OWNER_QA_PRIORITY_20260518_RETAINED_BLOCKERS.md`;
- `OWNER_QA_PRIORITY_20260517.md`;
- active `ACTIVE_MVOS_SOURCE_CONTRACT_REGISTRY.json` entries;
- the CodeCaptain `2026-05-18 21:23:26` contract review when non-conflicting with owner truth.

Unaccepted source truth remains a visible blocker. May 18 ads spend must remain gap/blocker unless a source packet proves zero spend or actual spend.

## Required Validation

The next proof wave must run:

```bash
python3 scripts/validate_policy_source_freshness.py --db <copied-db> --as-of 2026-05-18 --strict --json
python3 scripts/validate_policy_gate_results.py --db <copied-db> --strict --json
```

Expected proof behavior:

- accepted bridge rows can clear copied-temp-only freshness checks;
- unaccepted sources remain blockers;
- `blocks_publication=true` remains true unless a later production/publication contract explicitly clears it;
- missing ads spend is not inferred as zero.

## Stoplines

- Do not bridge unaccepted packets.
- Do not claim production source freshness.
- Do not set `production_authority=true`.
- Do not set missing May 18 ads spend to zero.
- Do not hide `src_ab_db_operational_truth`, stock truth, or ads truth blockers unless validators genuinely clear them on a copied DB.
