# Waybill Command Research (Kaspi Ops)

Scope: explain how the three command wrappers work, their dependencies,
and why `run_build_waybills.command` often fails in practice.

Files covered:
- `excel_ui/run_full_import.command`
- `excel_ui/run_send_whatsapp.command`
- `excel_ui/run_build_waybills.command`

This is a research document only (no code changes).

## 1) excel_ui/run_full_import.command

Purpose: fast “today-only” order intake from Kaspi API into CRM.

Flow:
1) `scripts/export_api_orders.py --all-stores --state KASPI_DELIVERY --days 2 --no-archive --verbose`
   - Pulls Kaspi API orders in KASPI_DELIVERY state (today-focused).
   - Writes an ActiveOrders-style Excel export.
2) `scripts/import_orders_to_crm.py --verbose`
   - Loads ActiveOrders Excel files, filters for shipping-ready orders,
     and inserts/updates rows in `excel_ui/SALES_KSP_CRM_V3.xlsx`.
   - Performs a Google Drive sync internally if rows changed.

Dependencies:
- API auth from `.env` via `core/integrations/kaspi_api_client.py`.
- Excel I/O (pandas, openpyxl, xlwings).
- CRM file: `excel_ui/SALES_KSP_CRM_V3.xlsx`.

## 2) excel_ui/run_send_whatsapp.command

Purpose: send grouped waybill PDFs via WhatsApp Web (semi-automated).

Flow:
1) `scripts/send_waybills_whatsapp.py --verbose`
   - Scans `excel_ui/Kaspi_orders/Today/` for per-store folders.
   - Sends PDFs in priority order:
     `SPECIAL_multi_line → SPECIAL_multi_qty → NORMAL_singles`.
   - Uses `pywhatkit` and a hardcoded `WHATSAPP_GROUP_ID` in the script.
   - Tracks already-sent PDFs in `sent_pdfs.json`.

Common blockers:
- `WHATSAPP_GROUP_ID` is `None` by default.
- `pywhatkit` not installed in the active Python env.
- WhatsApp Web not logged in.

## 3) excel_ui/run_build_waybills.command

Purpose: end-to-end waybill workflow (ship → download → group).

Flow:
1) Ship orders via API:
   - `scripts/ship_orders_api.py --verbose`
   - Reads CRM, computes parcel counts, calls Kaspi API.
2) Download waybills:
   - `scripts/download_waybills_api.py --verbose`
   - Pulls PDFs for orders in KASPI_DELIVERY state.
3) Build grouped bundles:
   - `scripts/build_daily_waybills.py --verbose`
   - Groups CRM orders with PDFs into output folder:
     `excel_ui/Kaspi_orders/Today/`.

Dependencies:
- `.env` tokens + `ENABLE_KASPI_WRITE=1` (required for shipping).
- CRM file with `MY_SIZE` filled: `excel_ui/SALES_KSP_CRM_V3.xlsx`.
- Planned shipping date logic (see failure causes below).
- Waybill PDFs in `excel_ui/ActiveOrders/waybills/` (downloaded by API).

## Why run_build_waybills.command “does not work properly”

Below are the most likely failure modes based on code:

### A) Shipping step blocked by write guard
File: `scripts/ship_orders_api.py`
- If `.env` does not set `ENABLE_KASPI_WRITE=1`,
  the API write is blocked (`KaspiWriteDisabledError`).
- Result: nothing transitions to KASPI_DELIVERY → no waybills to download.

### B) CRM filters exclude all orders
Files: `scripts/ship_orders_api.py`, `scripts/download_waybills_api.py`,
`scripts/build_daily_waybills.py`
- All three require `MY_SIZE` to be filled in CRM.
- `download_waybills_api.py` defaults to **exact planned date = today**.
- `build_daily_waybills.py` also filters to **exact planned date = today**.
If planned dates are missing, in a different column, or not equal to today,
the order list is empty → no PDFs downloaded and no bundles created.

### C) Wrong CRM file or sheet
All three scripts assume:
- CRM path: `excel_ui/SALES_KSP_CRM_V3.xlsx`
- Sheet: `SALES_KSP_CRM_1`
If the file is renamed/moved or sheet name differs, reading fails.

### D) Waybills stored in a different folder
`download_waybills_api.py` writes PDFs to:
`excel_ui/ActiveOrders/waybills/`
`build_daily_waybills.py` expects PDFs:
- in `excel_ui/ActiveOrders/waybills/` (API downloads), or
- in ZIPs under `excel_ui/ActiveOrders/` named `waybill*.zip`.

If PDFs/ZIPs are in another folder, grouping yields “missing waybills”.

### E) Order state mismatch
`download_waybills_api.py` only pulls API orders in `KASPI_DELIVERY`.
If `ship_orders_api.py` didn’t move them (auth error, write disabled),
there will be **zero** matching waybills even if orders exist in CRM.

### F) Missing dependencies / env
Common runtime issues:
- `.venv` missing or inactive → `python` lacks pandas/openpyxl/xlwings.
- Missing Kaspi API tokens in `.env` → auth errors in API calls.

## Quick sanity checklist (operator)

1) CRM file exists and MY_SIZE is filled for today’s orders.
2) Planned shipping date is exactly today (not yesterday or blank).
3) `.env` has valid Kaspi tokens and `ENABLE_KASPI_WRITE=1`.
4) After download step, PDFs appear in:
   `excel_ui/ActiveOrders/waybills/`.
5) Run build step and check:
   `excel_ui/Kaspi_orders/Today/` for output folders + manifests.

