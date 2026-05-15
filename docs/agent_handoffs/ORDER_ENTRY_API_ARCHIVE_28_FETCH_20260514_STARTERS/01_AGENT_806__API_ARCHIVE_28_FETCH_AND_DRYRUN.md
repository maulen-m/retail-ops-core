# Agent806 - API Archive Fetch For 28 Quarantined Order-Entry Rows

You are Agent806 in `~/Docs/Autonomous_business`.

## Mission

Use the existing read-only Kaspi API archive method to fetch recent order-entry evidence for the current `28` quarantined order-entry rows, then rerun the same read-only recovery dry-run against the new evidence.

## Read First

Read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-14_order-entry-api-archive-28-fetch/PLAN.md`
4. `~/Docs/Autonomous_business_agent_handoffs/2026-05-14_order-entry-owner-phrase-review/status_board.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-14_order-entry-owner-phrase-review/agent804_current_dry_run_review_packet_closeout.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-14_order-entry-owner-phrase-review/agent805_dry_run_packet_verifier_closeout.md`
7. `scripts/export_kaspi_archive_history.py`
8. `scripts/recover_order_entries_from_evidence.py`

## Source Rows

The current quarantine file is:

`~/Docs/Autonomous_business/exports/validation/order_entry_owner_phrase_review/20260514_192550_agent804/dry_run/quarantine_preview.jsonl`

It contains `28` rows, date range `2026-05-08` through `2026-05-13`, stores `STOREB`, `ACMEWEAR`, and `UNIVERSAL`.

## Evidence Root

Create and use this root:

`~/Docs/Autonomous_business/exports/validation/order_entry_owner_phrase_review/20260514_200026_agent806_api_archive_refetch/`

Suggested API archive output root:

`~/Docs/Autonomous_business/exports/validation/order_entry_owner_phrase_review/20260514_200026_agent806_api_archive_refetch/kaspi_archive_history_20260508_to_20260514_api_refetch`

Suggested dry-run output root:

`~/Docs/Autonomous_business/exports/validation/order_entry_owner_phrase_review/20260514_200026_agent806_api_archive_refetch/dry_run_with_refetch`

## Suggested Command Shape

First verify business automation is still paused:

```bash
python3 scripts/manage_business_automation.py verify --scope all-business --expect paused
```

Then run the read-only API archive fetch. Use `.env` only to load existing API credentials; do not print secrets.

```bash
set -a
source .env
set +a
python3 scripts/export_kaspi_archive_history.py \
  --since 2026-05-08 \
  --until 2026-05-14 \
  --stores UNIVERSAL,STOREB,ACMEWEAR \
  --strict \
  --date-mode creationDate \
  --fetch-entries \
  --max-workers 2 \
  --entry-workers 4 \
  --out-dir ~/Docs/Autonomous_business/exports/validation/order_entry_owner_phrase_review/20260514_200026_agent806_api_archive_refetch/kaspi_archive_history_20260508_to_20260514_api_refetch
```

Then rerun read-only recovery dry-run. Include the new API root plus the prior current packet roots:

```bash
python3 scripts/recover_order_entries_from_evidence.py \
  --db db/app.db \
  --target-source fact_orders_kaspi \
  --start-date 2026-05-05 \
  --as-of 2026-05-14 \
  --entry-required-only \
  --api-entry-root ~/Docs/Autonomous_business/exports/validation/order_entry_owner_phrase_review/20260514_200026_agent806_api_archive_refetch/kaspi_archive_history_20260508_to_20260514_api_refetch \
  --api-entry-root exports/validation/autonomous_phase0_5_approved_ads_order_materializer/20260514_100007/order_entry_materializer/kaspi_archive_history_20260505_to_20260514_current_capture \
  --api-entry-root exports/validation/frozen_window_option1_2_combined_copy_proof/20260514_113412/read_only_source_refresh/storeb_918424218_creationdate_refresh_env_113702 \
  --recovery-ts 2026-05-14T23:59:59+05:00 \
  --strict \
  --output-root ~/Docs/Autonomous_business/exports/validation/order_entry_owner_phrase_review/20260514_200026_agent806_api_archive_refetch/dry_run_with_refetch
```

If strict exits `2`, that is not a command failure by itself. Read the generated `summary.json` and quarantine preview.

## Required Analysis

Write small machine-readable sidecars under the evidence root:

- `quarantine_before_after.json`
- `matched_28_orders.csv`
- `remaining_quarantine_rows.csv`

At minimum, compare the original `28` order/store pairs to the new `archive_order_entries_raw.jsonl` files and report:

- how many of the `28` now have API raw entry evidence;
- which rows remain missing;
- whether recovered entries are still `API_RAW_ORDER_ENTRIES` only;
- whether the final dry-run has `strict.passed=true` and `quarantine.target_rows=0`.

## Closeout

Write:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-14_order-entry-owner-phrase-review/agent806_api_archive_28_fetch_closeout.md`

The closeout must include a standalone line:

`Gate: GREEN`

Use:

- `GREEN` only if strict dry-run passes with `quarantine.target_rows=0` and no protected surfaces were mutated.
- `YELLOW` if the API fetch ran and improved evidence but rows remain quarantined.
- `RED` if API fetch cannot run safely, access fails completely, or any protected surface was mutated.

## Non-Authorization

Do not production-apply. Do not set `ENABLE_ORDER_ENTRY_RECOVERY_WRITE`. Do not set `ENABLE_ORDER_ENTRY_RECOVERY_PROD_WRITE`. Do not mutate `db/app.db`, CRM workbook, scheduler, Google, Telegram, Kaspi write APIs, ad platforms, cash, stock, price, PO, or owner-publication surfaces.

Completion instruction is appended by the tmux orchestrator.
