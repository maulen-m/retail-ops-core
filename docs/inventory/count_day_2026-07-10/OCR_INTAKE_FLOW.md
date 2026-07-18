# OCR Intake Flow - Count Day 2026-07-10

Goal: turn count-day photos into an owner-approved manual count anchor without production writes during preparation.

## Existing Intake Surfaces Found

Manual count anchors:
- `config/anchors/manual_stock_counts/astana_warehouse_manual_stock_count_2026_05_30_2026_06_02.approved.json`
- `config/anchors/manual_stock_counts/astana_warehouse_manual_stock_count_2026_05_30_2026_06_02.approved_aggregate.csv`
- `config/anchors/manual_stock_counts/astana_warehouse_manual_stock_count_2026_06_04_pre_shipments.approved.json`
- `config/anchors/manual_stock_counts/astana_warehouse_manual_stock_count_2026_06_04_pre_shipments.approved_aggregate.csv`

Reusable tooling:
- `core/ops/manual_stock_count_manifest.py` validates approved manifest JSONs and can materialize aggregate CSV.
- `scripts/materialize_manual_stock_count_anchors.py` dry-runs and materializes count anchor metadata. Apply is separately gated.
- `scripts/materialize_temporary_ocr_stock_override.py` handles temporary OCR stock overrides for marketplace activation. It is not the count-day anchor path.

Current temporary OCR layer:
- `exports/current/temporary_ocr_stock_override/temporary_stock_decision_latest.csv`
- `exports/current/temporary_ocr_stock_override/temporary_stock_decision_latest.summary.json`

## Count-Day Flow

1. Photos
   - Capture source photos block by block using the OD-004 checklist.
   - Keep photo folders named by count block and timestamp.
   - Preserve originals. Do not edit source images used for OCR evidence.

2. OCR
   - Run three independent OCR passes.
   - Keep each pass output separately.
   - Mark unreadable cells as unresolved, not zero.

3. Reconciliation
   - Reconcile the three OCR passes into one intake CSV using `intake_template_20260710.csv`.
   - Preserve source image references per row.
   - Use expected-balance sheets only as a review aid.
   - Do not let the expected-balance sheet override the physical count.

4. Manifest Build
   - Convert the reconciled intake CSV to the manual manifest schema used by `core/ops/manual_stock_count_manifest.py`.
   - Include batch metadata, approval metadata, source artifact paths, expected totals, and one row per counted stock pool.
   - Owner approval is required before any production anchor apply.

5. Dry Run
   - Validate the manifest:
     - `.venv/bin/python -m core.ops.manual_stock_count_manifest --manifest PATH_TO_APPROVED_MANIFEST.json --write-aggregate-csv PATH_TO_AGGREGATE.csv`
   - Dry-run the anchor lane:
     - `.venv/bin/python scripts/materialize_manual_stock_count_anchors.py --db db/app.db --manifest PATH_TO_APPROVED_MANIFEST.json --output-root exports/validation/g_count_prep_20260706/manual_anchor_dry_run --json`
   - Dry-run the durable physical-count reconciliation lane:
     - `.venv/bin/python scripts/reconcile_manual_stock_count.py --db db/app.db --manifest PATH_TO_APPROVED_MANIFEST.approved.json --output-root exports/validation/manual_stock_count_reconcile_DATED`
   - Review `plan.csv`, `summary.json`, and `REPORT.md`. Each supported row proves the pre-count balance, post-count movement, adjustment delta, and projected current balance at the exact Asia/Almaty cut time.
   - Version 1 supports only `single_sku_pool` rows where `stock_pool_id == sku_id` and `applies_to_sku_ids == [sku_id]`. Shared pools are reported as blockers; no allocation is inferred.
   - A manifest source SHA/path or original batch already represented by another governed stock anchor or adjustment method is a hard blocker. Historical manifests must not be rematerialized through this lane.

6. Apply Gate
   - Apply is out of scope for this prep packet.
   - Future fixture apply requires `ENABLE_MANUAL_STOCK_COUNT_RECONCILE_WRITE=1`, `--apply`, and the exact `--expected-pre-sha256` from a clean dry-run.
   - Future production apply additionally requires `ALLOW_PRODUCTION_MANUAL_STOCK_COUNT_RECONCILE_WRITE=1`, an explicit `--backup-dir`, no SQLite sidecars, and both `--owner-instrument PATH_TO_DATED_OWNER_INSTRUMENT` and its exact `--owner-instrument-sha256`.
   - Generate the only accepted owner phrase with the read-only CLI mode: `.venv/bin/python scripts/reconcile_manual_stock_count.py --manifest PATH_TO_APPROVED_MANIFEST.approved.json --expected-pre-sha256 EXACT_CURRENT_DB_SHA --print-required-owner-approval-phrase`. The instrument file must contain exactly that literal phrase and its filename must contain the current Asia/Almaty apply date. The phrase binds the apply date, batch ID, manifest SHA, expected pre-DB SHA, exact allowed tables/write set, and `snapshot_rebuild=FORBIDDEN`; stale, arbitrary, or unrelated instruments fail closed.
   - The reconciler appends idempotent ledger adjustments and exact anchor/batch metadata in one transaction, then recomputes running balances for affected SKU/store pools. It never creates missing-size rows, clamps negatives to zero, or rebuilds `fact_inventory_snapshot_size`.
   - Reruns validate the immutable original count-cut note and arithmetic. Ordinary post-count movements are accepted; any newly arrived pre-count movement is a hard stop requiring owner review instead of silently changing the original adjustment.
   - Rebuild a morning snapshot only after the governed count apply and after all movements through the prior business day are complete.

## Synthetic Readiness Proof

Preparation dry-run artifacts:
- Synthetic manifest: `exports/validation/g_count_prep_20260706/synthetic_manual_count_manifest_20260710.approved.json`
- Parser proof: `exports/validation/g_count_prep_20260706/synthetic_manifest_validation.txt`
- Anchor dry-run proof: `exports/validation/g_count_prep_20260706/synthetic_anchor_dry_run_stdout.json`

The synthetic sample is not production authority. It exists only to prove the parser and count-anchor dry-run path are reachable before count day.

## Count-Day Naming Recommendation

Use these names for the real 2026-07-10 artifacts:

- Photo root: `manual_stock_count_2026_07_10_photos/`
- Reconciled intake CSV: `manual_stock_count_2026_07_10_reconciled_intake.csv`
- Approved manifest: `manual_stock_count_2026_07_10.approved.json`
- Aggregate CSV: `manual_stock_count_2026_07_10.approved_aggregate.csv`
- Dry-run output root: `exports/validation/manual_stock_count_2026_07_10_dry_run/`

## Required Owner/Operator Confirmation Before Apply

1. Count cut time in Asia/Almaty.
2. Whether count includes in-transit, quarantine, returns, and packed-not-shipped units.
3. Which count families require owner review before any activation action.
4. Whether OD-017 negative rows stay quarantined until manual correction.
5. Whether `CL` placeholder identity rows should be mapped during count day or isolated for later cleanup.
