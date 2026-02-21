# PLAN_2_WEEK_EXECUTION_BOARD_A_C_B_V3_POST_PROMOTION_2026-02-21

## Purpose
This plan turns TASK-392’s shipped contracts (inbound mismatch, offer linkage, profit realism, ads sidecar profit_after_ads, shipment safety, stock snapshot truth cutover) into operationally “always-on” invariants with minimal human time, and then advances toward PO money-gate automation and (optionally) a tightly controlled write-side canary. Reliability stance is fail-closed: if truth is unknown, we stop and surface it.

---

## Canonical References (do not duplicate; link only)
- Promotion evidence: `docs/OPS_ROLLOUT_EVIDENCE_TASK_392_ACB_V2_PROMOTION_2026-02-21.md`
- Current board plan (implemented): `docs/PLAN_2_WEEK_EXECUTION_BOARD_A_C_B_V2_2026-02-21.md`
- Stock truth anchor: `config/anchors/STOCK_SNAPSHOT_LATEST.xlsx`
- Inbound anchor: `config/anchors/INBOUND_CALENDAR_LATEST.xlsx`
- Ads contracts: `docs/marketing/ADS_SIDE_CAR_CONTRACT.md`, `docs/marketing/PROFIT_AFTER_ADS_CONTRACT.md`
- Shipment contracts: `docs/ops/SHIPMENT_HEALTH_STATES.md`, `docs/ops/SHIPMENT_PREFLIGHT.md`
- Profit realism contract: `docs/profit/PROFIT_REALISM_CONTRACT.md`
- Offer linkage contract: `docs/offer/offer_linkage_contract.md`

---

## Global Constraints
- Fail-closed everywhere: any missing/stale/invalid truth => STOP-THE-LINE.
- No absolute personal paths in active docs (use repo-relative paths or `<REPO_PATH>` placeholders).
- No DB/network “apply” writes in any phase unless explicitly called out with a separate “write canary” phase and dual-gating.
- Prefer a single sequential workstream in one branch/worktree.

---

## Phases

### P0_POST_PROMOTION_STABILIZATION
**Goal (measurable)**
- Confirm stability of the promoted contracts by producing a short “stabilization evidence note” after repeated green runs (no regressions).

**Inputs**
- `docs/OPS_ROLLOUT_EVIDENCE_TASK_392_ACB_V2_PROMOTION_2026-02-21.md`
- CI runs referenced there
- `exports/validation/board_2w_2026-02-21/**` (referenced, not embedded)

**Outputs**
- `docs/OPS_ROLLOUT_EVIDENCE_TASK_392_STABILIZATION_2026-02-23.md` (date can vary; use actual)
- `.claude/PROGRESS.md` updated with “stabilization complete” checkpoint (no premature “done”)

**Definition of Done**
- Accepted as done only when:
  1) Evidence doc exists and contains: (a) links/pointers to ≥3 consecutive green gate runs, (b) any observed flaky risks + mitigations, (c) rollback + minimum recheck.
  2) No new TBD/TODO placeholders remain in the evidence doc.

**Validation/Gates**
- Must record PASS evidence pointers for:
  - `python3 scripts/validate_params.py --strict`
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
  - `python3 scripts/run_contract_suite.py --fixture small`
  - `python3 scripts/validate_single_truth_system.py`
  - `bash scripts/lint_docs.sh`
  - `bash scripts/check_no_db_tracked.sh`
  - stop-line checks: validate-only scheduler + anchor health + ops_status + shipment preflight

**Rollback / backout**
- Revert only the stabilization evidence doc commit (docs-only) if it causes doc lint issues.

**Stop-the-line criteria**
- Any gate above fails OR evidence cannot be reproduced deterministically.

---

### P1_STOCK_SNAPSHOT_GOVERNANCE
**Goal (measurable)**
- Make `STOCK_SNAPSHOT_LATEST.xlsx` a first-class ops anchor with explicit freshness + update procedures so it never silently drifts.

**Inputs**
- `config/anchors/STOCK_SNAPSHOT_LATEST.xlsx`
- `scripts/check_anchor_health.py` (current behavior)
- `docs/DAILY_SOP.md` (operator flow)

**Outputs**
- `docs/ops/STOCK_SNAPSHOT_RUNBOOK.md`
- Updates to:
  - `config/anchors/README.md` (document stock snapshot anchor + thresholds + update loop)
  - `docs/DAILY_SOP.md` (explicit operator step + how to verify freshness)
- If needed: contract tests that fail if stock anchor is missing/broken/stale in headless fixtures

**Definition of Done**
- Accepted as done only when:
  1) Runbook exists and includes “how to update”, “how to verify”, and “what happens when stale” (fail-closed expectations).
  2) Anchor health tooling fails closed on broken/missing stock anchor (in both repo-root and `/tmp` cwd execution contexts).
  3) CI/headless fixture parity is protected by a contract test (no regressions).

**Validation/Gates**
- Same global gates as P0, plus explicit proof that:
  - stock anchor is validated by anchor-health (or equivalent gate) and fails closed when missing/broken.

**Rollback / backout**
- Revert doc/test changes if they introduce false-red without adding safety; retain fail-closed semantics.

**Stop-the-line criteria**
- Any discovered behavior that allows “stock snapshot present but semantically stale” to pass without a clear status signal.

---

