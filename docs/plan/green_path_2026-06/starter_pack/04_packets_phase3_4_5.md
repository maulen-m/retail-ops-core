# Packets — Phases 3, 4, 5

All inherit `00_README.md` common rules.

---

## PKT-PRICE (Fable 5 execution agent for floor economics + Codex 5.5 for plumbing; WA lease)

Fable-packet (per global protocol — judgment lane):
Title: Single floor source + vintage logging + leak stop + backlog re-measure
Project/repo: ~/Docs/Web_automation (+ AB floor docs)
Objective: G-PRICE-01..05 + G-WA-02 green.
Direction: Two satisfaction paths for G-PRICE-01 per YAML OD-003 — v7 ratification (needs G-FX-02 green: generate v7 CSV from Dim_sku_light_v7.md on fresh FX/landed-cost, repoint the 3 v6 consumers — apply_repricer_minmax_from_snapshots.py:835, web_auto/repricer_competitors.py:49, build_line52_market_decision_report.py:48 — retire v6) OR v6 explicit reaffirmation (FX deferred; no FX dependency). Floor rows moving >5% (YAML floor_change_review_threshold_pct) → wave-2 owner list at acceptance; proceed with unchanged rows. Then: vintage logging on every price write (max days since COGS/FX/floor/competitor; ≤7d required); refresh ALL WA pricing inputs before any apply (stock_snapshots/offers_book/pricelist snaps/external_db_truth — currently 77–114d stale, CN-043); kill the under-floor leak (CN-039: LINE52 sold at 7,999–8,130 TODAY vs floor 8,189); re-measure the 103-move backlog FRESH (discard the 2026-06-02 dry-run, CN-041) and disposition from the new scan.
Constraints: docs-before-code (owning floor doc updated first); rollback file staged before every upload (G-WA-02, verify_kaspi_pricelist_hash.py + WA inventory/verify_pricelist_snapshots_and_uploads.py); no price apply from stale inputs EVER (G-PRICE-04/05 are HARD).
Must-inspect: min_price_floor_35pct_by_sku_v6.csv; Dim_sku_light_v7.md; the 3 consumer scripts; repricer apply runbooks; CN-039/040/041/042/043.
Must-preserve: live watcher lanes (kaspi_marketing/repricer_items — they are healthy); existing upload/readback verification flow.
Return contract: floor decision record + consumer-repoint diff + first vintage-logged apply evidence + fresh backlog disposition + leak-stop verification (0 sub-floor sales trailing 7d).

---

## PKT-RELIST (Codex 5.5; S-effort)

/goal
Title: Dark-family relists, size-scoped
Repo: ~/Docs/Web_automation (+ AB read)
Branch/worktree: <RUNTIME>
Objective: G-DARK-01 green; G-DARK-02 measurement started.
Context: YAML OD-033 (default: relist RUSH_WHITE excluding L; T-SHIRT_BLACK incl. XL=10). DB offer table is stale (2026-05-03) — live offer fetch FIRST is the gate's own requirement. Stock numbers from the REBUILT snapshot (PKT-STOCK must be green).
Must-read: green_gates G-DARK-*; CN-054; offer/listing tooling in WA.
Allowed: offer fetch; size-scoped relist uploads with staged rollback; green_path_run/.
Forbidden: price changes beyond current approved prices (PKT-PRICE owns floors); reorders (auto-PO domain).
Write permission: APPLY_ALLOWED_AFTER_GATE.
Acceptance criteria: live fetch artifact; offers live for in-stock sizes only; first post-relist orders tracked; 30d recovery-slope measurement job scheduled (G-DARK-02).
Stop conditions: live fetch shows stock conflict vs rebuilt snapshot → park family + flag to PKT-STOCK.
Return contract: common + per-family relist evidence.

---

## PKT-LIQ (Fable 5 for tranche economics + Codex 5.5 execution; Opus review per tranche file)

