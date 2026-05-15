# Agent815 - WebUI Archive Lifecycle/Status Packet

Gate target: `GREEN` if read-only WebUI Archive evidence is refreshed/imported enough to define the lifecycle/status source route; `YELLOW` if login/session/source availability blocks a safe read-only packet.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-15_post_order_entry_next_phase_proof_wave/PLAN.md`
4. `~/Docs/Autonomous_business/docs/validation/WEBUI_ARCHIVE_SINGLE_TRUTH_CONTRACT.md`
5. `~/Docs/Autonomous_business/docs/validation/KASPI_ARCHIVE_UI_PACK_CONTRACT.md`
6. `~/Docs/Autonomous_business/exports/validation/order_entry_apply_and_daily_survival_parallel/20260515_085748/agent811_cash_po_exception_blocker_board/CASH_PO_EXCEPTION_BLOCKER_BOARD.md`
7. this starter prompt

Sibling Agents812, 813, 814, and 816 are parallel. Do not wait for them.

## Human-Approved Scope

The human owner approved read-only WebUI Archive source refresh for lifecycle/status evidence, including 90-day block downloads or existing repo import methods, for local evidence packets only.

No production DB apply, workbook mutation, scheduler mutation, external writes, owner publication, cash, PO, ads, price, or stock changes are authorized.

## Assignment

Use `scripts/run_webui_archive_source_refresh.py` and existing repo methods to refresh or import WebUI Archive lifecycle/status evidence for the current gap.

Prefer safe sequence:

1. `--mode import-existing` if local files are sufficient.
2. `--mode session-check` or `chrome-cdp-attach` only if needed and safe.
3. Live headless/headful read-only only within the approved source-refresh boundary.

Focus on lifecycle/status evidence for `2026-05-05..2026-05-15`, including missing `statusChangeDate` / completed-order status evidence.

Write evidence only under:

`~/Docs/Autonomous_business/exports/validation/post_order_entry_next_phase_proof_wave/20260515_0920/agent815_webui_archive_lifecycle_status/`

Required output:

`~/Docs/Autonomous_business/exports/validation/post_order_entry_next_phase_proof_wave/20260515_0920/agent815_webui_archive_lifecycle_status/WEBUI_ARCHIVE_LIFECYCLE_STATUS_PACKET.md`

Closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-15_post_order_entry_next_phase_proof_wave/agent815_webui_archive_lifecycle_status_closeout.md`

## Boundaries

Read-only source refresh/import and local evidence writes only. Do not mutate production DB, workbook, scheduler, Web_automation state, external accounts, owner publication, cash, PO, ads, price, or stock.

Gate: GREEN
