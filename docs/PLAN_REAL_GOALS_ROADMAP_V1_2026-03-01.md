# PLAN_REAL_GOALS_ROADMAP_V1_2026-03-01

## Purpose
Shift from “truth repair build mode” to “profit + capital allocation mode” with strict fail-closed governance.
Truth alignment (ocean-drop + BI) is now baseline; next work must directly unlock:
1) decision-grade economics (COGS/profit/ads),
2) autonomous PO proposals with capital protection,
3) low-human ops autopilot,
4) growth levers only after economics is trusted.


Real goals now (North Star hierarchy)
Goal 1 — Decision-grade economics (Profit you can trust)

You already have units/revenue integrity. Next is making COGS / gross profit / profit-after-ads reliable enough to steer buying and pricing.

Success definition:

BUSINESS_INSIDES emits profit metrics for the non-volatile window with:

0 missing SKU identity

0 missing costs for eligible SKUs

explicit return/volatility policy (fail-closed if violated)

No “profit inflation by N/A.”

Why it’s #1:

Without economics, the system can be perfectly correct and still make the wrong PO decisions.

Goal 2 — Autonomous capital allocation (PO engine as a machine)

Turn “truth” into “buy decisions” with Master Rules + PO logic, with strict capital protection:

Success definition:

Every proposed PO has:

ROIC (computed from rules doc)

capital-at-risk (worst-case COGS exposure)

untested SKU caps enforced

liquidation/exit plan (sell-through horizon)

reversibility/rollback path

And the system can run in:

Validate-only mode daily (no writes)

Apply mode only through gated canaries + approvals

Goal 3 — Ops autopilot (low human time)

The machine runs daily with <5% of your attention:

Success definition:

Daily run produces GREEN/RED status artifact

Exceptions are explicit, deduped, and contain “next action”

Missed scheduler runs are detected same day

No manual spreadsheet fixing required for routine days

Goal 4 — Growth levers (once profit truth exists)

Only after economics is reliable:

pricing strategy

ads spend allocation by ROAS

assortment expansion (new SKUs) with tight capital caps

store expansion / category growth

Higher-level roadmap (boards that matter now)

Think of the system as 3 engines:

Truth Engine (done enough)

Economics Engine (next)

Capital Engine (PO + cashflow + inventory) (after economics)

Roadmap tree (broad scope, but sequenced to reduce risk)
R0: Freeze & Operate Mode [Owner: Human + Coding Agent] {No new boards until 14-day streak green}
|
R1: Economics Truth (COGS/Profit/Ads/Returns policy) [Coding Agent] {business_insides_economics_ready STRICT PASS}
|
R2: Capital Engine (Autonomous PO proposals + risk gates) [Coding Agent] {PO_CONTRACT strict + ROIC + caps PASS}
|
R3: Execution Engine (Write canaries -> bounded live writes) [Coding Agent] {Canary ladder green; rollback proven}
|
R4: Growth Engine (pricing/ads/assortment) [Human sets targets; Coding Agent implements] {profit deltas validated}
|
R5: Scale & Governance (release cadence + audits + oracle packs) [Human + Coding Agent] {monthly audit passes}
The most efficient strategic shift

You need to stop “building for completeness” and start “operating with gates.”

New rule:

No new feature work unless it increases profit, reduces stockouts, reduces dead inventory, or reduces your daily ops minutes.

Everything else is noise.

Concrete operating cadence:

Daily: strict run → GREEN/RED → act only on exceptions

Weekly: one health scorecard review + one PO review

Monthly: oracle pack audit + cost mapping cleanup + release board


## Current Baseline (evidence-backed)
Board: ocean-drop alignment + statusdate ingestion is complete and gated GREEN.
- Branch/work: codex/TASK-ocean-drop-alignment-statusdate-v1
- Phase boundary SHAs:
  - 194ab93 — P0–P2 strict BI anchoring + API/UI split + UI tooling
  - 5b2dbec — P3–P5 merge/ingest/alignment validators + doctor/H5 wiring
  - 89e9031 — P6 closure fixes
  - 02e08f0 — DB schema snapshots
  - bf7ca40 — final evidence stamp
- Evidence (GREEN):
  - exports/validation/board_ocean_drop_alignment_statusdate_2026-03-01/full_gates_green_final.md
  - exports/validation/business_insides_ocean_drop_alignment/2026-02-26/alignment_report.json
  - exports/validation/archive_pack_integrity/ui/2026-02-26/integrity_report.json
  - exports/validation/sales_ocean_drop_parity/2026-02-26/parity_report.json
  - exports/daily/2026-02-26/sales_truth_drift_report.json
  - exports/diagnostics/2026-02-26/system_health.json
- Oracle baseline:
  - ~/Docs/Oracle/Autonomous_business/2026-03-01/124312_TASK-000_ocean-drop-alignment-statusdate-v1-primary-db-schemas.md

## Phase List

### R0 — Freeze & Operate Mode (stop building unless ROI)
**Goal**
- Prevent “endless build churn” and force ROI discipline.

**Inputs**
- Current strict chain + proving runner

**Outputs**
- Docs:
  - docs/ops/RELEASE_POLICY_OPERATE_MODE.md (NEW)
- Rule:
  - any change must declare ROI target + new gate + rollback

