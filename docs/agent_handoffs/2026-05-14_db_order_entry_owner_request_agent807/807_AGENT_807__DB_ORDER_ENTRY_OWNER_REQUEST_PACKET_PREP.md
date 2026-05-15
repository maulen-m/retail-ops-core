# Agent807 - DB Order-Entry Owner Request Packet Prep

You are Agent807 in `~/Docs/Autonomous_business`.

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-14_db_order_entry_owner_request/agent807_owner_approval_request_packet_closeout.md`

## Mission

Prepare the narrow owner approval request packet for DB-only order-entry recovery after CodeCaptain returned:

`GREEN_TO_PREPARE_OWNER_PRODUCTION_APPLY_APPROVAL_REQUEST_FOR_DB_ORDER_ENTRY_RECOVERY_ONLY`

This is packet/preflight work only. Production DB apply remains blocked.

## Required Reading

Read these before acting:

1. `AGENTS.md`
2. `docs/00_START_HERE.md`
3. `.claude/OPERATING.md`
4. `docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/CODECAPTAIN_CURRENT_426_419_0_OWNER_REQUEST_PREP_20260514.md`
5. `~/Docs/Oracle/Autonomous_business/2026-05-14/211726_TASK-000_db-order-entry-apply-contract-review-current-426-419-0/answer/Code Captain_14.05.2026_21_30_19.md`
6. `exports/validation/order_entry_apply_contract_review/20260514_211328_current_preflight/DB_ORDER_ENTRY_APPLY_CONTRACT_REVIEW_PACKET.md`
7. `exports/validation/order_entry_apply_contract_review/20260514_211328_current_preflight/dry_run/summary.json`

## Hard Boundary

Allowed:

- read-only current-boundary checks;
- strict dry-run without `--apply`;
- evidence packet writing under `exports/validation/db_order_entry_owner_approval_request/`;
- Oracle/CodeCaptain-style packet writing under `~/Docs/Oracle/Autonomous_business/2026-05-14/`;
- closeout writing to the assigned closeout path.

Forbidden:

- no production DB apply;
- no `--apply`;
- no DB write-enable env gate;
- no protected workbook mutation;
- no scheduler/LaunchAgent/plist/cron mutation;
- no Web_automation mutation;
- no browser/login automation or credential/session export;
- no external writes;
- no owner publication;
- no asking the owner for the phrase;
- no cash, PO, ads, price, or stock changes;
- no lifecycle/status repair;
- no treating manual WebUI archive as recovery source hierarchy.

If a command would mutate production state, do not run it.

## Evidence To Reconfirm

Current reviewed contract:

- DB path: `~/Docs/Autonomous_business/db/app.db`
- protected workbook: `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`
- expected DB SHA: `09198109d63611ee1de120d6168ffcadb4195f84dbabe39215ddb969e332440a`
- expected workbook SHA: `eb873974e05247eb30f8db0ce3d38db430eaa9d17afa2d698e1345bae8d91ba0`
- expected dry-run: `426` would-insert `fact_order_entries_kaspi` rows, `419` target order-store pairs, `0` quarantine rows
- source hierarchy: `API_RAW_ORDER_ENTRIES` only

Create a timestamped evidence root like:

`exports/validation/db_order_entry_owner_approval_request/20260514_<HHMMSS>_agent807_current_reconfirm/`

At minimum, capture:

- pre hashes for DB and workbook;
- DB integrity;
- holder/sidecar state;
- business automation quiet/paused status if available through `scripts/manage_business_automation.py`;
- strict no-apply dry-run summary;
- post hashes for DB and workbook;
- packet manifest.

You may reuse the exact no-apply dry-run command from:

`exports/validation/order_entry_apply_contract_review/20260514_211328_current_preflight/DB_ORDER_ENTRY_APPLY_CONTRACT_REVIEW_PACKET.md`

Change only `--output-root` to your new evidence root's `dry_run/` folder. Do not add `--apply`.

## Packet To Build

Build a compact owner approval request packet that includes:

- target DB path;
- target table `fact_order_entries_kaspi`;
- current DB SHA and workbook SHA;
- API-only dry-run summary;
- expected `426 / 419 / 0` counts;
- exact inert owner phrase from CodeCaptain;
- non-authorizations;
- backup-first plan;
- rollback command placeholder;
- pre-apply checklist;
- post-apply validation checklist;
- lifecycle/status caveat explicitly separate;
- manual WebUI archive labeled corroboration only, not source hierarchy.

Important: phrase text inside your packet is inert review text only. Do not ask the owner to paste it, do not treat the owner's broad approval in the current chat as the exact phrase, and do not claim production apply is approved.

Suggested packet path:

`exports/validation/db_order_entry_owner_approval_request/20260514_<HHMMSS>_agent807_current_reconfirm/OWNER_DB_ORDER_ENTRY_RECOVERY_APPROVAL_REQUEST_PACKET.md`

Suggested Oracle pack path:

`~/Docs/Oracle/Autonomous_business/2026-05-14/<HHMMSS>_TASK-000_db-order-entry-owner-approval-request-packet/`

## Gate Rules

Close `GREEN` only if:

- current DB/workbook hashes match the reviewed expected SHAs;
- DB integrity is `ok`;
- no unsafe sidecar/holder blocker remains;
- dry-run matches `426 / 419 / 0`;
- dry-run confirms no production mutation;
- packet clearly preserves all non-authorizations and lifecycle/status caveat.

Close `YELLOW` if packet is useful but any launch-time gate is stale, blocked, or needs new owner/CodeCaptain review.

Close `RED` if any mutation happened, the dry-run contract fails hard, or the packet would mislead the owner into approving broader authority.

Your closeout must include:

- READCHECK;
- commands run;
- files created;
- gate result;
- exact reason if not GREEN;
- next human/orchestrator action;
- standalone line `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
