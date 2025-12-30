# plan21.12.25_Part_7.md
**Project:** Autonomous Inventory/PO System  
**Date:** 2025-12-24  
**Scope:** Part 7 — Real Cutover + Profit Scaling (Shadow → Assisted → Partial Auto) + Growth Engines  
**Status entering Part 7:** Parts 0–6 complete (one-button daily pipeline, guardrails, approvals, partial-auto executor behind gates, run tracking + Telegram digests, reconciliation artifact, weekly KPI report, missing-data reporting, tests green).

---

## 0) Prime directive
Maximize profit growth **while protecting capital** from architectural and operational errors.

**Priority stack:**
1) Protect capital  
2) Build data (see clearly)  
3) Automate (efficiency)  
4) Scale (growth last)

---

## 1) Why Part 7 exists
Parts 0–6 built the “autonomous control system.”  
Part 7 is where we **use it in production** and then activate the true profit multipliers:

- Autonomy without cutover = a fancy simulator.
- Cutover without KPI proof = blind risk.
- KPI proof without growth engines = slow compounding (won’t hit $1M in 12–18 months).

---

## 2) Target outcomes for Part 7

### 2.1 Operational autonomy outcomes (trust + repeatability)
- **Shadow Mode:** 7 consecutive successful daily runs (no manual patching)
- **Assisted Mode:** 14 consecutive days where:
  - WARN lines are approved/rejected via `fact_po_approvals`
  - approvals include reasons
- **Partial Auto (ORDER_FULL only):** enabled for a controlled subset of drafts with:
  - zero duplicate executions (idempotency proven in the wild)
  - reconciliation artifacts generated daily
  - capital guardrails never violated

### 2.2 Business outcomes (measurable profit levers)
- Weekly autonomy report shows:
  - forecast bias is stable (no systematic under-estimation)
  - OOS/lost-sales proxy trending downward for top SKUs
  - blocked spend due to missing master data trending downward
- Documented “growth plan” for 2× and 3× profit-rate:
  - **2×**: multi-channel execution pilot
  - **3×**: supplier terms/lead time + pricing automation

---

## 3) Cutover ladder (canonical)

### Phase 1 — Shadow Mode (7 consecutive days)
- `AUTONOMOUS_PO_ENABLED=false`
- `PO_DRAFT_ONLY=true`

### Phase 2 — Assisted Mode (7–14 days)
- `AUTONOMOUS_PO_ENABLED=true`
- `PO_DRAFT_ONLY=true`

### Phase 3 — Partial Auto Execution (ORDER_FULL only) (14–30 days)
- `AUTONOMOUS_PO_ENABLED=true`
- `PO_DRAFT_ONLY=false`
- `AUTO_EXECUTE_MODE=ORDER_FULL_ONLY`

**Rule:** Partial auto starts with a spend cap (daily or per draft) even if global caps exist.

---

## 4) Workstreams and tasks (ordered by ROI × risk reduction)

### P7-A — Production Shadow/Assisted operations (NOW)
**Tasks**
1) Schedule daily run at 20:30 Almaty with clear log location.
2) Require `validate_params.py --strict` as the first gate.
3) Enforce daily review:
   - Shadow scorecard
   - Missing master data report (top spend impact)
   - Weekly autonomy report (once per week)

**Definition of Done**
- 7/7 shadow streak + 14/14 assisted streak logged in `fact_runs`
- Telegram digests are received daily

---

### P7-B — Data hygiene closure (NOW)
**Tasks**
- Attack missing master data blockers by spend impact:
  - weight_kg
  - unit_cost
  - sell_price
  - supplier mapping
- Track “blocked spend due to missing data” weekly and drive it toward near-zero for top 80% spend SKUs.

**Definition of Done**
- Missing-input blocks < 5% of proposed spend for 2 consecutive weeks.

---

### P7-C — Partial Auto “limited blast radius” rollout (NEXT)
**Tasks**
1) Enable Partial Auto **only** for ORDER_FULL lines.
2) Add additional rollout safety caps:
   - max executed spend per day
   - max executed spend per draft
   - optional: only allow execution for a whitelist of proven SKUs for week 1
3) Require reconciliation artifact review daily:
   - draft vs executed spend
   - skipped lines with reason
   - idempotency status

**Definition of Done**
- 10 consecutive executions succeed without incidents or manual rollback.

---

### P7-D — Growth Engine 1: Multi-channel execution pilot (NEXT)
**Goal:** unlock the first real profit-rate multiplier.

**Tasks**
- Pick first 20 “channel fit” SKUs for WB launch.
- Define channel demand coefficients + replenishment policy:
  - replenishment uses the same demand engine, but with channel weighting
- Define channel SOP:
  - pricing, listing, returns, shipment ops
- Add channel KPI tracking:
  - incremental revenue/profit contribution vs Kaspi-only baseline

**Definition of Done**
- Pilot SKUs produce measurable incremental profit without increasing OPEX linearly.

---

### P7-E — Growth Engine 2: Supplier + logistics optimization (NEXT/LATER)
**Goal:** preserve ROIC as capital scales.

**Tasks**
- Measure lead time distribution (mean + variance) and incorporate into ordering safety margins.
- Negotiate:
  - better terms (partial payment, longer payment window)
  - faster lead times / more frequent shipments
  - MOQ flexibility

**Definition of Done**
- Lower stockout risk + improved cash conversion cycle.

---

## 5) Capital protection rules (non-negotiable)
- Guardrails must block unsafe orders by default
- Approvals recorded for WARN lines
- Emergency rollback always available:
  - `AUTONOMOUS_PO_ENABLED=false`
  - `PO_DRAFT_ONLY=true`
- Any incident triggers immediate return to draft-only.

---

## 6) Commands reference
```bash
# Daily
python scripts/run_end_of_day.py

# Approvals
python scripts/approve_po_draft.py --list-pending

# Partial auto gates
python scripts/execute_po_draft.py --check-gates
python scripts/execute_po_draft.py --draft-id X --dry-run
python scripts/execute_po_draft.py --draft-id X  # when gates enabled
```
