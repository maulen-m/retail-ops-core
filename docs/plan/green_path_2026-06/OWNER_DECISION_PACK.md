# Owner Decision Pack — the single sitting before implementation

**Purpose**: one 60–90 minute session. You answer 30 decisions (most by accepting the recommended default) and hand over 4 data items. After this session, implementation runs agent-side to final acceptance with **zero mid-flight questions** — anything unforeseen resolves by the policies you set here, or parks in a deferred queue without blocking other work, and comes back to you only at acceptance.

**How to answer**: each decision takes one of three answers — `RECOMMENDED` (accept the default as written), `ALT-n` (a listed alternative), or `DEFER` (the pre-stated fallback applies automatically). An unanswered decision auto-records as DEFER + fallback, so the session cannot leave a blocking hole. Answers are recorded in `OWNER_DECISIONS_RECORDED.yaml` (machine-readable; agents consume ONLY that file, never this prose).

**Fast path**: answering "RECOMMENDED on everything + the 4 data drops" is a coherent, sequencing-safe package — verified as a set (the FX check precedes v7 ratification precedes any tranche pricing; INBOUND booking precedes count import precedes clearance; backup precedes everything). Estimated fast-path time: ~40 minutes, dominated by the data drops.

**What you're buying**: the decay is priced. Every day of delay currently costs ≈225,000 KZT of new margin-blind revenue (CN-026), ~25 more COGS-less completions (CN-025), +35 strict-gate failure items (CN-051), and continued ad spend against sizes the book says are empty (CN-056). The frozen book (13.36–17.27M KZT, CN-030/031) earns nothing while it waits.

**Decision dependency graph**:

```
A1 backup scope ─► everything
A3 freeze window ─► Phase -1 execution
B1 bank snapshot + C2 FX policy ─► cash anchor (G-CASH-01)
C2 FX ─► C1 v7 ratification ─► D-section tranche pricing + leak stop
B2 count protocol ─► stock truth (G-STOCK-02) ─► D6 envelope + the separate LINE51 tranche (outside the envelope cap)
C5 EOD first-apply ─► profit truth chain
D8 LINE31 cap ─► immediate (protects cash now, before Phase 2)
D2 auto-PO stays off ─► terminal (nothing depends on it; it depends on everything)
```

---

## SECTION A — SAFETY AUTHORITY (4 decisions; no DEFER allowed — these gate the program itself)

### OD-001 (A1) — Backup and clone scope
**Question**: Approve full Phase -1 backup scope before any write?
**Context**: No governed backup exists. An ad-hoc `app.db` backup from today (CN-059) proves the habit exists but isn't restore-tested, manifested, or complete. The DB is hot (order ingestion writes daily — the one alive pipeline, CN-001).
**RECOMMENDED**: Yes — full scope: both repos (git state + untracked operational files), all SQLite DBs **via `sqlite3 .backup` online method** (never file-copy of a hot WAL DB), workbooks, launchd plists, configs, WA runtime/watcher DBs/price snapshots, exports/logs; secrets backed up **locally only** with a redacted manifest; one restore test per backup class before any write (G-BCK-01/02).
**Alternatives**: ALT-1 repo+DB only (faster, leaves workbooks/configs unrestorable — not advised).
**Unblocks**: every write in the program. **Risk of deferral**: program cannot start.
**DEFER**: not allowed.

### OD-022 (A2) — Repo write authorization + branch policy
**Question**: Authorize implementation-phase writes to both repos, and under what branch/merge policy?
**Context**: Planning was read-only. Implementation must edit plists, scripts, configs, docs (docs-before-code), and run governed DB writes.
**RECOMMENDED**: Yes — writes allowed after G-BCK-01 passes; all repo edits on a dedicated branch per workstream (worktrees for parallel agents), merged only by the orchestrator after validation gates (G-REPO-01/02); DB writes only through env-gated `--apply` scripts under the single write lease (A4); no git history rewrites; program contract docs copied into the repo as the first write.
**Alternatives**: ALT-1 direct-to-main commits (faster, weaker rollback); ALT-2 patch-files-only that you apply manually (slowest, max control).
**Unblocks**: all code/config repair. **Risk of deferral**: nothing can be fixed.
**DEFER**: not allowed.