Fable-packet:
Title: Liquidation — fresh register, tranche-1, ladder operations, envelope tranches
Project/repo: both (AB truth; WA price execution)
Objective: G-LIQ-01..04 + G-WA-01 + G-CASH-04 green.
Direction: (1) G-LIQ-01: fresh snapshot + register re-run + A–E re-segmentation (June movement flips membership — ROMBIK accelerated, IVORY exited; CN-035/033). (2) Tranche-1 per YAML OD-011: the 11-family/1,003-unit canonical set (CN-032; quote 1,387,464 goods-only basis), ladder T1→T3 per OD-005 depths/dwell, every row carrying tranche_id/owner_decision_id/floor_version/stock_confidence/rollback_price (G-LIQ-02 schema; OD-032 exception rows pre-listed if any). (3) Lead-store map BEFORE first upload (G-WA-01: one lead store per SKU/size; no shared-pool full exposure; own stores excluded from competitor matching). (4) Standing ops: weekly release velocity, escalation only on measured sell-through vs stop-rules (<3% → stop), T4/T5 PARKED in wave 1. (5) Envelope tranches per OD-018: cumulative ≤5,000,000 KZT goods-only EXCLUDING LINE51_WHITE; LINE51 = own tranche ONLY after its count (G-LIQ-04), sized post-count. (6) Proceeds held as cash per G-CASH-04 — zero redeployment while stock/cash/PPCH gates red.
Constraints: ladder envelope ≠ forecast (never project proceeds in owner-facing text); fresh inputs before every upload (G-PRICE-04); rollback file per upload (G-WA-02).
Must-inspect: dead_stock register derivation (audit build_gap_csvs.py); CN-029..035; ladder EXT-L01..06 via dispositions; the WA upload lanes.
Must-preserve: non-tranche prices; healthy watcher lanes; G-ORD-04.
Return contract: re-segmented register + tranche files (with the 5 required fields per row) + lead-store map + weekly velocity reports + escalation log + envelope ledger (cumulative vs cap).

---

## PKT-STOREFRONT (Codex 5.5; S-effort)

