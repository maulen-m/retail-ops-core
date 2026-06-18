# WEBUI_ARCHIVE_AUTONOMOUS_REFRESH_WORKFLOW

## Purpose
Make long-range Kaspi sales/status source freshness repeatable without requiring the human owner to manually download every store archive.

This workflow is the operator layer on top of:
- `docs/validation/WEBUI_ARCHIVE_SINGLE_TRUTH_CONTRACT.md`
- `docs/validation/KASPI_ARCHIVE_UI_PACK_CONTRACT.md`
- `docs/validation/KASPI_ARCHIVE_API_PACK_CONTRACT.md`
- `scripts/run_webui_archive_source_refresh.py`

## Non-Negotiable Rule
Do not narrow the source acquisition to one SKU family such as LINE61 or LINE51 when a full-store ArchiveOrders export is available.

Default scope is all enabled Kaspi stores and all products/orders in the selected date window. Product-level filtering happens only downstream in copied-temp analysis.

## Trigger Points
Run this workflow, or explicitly document why it is not needed, whenever any task involves:
- sales data freshness or source coverage;
- stock re-anchor or inventory rebuild from a physical stock anchor;
- current inventory valuation or capital tied in stock;
- lifecycle, cancellation, return, status-change, status-ledger, or day-complete blockers;
- CodeCaptain or owner packets that rely on recent sales counts;
- impossible business signals, such as active products showing zero sales on days where the owner confirms sales happened;
- post-shipping daily reconciliation where API/workbook/DB rows disagree;
- archive/API order-entry repair where API rows lack historical status-change dates.

## Store Scope
Default store scope is every `sync_enabled` store in `config/kaspi_stores.yaml`.

Current enabled store codes are:
- `11KZ`
- `MELVIS`
- `STOREB`
- `ACMEWEAR`
- `UNIVERSAL`

If an agent narrows to `STOREB,ACMEWEAR,UNIVERSAL` or any smaller set, the closeout must say why and must mark omitted enabled stores as disclosed omissions, not silently complete.

## Source Hierarchy
Use sources in this order:

1. WebUI `ArchiveOrders.xlsx` exports from Kaspi Seller Cabinet Archive.
2. Existing manually downloaded WebUI `ArchiveOrders` files under `imports/webui_archive_manual/`.
3. Read-only Kaspi API archive fetches for speed, order-entry details, SKU identity, and raw order evidence.
4. Chrome/Playwright/Computer Use research only when the repo-owned downloader cannot complete the WebUI path safely.

WebUI archive is preferred for historical lifecycle truth because it carries `Дата изменения статуса`. API archive packs may be faster, but they do not replace WebUI status-change truth unless a reviewed contract explicitly says so.

## Downstream Stock View Split
Archive refresh outputs feed two different stock questions and must label them
separately:

- `PHYSICAL_WAREHOUSE_STOCK_ESTIMATE` answers how many units are probably still
  physically in the warehouse. It starts from the owner-approved stock anchor,
  adds confirmed inbound and accepted physical returns, and deducts shipped/sent
  orders by `ship_date`.
- `ECONOMIC_FINAL_SALES_STOCK` answers how many units are depleted by true
  completed sales for COGS, cash, and PnL. It starts from the owner-approved stock
  anchor, adds confirmed inbound and accepted return-QC stock, and deducts only
  completed/bought-out sales by WebUI `Дата изменения статуса`.

Do not use WebUI `Дата поступления заказа` or API `creationDate` as final sale
truth. If the shipped-source, inbound-source, or return-QC source is incomplete,
the correct closeout is `YELLOW`, not a collapsed stock number.

## Date Window Rule
Kaspi WebUI Archive date filters must be split into windows of `90` days or less.

Use `scripts/run_webui_archive_source_refresh.py` or `scripts/run_webui_archive_full_parse.py` so the repo planner creates deterministic blocks. Do not hand-build overlapping blocks unless the run manifest records the reason.

Use the repo date convention for business windows: local Asia/Almaty dates, inclusive `since..until`.

## Canonical CLI
Preferred source-refresh command:

```bash
python3 scripts/run_webui_archive_source_refresh.py \
  --since <YYYY-MM-DD> \
  --until <YYYY-MM-DD> \
  --mode auto \
  --strict
```

Default behavior with no `--stores` is all enabled stores from `config/kaspi_stores.yaml`.

Use `--stores` only for a scoped proof:

```bash
python3 scripts/run_webui_archive_source_refresh.py \
  --since 2026-05-05 \
  --until 2026-05-25 \
  --stores STOREB,ACMEWEAR,UNIVERSAL \
  --mode auto \
  --strict
```

