# DEPRECATED — archived in `docs/archive/plan_17.12.25_V1.md`.

# plan_17.12.25_V1.md
Path (must exist in repo docs):
~/Docs/Autonomous_business/docs/plan_17.12.25_V1.md

Date: 2025-12-17
Owner: Opus agent
Goal: Fix core inventory math (T_post / Target) and remove formula drift vs Master_Inventory_Rules_v6.md so PO‑4 (today) is correct.

---

## 0) Context (don’t re-do completed work)
Already done (don’t repeat):
- DemandEstimator OOS-aware demand (partial OOS, size share blending)
- StockTimelineBuilder / snapshot rebuild scaffolding
- Multi-PO cascading in dashboard

Current pain:
- T_post and Target are wrong in dashboard: T_post jumped from ~32 to ~53 days.
- This contaminates Target, order quantities, and prep-day estimation (via rough_order).

---

## 1) Root cause (must fix first)
### 1.1 Wrong definition of T_post in dashboard
Current implementation in scripts/generate_po_dashboard_data.py (calc_po_draft_manual) uses:
- T_post = R + L + (SS_total / D)
This is wrong.

Pre-Arr = Stock - D * L - This is wrong.
Correct it to: Pre-Arr = current + inbound - D * effective_L

Correct per rules and Excel contract:
- T_post = R + (SS_total / D)
This is post-arrival coverage only.
Lead time belongs in Pre-arrival consumption window, not inside T_post.

### 1.2 Why this produces the exact symptom
If L = 21, the wrong formula inflates T_post by +21 days → ~32 becomes ~53.

### 1.3 Related bug: hardcoded B
calc_po_draft_manual currently sets:
- B = 14 (hardcoded)
But B is product-type dependent (CL vs ELS) and must come from params (Dim_Params_PT / inventory_params).

---

## 2) Hotfix changes (must be done BEFORE generating PO‑4 today)

### 2.1 Fix T_post + Target in calc_po_draft_manual
File:
- ~/Docs/Autonomous_business/scripts/generate_po_dashboard_data.py

In calc_po_draft_manual:
- Replace:
  T_post = R + L + (ss_total / d_sku)
  target = d_sku * T_post
- With:
  T_post = R + (ss_total / d_sku) if d_sku > 0 else R
  target = d_sku * T_post  # = d_sku*R + ss_total

Also update the docstring comment block to reflect the corrected formula.

### 2.2 Keep lead time where it belongs (Pre-arrival)
Do NOT remove effective lead time logic:
- effective_L = L + prep_days
- pre_arrival = current + inbound - D * effective_L
This is correct and should remain. Lead time is already accounted here.

### 2.3 Use product-type B from params (no hardcode)
Replace:
- B = 14
With:
- B = params.B

Confirm params.B exists and is loaded from product type policy (CL/ELS).

### 2.4 (Optional but recommended today) Make naming unambiguous in output
The dashboard currently exposes “T_post_days”.
After fix, it truly means post-arrival cover days.
Optionally add a debug-only field:
- T_total_days = effective_L + T_post
Not used in ordering; only helps sanity-check.

---

## 3) Hardening fixes (do right after PO‑4 is generated)

### 3.1 Remove formula duplication (single source of truth)
Problem:
- scripts/generate_po_dashboard_data.py manually re-implements inventory math,
  but core/calc already has correct helpers (size allocation has correct T_post formulation).

Solution:
- Refactor calc_po_draft_manual to call core/calc helpers:
  - calc_pre_arrival_stock(...)
  - calc_t_post_for_size(...) or an SKU-level equivalent
  - calc_ss_total (or compute SS_total with params)
Goal: One canonical implementation.

### 3.2 Fix / deprecate legacy po_generator.py
There is a separate PO generator implementation (core/automation/po_generator.py) with outdated economics (gross price, wrong shipping).
Action:
- Either:
  A) Mark it deprecated in header + ensure no codepath calls it, OR
  B) Refactor it to use core/calc/economics.py and the same inventory math.

### 3.3 Add regression tests for T_post + Target
Add tests to prevent this exact regression:
- Given D, SS_total, R, L:
  - T_post must equal R + SS_total/D (NO L)
  - Target must equal D*T_post
  - Pre-arrival must use effective_L (L + prep)
Use LINE52 and LINE51 as named fixtures (or synthetic numbers).

---

## 4) Runbook (today) — generate PO‑4 after patch
1) Sync truth workbook → DB (if DB may be stale):
   - Use your “today truth” workbook:
     ~/Docs/Autonomous_business/excel/PO-generator_FILLED_2025-12-15_GPT_1.xlsx
   - Run sync script already implemented (sync_truth_workbook_to_db.py).

2) Regenerate dashboard data + HTML:
   - python scripts/generate_po_dashboard_data.py
   - python scripts/generate_po_dashboard_html.py

3) Sanity checks (must pass before sending PO‑4):
   - For LINE52 and LINE51:
     - T_post should drop by ~21 vs current dashboard output
     - Target should drop accordingly (because Target = D*R + SS_total, no lead time)
   - Days→Arr should still reflect effective_L (prep + L), not just L.

4) Proceed to PO‑4 generation / sending.

---

## 5) Acceptance criteria (non-negotiable)
- T_post uses: R + SS_total/D (no L).
- Target uses: D*T_post = D*R + SS_total.
- Pre-arrival uses effective lead time: (L + prep_days).
- B uses params.B (not hardcoded).
- PO‑4 generated today from the updated dashboard output.

---