/goal
Title: MELVIS + 11KZ disposition execution + LINE31 standing spend-vs-stock cross-check
Repo: ~/Docs/Autonomous_business
Branch/worktree: <RUNTIME>
Objective: G-STORE-01 + G-LINE31-01 green.
Context: (1) Stores: YAML OD-027 (default: archive both — stop daily polling, mark ARCHIVED in configs/docs, preserve history; revisit after PPCH v1). 129/141 days dead, polled daily fetching zero (CN-055). If DEFER: keep polling + publish the monthly lost-opportunity line instead. (2) LINE31 standing gate: PKT-LINE31GUARD's day-0 cap is only the PREP — G-LINE31-01 itself needs a daily cross-check job joining campaign spend (watcher data) against per-size buyable stock from the REBUILT snapshot (requires G-STOCK-03 green): any spend-day attributed to a 0-stock size → violation logged + creative auto-pause per the OD-008 guard; resume rule = per-size stock confidence green.
Must-read: green_gates G-STORE-01 + G-LINE31-01; CN-055/056; YAML OD-027 + OD-008/020 params.
Allowed: sync config + store-status docs; the daily cross-check job (new script under the validators' conventions); green_path_run/.
Forbidden: deleting historical store data; marketplace-side store actions (none authorized); campaign changes beyond the OD-008 envelope.
Write permission: PATCH_ALLOWED.
Acceptance criteria: decision record + config state match YAML; sync log confirms behavior next cycle; cross-check job producing daily with 0 spend-vs-empty-size days standing; G-ORD-04 still green after.
Return contract: common + config diff + first cross-check report.

---

## PKT-OPS (Codex 5.5; S-effort)

/goal
Title: Incident KZT telemetry
Repo: ~/Docs/Autonomous_business
Branch/worktree: <RUNTIME>
Objective: G-OPS-01 standing.
Context: INEF-17 stays HYPOTHESIS until measured (CN-061). Placeholder rate per YAML OD-030 (default 5,000 KZT/h marked ASSUMED). Wire a mandatory per-incident line (minutes × rate, incident class) into the ops/incident log path; 30d collection before any ranking.
Write permission: PATCH_ALLOWED.
Acceptance criteria: incident-line schema live; first entries flowing; 30d report scheduled.
Return contract: common.

---

## PKT-POGOV (Codex 5.5; Opus review on the 7 tests)

/goal
Title: PO governance — stop-buy gates, governed-OFF, size priors rebuild, forecast loop
Repo: ~/Docs/Autonomous_business
Branch/worktree: <RUNTIME>
Objective: G-PO-01 (Phase 3) then G-PO-02..03 (Phase 4).
Context: auto-PO stays OFF per OD-009 — your job is to make OFF *governed*: encode the 6 stop-buy gates (frozen-cover >180d / size-overstock / return / PPCH / cash / ads) as checks that also advise MANUAL POs; record restart criteria. Then Phase 4: rebuild dim_size_probability per the EXT-S01 spec (availability-adjusted, return-penalized, profit-weighted kept demand + Bayesian shrinkage to category fallback; SUIT-61 + BERSERK added; kids separate ladder; LINE31 excluded from auto-PO), enforce EXT-S02 thresholds, run the 7 EXT-S03 validation tests incl. 30d backtest (the only historical accuracy test was MAPE 93.7%, CN-065 — beating it is necessary but NOT sufficient; threshold set at acceptance).
Must-read: PO_CONTRACT + PO_making_logic_v3 (binding docs); dim_size_probability schema; dispositions EXT-S01..03 + EXT-L05; CN-065.
Allowed: gate config + prior rebuild via governed paths; green_path_run/.
Forbidden: creating ANY PO draft; enabling any auto-PO execution path.
Write permission: PATCH_ALLOWED + APPLY_ALLOWED_AFTER_GATE (priors table).
Commands: `python3 scripts/validate_po_capital_protection.py`; `python3 scripts/validate_po_money_gate.py`; `python3 scripts/validate_po_contract.py`; `python3 scripts/validate_po_dashboard_invariants.py`; backtest harness per EXT-S03.
Acceptance criteria: 0 drafts; gates encoded + validators exit 0; priors rebuilt with 7/7 tests passing + signed-bias report; restart-criteria doc recorded with OD-009 ref.
Return contract: common + test results + prior-change report (old vs new by family/size, flagged if change > owner threshold).

---

## PKT-METRICS (Fable 5 spec + Codex 5.5 build)

Fable-packet:
Title: PPCH v1 + owner dashboard cadences + contribution + capital-hours
Project/repo: ~/Docs/Autonomous_business
Objective: G-MET-01..04 green.
Direction: Implement the 11-metric stack (EXT-M01..M11 via dispositions.csv) with PPCH v1 as headline: `720 × Σ(net_contribution_i) / Σ(capital_kzt_stage × hours_stage)` monthly with confidence bands; denominator-consistent convention (CN-037: capitalized-rows basis; the v0 18.92%-vs-19.33% ambiguity must never recur — state basis on every figure); v0.75 interim honest headline until v1's inputs are all green; v0 retired from owner surfaces. Dashboard cadences per G-MET-02 (daily: failures/cash confidence/sales+profit coverage/ad CRR/exceptions; weekly: frozen capital/release velocity/stock confidence/comeback; monthly: PPCH/forecast/PO review). Per-SKU net contribution daily after EOD (G-MET-03). Capital-hours-by-stage ledger (G-MET-04) from PO payments/receipts/ledger/lifecycle/returns/cash events.
Constraints: every metric publishes its basis + as-of + confidence; ceiling language on INEF-06-derived figures (0.92–1.03M/month is a CEILING, CN-038); no metric ships without its data-readiness gate green (else it publishes as PENDING with the blocking gate named).
Must-inspect: profit_per_capital_hour_v0.csv derivation; dispositions EXT-M01..M11; CN-036/037/038.
Return contract: metric specs + first published bundle + cadence schedule + convention doc.

---

## PKT-ACCEPT (Phase 5; orchestrator + Opus audit agent)

/goal
Title: Acceptance — scored matrix, deferred-queue resolution, waivers, final handoff
Repo: both (read) + workspace (write)
Branch/worktree: n/a
Objective: G-ACC-01 + final G-SCHED-04 scoring.
Context: Procedure per GREEN_STATE_GATE_MATRIX.md §6. This is the program's second owner touchpoint.
Implementation requirements: run every STANDING verify_cmd post-EOD on acceptance day; verify every POINT artifact; produce scoreboard.csv final (gate_id, measured_value, scored_state, evidence); ADVISORY-not-green → waiver list; walk DEFERRED_QUEUE.md (each item: resolved / re-dated / within-fallback, with KZT exposure); assemble the final handoff per plan §7 (incl. before/after headline table: cash divergence, margin-blind window, frozen book + released KZT, strict-gate items, alert skips); owner session: waivers + deferred items + wave-2 lists (floor changes >5%, T4/T5, LINE51 post-count results) + sign-off into the YAML (append-only).
Acceptance criteria: 100% HARD gates GREEN; every ADVISORY green or waived; queue clean; sign-off recorded.
Return contract: the final handoff document.