### OD-023 (A3) — Freeze window + hot-backup method
**Question**: When does Phase -1 run, and does order-header ingestion stay live during backup?
**Context**: Pausing ingestion risks losing order headers (the only alive pipeline); not pausing risks backing up a moving target. `sqlite3 .backup` is online-safe.
**RECOMMENDED**: Short freeze (≤60 min) scheduled immediately **after** a daily ingest cycle completes; write-capable scheduled jobs paused for the window; ingestion itself left running (online `.backup` handles it); backup re-verified against post-window order count (G-BCK-03). You name the day/hour in the session.
**Alternatives**: ALT-1 full pause incl. ingestion (cleanest snapshot, loses up to window-length of headers — they re-sync after); ALT-2 no freeze at all (rely purely on online backup — acceptable but weaker manifest guarantees).
**Unblocks**: Phase -1 scheduling. **Risk of deferral**: backup quality undefined.
**DEFER**: not allowed (pick a window).

### OD-029 (A4) — Contact policy + single-writer rule
**Question**: Confirm the contact protocol and the single-write-orchestrator invariant?
**Context**: "Zero mid-flight contact" needs a defined emergency exception, a passive visibility channel, and the concurrency rule the expert made mandatory (EXT-A02).
**RECOMMENDED**: (a) STOP-THE-LINE list = the ONLY owner pings: backup/restore failure, unexpected rows in a write diff that no policy covers AND that blocks >50% of remaining work, evidence of data loss, any secret exposure, any live external action outside an approved envelope. (b) Everything else parks in `DEFERRED_QUEUE.md` (with KZT exposure + age) and surfaces at acceptance. (c) Passive heartbeat: a short status ping at each phase boundary (Telegram once alerting works; no response expected). (d) Exactly ONE write-capable orchestrator; one write lease per repo at a time; all other agents read-only (G-RDY-04).
**Alternatives**: ALT-1 daily digest instead of phase-boundary pings; ALT-2 no pings until acceptance.
**Unblocks**: the autonomy model. **Risk of deferral**: ambiguity returns as interruptions.
**DEFER**: not allowed.

---

## SECTION B — DATA DROPS (4 items; each validated WHILE YOU ARE STILL IN THE SESSION — a drop that fails validation after you leave becomes an owner contact, which this pack exists to prevent)

### OD-002 (B1) — Fresh bank snapshot (all accounts)
**Ask**: Provide a fresh all-account bank snapshot **dated within 48h of implementation start**: per account — id/label, currency, balance, as-of timestamp. State the FX basis for non-KZT balances (pairs with C2).
**Why fresh**: the 2026-06-01 snapshot (6,353,122 KZT-eq, CN-012) will be weeks old at execution; the expert flagged incompleteness risk (RISK-03). The 06-01 snapshot becomes the fallback only.
**In-session validation**: agent cross-checks the account list against the 2026-05-03 anchor batch (5 stores, CN-013) + the 06-01 doc; any missing account resolved before session ends.
**DEFER fallback**: cash lane (G-CASH-01/02) parks; every other lane proceeds. The 65.1M divergence stays.

### OD-004 (B2) — Physical count protocol + LINE51_WHITE extension scheduling
**Ask**: Approve the count protocol: who counts, when, artifact format (the existing `approved_aggregate.csv` format is good), tolerance vs book, and — critical — **authority precedence across the TWO already-approved counts** (2026-05-30..06-02, 1,833u/39 skus; 2026-06-04 "pre_shipments", 3,989u/66 rows, CN-015/016): recommended precedence = 2026-06-04 supersedes for overlapping SKUs, 05-30 batch fills the rest, both imported as dated governed batches AFTER INBOUND booking (G-STOCK-01→02). Schedule the LINE51_WHITE extension count (its 1,090-unit/5.10M position is blocked from any markdown until counted, G-LIQ-04).
**In-session validation**: agent verifies both count artifacts open + totals match (1,833 / 3,989); LINE51 count date lands on the calendar.
**DEFER fallback**: stock-truth lane proceeds with the two existing counts only; LINE51 stays markdown-blocked (G-LIQ-04 enforces); tranche-1 (which excludes LINE51) unaffected.

