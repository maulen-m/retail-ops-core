# plan21.12.25_Part_4.md

**Project:** Autonomous Inventory/PO System  
**Date:** 2025-12-22  
**Scope:** Part 4 — Cutover Ladder (Shadow → Assisted → Partial Auto) + Fix the last “trust killers”  
**Status entering Part 4:** Part 3 code is in place (guardrails wired, schema drift fixed, overrides consistent via `d_final_with_override`, run history + Telegram alerts, kill switches).

---

## 0) Prime directive
Maximize profit growth **while protecting capital** from architectural and operational errors.

**Priority stack (never violate):**
1) Protect capital  
2) Build data (see clearly)  
3) Automate (efficiency)  
4) Scale (growth last)

---

## 1) Why Part 4 exists
A system becomes “autonomous” only when:
- it runs daily without babysitting
- it produces *stable, explainable* outputs
- it’s observable (run history + alerts)
- and its money-moving actions are gated by capital safety + approvals

**Part 3 built the machinery.  
Part 4 proves it in the real world and performs a controlled cutover.**

---

## 2) Non-negotiable cutover gates
Before any move beyond “draft-only”:
1) **Test suite is green OR failures are explicitly quarantined** with xfail + documented issue ID  
   - “pre-existing failures” are still risk until proven irrelevant.
2) **7 consecutive daily runs succeed** (same schedule, same artifacts)  
3) **Dashboard and Auto-PO remain consistent** (same demand source, same logic, same guardrails outcomes)  
4) **Capital guardrails block unsafe spend by default** (no bypass without explicit approval + reason)

---

## 3) Workstreams (ordered by ROI × risk reduction)

### P4-A — Test failures triage (NOW)
Current state: `922 passed, 3 failed, 4 skipped`.

**Why this matters:**  
Two of the failures are described as “data grain” and “demand estimator” tests — those are *exactly* the foundations of correct PO decisions. They are not optional.

**Tasks**
- A1) Identify the 3 failing tests and categorize:
  - **Real bug** (fix it)
  - **Flaky/fixture issue** (make deterministic)
  - **Legacy expected failure** (convert to `xfail` and open `TASK-###` with clear acceptance criteria)
- A2) Reduce skipped tests:
  - If they’re skipped because of missing env/data → add a minimal fixture DB and run them in CI.
  - If truly integration-only → keep skipped but document exactly when/how to run.

**Definition of Done**
- `pytest` returns **0 failures** on a clean machine
- any `xfail` has a linked issue and a written reason

---

### P4-B — Shadow Mode (7 days) with scorecard (NOW)
**Mode definition:** system runs daily and produces:
- dashboard JSON
- auto-PO drafts (still draft-only)
- demand diagnostics
- guardrails summary
- run history persisted
- Telegram “success digest” + “failure alert”

**Kill switch defaults remain:**
- `AUTONOMOUS_PO_ENABLED=false`
- `PO_DRAFT_ONLY=true`

**Tasks**
- B1) Ensure `scripts/seed_params.py` is idempotent (no overwriting current rates/caps).
- B2) Schedule the daily run (20:30 Almaty) using your existing scheduler mechanism.
- B3) Add a daily “shadow scorecard” export, e.g. `exports/shadow_scorecard_YYYY-MM-DD.csv`:
  - total proposed spend (KZT)
  - count ORDER_FULL / ORDER_WITH_FLAG / REVIEW_REQUIRED
  - top 10 SKUs by spend
  - concentration breaches prevented
  - budget cap blocks
  - missing-input blocks (and the exact missing field)
  - override count + top overridden SKUs
  - number of SKUs using fallback demand (no estimate)

**Definition of Done**
- 7 consecutive days produce artifacts + run records
- Telegram digest includes the scorecard headline metrics

---

### P4-C — “Decision quality” monitoring (NEXT)
**Goal:** prove that demand and PO decisions are behaving like the business expects.

**Tasks**
- C1) Add weekly backtest metrics from actual sales:
  - demand bias (WAPE/bias) for top SKUs
  - stockout events and estimated lost sales
  - frequency of “suppression detected” vs “real decline likely”
- C2) Add guardrails effectiveness metrics:
  - how much spend was blocked by ROIC < 10%
  - how much spend was blocked by concentration > 20%
  - how much spend was blocked by budget caps
  - how many blocks were due to missing inputs (data hygiene measure)

**Definition of Done**
- A “Weekly Autonomy Report” can be generated from DB only (no Excel)

---

### P4-D — Assisted Autonomy (approval workflow) (NEXT)
**Mode definition:** system produces drafts + guardrail decisions, and humans approve WARN lines.

**Tasks**
- D1) Implement approval capture:
  - table `fact_po_approvals(draft_id, approved_by, approved_at, decision, notes)`
  - CLI: `scripts/approve_po_draft.py --draft-id X --approve/--reject --notes "..."`
- D2) Telegram improvement (optional):
  - include draft_id and a short “approve link” pattern or code for easy manual approval (even if fully interactive buttons come later).

**Definition of Done**
- WARN lines cannot progress without recorded approval
- BLOCK lines cannot progress without explicit override + reason

---

### P4-E — Partial Auto (only ORDER_FULL) (LATER)
**Mode definition:** autop-run executes only the safest class of orders.

**Rules**
- Execute ONLY `ORDER_FULL`
- Still block on missing inputs / budget caps / concentration breaches
- Keep “draft-only” option as the immediate rollback

**Definition of Done**
- 30-day scorecard shows stable performance and no capital incidents

---

## 4) Runbook (minimum viable daily ops)
1) `python scripts/validate_params.py`
2) `python scripts/run_end_of_day.py`
3) Confirm Telegram digest received
4) Spot-check:
   - top 5 spend SKUs
   - any new overrides
   - any missing-input blocks (fix the master data)

---

## 5) Rollback plan
- Keep manual PO flow as fallback.
- If any smoke test fails, system stays in shadow/draft-only.
- Parameter changes are effective-dated → rollback = insert earlier effective row.

---

## 6) Deliverables for Part 4
- Green tests (or explicit xfail with issue IDs)
- 7-day shadow scorecards + run history
- Weekly autonomy report script
- Approval workflow (DB + CLI)
- Updated docs: DAILY_SOP.md section “Part 4 Cutover Ladder”
