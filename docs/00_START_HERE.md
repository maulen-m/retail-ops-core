# 00_START_HERE — Docs Index (Kaspi-only)

**Goal:** maximize signal-to-noise for agents (Codex/Opus) and humans.  
**Scope:** This repo currently operates **Kaspi only**.

---

## 1) Source-of-truth ladder (avoid “truth contamination”)

When documents disagree, resolve conflicts in this order:

1. **`inventory/Master_Inventory_Rules_v8.md`**  
   *Formulas + parameters (SS/ROP/ROIC, unit economics, delivery fee rules, prep days, partial OOS detection).*

2. **`protocol/active/PO_making_logic_v2.md`**  
   *Algorithmic PO construction and size allocation logic. Must conform to v8 formulas.*

3. **`inventory/Sales_Data_Model_V16.md`**  
   *Schemas and column meanings (V16).*

4. **`ARCHITECTURE.md`**  
   *Code/module structure and responsibilities.*

5. **`inventory/Excel_UI_Contract_for_CRM_*` + `inventory/Automation_Handoff_V16.md`**  
   *Excel/Python equivalence contract and validation rules (must be updated to v8/V16).*

**Rule:** Do not duplicate formulas across docs. If a doc needs a formula, it should link to v8.

---

## 2) Minimum reading set (fast onboarding)

### If you’re doing **inventory math / demand / PO logic**
Read in this order:
1. `inventory/Master_Inventory_Rules_v8.md`
2. `protocol/active/PO_making_logic_v2.md`
3. `size_engine_specification.md` (size probability + assignment cascade)

### If you’re doing **data ingestion / DB schemas**
1. `inventory/Sales_Data_Model_V16.md`
2. `inventory/Automation_Handoff_V16.md`
3. `inventory/Excel_UI_Contract_for_CRM_*`

### If you’re doing **Kaspi orders automation**
1. `docs/DAILY_SOP.md`
2. `KASPI_API_INTEGRATION.md`
3. `Kaspi_API_Official_document_8.12.2025_GP.md` (reference)

### If you’re changing **system architecture / modules**
1. `ARCHITECTURE.md`
2. `inventory/Automation_Handoff_V16.md` (interfaces + outputs)

---

## 3) Docs categories (so agents don’t waste context)

### A) Contracts (authoritative, must stay consistent)
- `inventory/Master_Inventory_Rules_v8.md`  ✅
- `inventory/Excel_UI_Contract_for_CRM_*` ✅
- `inventory/Automation_Handoff_V16.md` ✅
- `inventory/Sales_Data_Model_V16.md` ✅
- `protocol/active/PO_making_logic_v2.md` ✅

### B) Operating procedures (how to run the machine)
- `DAILY_SOP.md`
- `PACKAGING_RULES.md`
- `DAILY_WORKFLOW.md`

### C) Architecture (how the code is shaped)
- `ARCHITECTURE.md`
- `KASPI_API_INTEGRATION.md`

### D) Protocols & plans (use only when assigned)
Everything under `protocol/` is split into:
- **`protocol/active/`** → current workstreams
- **`protocol/archive/`** → historical artifacts

Agents should **not** read all protocols by default.

---

## 4) Current doc debt (what’s known to be wrong/outdated)

- Some docs may still reference outdated VAT or delivery fee tiers.  
  These must be updated to match v8 and the Kaspi 2026 fee matrix.

- Some docs/plans include non-Kaspi assumptions.  
  Repo scope is Kaspi-only → remove or archive those sections.

- The legacy oracle pack summary is deprecated; use `SYSTEM_OVERVIEW.md` instead.

---

## 5) If you’re an agent: operating rules

1. Always read this file first.
2. Then read only the **minimum reading set** for your task.
3. Treat anything labeled **DEPRECATED** as read-only history.
4. If you find a formula mismatch: update **v8 first**, then propagate to Excel/Python.
