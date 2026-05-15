# Workflow SOP v2.0
## Inventory Core — Simplified Operations (V18.1_V2)
**Created:** December 3, 2025  
**Updated:** December 4, 2025  
**Effective with:** Inventory_Core_V18.1_V2.xlsx

---

## 1. File Architecture

### Active Files

| File | Purpose | Update Frequency |
|------|---------|------------------|
| **Inventory_Core_V18.1_V2.xlsx** | Frozen UI — ABC_View, status flags | Weekly review |
| **Kaspi_Export_[DATE].xlsx** | Raw daily export from Kaspi | Daily (download) |
| **Stock_Count_[DATE].xlsx** | Physical count snapshots | When reconciling |

### Archived Files (Read-Only Reference)

| File | Former Purpose | Archive Reason |
|------|----------------|----------------|
| `PO_storing.xlsx` | PO entry + old ABC | Replaced by Fact_PO_Lines + ABC_View |
| `SALES_KSP_CRM_V3.xlsx` | Sales processing | Column semantics reference only |
| `SALES_KSP_CRM_GPT_15_9_25.xlsx` | Legacy sales | Canonical row source (13,371 rows) |
| `Business_model_V3.xlsx` | PO master, costs | Historical reference only |
| `Sku_Map_CRM_3.xlsx` | SKU mapping | Data now in Dim_SKU |

### Project 3 (CRM) Takes Over

| Task | Excel UI | Project 3 Python |
|------|-----------|------------------|
| Sales ingestion | Manual paste | **Automated** |
| Daily aggregation | SUMIFS | **SQL/Python** |
| ROIC calculations | ABC_View | **Automated** |
| PO recommendations | Suggested_Order_Qty | **Automated** |

---

## 2. Weekly Decision Cycle (< 30 min)

### Step 1: Open ABC_View (2 min)

1. Open `Inventory_Core_V18.1_V2.xlsx`
2. Navigate to `ABC_View` sheet
3. Let formulas recalculate (wait for status bar)

### Step 2: Review Status Flags (5 min)

Sort by **Status** column (AD):

| Status | Meaning | Action |
|--------|---------|--------|
| ⚠️ REORDER | Total stock below ROP | Place PO this week |
| 📦 WAIT (inbound) | Current low but inbound covers | Monitor; PO in transit |
| ✅ OK | Total stock above ROP | No action needed |

For REORDER SKUs, check:
- `Suggested_Order_Qty` (column AC)
- `ROIC_pct` (column AB) — is it worth the capital?

### Step 3: Update PO Status (3 min)

1. Go to `Fact_PO_Lines` sheet
2. Find any POs that shipped → change Status to `IN_TRANSIT`
3. Find any POs that arrived → change Status to `DELIVERED`
4. `tb_Inbound` auto-updates (only shows IN_TRANSIT)

### Step 4: Decide Order Quantities (10 min)

1. For each REORDER SKU:
   - Use `Suggested_Order_Qty` as baseline
   - Adjust based on capital constraints
   - Consider ROIC ranking (higher ROIC = priority)
2. Allocate by size using size mix percentages

### Step 5: Record New PO (5 min)

1. Go to `Fact_PO_Lines` sheet
2. Add new rows for each SKU × Size:
   - `Internal_order_id` — your PO number
   - `SKU_KEY` — exact SKU_key
   - `MY_SIZE` — size code
   - `Order_Quantity` — units
   - `Status` — `UNPAID` or `PAID`
   - `Ast_arrival_date` — expected arrival (today + L_days)
3. Send PO to supplier via WhatsApp/Email

### Step 6: Verify (2 min)

1. Check ABC_View recalculated
2. SKU you just ordered should now show `📦 WAIT (inbound)`
3. Done!

---

## 3. What You DON'T Do Anymore

| Old Process | Why It's Gone |
|-------------|---------------|
| ❌ Rebuild Fact_Sales_Daily by hand | Derived view — all formulas |
| ❌ Process sales through SALES_KSP_CRM_V3 | Bypassed; direct to Fact_Sales |
| ❌ Open PO_storing.xlsx for new POs | Use Fact_PO_Lines |
| ❌ Edit formula columns in Fact_Sales | J-P are all formulas |
| ❌ Worry about Dim_PO_Header | Deprecated in current Excel |

---

## 4. Status Flag Reference

| Status | Condition | Action |
|--------|-----------|--------|
| ⚠️ REORDER | `Total_stock < ROP` | Place PO now |
| 📦 WAIT | `Current < ROP` but `Total ≥ ROP` | Monitor; inbound covers |
| ✅ OK | `Total ≥ ROP` | No action |

**Formula in ABC_View.AD:**
```excel
=IF(E2<U2,"⚠️ REORDER",IF(C2<U2,"📦 WAIT (inbound)","✅ OK"))
```

Where:
- C = Current_stock
- E = Total_stock (Current + Inbound)
- U = ROP

---

## 5. Key Formulas (Reference)

All formulas live in `inventory/Master_Inventory_Rules_v9.md`.
Do not change Excel formulas without updating `inventory/Master_Inventory_Rules_v9.md` first.

---

## 6. Fact_Sales Column Map (V16)

For column layouts, use `inventory/Sales_Data_Model_V16.md`.  
If manual entry is required, only fill **data columns**; formula columns auto-calc.

---

## 7. Fact_Sales_Daily — DO NOT EDIT

Fact_Sales_Daily is a **derived view**. See `inventory/Sales_Data_Model_V16.md`.
| G (Profit) | SUMIFS | P (Profit_line) |

**If you see hard-coded numbers here, it's a bug.** Report it.

---

## 8. Troubleshooting

| Problem | Check | Fix |
|---------|-------|-----|
| D_30 shows 0 | No sales in Fact_Sales for this SKU | Normal for slow/new SKUs |
| Status stuck on REORDER | PO not recorded or Status wrong | Add PO to Fact_PO_Lines, set IN_TRANSIT |
| Inbound_units not updating | Status not "IN_TRANSIT" | Fix Status column value |
| ROIC seems wrong | Check COGS, Price, D_30 | Verify Dim_SKU values |
| Revenue = Delivery in Daily | Wrong SUMIFS column | Bug — columns should be D→L, E→J |

---

## 9. Future: Project 3 Takes Over

Once Project 3 (CRM/Python) is operational:

| Your Role | Excel | Python |
|-----------|-------|--------|
| Review decisions | Open ABC_View | Dashboard |
| Track orders | Fact_PO_Lines | Automated |
| Import sales | Manual | **Automated** |
| Calculate ROIC | Formulas | **Automated** |

Excel becomes a backup/validation tool. Python is the brain.

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-12-03 | Initial SOP for V14 workflow |
| **2.0** | **2026-01-05** | **Aligned to V18.1_V2:** References v8 + Sales_Data_Model_V16. |
