# Sales Truth Protocol (Kaspi-only)

## 1) Purpose
Guarantee a single, reliable source of truth for sales while keeping the pipeline idempotent and auditable.

## 2) Source-of-truth rules
- **Future orders (daily ops):** `SALES_KSP_CRM_V3.xlsx` → `SALES_KSP_CRM_1` → `tb_SalesRaw`
  - This is the authoritative source for **new** orders once sizes are assigned (end-of-day).
- **Historical backfill:** `SALES_KSP_CRM_V3.xlsx` → `Archive_sales`
  - Used **only** to repopulate history.
  - Do not use Archive_sales for new orders.
- **DB tables are derived:**
  - `sales_fact_v2` and `fact_sales` are downstream products; they must be rebuilt/updated from CRM.

## 3) Canonical deduplication key
**Dedup key (required):**
```
store_code + order_id + kaspi_offer_name + sku_key + my_size
```
Why:
- `order_id` alone is not enough for multi-line orders.
- `sku_id` alone can collapse distinct `kaspi_offer_name` lines that share the same size.
- This key preserves the true order-line grain even when SKU_ID naming is inconsistent.

## 4) Daily (end-of-day) pipeline behavior
**When:** evening run (after sizes are finalized).

**Steps:**
1. **CRM → DB sync** (`scripts/sync_crm_to_db.py`)
   - Reads `SALES_KSP_CRM_1` / `tb_SalesRaw`.
   - Updates **both** `sales_fact_v2` and `fact_sales` using the canonical dedup key.
   - Computes economics with v8 (delivery fee, net rev, cogs, profit) for `fact_sales`.
2. **Aggregate rebuild** (`scripts/build_daily_aggregates.py`)
   - Rebuilds `fact_sales_daily` and `fact_sales_daily_size` for the updated date range.
3. **API status sync** (`scripts/sync_kaspi_orders.py --all --since <cutoff - lookback>`)
   - Updates `fact_orders_kaspi` with real order status (cancel/return/completed).

## 5) Delivery fee policy
- **Primary:** use seller delivery fee from CRM if present.
- **Fallback:** compute with v8 delivery fee matrix if fee is missing or zero.
- **Backfill:** use `scripts/backfill_delivery_fees.py` only as a last resort.

## 6) Historical rebuild (Archive_sales)
- Use `scripts/rebuild_fact_sales.py` to repopulate history.
- Dedup uses the canonical key: `(store_code, order_id, kaspi_offer_name, sku_key, my_size)`.
- If SKU_ID is missing, resolve via `dim_sku_size` before falling back to derived IDs.

## 7) Drift detection + reconciliation
- Daily check: CRM rows (tb_SalesRaw) vs DB fact_sales row count for the same date range.
- If drift exceeds threshold, log an ISSUE and re-run the CRM → DB sync step.

## 8) Guardrails
- Do **not** change formulas outside `Master_Inventory_Rules_v8.md`.
- Do **not** relax dedupe logic.
- If API sync fails, treat it as a blocker (no silent pass).

