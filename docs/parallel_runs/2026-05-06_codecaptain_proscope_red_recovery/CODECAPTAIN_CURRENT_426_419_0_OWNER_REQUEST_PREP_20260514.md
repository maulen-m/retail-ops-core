# CodeCaptain Current 426/419/0 Owner Request Prep - 2026-05-14

Timestamp: `2026-05-14 21:35 +0500`

Source answer:

`~/Docs/Oracle/Autonomous_business/2026-05-14/211726_TASK-000_db-order-entry-apply-contract-review-current-426-419-0/answer/Code Captain_14.05.2026_21_30_19.md`

CodeCaptain gate:

`GREEN_TO_PREPARE_OWNER_PRODUCTION_APPLY_APPROVAL_REQUEST_FOR_DB_ORDER_ENTRY_RECOVERY_ONLY`

## Decision

Open the narrow DB-only order-entry owner-request preparation lane.

This authorizes preparing the owner approval request packet and rechecking the current boundary. It does not authorize production DB apply, owner phrase acceptance, workbook mutation, scheduler mutation, external writes, lifecycle/status repair, owner publication, cash, PO, ads, price, or stock changes.

The human owner's current broad approval is accepted for this plan implementation lane only. It is not accepted as the production apply authorization because CodeCaptain requires the exact reviewed phrase to be sent later in the correct launch context after launch-time gates pass.

## Current Reviewed Contract

- Target DB: `~/Docs/Autonomous_business/db/app.db`
- Target table: `fact_order_entries_kaspi`
- Source hierarchy: `API_RAW_ORDER_ENTRIES` only
- Expected would-insert rows: `426`
- Expected target order-store pairs: `419`
- Expected quarantine target rows: `0`
- Reviewed DB SHA: `09198109d63611ee1de120d6168ffcadb4195f84dbabe39215ddb969e332440a`
- Reviewed workbook SHA: `eb873974e05247eb30f8db0ce3d38db430eaa9d17afa2d698e1345bae8d91ba0`

Reviewed current-boundary evidence:

`~/Docs/Autonomous_business/exports/validation/order_entry_apply_contract_review/20260514_211328_current_preflight/`

## Inert Owner Phrase

This phrase is packet text only. It does not authorize apply unless the owner later sends it exactly in the correct launch context after all launch-time checks pass.

```text
AUTHORIZE DB-ONLY ORDER-ENTRY RECOVERY APPLY FOR ~/Docs/Autonomous_business/db/app.db AT PRE-SHA 09198109d63611ee1de120d6168ffcadb4195f84dbabe39215ddb969e332440a USING API_RAW_ORDER_ENTRIES ONLY; EXPECTED WOULD-INSERT 426 FACT_ORDER_ENTRIES_KASPI ROWS FOR 419 ORDER-STORE PAIRS WITH 0 QUARANTINE ROWS; NO WORKBOOK, SCHEDULER, EXTERNAL, WEBUI, CASH, PO, ADS, PRICE, STOCK, OWNER-PUBLICATION, OR LIFECYCLE-STATUS AUTHORITY.
```

## Execution Route

Launch Agent807 as a bounded execution agent through tmux orchestration.

Agent807 may:

- re-run read-only boundary checks;
- re-run the strict no-apply dry-run if needed;
- build a compact owner approval request packet;
- build an evidence manifest and rollback/apply checklist for later human review.

Agent807 must not:

- run `--apply`;
- set write-enable env gates for DB mutation;
- ask the owner for the phrase;
- mutate `db/app.db`, the protected workbook, launchd/schedulers, Web_automation, browser sessions, external accounts, cash, PO, ads, price, stock, or owner publication surfaces.

## Required Stop Conditions

Agent807 must close `YELLOW` or `RED` and stop before owner-ready wording if any of these occur:

- current DB SHA differs from `09198109d63611ee1de120d6168ffcadb4195f84dbabe39215ddb969e332440a`;
- current workbook SHA differs from `eb873974e05247eb30f8db0ce3d38db430eaa9d17afa2d698e1345bae8d91ba0`;
- DB integrity is not `ok`;
- unsafe SQLite sidecar exists;
- active protected-surface holder remains;
- fresh dry-run does not match `426 / 419 / 0`;
- dry-run reports `inserted_entry_rows > 0` or `production_db_modified=true`;
- source hierarchy includes workbook, manual WebUI archive, reserve archive, synthetic, or any non-API source;
- lifecycle/status caveat is presented as resolved.

## Next Gate

After Agent807 closes, the orchestrator reviews the packet. Only then can the human owner choose to send the exact phrase as a separate launch-context approval.

Gate: GREEN_TO_LAUNCH_AGENT807_OWNER_REQUEST_PACKET_PREP_ONLY
