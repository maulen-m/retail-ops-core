# Automation Handoff — V16 (Kaspi-only)
## Project 1 → Project 3 Transition Document
**Created:** 2026-01-05  
**Source:** Inventory_Core_V18.1_V2.xlsx  
**Target:** Project 3 CRM/DB (system of record)

---

## 1. Executive Summary

Excel is **UI only**. Project 3 (DB/Python) is the system of record. This doc defines the
minimum contract to keep Excel and Python aligned.

**Source of truth:** `inventory/Master_Inventory_Rules_v9.md` (formulas + parameters).
**Schema contract:** `inventory/Sales_Data_Model_V16.md`.

---

## 2. Required DB Tables (Kaspi-only)

| Table | Purpose | Grain |
|-------|---------|-------|
| `fact_sales_raw` | Raw Kaspi exports | Order line |
| `fact_sales` | Cleaned transactions | Order line |
| `fact_sales_daily` | Daily aggregates | Date × SKU |
| `dim_sku` | SKU master | SKU_key |
| `dim_sku_size` | Size dimension | SKU_ID |
| `dim_params` / `dim_params_pt` | Parameters | Param key |
| `dim_delivery_fees` | Kaspi fee matrix | lookup rows |
| `fact_po_lines` | PO tracking | PO × SKU × Size |

---

## 3. Core Calculations

All formulas are defined in `inventory/Master_Inventory_Rules_v9.md`.
Do **not** duplicate formulas here. If anything changes, update `inventory/Master_Inventory_Rules_v9.md` first.

Key requirements:
- VAT_rate = **0.04**
- Kaspi delivery fee uses **matrix lookup** (not legacy tiers)
- Safety stock/ROP uses **Effective_L**
- Partial OOS suppression uses size-level detection

---

## 4. Automation Workflows (Kaspi-only)

| Workflow | Trigger | Action |
|----------|---------|--------|
| Sales ingestion | Daily/scheduled | Parse Kaspi export → fact_sales_raw → fact_sales |
| Daily aggregation | After ingestion | Rebuild fact_sales_daily |
| ROIC refresh | After aggregation | Recalculate ABC metrics per SKU |
| Reorder alerts | When status = REORDER | Telegram notifications |
| PO status update | When goods ship/arrive | Update fact_po_lines.status |

---

## 5. Data Sources

### 5.1 Legacy Sales (One-Time Import)

| File | Role | Use |
|------|------|-----|
| `SALES_KSP_CRM_GPT_15.9.25.xlsx` | Canonical legacy rows | Import Archive_sales sheet |

### 5.2 Future Ingestion (Kaspi-only)

| Source | Format | Notes |
|--------|--------|-------|
| Kaspi daily export | ActiveOrders_Example.xlsx format | Column mapping in `config/kaspi_column_map.yaml` |

---

## 6. Validation Requirements

Before Project 3 changes go live:

| Check | Method | Threshold |
|-------|--------|-----------|
| D_30 matches Excel | Compare SKU sample | ±1% |
| SS_total matches Excel | Compare SKU sample | ±1% |
| ROIC matches Excel | Compare SKU sample | ±2% |
| Status flags identical | ABC_View match | 100% |

---

## 7. Change Control

1. Update `inventory/Master_Inventory_Rules_v9.md` **first**.
2. Update Excel workbook formulas (V18.1_V2).
3. Update Python implementation + tests.
4. Update this handoff doc only if interfaces change.

---

*This contract is binding for Project 1 (Excel UI) and Project 3 (CRM/DB).*  
*Kaspi-only until further notice.*