### P2_ADS_SIDECAR_OPS_INTEGRATION_READ_ONLY
**Goal (measurable)**
- Make ads sidecar “operationally present” with near-zero human time:
  - Either profit_after_ads is publishable with freshness proof, or it is explicitly N/A with a reason.

**Inputs**
- `docs/marketing/ADS_SIDE_CAR_CONTRACT.md`
- `docs/marketing/PROFIT_AFTER_ADS_CONTRACT.md`
- `scripts/sync_ads_sidecar.py`
- `scripts/build_profit_after_ads.py`
- `scripts/generate_business_insides.py`

**Outputs**
- `docs/marketing/ADS_SIDECAR_OPS_RUNBOOK.md`
- `docs/OPS_ROLLOUT_EVIDENCE_ADS_SIDECAR_OPS_2026-02-xx.md`
- (Optional) Add an ops_status section/output describing ads sidecar status if not already present.

**Definition of Done**
- Accepted as done only when:
  1) Runbook exists and includes: source-of-truth for ads DB path(s), freshness thresholds, failure modes, and how profit_after_ads gating behaves.
  2) Evidence shows both:
     - a GREEN case (fresh ads sidecar => profit_after_ads publishable)
     - a RED case (stale/missing => profit_after_ads N/A) with correct fail-closed semantics.
  3) No write-side ads actions are enabled by default.

**Validation/Gates**
- Must include proofs for:
  - strict validators still PASS with ads sidecar missing (but profit_after_ads is gated to N/A).
  - strict validators PASS with ads sidecar present and fresh.

**Rollback / backout**
- Revert scheduling/ops wiring first; keep contracts in place.

**Stop-the-line criteria**
- Any path that allows profit_after_ads publication without freshness proof.

---

### P3_OFFER_LINKAGE_STRICT_CUTOVER
**Goal (measurable)**
- Transition from “strict available” to “strict enforced” on offer linkage, with a controlled cutover plan and an escape hatch.

**Inputs**
- `docs/offer/offer_linkage_contract.md`
- `scripts/validate_offer_linkage.py`
- Current strict chain wiring in `scripts/validate_params.py`

**Outputs**
- `docs/offer/OFFER_LINKAGE_STRICT_CUTOVER_PLAN.md`
- A decision record in `.claude/DECISIONS.md` describing:
  - when strict becomes default
  - what the temporary bypass is (if any) and its expiry

**Definition of Done**
- Accepted as done only when:
  1) Cutover plan exists with a clear date/condition for strict-by-default.
  2) The system fails closed when linkage gaps exceed the defined threshold under default ops runs.
  3) Any bypass is explicit, logged, and time-bounded.

**Validation/Gates**
- Must demonstrate:
  - strict mode blocks when linkage invalid
  - non-strict mode cannot accidentally be used in production paths without explicit operator intent

**Rollback / backout**
- Revert default strict setting; keep validator and reporting.

**Stop-the-line criteria**
- Any “silent non-strict” execution path in production scheduler flows.

---

### P4_PO_MONEY_GATE_AUTOMATION
**Goal (measurable)**
- Define and enforce a “PO money gate”: PO creation/publication is blocked unless inputs are proven consistent (inbound + stock snapshot + linkage + COGS integrity).

**Inputs**
- Inbound validator outputs
- Stock snapshot anchor
- Offer linkage validator
- Profit/COGS integrity validators
- PO generation scripts (existing PO pipeline)

**Outputs**
- `docs/po/PO_MONEY_GATE_CONTRACT.md`
- Contract tests that enforce the gate and prevent bypass
- Evidence doc: `docs/OPS_ROLLOUT_EVIDENCE_PO_MONEY_GATE_2026-02-xx.md`

**Definition of Done**
- Accepted as done only when:
  1) Contract clearly defines: required green inputs, failure modes, and what is blocked.
  2) At least one fail-first test shows PO generation is blocked when any prerequisite is red.
  3) A green run shows PO generation proceeds only with all prerequisites green.

**Validation/Gates**
- Full global gate chain + fail-first evidence artifacts.

**Rollback / backout**
- Revert gate enforcement; keep validators and reporting.

**Stop-the-line criteria**
- Any discovered bypass that allows PO decisions while data is known-invalid.

---

### P5_WRITE_SIDE_CANARY_OPTIONAL (HIGH RISK; only after P0–P4 are stable)
**Goal (measurable)**
- Prepare (not necessarily execute) a tightly controlled, reversible canary write plan for a single write path with full audit.

**Inputs**
- Existing write gating contracts/manifests (write-side gating validator)
- Target write path runbook(s)

**Outputs**
- `docs/ops/WRITE_CANARY_PLAN_V1.md`
- A manifest update proposal + tests that guarantee dual-gate behavior

**Definition of Done**
- Accepted as done only when:
  1) Canary plan includes: scope cap, rollback, audit, alerting, and “kill switch”.
  2) Write remains OFF by default; enabling requires explicit double gating.

**Validation/Gates**
- Contract tests for gating behavior + dry-run execution evidence only.

**Rollback / backout**
- Revert manifest/docs changes if any risk of accidental apply remains.

**Stop-the-line criteria**
- Any path enabling writes without explicit operator intent.

---

## If attachments are missing (assumptions policy)
- If any referenced file/path is missing:
  1) STOP and log in `.claude/ISSUES.md` with exact missing path(s).
  2) Add a minimal reproduction note (what command/test/doc referenced it).
  3) Proceed only if a safe fallback exists that preserves fail-closed behavior; otherwise block the phase.