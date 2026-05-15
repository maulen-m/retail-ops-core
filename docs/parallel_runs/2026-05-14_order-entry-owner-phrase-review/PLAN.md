# Order-Entry Owner-Phrase Review Packet Plan

Purpose: implement CodeCaptain's `GREEN_TO_PREPARE_NARROW_OWNER_PHRASE_REQUEST_REVIEW_ONLY` decision while preserving all stoplines.

## Current Preflight

At orchestration preflight on `2026-05-14 19:23 +05`:

- `all-business` automation verify: `OK`, `0/27` labels loaded.
- `db/app.db` hash: `09198109d63611ee1de120d6168ffcadb4195f84dbabe39215ddb969e332440a`.
- `excel_ui/SALES_KSP_CRM_V3.xlsx` hash: `eb873974e05247eb30f8db0ce3d38db430eaa9d17afa2d698e1345bae8d91ba0`.
- `db/app.db` integrity: `ok`.

Reviewed frozen hashes in the patched readiness packet:

```text
0b5f6c1bd8dcfeb387a50b94bc3afa2b4391d3dfacc0f452ebbfa9bcfed9a5d6  db/app.db
e7ff6fd8da8938b3247343a58e1257c102ac1d62077f68f33ad7a5b8a45ec870  excel_ui/SALES_KSP_CRM_V3.xlsx
```

Because both current hashes differ from the reviewed frozen hashes, this rollout must be drift-aware. It may run the current-production dry-run and package evidence, but it must not claim owner-phrase readiness unless the packet explicitly routes the drift to reviewed-equivalent/new-proof review.

## Inputs

- CodeCaptain GREEN re-review answer:
  `~/Docs/Oracle/Autonomous_business/2026-05-14/182340_TASK-000_codecaptain-order-entry-readiness-packet-patch-rereview/answer/Code Captain_14.05.2026_19_20_41 .md`
- Patched readiness packet:
  `~/Docs/Autonomous_business/exports/validation/frozen_window_option1_2_combined_copy_proof/20260514_113412/production_readiness/ORDER_ENTRY_PRODUCTION_APPLY_READINESS_PACKET.md`
- Prior re-review pack:
  `~/Docs/Oracle/Autonomous_business/2026-05-14/182340_TASK-000_codecaptain-order-entry-readiness-packet-patch-rereview`

## Roles

Agent 804: execution writer.

- May run read-only current-production dry-run.
- May write local evidence, Oracle review packet, and assigned handoff files.
- Must not use `--apply`.
- Must not set write env gates.
- Must not ask owner for phrase.
- Must not mutate production DB, workbook, scheduler, external systems, ad-platforms, cash, PO, stock, or price.

Agent 805: read-only verifier after Agent 804.

- Reads Agent 804 output and dry-run summary.
- Independently verifies source hierarchy, row counts, quarantine, hashes, stoplines, and non-authorization boundaries.
- Writes only its assigned closeout.

## Expected Outcome

If current dry-run and boundary checks pass but hashes drifted, create a CodeCaptain review packet asking whether the current dry-run constitutes a reviewed-equivalent target set / explicit boundary review, before any owner phrase request is prepared.

If dry-run row counts, source hierarchy, quarantine, holders, or integrity fail, keep the lane YELLOW or RED with exact evidence.

Production apply remains blocked in all cases.