**Definition of Done**
Accepted as done only when:
- Release policy doc exists.
- Any new PR must include:
  - measurable ROI claim (profit/time/risk)
  - gate transcript path
  - rollback plan

**Validation/Gates**
- lint_docs + validate_single_truth_system remain mandatory for any change.

**Rollback**
- Revert policy doc change if needed (no runtime impact).

**Stop-the-line**
- New features without ROI and gates.

---

### R1 — Economics Truth (Decision-grade profit)
**Goal**
- BUSINESS_INSIDES economics becomes decision-grade for non-volatile window.

**Inputs**
- Sales truth views (already aligned)
- Cost sources (DB dimensions / ledgers)
- Ads spend source (if used)
- Return/volatility policy (explicit)

**Outputs**
- Validator:
  - scripts/validate_business_insides_economics_ready.py (extend if needed)
- Contract doc:
  - docs/validation/BUSINESS_INSIDES_ECONOMICS_PUBLICATION_CONTRACT.md (NEW)
- Artifacts:
  - exports/validation/business_insides_economics/<AS_OF>/economics_ready_report.json/.md

**Definition of Done**
Accepted as done only when:
- Profit metrics are published ONLY for eligible days (per contract).
- Nonvolatile days have:
  - 0 missing sku_key
  - 0 missing unit_cost for eligible SKUs
- Any missing economics produces RED + explicit missing SKU list.

**Validation/Gates**
- python3 scripts/validate_business_insides_economics_ready.py --as-of <AS_OF> --strict
- Full strict chain transcript captured.

**Rollback**
- Revert contract/validator.
- Keep profit locked if uncertain (safe default).

**Stop-the-line**
- Any profit published with missing costs/identity.
- Any formula change without updating docs/inventory/Master_Inventory_Rules_v8.md first.

---

### R2 — Capital Engine (Autonomous PO proposals)
**Goal**
- Generate PO proposals with strict ROIC + capital protection gates.

**Inputs**
- docs/inventory/Master_Inventory_Rules_v8.md (canonical formulas/caps)
- protocol/active/PO_making_logic_v2.md (algorithm; must conform to v8)
- Inventory truth + lead times + cash constraints
- Economics outputs from R1

**Outputs**
- scripts/generate_po_proposals.py (NEW or extend existing)
- exports/po/<AS_OF>/po_proposals.json + .md
- Validator:
  - scripts/validate_po_capital_protection.py (NEW)
- Evidence transcript under exports/validation/...

**Definition of Done**
Accepted as done only when:
- Every proposed PO line includes:
  - computed ROIC
  - capital at risk
  - untested SKU cap compliance
  - exit/liquidation horizon
- Validator fails closed on any missing input.

**Validation/Gates**
- python3 scripts/validate_po_capital_protection.py --as-of <AS_OF> --strict
- python3 scripts/run_contract_suite.py --fixture small (if applicable)
- Full strict chain transcript.

**Rollback**
- PO proposals are read-only artifacts (no writes); rollback is N/A.

**Stop-the-line**
- Any PO proposal without ROIC/caps/exit path.

---

### R3 — Execution Engine (bounded writes via canaries)
**Goal**
- Expand from validate-only to safe staged writes (DB then API), reversible.

**Inputs**
- Existing write-canary framework/runbooks
- Stable proving streak (R4)

**Outputs**
- Canary ladder plan doc + scripts:
  - docs/ops/WRITE_CANARY_LADDER_V1.md (NEW)
  - scripts/run_write_canary_<domain>.py (NEW as needed)
- Rollback artifacts standard (backup + manifest)

**Definition of Done**
Accepted as done only when:
- Every write path has:
  - dry-run default
  - explicit apply gate
  - backup + manifest
  - rollback rehearsed

**Validation/Gates**
- Canaries PASS on 7 consecutive days before promotion.

**Rollback**
- Restore DB backups; revert commits.

**Stop-the-line**
- Any write without rollback story.

---

### R4 — Proving streak (operate the machine)
**Goal**
- 14 consecutive GREEN days in strict mode.

**Inputs**
- scripts/run_h5_proving_day.py
- scripts/validate_h5_artifact_set.py
- New economics and PO gates

**Outputs**
- exports/validation/h5_proving_streak/<END_DAY>/streak_report.json/.md

**Definition of Done**
Accepted as done only when:
- streak validator PASS for 14 days
- no decision outputs on RED days

**Validation/Gates**
- daily strict runner + artifact validator + streak validator

**Rollback**
- N/A (streak is observational). Restart streak after fixes.

**Stop-the-line**
- Any day produces decision-grade output while RED.

---

### R5 — Growth engine (only after economics truth)
**Goal**
- Improve profit via pricing/ads/assortment decisions backed by economics truth.

**Inputs**
- Decision-grade profit (R1)
- PO discipline (R2)

**Outputs**
- experiments/ reports with measured deltas
- weekly health scorecard includes ROI deltas

**Definition of Done**
Accepted as done only when:
- change has measurable profit delta and passes truth gates

**Stop-the-line**
- growth changes without economics truth.

## If attachments are missing (assumptions policy)
- Missing required inputs => FAIL CLOSED and emit missing_inputs artifact.
- Never “skip and still green.”