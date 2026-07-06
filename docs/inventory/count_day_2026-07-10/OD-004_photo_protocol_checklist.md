# OD-004 Photo Protocol Checklist - Count Day 2026-07-10

Source authority:
- `docs/plan/green_path_2026-06/OWNER_DECISIONS_RECORDED.yaml`, decision `OD-004`
- Supporting prose: `docs/plan/green_path_2026-06/OWNER_DECISION_PACK.md`
- Supporting canonical batch draft: `docs/plan/green_path_2026-06/reconciliation/count_batch_2026-06-11_2200/count_batch_canonical_DRAFT.md`

Status:
- OD-004 registry was found.
- This checklist restates the protocol for 2026-07-10 operator use. It is not a replacement authority.

## Before Photos

1. Finish all physically relevant warehouse moves for the cut point.
2. Freeze the count area by family or shelf group before starting photos.
3. Keep marketplace activation, sales decisions, and DB writes outside the photo capture flow.
4. Prepare one folder per count block with a stable timestamp in Asia/Almaty time.
5. Put one visible family/area label in the first image of each block.

## Photo Capture

1. Photograph every pile, box, rack, and visible size label for the block.
2. Capture labels straight-on when possible.
3. Capture a wider context image before close-ups when the shelf or pile grouping matters.
4. Avoid mixing two unrelated families in one close-up unless the label makes the separation obvious.
5. Retake any blurred size or quantity image before moving to the next block.
6. If a size is physically present but unreadable, mark it for owner/operator follow-up. Do not infer it.

## OD-004 OCR And Reconciliation Standard

The OD-004 decision recorded a three-pass OCR protocol:

1. Run three independent OCR passes:
   - pass 1: Opus-style OCR
   - pass 2: Opus-style OCR
   - pass 3: Codex-style OCR
2. Reconcile the three pass outputs at host level.
3. Build one canonical draft count manifest.
4. Send unresolved blocking cells to owner instead of guessing.
5. Keep source images and reconciled manifest paths in the evidence folder.

## OD-004 Count Semantics To Preserve

The June OD-004 registry established these interpretation rules:

1. Dot-separated digits are SUM additions unless the registry for that batch says otherwise.
2. A number followed by a right-arrow marker means FULL_SUPERSEDE.
3. An empty size is NOT_CAPTURED, not zero.
4. Restored cancel-return stock without order linkage is included as stock when source-backed.
5. Newer owner-approved count layers take precedence over older layers.
6. Post-count trusted movements must be applied after the count anchor; do not rebuild a partial range that resets opening balances.

## Count-Day Checklist

1. Create photo folders before counting.
2. Capture source photos block by block.
3. Run the three OCR passes.
4. Reconcile OCR into `intake_template_20260710.csv` shape.
5. Review negative, held, OD-017, and CL identity rows against the printable count sheets.
6. Convert the reconciled intake CSV into an approved manual count manifest.
7. Run the anchor materializer dry first.
8. Only apply after owner approval, DB backup, explicit write-enable env gate, and `--apply`.

## Stop Conditions

Stop and ask owner/operator when:
- a size label is unreadable and materially changes quantity;
- a count family maps to more than one candidate `sku_key` or `sku_id`;
- a row maps only to `CL` placeholder identity;
- the physical count conflicts with an active hold/negative-stock exception;
- the count requires changing OD-004 semantics instead of applying them.
