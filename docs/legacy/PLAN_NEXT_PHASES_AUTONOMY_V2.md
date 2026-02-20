# PLAN_NEXT_PHASES_AUTONOMY_V2 (Post‑V4)
Status: PROPOSED
Scope: Kaspi-only. Builds on: PLAN_POST_V4_AUTONOMOUS_PO_AND_WRITE_SIDE_AUTOMATION_V1.md.

## Non-negotiables (carry forward)
- Truth ladder: v8 formulas → PO logic → V16 schema → architecture. Do not duplicate formulas.  (see docs/00_START_HERE.md)  :contentReference[oaicite:7]{index=7}
- Tests FIRST: tests must fail before code changes; then minimal fix; then run gates.
- Write-side is OFF by default: env flag + CLI flag + allowlist + rollback; tested.
- Parallel agent work: ignore unrelated repo changes, keep the same branch. All agents must work in same repo main worktree, same branch. 
- Required gates (every phase):
  - python3 scripts/validate_params.py --strict
  - pytest -q
  - scripts/lint_docs.sh
  - scripts/check_no_db_tracked.sh
  - (If cashflow touched) python3 scripts/validate_cashflow_invariants.py
  - (If cashflow touched) python3 scripts/validate_inventory_cost_drift.py
  - (If cashflow touched) ENABLE_CASHFLOW_WRITE=1 python3 scripts/run_end_of_day.py --verbose

---

## Phase L — “Always-green” validation environment (CI-grade locally)
Goal: Gates fail only for real regressions, not missing tables/data.
Problem: Some tests can still fail in fresh worktrees without a populated DB; this is operationally dangerous.

Deliverables
1) Deterministic fixture DBs for:
   - core PO contract runner
   - StageCode + waybill selection
   - transfer_ledger invariants (minimal)
2) One command to run “the full contract suite” on fixtures:
   - python3 scripts/run_contract_suite.py --fixture small
3) Tests:
   - assert fixture DB includes required tables referenced by tests
   - assert contract runner returns deterministic outputs

Success criteria (verifiable)
- Running the contract suite on a clean clone yields 100% green tests with no external secrets.
- Any missing-table condition is caught by a dedicated “fixture completeness” test.

---

## Phase M — Kaspi Pricelist: production hosting + canary rollout
Goal: Fully automatic, safe price/stock/preorder sync (still gated; reversible).

Deliverables
1) Hosting deploy (pick one):
   - S3+CloudFront (recommended) OR VPS nginx with Let’s Encrypt.
2) scripts/deploy_kaspi_pricelist.py:
   - uploads XML to HTTPS path per store
   - writes last-known-good backup before overwrite
3) Health checks:
   - script that verifies the HTTPS URL is reachable and content is valid XML
   - script that verifies “published file == locally generated hash”
4) Tests:
   - publish deploy is blocked unless ENABLE_KASPI_PRICELIST_PUBLISH=1 AND --publish
   - deploy writes backup first; rollback republish works

Rollout (strict)
- Stage 1: UNIVERSAL allowlist (top N)
- Stage 2: UNIVERSAL full active allowlist export
- Stage 3: STOREB, ACMEWEAR

---

## Phase N — StageCode “no raw state/status anywhere” closure
Goal: Remove lifecycle ambiguity permanently.

Deliverables
1) Migrate any remaining selection paths to StageCode.
2) Harden StageCode tests with edge-case fixtures:
   - cancels, returns, sign-required, delayed courier handover
3) Enforce a guard in gates:
   - forbid raw state/status comparisons in pipeline scripts (allow only StageCode).

Success criteria (verifiable)
- Guard test passes.
- No production selection code branches on raw (state,status) directly.

---

## Phase O — Kaspi enrichment expansion (optional, behind flags)
Goal: Increase correctness for multi-line orders and product metadata without destabilizing sync.
Reference: KASPI_API_INTEGRATION_GAP_PLAN.md.  :contentReference[oaicite:8]{index=8}

Deliverables
- Add missing endpoints (Q7/Q8/Q9/Q11) and cache tables; idempotent inserts.
- Keep enrichment default OFF; fail-open; rate-limit; per-store rollout.
- Tests cover:
  - idempotency
  - cache hit behavior
  - “enrichment failure does not break base sync”

---

## Phase P — “Zero-owner daily ops” (optional, highest owner-time ROI)
Goal: Eliminate Google Sheets + manual PDF bundling; create a packaging station UI.

Deliverables
- Local LAN web UI served from Mac:
  - call queue → size input → “Done”
  - strict validation: cannot complete without call outcome
- Auto-trigger at “all done”:
  - waybill build + deterministic bundle ordering
- Packaging station mode on Windows:
  - show one order → auto-print label → Done → next
- Tests:
  - state machine tests (pending-size → ready-to-pack → packed)
  - deadline tests (18:30 cutoff behavior)

---

## Definition of Done (autonomy v2)
- L: clean-clone contract suite is green (fixture-complete)
- M: pricelist hosting + canary deployed; rollback proven
- N: StageCode everywhere + guard enforced
- O/P: optional, but recommended for ROI on owner time