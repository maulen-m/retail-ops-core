# Web Automations Read-Only Shipped Orders Handoff

## Purpose
Give the external `web_automations` repo efficient, read-only access to the real shipped-order / final-size context produced by the Autonomous Business daily ops workflow.

This handoff is intentionally fail-closed:
- `web_automations` may read from this repo
- `web_automations` must not write into this repo
- DB truth and send artifacts remain owned by `Autonomous_business`

## Non-Negotiable Access Contract
- Treat this repo as a read-only source.
- Do not write to:
  - `db/app.db`
  - `excel_ui/`
  - `exports/`
  - `.claude/`
- Open SQLite in read-only mode only:
  - `file:~/Docs/Autonomous_business/db/app.db?mode=ro`
- If `web_automations` needs cached or normalized snapshots, write them inside the `web_automations` repo only.

## Canonical Data Sources

### 1. Final operational truth: `db/app.db -> fact_orders_kaspi`
Use this for:
- final assigned size
- order/store identity
- current shipped status
- waybill URL / number
- actual shipment timestamps

Canonical table:
- [fact_orders_kaspi schema](~/Docs/Autonomous_business/db/app.db)

Key fields:
- `order_id`
- `store_code`
- `kaspi_offer_name`
- `sku_key`
- `sku_id`
- `quantity`
- `assigned_size`
- `size_source`
- `internal_status`
- `planned_shipment_date`
- `actual_shipment_date`
- `courier_transmission_date`
- `waybill_url`
- `waybill_number`

Important rule:
- For final size, prefer `assigned_size`.
- `my_size` is operator-input history, not the final post-writeback truth.

### 2. Actual delivery truth: `Today/MERGED/SEND/<batch>/send_batch_manifest.json` + channel ledger
Use this for:
- which PDF bundles were built
- which order IDs were included in each bundle
- whether each bundle was actually confirmed as sent in Telegram or fallback WhatsApp

Canonical location:
- [MERGED SEND root](~/Docs/Autonomous_business/excel_ui/Kaspi_orders/Today/MERGED/SEND)

Manifest file:
- `send_batch_manifest.json`

Primary Telegram ledger file:
- `telegram_send_ledger.json`

Fallback WhatsApp ledger file:
- `send_ledger.json`

What each file means:
- `send_batch_manifest.json`:
  - immutable batch composition
  - target date
  - bundle filenames
  - order IDs inside each bundle
  - group/core naming context
- `telegram_send_ledger.json`:
  - primary Telegram send-state progression
  - final durable states per PDF:
    - `confirmed`
    - `unsure`
    - `failed`
    - non-final transitional state `api_started`
- `send_ledger.json`:
  - fallback WhatsApp send-state progression
  - final durable states per PDF:
    - `confirmed`
    - `unsure`
    - `failed`
    - non-final transitional states like `opened` / `clicked`

Important rule:
- Do not infer delivery completion from DB.
- Delivery truth lives in the channel ledger, not in `fact_orders_kaspi`.
- Prefer `telegram_send_ledger.json` when present; use WhatsApp `send_ledger.json` only when the delivery report shows WhatsApp fallback was the delivery channel.

### 3. Audit / recovery truth: `exports/google_ops_board/workflow_runs/<YYYY-MM-DD>/<run_id>/`
Use this for:
- latest successful closeout evidence
- stage-by-stage reports
- failure analysis / replay context

Canonical location:
- [workflow_runs](~/Docs/Autonomous_business/exports/google_ops_board/workflow_runs)

Useful files:
- `closeout_report.json`
- `shipping_report.json`
- `step_download_waybills.json`
- `step_build_waybills.json`
- `step_delivery_send.json`
- `delivery_send_report.json`
- legacy/fallback only: `step_whatsapp_send.json`

Important rule:
- Use workflow-run artifacts as audit/evidence, not as the primary source for final size or per-order shipment truth.

## What To Read For Each Need

### Need: “What is the final real size for shipped orders?”
Read:
- `db/app.db -> fact_orders_kaspi.assigned_size`

Do not use:
- Google Sheet `MY_SIZE`
- Excel workbook
- WhatsApp batch filenames