### OD-024 (B3) — Offsite backup destination
**Ask**: Name the offsite/external backup destination (drive/NAS/cloud path) + credentials handed over privately (never in any artifact).
**In-session validation**: agent write-tests the destination with a dummy file + verifies capacity.
**DEFER fallback**: local-only backups (G-BCK-01 still passes); G-BCK-04 parks as ADVISORY-pending; revisit at acceptance.

### OD-031 (B4) — Telegram alert credentials confirmation
**Ask**: Confirm the TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID already present in the repo `.env` (CN-050) are the CURRENT, working pair you want alerts on.
**In-session validation**: agent sends one live test message to that chat while you watch — the single most important 10 seconds of the session (alerting worked before 2026-02-13 and has been silent for 119 days; 66/66 alerts skipped).
**DEFER fallback**: none needed if test passes; if you defer the test, G-ALERT-01 runs its forced-failure proof unattended and pings the chat — if nothing arrives, the lane parks and EVERYTHING in Phase 1+ slows. Do not defer this one.

---

## SECTION C — POLICY DEFAULTS (10 decisions; DEFER allowed, fallback pre-stated)

### OD-003 (C1) — v7 pricing floor ratification path
**Context**: v6 floors (2026-03-27) are consumed by 3 production scripts; v7 cost truth exists only as an unconsumed MD (CN-042). The verified leak (12,839 KZT/30d, still active today, CN-039) is a malfunction under EITHER floor; the additional 105–113k/30d is v7-contingent (CN-040).
**RECOMMENDED**: Conditional ratification: after the FX/landed-cost check (C2) re-derives v7 numbers, generate the v7 CSV, repoint all consumers to it as THE single source (owning doc updated first), retire v6. If the FX check moves any floor >5%, the changed rows come back to you at acceptance as a wave-2 list — implementation proceeds with the unchanged rows.
**ALT-1**: keep v6, schedule a fresh v8 derivation. **ALT-2**: ratify v7 as-is without FX check (not advised — 126-day-stale FX inside).
**DEFER fallback**: v6 stays binding; leak-stop (G-PRICE-03) enforced on v6 basis; tranche pricing uses v6 floors; the 105k/30d ceiling stays unrealized.

### OD-013 (C2) — FX + landed-cost policy
**Context**: FX frozen 126 days (CN-009); landed cost never populated; every COGS/valuation/floor figure is an unanchored estimate (INEF-12). The expert owner-gated this but forgot its OD row (DEF-03).
**RECOMMENDED**: Weekly CNY/KZT + USD/KZT entry into `dim_fx_rates` — source = National Bank of Kazakhstan official rate (or your bank's actual conversion rate if you prefer realism over auditability — pick one, it's recorded); entered by the automation with a weekly verification line in the owner digest; landed cost = invoice + freight at receive time going forward, marked `MISSING` historically rather than back-fabricated; ONE COGS authority doc replaces the 3 LINE52 constants (G-FX-02).
**ALT-1**: owner enters FX manually weekly. **ALT-2**: monthly cadence (weaker, drifts).
**DEFER fallback**: FX lane parks → cash anchor still writes (balances are KZT-dominated) but non-KZT legs carry stale-FX flags; v7 ratification (C1) parks → v6 stays.

### OD-014 (C3) — P&L restatement publication
**Context**: April booked 4,856,291 KZT at literally 100% margin (CN-027); Mar–Jun will be restated once COGS backfills.
**RECOMMENDED**: Restate internally with a visible `RESTATED_2026-06` flag on affected months; no external/published figures exist to protect, so full restatement (not annotate-only).
**ALT-1**: annotate-only (keep old numbers, add correction note).
**DEFER fallback**: backfill proceeds; published monthly views carry `PENDING_RESTATEMENT` flag; restatement decision returns at acceptance.

