# WebUI Archive Autonomous Refresh Workflow Handoff

## Objective
Create a durable autonomous WebUI ArchiveOrders source-refresh route so sales, lifecycle, cancellation, return, and status-change truth can be refreshed across all enabled Kaspi stores without repeated human manual downloading.

## Why This Exists
The current April 23 stock re-anchor replay exposed an owner-confirmed sales gap: LINE61 and LINE51 cannot have zero sales across the active May window. That means the issue is source acquisition/acceptance, not stock math alone.

The helper agent must fix the workflow layer first, then only use refreshed evidence in copied-temp proof lanes until a later reviewed apply is approved.

## Canonical Docs
Read in this order:

1. `AGENTS.md`
2. `docs/00_START_HERE.md`
3. `docs/validation/WEBUI_ARCHIVE_AUTONOMOUS_REFRESH_WORKFLOW.md`
4. `docs/validation/WEBUI_ARCHIVE_SINGLE_TRUTH_CONTRACT.md`
5. `docs/validation/KASPI_ARCHIVE_UI_PACK_CONTRACT.md`
6. `docs/validation/KASPI_ARCHIVE_API_PACK_CONTRACT.md`
7. `scripts/run_webui_archive_source_refresh.py`
8. `scripts/run_webui_archive_full_parse.py`
9. `scripts/playwright/download_kaspi_archive_webui.py`

## Current Manual Example
Use this local source folder as the observed manual-download example:

`imports/webui_archive_manual/26.05.2026_14_34_04`

It shows the intended Kaspi Seller Cabinet Archive flow: choose a date range of `90` days or less, apply, export to Excel, and preserve the resulting `ArchiveOrders.xlsx` file by store.

## Implementation Boundary
Allowed:
- read-only inspection of repo scripts, docs, config, `.env` key names, and local evidence;
- local documentation and starter/handoff updates;
- code/test changes to improve the repo-owned read-only downloader or CLI;
- read-only WebUI/API source acquisition only after the owner approval phrase is present in the launch prompt;
- Chrome/Computer Use only for UI observation, selector research, and download-only automation;
- local evidence manifests, diagnostics, screenshots, and closeouts.

Not allowed:
- production DB writes;
- workbook writes;
- scheduler/LaunchAgent/cron changes;
- source-pointer writes;
- Web_automation writes;
- Kaspi/API/WebUI mutations;
- order acceptance/cancellation/status changes;
- merchant stock or price changes;
- ad bid/budget/campaign/spend changes;
- cash movement;
- supplier payment;
- PO commitment;
- owner publication;
- production preflight or production apply.

## Expected Agent Outcome
The helper agent should produce:
- a closeout stating whether the current CLI can autonomously fetch all enabled stores in `90`-day blocks;
- any minimal repo patches required to make that CLI reliable and test-covered;
- a command recipe for importing manual ArchiveOrders folders;
- a command recipe for all-store live WebUI refresh;
- a clear fallback rule for API archive evidence;
- a source-pack evidence path if a read-only fetch is authorized and executed;
- exact blockers if any store remains login/download/header-only blocked.

## Success Gate
`GREEN` means the workflow is documented, CLI path is verified by focused tests, and any authorized read-only source acquisition produced a valid WebUI pack for the requested scope without protected-surface drift.

`YELLOW` means the workflow is safer and documented, but some store/window/source acquisition remains blocked or only partially proven.

`RED` means a protected surface changed, secrets leaked, or any WebUI/API/Kaspi mutation happened.

## Starter Pointer
Launch the helper agent with:

`Read the repo bootstrap context and execute docs/agent_handoffs/WEBUI_ARCHIVE_AUTONOMOUS_REFRESH_WORKFLOW_20260526_STARTERS/01_AGENT__WEBUI_ARCHIVE_AUTONOMOUS_REFRESH_CLI_AND_UI_RESEARCH.md`
