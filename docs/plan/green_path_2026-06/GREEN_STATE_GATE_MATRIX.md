# Green-State Gate Matrix — the definition of 100% GREEN

Data: `green_gates.csv` (71 gates, 17 columns — 61 HARD / 10 ADVISORY). This document defines how to read and score it. Every number cited traces to `reconciliation/canonical_numbers.csv` (CN-*); every design choice to `reconciliation/dispositions.csv`.

## 1. The formula

**100% GREEN = every HARD gate GREEN + every ADVISORY gate GREEN-or-owner-WAIVED + the deferred-decisions queue empty or every item within its pre-stated fallback policy.**

Three principles:

1. **Green = governed, measured, decided — not necessarily automated or running.** A deliberately-OFF system is GREEN when it is off *behind recorded gates* (the template is G-PO-01: auto-PO stays off, stop-buy gates encoded, restart criteria + owner decision recorded). Likewise "archive MELVIS/11KZ" satisfies G-STORE-01: a recorded kill is green; silent decay is not.
2. **POINT_IN_TIME gates** are achieved once and evidenced by an artifact (backup manifest, backfill diff, count import log). **STANDING gates** carry a freshness SLA and must hold at acceptance time *and* be re-checkable any day after.
3. **Check-time semantics**: STANDING freshness gates are evaluated **after the nightly 21:00–21:10 run window** (strict preflight 21:00, residual checker 21:05). Checking mid-day reads yesterday's state and will flap. Acceptance scoring (G-ACC-01) runs post-EOD.

## 2. Gate census

| Phase | Gates | HARD | Domains |
|---|---|---|---|
| -1 Freeze/Backup | 4 (G-BCK-01..03, G-ORD-04) | 4 | backup, orders (protect the one live pipeline) |
| 0 Readiness | 6 (G-RDY-01..04, G-REPO-01..02) | 6 | readiness, repo_guards |
| 1 Infra/Alerting | 6 (G-SCHED-01..03, G-ALERT-01..02, G-BCK-04) | 6 | scheduler, alerting |
| 2 Truth restoration | 32 (orders G-ORD-01..03, profit G-COGS-01..04, fx 2, cash G-CASH-01..03, stock G-STOCK-01..05, returns G-RET-01..02, ads 3, quarantine 4 + G-SCHED-05, residuals 1, pricing G-PRICE-01/04, storefront G-LINE31-01, scheduler G-SCHED-04) | 29 | the core |
| 3 Business interventions | 16 (pricing G-PRICE-02/03/05, wa 2, relist 2 incl. G-DARK-02, returns G-RET-03, liquidation G-LIQ-01..04 + G-CASH-04, storefront G-STORE-01, ops 1, po G-PO-01) | 13 | actions on restored truth |
| 4 Structural loops | 6 (metrics 4, po_gov 2) | 2 | PPCH v1, priors, forecast |
| 5 Acceptance | 1 (G-ACC-01) | 1 | the close |

Totals: **71 gates, 61 HARD, 10 ADVISORY.** (The CSV is authoritative; G-BCK-04 and G-SCHED-04/05 straddle phases by design: created in one phase, converging in another. G-STOCK-05 and G-PRICE-05 are HARD per QA-2: the confidence score is a control other HARD lanes consume, and "no apply from stale dry-runs" guards a −135,728 KZT/unit cut backlog.)

**Phase -1 protective action (not a gate)**: the LINE31 ads pause/cap (OD-008) executes on day 0, before backup — it is a reversible EXTERNAL action (ads console), not a repo/DB write, pre-authorized as its own envelope with rollback RB-ADS. The backup-first rule (G-BCK-01) governs repo/DB/workbook/config writes; it does not delay this bleeding-stopper. The STANDING gate G-LINE31-01 (spend-vs-stock cross-check) still lands in Phase 2 when stock truth exists.

## 3. Conventions