### OD-015 (C4) — First supervised applies (batch authorization)
**Context**: Three one-time applies need explicit authorization: (a) first EOD apply after dry-run passes (G-SCHED-02), (b) residual settlement apply scoped to the verified 120-order/425,015.24 set (G-RESID-01), (c) the COGS backfill apply (G-COGS-02). Each has dry-run-first + diff + rollback per the go/no-go table (G-RDY-01).
**RECOMMENDED**: Pre-authorize all three, contingent on: dry-run diff matches the scoped set within ±2%, backup current, alert path live. Any out-of-scope row in the diff → STOP-THE-LINE (A4).
**ALT-1**: authorize (a)+(b) now, hold (c) for a mid-program ping (one extra contact).
**DEFER fallback**: each parks individually; EOD park freezes the profit chain (expensive — ~225k KZT/day of new blind revenue continues).

### OD-016 (C5) — Strict-gate classes: no silent reclassification
**Context**: The nightly strict gate is RED with 150 items and worsening (CN-051). A YELLOW_ADVISORY label exists but only inside LINE31-launch scope (CN-052) — narrower than the audit feared.
**RECOMMENDED**: Standing rule: red strict-gate classes are NEVER reclassified to advisory; they drain only by fixing root causes (residuals → G-RESID-01; workbook-anchor → G-QUAR-01). If a NEW failure class appears mid-program, its lane stops, it parks with exposure quantified, other lanes continue.
**ALT-1**: allow temporary advisory windows per class with auto-expiry (adds flexibility, risks normalization of red).
**DEFER fallback**: recommended rule applies by default (it is the conservative option).

### OD-017 (C6) — Clamp re-enable conditions
**Context**: Negative-stock clamps fabricated +14,672 phantom units (CN-014); dormant since 2026-05-30 but ungoverned (would resume with EOD revival).
**RECOMMENDED**: Clamps stay DISABLED through Phase 2. Re-enable only after: 7 consecutive clean ledger↔snapshot↔count reconciliation days (G-STOCK-03), AND every clamp event becomes governed (batch-recorded, reason-coded, per-day magnitude cap = 20 units/SKU), AND negative replay results route to quarantine instead of clamping (G-STOCK-05).
**ALT-1**: permanent disable; negatives always quarantine (strictest).
**DEFER fallback**: clamps stay disabled (safe); negative-stock noise accumulates in quarantine for acceptance review.

### OD-025 (C7) — Quarantine disposition defaults
**Context**: 297 quarantined rows untouched for 34–40 days (CN-020/022) + 657 newer orders never quarantined (CN-021). Without defaults, triage = hundreds of owner micro-questions.
**RECOMMENDED**: Default rule table: header-gap order whose entries arrive via backfill → auto-resolve; header-gap with no recoverable entries after backfill → close as `HEADER_ONLY_ACCEPTED` with gross exposure logged (revenue stands, line detail marked absent); product-identity rows → resolve by `dim_sku` canonical match where unambiguous, else close as `IDENTITY_UNRESOLVED` (excluded from per-SKU truth, listed at acceptance); workbook-anchor rows (620,891 net leg) → keep separate, reconcile against restored sales truth, never merge legs; the 9 exceptions → resolve by the matching restored pipeline, the LINE61_4XL_EXCLUDED one closes per existing owner rule.
**ALT-1**: owner reviews every row at acceptance (triage produces a worksheet instead of closures).
**DEFER fallback**: ALT-1 automatically (worksheet mode — nothing closes without you, exposure metric still publishes).

### OD-026 (C8) — Returns QC-fail handling
**Context**: The QC loop (G-RET-02) needs a fail branch: returned item fails inspection — then what?
**RECOMMENDED**: QC-fail → loss event booked at COGS + photo/reason code; item physically binned to a `DEFECT` shelf; monthly defect-lot decision (bundle-sale vs scrap) batched to you. QC-pass → stock re-entry event (sellable).
**ALT-1**: defect-relist at markdown immediately (faster cash, pollutes listings).
**DEFER fallback**: all QC-fails accumulate as `PENDING_DISPOSITION` loss events; first defect-lot decision at acceptance.