### Need: “Which orders were actually shipped?”
Read:
- `fact_orders_kaspi.internal_status`
- `fact_orders_kaspi.actual_shipment_date`
- `fact_orders_kaspi.courier_transmission_date`

Recommended shipped predicate:
- `internal_status = 'SHIPPED'`
- and `actual_shipment_date` or `courier_transmission_date` is non-empty

### Need: “Which bundles were actually sent in WhatsApp?”
Read:
- latest relevant `send_batch_manifest.json`
- matching `send_ledger.json`

Recommended confirmed predicate:
- ledger entry `state = 'confirmed'`

### Need: “Which orders were included in which sent bundle?”
Read:
- `send_batch_manifest.json.entries[*].order_ids`
- join to ledger by `pdf_key`

## Recommended Read Path For `web_automations`

### Step 1. Resolve repo root
Use one explicit env var in `web_automations`:

```bash
export AB_SOURCE_ROOT="~/Docs/Autonomous_business"
```

### Step 2. Read DB in strict read-only mode
Python example:

```python
import sqlite3

AB_DB_URI = "file:~/Docs/Autonomous_business/db/app.db?mode=ro"
conn = sqlite3.connect(AB_DB_URI, uri=True)
conn.row_factory = sqlite3.Row
```

### Step 3. Pull shipped-order truth from DB
Recommended query for one operational date:

```sql
SELECT
    id,
    order_id,
    store_code,
    kaspi_offer_name,
    sku_key,
    sku_id,
    quantity,
    assigned_size,
    size_source,
    internal_status,
    planned_shipment_date,
    actual_shipment_date,
    courier_transmission_date,
    waybill_url,
    waybill_number
FROM fact_orders_kaspi
WHERE planned_shipment_date = :target_date
  AND internal_status = 'SHIPPED'
  AND COALESCE(actual_shipment_date, courier_transmission_date, '') != ''
ORDER BY store_code, order_id, id;
```

### Step 4. Pull confirmed WhatsApp-send context from the latest SEND batch
Recommended batch selection logic:
1. Look under:
   - `~/Docs/Autonomous_business/excel_ui/Kaspi_orders/Today/MERGED/SEND`
2. Select the latest child folder that contains both:
   - `send_batch_manifest.json`
   - `send_ledger.json`
3. Prefer a batch whose manifest `target_date` matches your requested operational date.

Python example:

```python
import json
from pathlib import Path

send_root = Path("~/Docs/Autonomous_business/excel_ui/Kaspi_orders/Today/MERGED/SEND")
batches = sorted(
    [p for p in send_root.iterdir() if p.is_dir() and (p / "send_batch_manifest.json").exists()],
    key=lambda p: (p / "send_batch_manifest.json").stat().st_mtime,
)
batch = batches[-1]
manifest = json.loads((batch / "send_batch_manifest.json").read_text(encoding="utf-8"))
ledger = json.loads((batch / "send_ledger.json").read_text(encoding="utf-8"))
```

### Step 5. Join manifest entries to ledger-confirmed state
Recommended logic:
- iterate `manifest["entries"]`
- use `entry["pdf_key"]` to locate the ledger row
- keep only entries where:
  - `ledger["entries"][pdf_key]["state"] == "confirmed"`
- expand `entry["order_ids"]` if you need order-level context

This produces the clean mapping:
- order ID -> confirmed bundle filename
- bundle filename -> confirmed send state

## Practical Unified Model For `web_automations`

The simplest useful unified model is:

```json
{
  "target_date": "2026-04-17",
  "orders": [
    {
      "order_id": "891434681",
      "store_code": "UNIVERSAL",
      "sku_key": "CL_...",
      "sku_id": "CL_..._XL",
      "kaspi_offer_name": "...",
      "final_size": "XL",
      "size_source": "GOOGLE_OPS_BOARD",
      "internal_status": "SHIPPED",
      "actual_shipment_date": "2026-04-17 19:54:20",
      "courier_transmission_date": "2026-04-17 19:54:20",
      "waybill_url": "https://kaspi.kz/shop/api/...",
      "bundle_filename": "Принт_5в1_черный_XL-12.pdf",
      "bundle_pdf_key": "...",
      "whatsapp_ledger_state": "confirmed"
    }
  ]
}
```