- **verify_cmd** uses only (a) the 130-script validator inventory confirmed on disk 2026-06-12 (CN-053; e.g. `validate_order_entries_freshness.py`, `validate_cogs_completeness_by_month.py`, `validate_returns_economics_audit.py`, `validate_ads_spend_reality.py`, `validate_scheduler_heartbeat.py`, `validate_ledger.py`, `validate_cashflow_invariants.py`), (b) read-only sqlite queries (`ro-query:` prefix; always `file:...?mode=ro`), (c) artifact inspections (`artifact:` prefix), (d) `launchctl` read-only queries. The expert's garbled §12 command block was never copied (DEF-01). **Script existence is verified; exact pass/fail semantics of each validator are confirmed by the executing agent at workstream start** — if a validator's actual scope differs from the gate's intent, the agent records the delta in the run log and substitutes the correct check rather than forcing the named one.
- **current_state** is as-of 2026-06-12 ~19:30 +05 (the live sweep). RED = not satisfied; YELLOW = partially (e.g. clamps dormant but ungoverned); GREEN = satisfied (exactly one today: G-ORD-04 header ingestion); UNKNOWN = never measured.
- **owner_waivable=yes** means the owner may, at acceptance, accept the gate's absence with a recorded waiver (mostly ADVISORY metrics/cadences). HARD gates with `owner_waivable=no` cannot be waived — they are the program.
- **rollback_ref** points to the rollback map in the master plan (RB-GIT, RB-DB, RB-WORKBOOK, RB-PLIST, RB-ENV, RB-PRICE, RB-ADS, RB-CASH-ANCHOR, RB-STOCK-ANCHOR) — adopted from expert §12 (EXT-V02) plus the Phase-0 rehearsal requirement (G-RDY-02).
- **Re-baseline rule**: `current_state` values and all CN figures are *planning* inputs. Every workstream packet re-derives its own input numbers (read-only) at execution start; gates are scored on execution-time values. The live sweep proved why: tranche membership flipped twice in 48h (CN-033/035).
- **DEFER-safe pricing path**: G-PRICE-01 is satisfiable two ways — v7 ratification (requires G-FX-02 green) or explicit v6 reaffirmation (no FX dependency). If the owner defers OD-013/OD-003, the leak-stop (G-PRICE-03) and the liquidation chain proceed on the reaffirmed v6 basis exactly as the decision pack's fallbacks promise; only the FX lane itself (G-FX-01/02) parks.

## 4. Dependency spine (matches the master plan)

```
G-BCK-01..03 ──► G-RDY-01..04 ──► G-SCHED-01 ──► G-ALERT-01/02, G-SCHED-02/03, G-BCK-04
                                      │
        ┌─────────────────────────────┴──── Phase 2 fan-out (parallel lanes) ────────────┐
        │ G-ORD-01..03 (lines/status)   G-COGS-01..04 (profit)   G-FX-01/02 ──► G-CASH-01..03
        │ G-RET-01/02 (returns)         G-ADS-01..03 (ads)       G-QUAR-01..04  G-RESID-01
        │ G-STOCK-01 ──► G-STOCK-02 ──► G-STOCK-03 ──► G-STOCK-04/05   (strict order: INBOUND → counts → snapshot → clamps)
        │ G-PRICE-04 (input refresh)    G-LINE31-01 (spend guard — early, protects cash now)
        └──────────────────────────────────────┬──────────────────────────────────────────┘
                                               ▼
    Phase 3: G-PRICE-01..03/05, G-WA-01/02, G-DARK-01/02, G-LIQ-01──►02──►03 (+G-LIQ-04 LINE51 block, G-CASH-04), G-STORE-01, G-OPS-01, G-PO-01
                                               ▼
    Phase 4: G-PO-02/03, G-MET-01..04          ▼
    Phase 5: G-SCHED-04 (strict gate 0 items) + G-ACC-01 (acceptance)
```

## 5. What turns the 65.1M / 13.4M / 18.9M headlines off

- The **65,144,687.12 KZT cash fiction** (CN-012) dies at G-CASH-01/02 (fresh anchor + rebuilt events + weekly cadence).
- The **13,357,890–17,269,630 KZT frozen book** (CN-030/031) becomes actionable at G-LIQ-01..03 and *measured* by release velocity (EXT-M04); the first 1,387,464 KZT (CN-032) needs only G-LIQ-01/02 after the stock+floor chains.
- The **18,853,031 KZT margin-blind window growing 225k/day** (CN-026) stops growing at G-COGS-01 and is repaired by G-COGS-02/04.
- The **+35/day strict-gate degradation** (CN-051) reverses at G-RESID-01 (132 items) + G-QUAR-01 (18 items) and lands at zero in G-SCHED-04.
- The **silent-failure regime** (CN-048..051) ends at G-ALERT-01/02 + G-SCHED-01..03 — the cheapest gates in the matrix and the precondition for trusting everything else.

## 6. Acceptance scoring procedure (consumed by G-ACC-01)

1. Run every STANDING verify_cmd post-EOD on the acceptance day; record exit codes/values.
2. Verify every POINT_IN_TIME gate's artifact exists and matches its `expected`.
3. Produce the scored matrix (this CSV + two columns: `measured_value`, `scored_state`).
4. List ADVISORY gates not green → owner waiver decisions (recorded in the decision YAML).
5. Review `DEFERRED_QUEUE.md`: every parked item resolved, re-dated, or within fallback.
6. Owner signs; the program closes with the final handoff bundle (master plan §closeout).