### OD-032 (C9) — Below-floor exception path
**Context**: Ladder tiers T4/T5 may need below-COGS pricing for terminal stock (EXT-L02); C1 sets the binding floor.
**RECOMMENDED**: Below binding floor requires a per-tranche exception row pre-listed in the tranche file (SKU/size, floor, proposed price, expected loss KZT) — approved as part of each tranche envelope (D6), never improvised; T4/T5 tranches in wave 1 are PARKED entirely (tranche-1 is T1–T3 only), so no below-floor sale can occur before you see cycle-1 results.
**ALT-1**: absolute no-below-floor ever (may strand terminal stock forever).
**DEFER fallback**: recommended (T4/T5 parked) applies by default.

### OD-028 (C10) — Agent ops budget
**Context**: Implementation runs multi-agent (Codex backend lanes + orchestrator + reviewers). A runaway loop or stuck lane should degrade gracefully, not silently burn.
**RECOMMENDED**: Per-workstream caps: 4h wall-clock / lane before mandatory park-and-report; retry-once-then-park on agent failure; total program token/compute budget = whatever your current Claude/Codex plans allow without overage purchases (no new paid API keys introduced without a STOP-THE-LINE ping); cost-bearing external calls (none planned) forbidden by default.
**ALT-1**: name a hard KZT/$ budget figure.
**DEFER fallback**: recommended caps apply.
**Consumer**: not a gate — the orchestrator's lane management enforces this (caps carried in every dispatch packet; park events logged against G-RDY-04's lease log).

---

## SECTION D — BUSINESS JUDGMENT (12 decisions; these move money)

