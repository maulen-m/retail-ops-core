# PLAN_POST_V4_AUTONOMOUS_PO_AND_WRITE_SIDE_AUTOMATION_V1

**Status:** DRAFT  
**Scope:** Kaspi-only. Post completion of `docs/PLAN_CASHFLOW_V4_COMPLETION_AND_KASPI_API_MAX_AUTOMATION.md`.  
**Primary Goal:** Close the loop from decision-grade cashflow → decision-grade PO recommendations → (optionally) safe write-side actions (Kaspi pricelist), while minimizing capital-loss risk.

---

## 0) Non‑negotiables (must hold for every phase)

### 0.1 Truth ladder (do not contaminate truth)
When docs disagree, resolve in this order:
1) `inventory/Master_Inventory_Rules_v8.md` (formulas + unit economics)
2) `protocol/active/PO_making_logic_v2.md` (algorithmic steps; must conform to v8 formulas)
3) `inventory/Sales_Data_Model_V16.md` (schemas)
4) `ARCHITECTURE.md` (module boundaries)
5) `inventory/Excel_UI_Contract_for_CRM_*` + `inventory/Automation_Handoff_V16.md`

**Rule:** do not duplicate formulas across docs; reference v8 instead.

### 0.2 Test‑first execution
For each phase:
1) write/extend tests that fail on current behavior
2) implement minimal code to pass tests
3) run full gates (listed below)
4) only then declare results

### 0.3 Write barriers
Any “write side” automation (publishing Kaspi pricelist, creating supplier POs, etc.) is OFF by default.
Enable only behind an explicit env flag + explicit CLI flag + allowlist rollout.

### 0.4 Required gates (every phase)
- `python3 scripts/validate_params.py --strict`
- `pytest -q`
- `scripts/lint_docs.sh`
- `scripts/check_no_db_tracked.sh`

Cashflow-touching phases must additionally pass:
- `python3 scripts/validate_cashflow_invariants.py`
- `python3 scripts/validate_inventory_cost_drift.py`
- `ENABLE_CASHFLOW_WRITE=1 python3 scripts/run_end_of_day.py --verbose`

---

## 1) Where we are now (baseline)
- Cashflow V4 plan completed (through Phase G), including trust anchors and API enrichment capability.
- StageCode contract exists and is already used in enrichment selection.
- A separate write-side “Goods automation” exists as an optional future step and must remain behind explicit enable flags.

Daily pipeline ordering constraint remains:
Kaspi sync → cashflow rebuild → preflight → dashboards; cashflow reads DB only.

---

## 2) Phase H — PO “Money Gate”: contract + golden fixtures (CRITICAL PATH)

### Goal
Make PO recommendations *provably correct* vs a contract, so automation cannot silently deploy capital on wrong math.

### Deliverables
- `docs/validation/PO_CONTRACT.md`
  - Defines the exact output fields and tolerances for PO recommendation correctness.
- Golden fixtures:
  - One small deterministic fixture DB (or fixture tables) for repeatable PO computation.
  - One “expected outputs” artifact (CSV/JSON) produced from the contract baseline.
- Tests:
  - `tests/test_po_contract.py` (or equivalent) that runs PO generation on fixture data and asserts:
    - SS/ROP/T_post math matches v8 formulas (within tolerance)
    - ROIC gates match thresholds (see Architecture / params)
    - Status labeling exact match (REORDER/WAIT/OK)
    - Suggested_Q and size allocation outputs are stable/deterministic

### Gates
- Required gates (0.4)
- Plus: a single “contract runner” command that is stable locally, e.g.:
  - `python3 scripts/validate_po_contract.py --fixture small`

### Stop condition (hard fail)
If any contract check exceeds tolerance, STOP and fix before moving on.

Rollback
- `git revert <commit>`
- Restore DB from last trusted backup in `.claude/SESSION_LOG.md`

---

## 3) Phase I — Close the loop: PO dashboard must embed capital-protection gates

### Goal
PO output must never “look green” if it violates core capital-protection rules.

### Required rules (must be enforced or explicitly surfaced)
- 20% concentration rule (no single SKU > 20% of total deployed capital)
- ROIC gate thresholds (≥20% auto, 10–20% flagged, <10% review) as used in the system

### Deliverables
- PO dashboard data includes:
  - per-SKU capital share
  - ROIC action + explanation
  - “Blocked by cashflow preflight?” boolean + reason
- Tests:
  - synthetic fixture that triggers each rule (concentration breach, ROIC low, cashflow preflight fail)

### Gates
- Required gates (0.4)
- Plus: deterministic PO dashboard data export in CI/test environment

---

## 4) Phase J — StageCode rollout (parallelizable, but required before “more automation”)

### Goal
No production logic uses raw Kaspi state/status checks directly; StageCode is the only selection primitive.

### Deliverables
- Refactor remaining pipelines (order sync selection, waybills, alerts, translators) to StageCode
- Add a guard test/script:
  - simple grep-based check or static rule that fails CI if forbidden patterns exist
- Expand StageCode test coverage with real-world edge cases (cancel/return/sign_required)

### Gates
- Required gates (0.4)
- Plus: StageCode guard check must pass

---

## 5) Phase K — Write-side automation: Kaspi pricelist (dry-run → canary → publish)

### Goal
Automate price/stock/preorder publishing safely, with auditability and rollback.

### Phase K1 (dry-run only)
Deliverables:
- Module to generate deterministic Kaspi XML pricelist per store
- Validators:
  - schema/field validation
  - SKU uniqueness
  - price/stock/preorder bounds
  - XML escaping + UTF-8
- Diff report:
  - price/stock deltas vs previous published state (or previous generated snapshot)
- Tests:
  - deterministic XML output test
  - validator rejects invalid values
  - diff report correctness

Gates:
- Required gates (0.4)

### Phase K2 (controlled publish)
Deliverables:
- Publishing only when BOTH:
  - `ENABLE_KASPI_PRICELIST_PUBLISH=1`
  - `--publish` flag passed
- Allowlist rollout:
  - start with a small allowlist file of SKUs
- Rollback plan:
  - keep last-known-good XML snapshot; republish it as immediate rollback

Gates:
- Required gates (0.4)
- Plus: “publish disabled by default” test

---

## 6) Definition of done (this plan)
System is “autonomy-ready” (still human-approved writes) when:
1) PO contract tests are green on fixtures (Phase H)
2) PO dashboard surfaces capital-protection gates and blocks unsafe POs (Phase I)
3) StageCode is the only lifecycle selector across pipelines (Phase J)
4) Pricelist automation is safe in dry-run and publish is behind hard gates (Phase K)

Only after all are true:
- Consider “approval automation” (still not auto-buy) and broader rollouts.
