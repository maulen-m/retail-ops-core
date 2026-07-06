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

6. Apply Gate
   - Apply is out of scope for this prep packet.
   - Future apply requires owner approval, DB backup, explicit write-enable env gate, and `--apply`.

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