Recommended ownership split:
- DB contributes:
  - order-level truth
  - final size
  - shipment timestamps
- manifest + ledger contribute:
  - bundle-level send truth
  - actual WhatsApp confirmation state

## Important Caveats

### 1. One Kaspi order can have multiple DB rows
`fact_orders_kaspi` is line-aware. Do not assume one row per `order_id`.

Current uniqueness contract:
- `(order_id, sku_id, store_code)`

If `web_automations` wants one row per order, it must aggregate intentionally.

### 2. `waybill_downloaded` is not the best shipped/send truth
Do not use `waybill_downloaded` alone as the authoritative shipped indicator.

Prefer:
- `internal_status = 'SHIPPED'`
- `actual_shipment_date` / `courier_transmission_date`
- `waybill_url` presence

### 3. Google Sheet is not truth
Do not read Google Sheets for durable order/sizing context if DB is available.

Google Sheet is:
- operator UI
- mutable during the day
- reset / rebuilt across days

### 4. `Today/` is an active-day surface
The SEND batch under `excel_ui/Kaspi_orders/Today/...` is the live operational surface.

For historical or audit-grade use:
- prefer storing your own normalized snapshot in `web_automations`
- or use `exports/google_ops_board/workflow_runs/<date>/...` as the durable evidence layer

### 5. There is not currently a canonical DB “WhatsApp sent” column
If `web_automations` needs confirmed-send truth, it must read the ledger.

## Minimum Efficient Integration Contract

For `web_automations`, the recommended minimum contract is:

1. Read-only SQLite connection to `fact_orders_kaspi`
2. Read-only JSON read of the latest matching `send_batch_manifest.json`
3. Read-only JSON read of the matching `send_ledger.json`
4. Normalize the joined result into its own local cache/snapshot

That avoids:
- touching Google Sheets
- touching Excel
- writing into this repo
- depending on fragile UI artifacts

## Example: Read-Only Order Context Query

```python
import sqlite3

TARGET_DATE = "2026-04-17"
DB_URI = "file:~/Docs/Autonomous_business/db/app.db?mode=ro"

conn = sqlite3.connect(DB_URI, uri=True)
conn.row_factory = sqlite3.Row

rows = conn.execute(
    """
    SELECT
        id,
        order_id,
        store_code,
        kaspi_offer_name,
        sku_key,
        sku_id,
        quantity,
        assigned_size,
        size_source,
        internal_status,
        planned_shipment_date,
        actual_shipment_date,
        courier_transmission_date,
        waybill_url,
        waybill_number
    FROM fact_orders_kaspi
    WHERE planned_shipment_date = ?
      AND internal_status = 'SHIPPED'
      AND COALESCE(actual_shipment_date, courier_transmission_date, '') != ''
    ORDER BY store_code, order_id, id
    """,
    (TARGET_DATE,),
).fetchall()
```

## Current Real Example
For `2026-04-17`, the live system recorded shipped rows like:
- `order_id=891434681`, `assigned_size=XL`, `size_source=GOOGLE_OPS_BOARD`, `internal_status=SHIPPED`
- `order_id=891472309`, `assigned_size=L`, `size_source=GOOGLE_OPS_BOARD`, `internal_status=SHIPPED`

And the confirmed send batch was:
- [17.04.26_MERGED_qnt58](~/Docs/Autonomous_business/excel_ui/Kaspi_orders/Today/MERGED/SEND/17.04.26_MERGED_qnt58)

## Do Not Use As Truth
- `.claude/*.md`
- Google Sheet tabs
- runtime logs
- ad hoc CSVs under `exports/` unless you explicitly need evidence/audit

## Owner-Approved Integration Shape
The intended external integration pattern is:
- `Autonomous_business` owns ops truth and produces it
- `web_automations` consumes that truth read-only for context
- any derived cache, feature vectors, prompts, or automation state are stored inside `web_automations`, not here
