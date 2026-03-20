# PLAN — Option 1 + Option 3 Identity Stabilization (Fail-Closed)
Date: 2026-03-03
Scope: stabilize order identity for Kaspi daily ops using (1) external snapshot bridge and (3) API ingestion root-cause repair.

## Objective
Make identity fields (`sku_key`, `sku_id`, `my_size`, `kaspi_offer_name`) deterministic and auditable for daily imports/ship/waybill and sales truth.

## Non-negotiables
- Fail-closed by default.
- No silent fallback mappings.
- External repo (`~/Docs/Web_automation`) is read-only reference only.
- DB writes only with `--apply` + env gate + backup + apply manifest.

## Current baseline (must be reproduced)
- Artifact: `exports/validation/identity_option1_option3_plan_2026-03-03/baseline_identity_gap_summary.json`
- Supporting CSVs:
  - `exports/validation/identity_option1_option3_plan_2026-03-03/db_recent_identity_nulls_by_store.csv`
  - `exports/validation/identity_option1_option3_plan_2026-03-03/web_snapshot_identity_unresolved_summary_2026-03-02.csv`

## Phase P0 — Contracts + Source Registry
### Deliverables
- `docs/validation/KASPI_IDENTITY_BRIDGE_CONTRACT.md`
- `config/anchors/kaspi_external_mapping_snapshot.json` (path + sha256 + generated_at + source manifest)

### Implementation
- Define canonical key precedence for mapping:
  1) explicit local override
  2) external mapping snapshot bridge
  3) `dim_kaspi_article_map`
  4) parser fallback
- Define mandatory audit columns: `identity_source`, `identity_confidence`, `resolver_version`, `resolver_key_type`.

### Tests
- `tests/test_identity_bridge_contract.py`
- Red: missing anchor/sha mismatch => fail.
- Green: valid anchor with deterministic parse => pass.

### Evidence
- `exports/validation/identity_bridge_contract/<run_id>/contract_validation.json`

## Phase P1 — External Mapping Bridge (Read-only)
### Deliverables
- `scripts/build_external_identity_bridge_snapshot.py`
- Output:
  - `exports/reference/identity_bridge/<as_of>/identity_bridge_snapshot.csv`
  - `exports/reference/identity_bridge/<as_of>/identity_bridge_manifest.json`

### Implementation
- Read external snapshot files (`universal_snapshot_*.xlsx`, `store-b_snapshot_*.xlsx`) and normalize to:
  - `store_code`, `kaspi_article`, `resolved_url`, `resolved_kaspi_offer_name`, `effective_sku_key`, `effective_final_size`, `mapping_method`, `mapping_status`, `identity_status`.
- Reject rows with `mapping_status=deprecated` by default (configurable explicit allowlist only).

### Tests
- `tests/test_build_external_identity_bridge_snapshot.py`
- Deterministic hash/reproducibility test.
- Reject malformed schema / missing required columns.

### Evidence
- `exports/validation/identity_bridge_snapshot/<run_id>/snapshot_report.md`

## Phase P2 — Local Identity Resolver + Backfill (Option 1 containment)
### Deliverables
- `scripts/resolve_order_identity_from_bridge.py`
- `scripts/backfill_recent_order_identity.py`
- New local table/migration: `identity_resolution_audit` (or equivalent)

### Implementation
- Dry-run default.
- Apply mode requires:
  - `ENABLE_IDENTITY_BACKFILL_APPLY=1`
  - `--apply`
  - DB backup `runtime/backups/app.db.pre_identity_backfill_<timestamp>.sqlite`
  - apply manifest `exports/validation/identity_backfill/<run_id>/apply_manifest.json`
- Backfill window default: last 45 days.
- Populate null `sku_key/sku_id/my_size/kaspi_offer_name` only when deterministic match exists.
- Unresolved rows are emitted to quarantine, never guessed.

### Tests
- `tests/test_resolve_order_identity_from_bridge.py`
- `tests/test_backfill_recent_order_identity_apply_gating.py`
- Ensure idempotence (run twice, same result).

### Evidence
- `exports/validation/identity_backfill/<run_id>/dry_run_report.json`
- `exports/validation/identity_backfill/<run_id>/unresolved_rows.csv`

## Phase P3 — Ingestion Root-Cause Repair (Option 3)
### Deliverables
- Update ingestion path:
  - `scripts/sync_kaspi_orders.py`
  - `core/sync/order_sync_engine.py`
  - (if needed) `core/integrations/kaspi_api_client.py`
- Ensure fresh entries feed:
  - `fact_order_entries_kaspi` populated for new orders
  - `offer_id/article` fields retained

### Implementation
- Hard gate in ingestion:
  - If new orders for the run have missing identity-bearing fields above threshold (default 0 for strict), fail run.
- Persist run metrics to:
  - `exports/validation/identity_ingest_freshness/<as_of>/ingest_identity_freshness.json`

### Tests
- `tests/test_order_sync_identity_payload_contract.py`
- `tests/test_fact_order_entries_freshness_gate.py`

### Evidence
- `exports/validation/identity_ingest_freshness/<as_of>/ingest_identity_freshness.md`

## Phase P4 — Strict Gates Integration
### Deliverables
- `scripts/validate_identity_coverage.py`
- `scripts/validate_mapping_parity_external_snapshot.py`
- `scripts/validate_no_random_sku_assignments.py`
- Wire into `scripts/system_doctor.py --strict`

### Implementation
- Stopline if:
  - null identity rate > threshold
  - unexpected divergence from external bridge for bridged rows
  - guessed/random mapping source appears

### Tests
- `tests/test_validate_identity_coverage.py`
- `tests/test_validate_mapping_parity_external_snapshot.py`
- `tests/test_validate_no_random_sku_assignments.py`

### Evidence
- `exports/validation/identity_gates/<as_of>/identity_gate_report.json`

## Phase P5 — Daily Ops Integration (Import/Waybill/Ship)
### Deliverables
- Preflight hook before `run_full_import.command` and waybill build:
  - block if unresolved identity above policy threshold for target window
- Report artifact:
  - `exports/daily/<as_of>/identity_operational_readiness.json`

### Tests
- `tests/test_daily_ops_identity_preflight_contract.py`

### Evidence
- `exports/validation/identity_ops_preflight/<as_of>/preflight_report.md`

## Phase P6 — Historical Cleanup Program (bounded)
### Deliverables
- `scripts/run_identity_historical_reconciliation.py`
- Windowed reconciliation (monthly chunks), never blind full rewrite.

### Tests
- `tests/test_identity_historical_reconciliation.py`

### Evidence
- `exports/validation/identity_historical/<run_id>/window_summary.csv`
- `exports/validation/identity_historical/<run_id>/top_root_causes.md`

## Mandatory Gates (final closeout)
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
- `python3 scripts/validate_params.py --strict`
- `python3 scripts/validate_single_truth_system.py`
- `bash scripts/lint_docs.sh`
- `python3 scripts/system_doctor.py --strict --project-root . --as-of <AS_OF>`
- `python3 scripts/validate_identity_coverage.py --as-of <AS_OF> --strict`
- `python3 scripts/validate_mapping_parity_external_snapshot.py --as-of <AS_OF> --strict`
- `python3 scripts/validate_no_random_sku_assignments.py --as-of <AS_OF> --strict`

## Success Criteria
- New orders no longer enter with null identity core fields.
- Recent window null identity rate at/under contract thresholds.
- All mapping writes are auditable and reproducible.
- Daily ops strict chain blocks on identity drift before financial publication.
