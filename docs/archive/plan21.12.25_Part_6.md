# plan21.12.25_Part_6.md

**Project:** Autonomous Inventory/PO System  
**Date:** 2025-12-24  
**Scope:** Part 6 — Run the System for Real (Shadow → Assisted → Partial Auto) + Business KPIs + Reconciliation  
**Status entering Part 6:** Parts 0–5 complete (one-button daily pipeline, guardrails, approvals, partial-auto executor behind gates, run tracking, Telegram digests, tests green).

---

## 0) Prime directive
Maximize profit growth **while protecting capital** from architectural and operational errors.

**Priority stack:**
1) Protect capital  
2) Build data (see clearly)  
3) Automate (efficiency)  
4) Scale (growth last)

---

## 1) Why Part 6 exists
Part 5 built the **control system**.  
Part 6 proves it under real operations and closes the loop from:
**recommendation → decision → execution → reconciliation → learning**.

The most common failure mode after “code complete” is:
- parameters drift (FX/VAT/budgets stale)
- data hygiene issues (missing cost/weight/price)
- approvals are ignored (people revert to verbal decisions)
- execution is non-idempotent (double orders)
- no reconciliation (system believes inventory that doesn't exist)

---

## 2) Operational cutover ladder (default)
### Phase 1 — Shadow Mode (7 consecutive runs)
- `AUTONOMOUS_PO_ENABLED=false`
- `PO_DRAFT_ONLY=true`
- Daily artifacts:
  - dashboard export
  - PO drafts
  - shadow scorecard (summary + detail)
  - run history rows (fact_runs / fact_run_steps)
  - Telegram success digest

**Spend:** 0

### Phase 2 — Assisted Mode (7–14 days)
- `AUTONOMOUS_PO_ENABLED=true`
- `PO_DRAFT_ONLY=true`
- Approvals required for WARN lines:
  - record to `fact_po_approvals`
- Spend remains manual (but decisions are recorded)

### Phase 3 — Partial Auto Execution (ORDER_FULL only) (14–30 days)
- `AUTONOMOUS_PO_ENABLED=true`
- `PO_DRAFT_ONLY=false`
- `AUTO_EXECUTE_MODE=ORDER_FULL_ONLY`
- Execute only “approved” lines and re-run guardrails at execution time.

### Phase 4 — Full Auto (later)
Only after stable scorecards + zero incidents.

---

## 3) Part 6 workstreams

### P6-A — Parameter governance (P0)
**Goal:** ensure the brain is running with valid parameters.

**Daily strict validation**
- `python scripts/validate_params.py --strict`

**Update policy**
- FX rates: update weekly (or whenever KZT moves materially)
- Budget caps: monthly, with explicit “available capital” backing
- VAT rate: effective-date already supported (watch 2026-01-01 boundary)

**Definition of Done**
- strict validation runs daily; no “defaults” are silently used

---

### P6-B — Shadow Mode streak (P0)
**Goal:** 7 consecutive successful daily runs.

**Daily procedure**
1) `python scripts/run_end_of_day.py`
2) Confirm Telegram digest received
3) Review `exports/shadow_scorecard_YYYY-MM-DD.csv`

**Scorecard review checklist**
- Total proposed spend vs caps
- Top 10 SKUs by spend
- Blocked spend by reason
- Missing-input blocks list (fix master data)

**Definition of Done**
- 7 consecutive days succeed with full artifacts

---

### P6-C — Data hygiene closure loop (P0)
**Goal:** reduce “missing inputs” blockers.

**Actions**
- Weekly: prioritize fixing missing fields for SKUs that represent top 80% of proposed spend:
  - weight_kg
  - unit_cost
  - sell_price
  - supplier mapping / size mapping

**Definition of Done**
- missing-input blocks < 5% of proposed spend by day 7

---

### P6-D — Assisted Mode operations (P1)
**Goal:** approvals become the real control system.

**Daily**
- list pending approvals:
  - `python scripts/approve_po_draft.py --list-pending`
- approve/reject with notes (audit trail required)

**Definition of Done**
- all WARN lines have approvals recorded (or are rejected)

---

### P6-E — Execution + reconciliation (P1)
**Goal:** when partial auto is enabled, we can prove we didn’t “double execute” and we can reconcile what actually happened.

**Execution discipline**
- Always run execution script with `--check-gates` before enabling.
- Prefer `--dry-run` for the first week even if gates are enabled.

**Reconciliation tasks**
- Add an “executed vs draft” reconciliation artifact:
  - executed spend
  - executed qty
  - blocked/skipped lines and reasons
  - idempotency check status

**Definition of Done**
- can answer “what did we execute yesterday?” from DB only

---

### P6-F — Weekly business KPI report (P1)
**Goal:** prove the system improves profit and reduces stockouts.

**Suggested KPIs**
- Fill rate proxy: days in stock for top SKUs
- Stockout loss proxy: OOS days × demand estimate
- Inventory turns
- Cash locked in inventory vs cap
- Forecast bias (actual sales vs predicted) for top SKUs

**Definition of Done**
- script generates weekly report without Excel

---

## 4) Go/No-Go gates
**Move to Assisted Mode only when**
- 7 consecutive shadow runs succeed
- scorecard stable (no wild spend spikes)
- missing-input blocks < 5% of spend

**Move to Partial Auto only when**
- Assisted Mode used daily (approvals recorded)
- no budget/concentration surprises
- “execute” is proven idempotent with dry-run comparisons

---

## 5) Emergency rollback
At any time:
```bash
export AUTONOMOUS_PO_ENABLED=false
export PO_DRAFT_ONLY=true
```

---

## 6) Commands reference
```bash
# Daily
python scripts/run_end_of_day.py

# Scorecard (if not already part of the pipeline)
python scripts/generate_shadow_scorecard.py

# Approvals
python scripts/approve_po_draft.py --list-pending
python scripts/approve_po_draft.py --draft-id X --approve --notes "..."
python scripts/approve_po_draft.py --draft-id X --reject --notes "..."

# Execution gates and dry-run
python scripts/execute_po_draft.py --check-gates
python scripts/execute_po_draft.py --draft-id X --dry-run
```