Import an existing manual source folder:

```bash
python3 scripts/run_webui_archive_source_refresh.py \
  --since 2026-03-01 \
  --until 2026-05-26 \
  --source-root imports/webui_archive_manual/26.05.2026_14_34_04 \
  --stores ACMEWEAR,STOREB \
  --mode import-existing \
  --strict
```

Run live WebUI acquisition with a visible browser/manual login fallback:

```bash
python3 scripts/run_webui_archive_source_refresh.py \
  --since 2026-05-05 \
  --until 2026-05-25 \
  --mode headful-manual-login \
  --allow-manual-download \
  --strict
```

Current Seller Cabinet Archive UI observations used by the repo downloader:

- archive page URL state: `status=ARCHIVED`;
- date inputs: `Дата От` and `Дата До`;
- apply button: `Применить`;
- export button: `Выгрузить в EXCEL`.

`chrome-cdp-attach` is intentionally fail-closed until the repo-owned downloader supports it. Chrome AutoConnect or Computer Use may be used to research the UI and improve the repo CLI, but should not become an undocumented alternate truth path.

## API Fast Lane
For order-entry/SKU detail gaps, use the API archive exporter as a supporting evidence lane:

```bash
python3 scripts/export_kaspi_archive_history.py \
  --since <YYYY-MM-DD> \
  --until <YYYY-MM-DD> \
  --date-mode creationDate \
  --no-require-status-change-date-for-completed \
  --out-dir exports/validation/<run_slug>/kaspi_archive_history_<since>_to_<until>
```

API archive output must be labeled as API evidence. It can support SKU identity and raw order-entry repair, but WebUI archive remains the required source when the blocker is `status_change_at`, lifecycle date, cancellation/return chronology, or day-complete evidence.

The API exporter loads the repo `.env` by default for read-only token access and must not print token values.

## Required Outputs
Every autonomous refresh run must produce:
- immutable raw `ArchiveOrders` files with store/window attribution;
- SHA-256 manifest for source and copied files;
- normalized per-store CSV/XLSX outputs;
- merged all-store CSV/XLSX output;
- integrity report proving required WebUI columns and nonblank completed-row status-change dates;
- run summary showing stores, windows, failures, omissions, and effective mode;
- manifest fields for `all_enabled_stores`, `target_stores`, `omitted_enabled_stores`, `planned_windows`, and `expected_block_count`;
- explicit note whether production DB, workbook, scheduler, source pointers, external accounts, price, stock, cash, PO, ads, and owner publication were untouched.

## Gate Colors
Call the refresh `GREEN` only if:
- every targeted enabled store/window completed;
- all raw source files have hash provenance;
- pack integrity is green;
- completed/delivered rows that require status-change dates have them;
- no protected production surface changed.

Call it `YELLOW` if:
- some stores/windows are missing, header-only, or login/download blocked;
- API evidence exists but WebUI status-change truth is incomplete;
- the pack is useful for copied-temp analysis but not complete enough for production promotion.

Call it `RED` if:
- a protected production surface drifted;
- the agent performed a WebUI/API/Kaspi mutation;
- source files were overwritten without provenance;
- secrets were exposed in logs or evidence.

## Current Sales-Gap Repair Target
The current owner-confirmed blocker is that LINE61 and LINE51 post-`2026-05-04` sales are incomplete in the April 23 stock re-anchor replay. The next repair should acquire all-store/all-product WebUI ArchiveOrders evidence for at least:

- `2026-05-05` through `2026-05-25`

Exact command:

```bash
python3 scripts/run_webui_archive_source_refresh.py \
  --since 2026-05-05 \
  --until 2026-05-25 \
  --mode live-headless \
  --strict
```

For a broader one-shot repair aligned with the provided manual example, use:

- `2026-03-01` through `2026-05-26`

After source refresh, downstream agents may use the merged evidence only in copied-temp replay until CodeCaptain/owner approve any production preflight/apply conversation.

## Future-Agent Checklist
Before any future agent says sales data is fresh, it must answer:
- Which store scope was used?
- Which product scope was used?
- Which date windows were fetched?
- Was WebUI ArchiveOrders used, API archive used, or both?
- Did the evidence include `Дата изменения статуса`?
- Which enabled stores were omitted, if any?
- Which command generated the source pack?
- Where is the run manifest?
- Did any protected surface change?

If any answer is missing, the correct gate is `YELLOW`, not `GREEN`.
