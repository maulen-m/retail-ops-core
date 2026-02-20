# plan21.12.25_Part_5.md

**Project:** Autonomous Inventory/PO System  
**Date:** 2025-12-23  
**Scope:** Part 5 — Cutover Execution (Shadow → Assisted → Partial Auto) + Scorecard Governance  
**Status entering Part 5:** Parts 0–4 complete (tests stabilized, guardrails wired, schema in sync, run history + Telegram alerts, shadow scorecard + approvals workflow in place).

---

## 0) Prime directive
Maximize profit growth **while protecting capital** from architectural and operational errors.

**Priority stack (never violate):**
1) Protect capital  
2) Build data (see clearly)  
3) Automate (efficiency)  
4) Scale (growth last)

---

## 1) What Part 5 is (and is not)
**Part 5 is NOT more code-for-the-sake-of-code.**  
Part 5 is controlled operations + measurable trust-building.

**Goal:** Move from “draft-only safety” to “assisted autonomy” and then to “partial auto execution” without risking a capital incident.

---

## 2) Cutover ladder (canonical)
### Phase 1 — Shadow Mode (7 consecutive days)
- `AUTONOMOUS_PO_ENABLED=false`
- `PO_DRAFT_ONLY=true`
- Output drafts + dashboards + scorecard + run logs
- Spend: **0** (human remains the spender)

### Phase 2 — Assisted Mode (7–14 days)
- `AUTONOMOUS_PO_ENABLED=true`
- `PO_DRAFT_ONLY=true`
- Drafts produced daily; **WARN lines require approval** in `fact_po_approvals`
- Spend still executed manually, but approvals are recorded

### Phase 3 — Partial Auto (ORDER_FULL only) (14–30 days)
- `AUTONOMOUS_PO_ENABLED=true`
- `PO_DRAFT_ONLY=false` (only when the executor is ready)
- Execute ONLY lines with:
  - guardrails result = approved
  - ROIC tier = ORDER_FULL
  - no missing-input blocks
  - within budget caps and concentration rules

### Phase 4 — Full Auto (later)
Only after 30 days of boring scorecards and zero incidents.

---

## 3) Part 5 Workstreams

### P5-A — Day 0 setup (NOW)
**Checklist**
1) Seed parameters (idempotent)
   - `python scripts/seed_params.py`
2) Validate parameters
   - `python scripts/validate_params.py`
3) Confirm Telegram alerts are working (failure + success digest)
4) Confirm kill switches are safe defaults

**Definition of Done**
- `validate_params.py` passes
- Telegram test alert delivered

---

### P5-B — Shadow Mode operations (7 consecutive runs) (NOW)
**Daily run commands**
1) `python scripts/validate_params.py`
2) `python scripts/run_end_of_day.py`
3) `python scripts/generate_shadow_scorecard.py`

**Daily review (10 minutes)**
- Open `exports/shadow_scorecard_YYYY-MM-DD.csv`
- Check:
  - total proposed spend vs caps
  - ORDER_FULL/WARN/BLOCK counts
  - blocked spend by reason
  - missing-input blocks list (this is your “data hygiene todo list”)
  - override usage count

**Definition of Done**
- 7 consecutive daily runs succeed and write:
  - run record to `fact_runs`
  - scorecard CSV outputs
  - Telegram success digest with headline metrics

---

### P5-C — Scorecard governance (NOW/NEXT)
**Goal:** Define “stable enough” criteria so cutover decisions are objective.

**Recommended stability gates (default)**
- No run failures in the 7-day window
- Missing-input blocks trend downward and are < 5% of proposed spend by Day 7
- Budget cap blocks are explainable and not caused by broken FX/VAT rows
- Concentration rule does not require extreme quantity clipping on multiple days
- Override usage is stable (no sudden spikes without documented reasons)

**Definition of Done**
- A written “Go/No-Go” note exists for moving to Assisted Mode

---

### P5-D — Assisted Mode execution (NEXT)
**Objective:** Start using approvals as a real control system.

**Daily**
- List pending approvals:
  - `python scripts/approve_po_draft.py --list-pending`
- Review WARN lines (top by spend first)
- Approve/reject with reason:
  - `python scripts/approve_po_draft.py --draft-id X --approve --notes "..."`

**Definition of Done**
- WARN lines cannot be marked ready without approvals recorded
- Approval log is used daily (no “approvals in head”)

---

### P5-E — Partial Auto execution (ORDER_FULL only) (NEXT/LATER)
**Objective:** Let the system execute the safest class of orders while remaining reversible.

**Tasks**
- Add an executor script that:
  1) loads a draft
  2) re-runs guardrails (idempotent safety)
  3) filters to ORDER_FULL-approved lines only
  4) writes the final “executed” artifact
  5) records execution status in run steps

**Hard safety rules**
- Any blocker => execute nothing
- Any missing critical inputs => execute nothing
- Any budget cap breach => execute nothing
- Require explicit env var:
  - `AUTONOMOUS_PO_ENABLED=true`
  - `PO_DRAFT_ONLY=false`
  - (recommended) `AUTO_EXECUTE_MODE=ORDER_FULL_ONLY`

**Definition of Done**
- 14 consecutive days of Assisted Mode show stable scorecards + approvals
- Partial Auto is enabled for ORDER_FULL only and can be rolled back instantly

---

### P5-F — Hygiene loop (continuous)
Most autonomy failures aren’t math — they’re missing master data.

**Daily**
- Fix the top missing-input blockers:
  - weight_kg
  - unit_cost
  - sell_price
  - supplier mapping

**Definition of Done**
- Missing-input blockers drop to near-zero for top 80% spend SKUs

---

## 4) Risk controls and rollback
**Emergency rollback**
- `export AUTONOMOUS_PO_ENABLED=false`
- `export PO_DRAFT_ONLY=true`

**Rule**
- If smoke tests fail or run tracker records a failed step, system stays in Shadow/Draft-only.

---

## 5) Definition of Done for Part 5
Part 5 is complete when:
1) 7 consecutive shadow runs succeed with scorecards + run history + Telegram digest
2) Assisted approvals are used daily for WARN lines (with audit trail)
3) A Go/No-Go decision is made with objective scorecard evidence
4) Partial Auto execution plan is ready (code + env gating) even if not enabled yet

---

## 6) Commands reference
```bash
# Validate parameters
python3 scripts/validate_params.py

# End-of-day pipeline
python3 scripts/run_end_of_day.py

# Shadow scorecard
python3 scripts/generate_shadow_scorecard.py

# Approvals
python3 scripts/approve_po_draft.py --list-pending
python3 scripts/approve_po_draft.py --draft-id X --approve --notes "..."
```
