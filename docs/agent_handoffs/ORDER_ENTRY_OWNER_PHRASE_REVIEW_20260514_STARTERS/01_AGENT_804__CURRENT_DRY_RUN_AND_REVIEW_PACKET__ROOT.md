# Agent 804 - Current Dry-Run And Owner-Phrase Review Packet

Before executing, read:
1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-14_order-entry-owner-phrase-review/PLAN.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/ORDER_ENTRY_OWNER_PHRASE_REVIEW_20260514_STARTERS/01_AGENT_804__CURRENT_DRY_RUN_AND_REVIEW_PACKET__ROOT.md`
6. `~/Docs/Oracle/Autonomous_business/2026-05-14/182340_TASK-000_codecaptain-order-entry-readiness-packet-patch-rereview/answer/Code Captain_14.05.2026_19_20_41 .md`
7. `~/Docs/Autonomous_business/exports/validation/frozen_window_option1_2_combined_copy_proof/20260514_113412/production_readiness/ORDER_ENTRY_PRODUCTION_APPLY_READINESS_PACKET.md`

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-14_order-entry-owner-phrase-review/agent804_current_dry_run_review_packet_closeout.md`

## Role

You are the execution writer for a review-only lane.

Allowed writes:

- local evidence under `~/Docs/Autonomous_business/exports/validation/order_entry_owner_phrase_review/`;
- Oracle review packet under `~/Docs/Oracle/Autonomous_business/2026-05-14/`;
- assigned handoff files under `~/Docs/Autonomous_business_agent_handoffs/2026-05-14_order-entry-owner-phrase-review/`;
- optional status board in that same handoff folder.

Forbidden:

- no `--apply`;
- no `ENABLE_ORDER_ENTRY_RECOVERY_WRITE`;
- no `ENABLE_ORDER_ENTRY_RECOVERY_PROD_WRITE`;
- no production DB mutation;
- no workbook mutation;
- no scheduler mutation;
- no external writes;
- no ad-platform writes;
- no owner publication;
- no owner approval request;
- no cash movement, supplier payment, PO commitment, stock change, or price change.

## Required Steps

1. Re-run current safety preflight:
   - `python3 scripts/manage_business_automation.py verify --scope all-business --expect paused --output-json <run_root>/verify_all_business_paused.json`
   - `shasum -a 256 db/app.db excel_ui/SALES_KSP_CRM_V3.xlsx > <run_root>/current_hashes.sha256`
   - `sqlite3 db/app.db 'PRAGMA integrity_check;' > <run_root>/db_integrity.txt`
   - `lsof db/app.db excel_ui/SALES_KSP_CRM_V3.xlsx > <run_root>/holders.txt 2>&1 || true`
2. Record that the current DB/workbook hashes already differ from the reviewed frozen hashes in the plan.
3. If holders are active beyond your own commands, stop YELLOW/RED.
4. Run the current-production dry-run only, with no apply and no write env gates:

```bash
python3 scripts/recover_order_entries_from_evidence.py \
  --db db/app.db \
  --target-source fact_orders_kaspi \
  --start-date 2026-05-05 \
  --as-of 2026-05-14 \
  --entry-required-only \
  --api-entry-root exports/validation/autonomous_phase0_5_approved_ads_order_materializer/20260514_100007/order_entry_materializer/kaspi_archive_history_20260505_to_20260514_current_capture \
  --api-entry-root exports/validation/frozen_window_option1_2_combined_copy_proof/20260514_113412/read_only_source_refresh/storeb_918424218_creationdate_refresh_env_113702 \
  --recovery-ts 2026-05-14T23:59:59+05:00 \
  --strict \
  --output-root <run_root>/dry_run
```

5. Inspect `<run_root>/dry_run/summary.json`.
6. Build a CodeCaptain review packet. Because the current hashes drifted, the packet must ask for explicit current-boundary / reviewed-equivalent decision before any owner phrase request is prepared.
7. Do not draft an active owner approval phrase. If including owner-facing scope text, mark it `INERT_REVIEW_TEXT_NOT_AUTHORIZATION`.

## Required Review Packet Contents

Include:

- main prompt markdown;
- patched readiness packet;
- CodeCaptain GREEN re-review answer;
- current hashes;
- DB integrity;
- holders evidence;
- paused automation verification;
- dry-run summary and stdout/stderr if present;
- exact non-authorizations;
- exact stoplines;
- Agent 804 closeout.

## Gate Rules

Use `Gate: GREEN` only if a complete inert review packet is built and clearly says current boundary drift requires CodeCaptain/current-boundary acceptance before owner phrase request.

Use `Gate: YELLOW` if dry-run completes but row counts/source hierarchy/hash drift make owner-phrase readiness unresolved.

Use `Gate: RED` if dry-run fails in a way that invalidates the lane, holders are active, automations are not paused, or any forbidden mutation happened.