### OD-008 (D1) — LINE31 spend guard ⚡ most time-sensitive
**Context**: The LINE31 campaign is taking orders against sizes the book says are empty — 2XL oversold to −1 with a 4th order accepted 2026-06-11 21:40, M=0, S=1 (CN-056). Each phantom-size order risks a cancellation/return loop.
**RECOMMENDED**: Immediately (day 0, before backup even — this is a reversible EXTERNAL action in the ads console, not a repo/DB write, so it does not violate backup-first; rollback = restore prior budgets/status from the pre-change export, RB-ADS): pause creatives/targeting for 2XL/M/S; cap remaining LINE31 spend at 10,000 KZT/day; full resume only when per-size stock confidence is green (G-LINE31-01, the standing Phase-2 cross-check).
**ALT-1**: pause the whole campaign (cleaner, loses the selling sizes' momentum ~13 units/12d); ALT-2 (OD-020 variant): different cap value — name it.
**DEFER fallback**: guard auto-applies at cap=current 7d average spend with empty-size creatives paused (the minimal-intervention version).

### OD-020 (D2) — LINE31 cap value
**RECOMMENDED**: 10,000 KZT/day (≈ current June average; June-to-date 117,011 KZT total across the store, CN-044).
**DEFER fallback**: 7d trailing average auto-cap.

### OD-019 (D3) — Campaign kill/fix thresholds
**Context**: 2794142 is no longer zero-GMV (first conversion 06-12) but runs June CRR 82.8% vs siblings 5.8–29.6% (CN-046). Named-campaign kills go stale in days; threshold rules don't.
**RECOMMENDED**: Standing rule (G-ADS-02): any campaign with 14d CRR > 35% AND 14d contribution < 0 → auto-pause + log; 14d CRR 20–35% → flag for fix (bid/targeting) in the weekly digest. Applied to all campaigns including 2794142 the day ads truth restores.
**ALT-1**: kill 2794142 by name now + adopt thresholds later; ALT-2: different threshold numbers.
**DEFER fallback**: report-only mode — the daily CRR check publishes, nothing auto-pauses, kill list waits at acceptance.

### OD-005 (D4) — Liquidation ladder + floors
**Context**: T0–T5 ladder adopted (EXT-L02); release curve is a planning envelope, never a forecast (EXT-L03).
**RECOMMENDED**: Approve the ladder with: T1 0–5% / T2 10–15% / T3 20–30% depths vs current price, dwell 7/7–10/10–14 days, escalation only on measured sell-through <3%; everything stays above the binding floor (C1) except per-row exceptions per C9; T4/T5 parked in wave 1.
**ALT-1**: shallower (T2 max 10%) — slower release; ALT-2: aggressive from day 1 (T3 start) — margin destruction risk.
**DEFER fallback**: ladder approved at T1–T2 only (visibility + soft markdown), T3+ parks.

### OD-011 (D5) — Tranche-1 authorization
**Context**: Canonical tranche-1 = 11 families / 1,003 units / **1,387,464 KZT goods-only** (1,413,954 tiered / 1,704,105 waterfall) — all with ZERO completed sales in 30d+ and zero June movement (CN-032). LINE51_WHITE is NOT in it (separate, count-gated, D-B2).
**RECOMMENDED**: Authorize tranche-1 on the 11-family list under the D4 ladder, contingent on: fresh snapshot + register re-run first (G-LIQ-01 — membership flipped twice in 48h during planning), stock-confidence pass per family (T0), floor + vintage logging live (G-PRICE-01/02), every row carrying tranche_id/decision_id/floor_version/confidence/rollback price (G-LIQ-02), one lead store per SKU/size (G-WA-01).
**ALT-1**: half-tranche pilot (5 smallest families ≈ 250k KZT) first.
**DEFER fallback**: liquidation parks entirely; frozen book keeps earning 0%.

### OD-018 (D6) — Tranche-2+ pre-authorization envelope
**Context**: Without this, every subsequent tranche is a mid-flight owner contact (the exact failure mode this pack prevents).
**RECOMMENDED**: Standing envelope: agents may launch subsequent tranches within — cumulative book value ≤ 5,000,000 KZT goods-only across all wave-1 tranches **excluding LINE51_WHITE** (its 5,101,200 KZT position alone exceeds the cap by design — it is NOT inside this envelope; it runs as its own separately-authorized tranche ONLY after its count (B2), sized post-count, gated by G-LIQ-04); max depth T3; auto-stop on (sell-through <3% after full dwell ×2 consecutive tiers) OR (any floor breach) OR (any stock-confidence drop on a tranche family); T4/T5 + anything beyond the cap batches to you at acceptance with cycle-1 measured results.
**ALT-1**: tranche-by-tranche approval via async ping (one contact per tranche, ~weekly).
**DEFER fallback**: tranche-1 only; everything further waits for acceptance.

### OD-033 (D7) — Dark-family relists
**Context**: RUSH_WHITE (24d dark, 105 units on book) + T-SHIRT_BLACK (50d dark, 132 units) forfeit ~198–254k KZT/month serviceable from current stock (CN-054).
**RECOMMENDED**: Approve size-scoped relists (exclude empty sizes: RUSH_WHITE L; include T-SHIRT XL=10) after live offer fetch + stock-confidence check (G-DARK-01); reorder decisions for dead key sizes stay OUT (that's auto-PO territory, D9).
**ALT-1**: relist only one family as a test.
**DEFER fallback**: relists park; the monthly forfeit continues and is logged as deferred-queue exposure.

### OD-027 (D8) — MELVIS + 11KZ disposition
**Context**: Dead 129/141 days, polled daily fetching zero (CN-055). The expert's "put a decision on record" is a non-answer — here is the forced choice.
**RECOMMENDED**: ARCHIVE both: stop daily polling, mark stores ARCHIVED in configs/docs, preserve historical truth; revisit only after PPCH v1 publishes (their Jan–Feb run-rate was ~0.6M KZT/month combined — re-entry is a capital-allocation question for a working metric, not a default).
**ALT-1**: relaunch test on ONE store with a 50k KZT ad budget cap; ALT-2: keep polling (status quo, costs nothing but decision-blindness).
**DEFER fallback**: keep polling (status quo) + the lost-opportunity line publishes monthly so the cost stays visible.

### OD-009 (D9) — Auto-PO stays off (governed)
**Context**: Forecast machinery dead since 2025-12; only accuracy test ever: MAPE 93.7% (CN-065). The ~11.06M misallocation pattern is what auto-PO would automate today.
**RECOMMENDED**: Auto-PO remains OFF behind recorded gates (G-PO-01) until ALL of: COGS truth green ≥30d, stock truth green ≥30d, cash truth green, FX/floor vintage green, size priors rebuilt + 7/7 validation tests pass (G-PO-02), forecast backtest meets a threshold you set at acceptance, and your explicit restart approval. Manual purchasing continues meanwhile, with the stop-buy gates (>180d cover, size-overstock, returns) as advisory checks on YOUR manual POs too.
**ALT-1**: draft-only mode earlier (auto-PO writes drafts, never executes).
**DEFER fallback**: identical to recommended (this default IS the conservative state).

### OD-010 (D10) — Metric headline adoption
**Context**: PPCH v0 headline (18.92%/30d denominator-consistent; CN-037) overstates ~2–3x vs honest v0.75 (6.0–9.9%). The expert's v1 (net contribution per capital-hour) needs Phase-2 truth to compute.
**RECOMMENDED**: Adopt PPCH v1 as the owner headline once computable (G-MET-01), with confidence bands; v0.75 published as the interim honest number starting when COGS backfill lands; v0 retired from owner-facing surfaces (kept as a diagnostic); dashboard = PPCH v1 + confidence, frozen capital, release velocity, cash-truth confidence, exception exposure.
**ALT-1**: keep ROIC-style metrics alongside.
**DEFER fallback**: v0.75 interim becomes the standing headline until you choose.

### OD-030 (D11) — Operator labor valuation
**Context**: INEF-17 (26–382k KZT/month) is HYPOTHESIS — no time/payroll data (CN-061).
**RECOMMENDED**: Defer valuation; mandate telemetry now (every incident logs minutes + a KZT line at a placeholder rate of 5,000 KZT/hour clearly marked ASSUMED, G-OPS-01); revisit with 30d of real data at acceptance.
**ALT-1**: set your real hourly rate now (sharper, takes 10 seconds — if you know it, choose this).
**DEFER fallback**: identical to recommended.

### OD-006 (D12) — Returns handling policy (the loop itself)
**Context**: Returned goods never re-enter stock or P&L — 366–903k KZT YTD band (CN-062); 12 more returns recognized in June, zero re-entered (CN-019).
**RECOMMENDED**: Full loop: pickup-confirmation predicate writes `returned_to_warehouse` (G-RET-01) → physical QC within 7 days of pickup → QC-pass re-enters sellable stock via ledger event; QC-fail per C8. You (or staff) DO the physical QC; the system finally records it.
**ALT-1**: manual handling outside the DB (status quo — the band keeps compounding ~245k/month).
**DEFER fallback**: telemetry-only mode — flags + QC events record, no stock re-entry until you confirm the physical workflow (band keeps compounding but becomes measured).

---

## Recording the session

Answers land in `OWNER_DECISIONS_RECORDED.yaml` (template beside this file): `decision_id / answer (RECOMMENDED|ALT-n|DEFER) / params (e.g. cap values, dates, rates) / timestamp`. The file is append-only after the session; agents consume only the YAML; amendments are owner-initiated new entries (never edits). Section-B drops are validated before the session closes; their artifacts/paths are referenced (never embedded) in the YAML.

**Session script** (suggested order, ~60–90 min): A1→A4 (10 min) → B4 Telegram test FIRST (it takes 2 minutes and unblocks the most) → B1/B2/B3 (20–30 min) → C1..C10 accept-or-adjust (15 min) → D1/D2 first (⚡), then D3..D12 (20–30 min) → agent reads back the YAML → done. After this, the next thing you hear is either a phase-boundary heartbeat or the acceptance review.
