# Agent 805 - Dry-Run Packet Verifier

Before executing, read:
1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-14_order-entry-owner-phrase-review/PLAN.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/ORDER_ENTRY_OWNER_PHRASE_REVIEW_20260514_STARTERS/02_AGENT_805__DRY_RUN_PACKET_VERIFIER__AFTER_804.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-14_order-entry-owner-phrase-review/agent804_current_dry_run_review_packet_closeout.md`

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-14_order-entry-owner-phrase-review/agent805_dry_run_packet_verifier_closeout.md`

## Role

You are a read-only verifier after Agent 804.

Allowed write:

- your assigned closeout only.

Forbidden:

- no repo edits;
- no DB/workbook/config/scheduler mutation;
- no external writes;
- no owner request;
- no production apply.

## Verification Tasks

1. Read Agent 804 closeout and its stated run root / Oracle packet path.
2. Inspect current hashes, paused automation proof, DB integrity, holders evidence, and dry-run `summary.json`.
3. Verify whether summary fields match the patched readiness requirements:
   - `strict.passed=true`;
   - `apply.would_insert_entry_rows=398`, or exact drift documented;
   - `target.order_store_pairs=391`, or reviewed-equivalent target set documented;
   - `quarantine.target_rows=0`;
   - `source_hierarchy=["API_RAW_ORDER_ENTRIES"]`;
   - `sources.source_mode="api_raw_order_entries_only"`;
   - `sources.workbook_sources_used=false`;
   - `sources.webui_archive_sources_used=false`;
   - `entry_candidates.non_api_entry_rows=0`;
   - no targeted STOREB refresh `statusChangeDate` / lifecycle authority.
4. Confirm the packet remains inert and review-only.
5. Confirm that current boundary drift is not hidden.

## Gate Rules

Use `Gate: GREEN` only if Agent 804's packet is internally consistent, inert, and ready for CodeCaptain current-boundary/reviewed-equivalent review.

Use `Gate: YELLOW` if packet or dry-run is usable but needs a small patch.

Use `Gate: RED` if the packet implies owner authorization/production apply, hides boundary drift, or dry-run evidence contradicts the claimed result.
