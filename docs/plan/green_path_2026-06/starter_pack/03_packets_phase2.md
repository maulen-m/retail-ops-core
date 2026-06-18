# Packets — Phase 2 (truth restoration)

All inherit `00_README.md` common rules. AB DB writes serialize through the single lease; read-only portions overlap freely. Every apply: dry-run diff → (Opus review where marked) → orchestrator ACCEPT → apply.

---

## PKT-LINES (Codex 5.5)

/goal
Title: Line-entries hole backfill + status-event restart + freshness guards
Repo: ~/Docs/Autonomous_business
Branch/worktree: <RUNTIME>
Objective: G-ORD-01..03 green.
Context: Writer SELF-REVIVED 2026-06-11 (CN-002) — do NOT "restart" it; backfill the hole: 657 orders created 2026-05-15..06-04 (+ stragglers 06-05..12 beyond the 138 covered). Entries exist through 05-14 — backfill from 05-01 ONLY with idempotent dedup (DEF-06). order_status_event is separately dead (max event_ts 2026-05-04, CN-003) — its capture needs actual restart. Re-baseline both counts at entry.
Must-read: green_gates G-ORD-01..03; the entries-fetch + status-event code paths; canonical_numbers CN-002/003/021/028.
Allowed: the entries/status fetch+backfill scripts' write paths (via their own env-gated apply); green_path_run/.
Forbidden: touching fact_orders_kaspi writer; manual INSERTs outside the scripts' governed paths.
Write permission: APPLY_ALLOWED_AFTER_GATE.
Commands: backfill dry-run first; `python3 scripts/validate_order_entries_freshness.py`; `python3 scripts/validate_kaspi_state_transition.py`; `python3 scripts/validate_order_status_audit_history.py`; `python3 scripts/audit_orders_size_integrity.py`; dup-check ro-query (order_id×sku×qty unique).
Acceptance criteria: 0 entry-less orders in the hole window; 0 duplicate entries; status events flowing (max event_ts ≥ today−1); freshness validators exit 0 two consecutive days.
Stop conditions: Kaspi API fetch for historical windows fails/throttles → backfill what's available, park the remainder with order-id list + exposure.
Return contract: common + before/after entry-less counts per week-bucket.

---

## PKT-PROFIT (Codex 5.5; Opus review MANDATORY on the backfill diff)

/goal
Title: COGS recognition restart + Mar–Jun backfill + sales-chain unfreeze + April restatement
Repo: ~/Docs/Autonomous_business
Branch/worktree: <RUNTIME>
Objective: G-COGS-01..04 green.
Context: COGS translator dead → 4,734 completed orders legless growing ~25/day (CN-025); margin-blind window 18,853,031 KZT growing ~225k/day (CN-026); April booked at literally 100% margin (CN-027). Scope backfill to dim_sku.cogs_kzt IS NOT NULL; COGS-less (LINE31 etc.) → quarantine explicitly (pre-decided). Restatement mode per YAML OD-014 (default: internal restate with RESTATED_2026-06 flag). EOD must already be live (PKT-INFRA-SCHED).
Must-read: green_gates G-COGS-*; the COGS-recognition/translator code; sales_fact_v2 + fact_sales_daily build paths; CN-025/026/027.
Allowed: the recognition/backfill scripts' governed write paths; green_path_run/.
Forbidden: inventing COGS values (only dim_sku/override sources); touching FX (PKT-FX owns it); merging quarantine legs.
Write permission: APPLY_ALLOWED_AFTER_GATE (OD-015.params.cogs_backfill_apply must be true/RECOMMENDED).
Commands: dry-run with month-bucketed before/after (with-COGS/completed per month vs CN-025 baselines: Feb 1543/1575, Mar 601/2063, Apr 0/1736, May 61/1340, Jun 0/<rebaseline>); `python3 scripts/validate_cogs_completeness_by_month.py`; `python3 scripts/validate_profit_publication_integrity.py`; `python3 scripts/validate_monthly_economics_parity.py`; `python3 scripts/validate_data_completeness.py`.
Acceptance criteria: current-month legless (COGS-sourced SKUs) = 0 standing; backfill coverage published before/after; April margin corrected/annotated per OD-014; sales chain max-dates ≥ today−1; quarantined COGS-less list delivered.
Stop conditions: backfill diff touches orders outside Mar–Jun completed scope → halt + Opus review; any 100%-margin month REMAINS after backfill → investigate before closing.
Return contract: common + monthly coverage table + quarantined-SKU list.

---

## PKT-FX (Codex 5.5 + Fable review on the authority doc)

/goal
Title: FX refresh + weekly cadence + landed-cost policy + single COGS authority
Repo: ~/Docs/Autonomous_business
Branch/worktree: <RUNTIME>
Objective: G-FX-01..02 green.
Context: FX frozen 126d (CN-009). Source/cadence per YAML OD-013.params. Landed cost: populate at receive-time going forward, mark MISSING historically (never back-fabricate). Collapse the 3 LINE52 constants + v6/v7/MD duplication into ONE documented authority (doc updated FIRST, G-REPO-02) — coordinate with PKT-PRICE (it consumes your output for the v7 path).
Must-read: green_gates G-FX-*; dim_fx_rates schema; the COGS formula sites (grep for cogs constants); Dim_sku_light_v7.md; CN-009/042.
Allowed: dim_fx_rates governed import; the authority doc + the constant-collapse code patch; green_path_run/.
Forbidden: changing floor VALUES (PKT-PRICE's call); touching price uploads.
Write permission: APPLY_ALLOWED_AFTER_GATE.
Commands: FX import dry-run; `python3 scripts/validate_policy_source_freshness.py`; `python3 scripts/validate_cogs_realism_vs_forensic.py`; `python3 scripts/audit_cogs_realism.py`; `pytest -q` on touched modules.
Acceptance criteria: dim_fx_rates ≤7d + cadence scheduled; ONE authority path (grep proves); landed-cost policy doc landed; validators exit 0.
Stop conditions: FX deferred in YAML → park this lane cleanly (G-PRICE-01 proceeds on v6-reaffirm path; record the park).
Return contract: common + constants-collapse diff summary.

---

## PKT-CASH (Codex 5.5; Opus review MANDATORY on anchor write)

/goal
Title: Fresh bank anchor + cashflow rebuild + weekly re-anchor cadence
Repo: ~/Docs/Autonomous_business
Branch/worktree: <RUNTIME>
Objective: G-CASH-01..03 green (G-CASH-04 standing rule noted for Phase 3).
Context: 65,144,687.12 KZT model-vs-bank fiction (CN-012); anchor table has ONE batch ever (2026-05-03, CN-013). Owner's FRESH snapshot artifact per YAML OD-002.params.snapshot_artifact_path (validated in-session). Anchor rollback was REHEARSED in PKT-READY — follow that exact procedure if needed. Preserve D1 cash-at-delivered contract.
Must-read: green_gates G-CASH-*; CASHFLOW_TRUTH_CONTRACT + KASPI_ORDER_CASHFLOW_TRACKING docs; cashflow_cash_anchor schema; the rebuild scripts; CN-012/013.
Allowed: anchor governed write; cashflow rebuild scripts' paths; green_path_run/.
Forbidden: silent edits to prior anchors/events (compensating entries only); touching COGS legs (PKT-PROFIT owns).
Write permission: APPLY_ALLOWED_AFTER_GATE.
Commands: anchor dry-run; `python3 scripts/validate_cashflow_invariants.py`; `python3 scripts/validate_monthly_cash_reconciliation.py`; `python3 scripts/validate_cashflow_actual_model_separation.py`; `python3 scripts/validate_order_cashflow_coverage.py`.
Acceptance criteria: new anchor batch (all accounts, FX basis logged); events rebuilt through current; |model−bank| ≤1% on anchor day; weekly cadence scheduled; all 4 validators exit 0.
Stop conditions: snapshot artifact missing an account vs the in-session validation record → STOP-THE-LINE (owner data drift); divergence persists >1% after rebuild → park with decomposition analysis (do not chase).
Return contract: common + divergence before/after.

---

## PKT-STOCK (Codex 5.5; SINGLE packet, ABSOLUTE internal order; Opus review per step)

/goal
Title: Stock truth: INBOUND booking → BOTH count imports → snapshot rebuild → clamp governance → confidence score
Repo: ~/Docs/Autonomous_business
Branch/worktree: <RUNTIME>
Objective: G-STOCK-01..05 green, in that order. NEVER reorder: anchor events are additive — count-before-INBOUND double-adds (audit A2-07, ratified by expert).
Context: Snapshot frozen 2026-05-31; book +20.7% over physical; +14,672 clamp units (CN-006/014/015). TWO approved counts exist: 2026-05-30..06-02 (1,833u/39 skus) and 2026-06-04 pre_shipments (3,989u/66 rows) — precedence per YAML OD-004.params (default: 06-04 supersedes overlap, 05-30 fills rest), both as dated governed batches. Negative replay results → quarantine, NEVER clamp (OD-017). Clamps stay disabled until OD-017 conditions (7 clean days + governed-only + 20u/day cap).
Must-read: green_gates G-STOCK-*; Master_Inventory_Rules_v9 (canonical inventory doc); stock_ledger/stock_anchor/stock_adjustment_batch schemas; the count artifacts (paths in CN-015/016); the import + snapshot scripts; rehearsal log from PKT-READY.
Allowed: governed ledger/anchor/batch writes via scripts; snapshot rebuild; green_path_run/.
Forbidden: manual ledger INSERTs; any clamp re-enable before OD-017 conditions; touching sales legs.
Write permission: APPLY_ALLOWED_AFTER_GATE (Opus review before EACH of the 3 write steps).
Commands: per step dry-runs; `python3 scripts/validate_ledger.py`; `python3 scripts/validate_snapshot_vs_snapshot_z.py`; `python3 scripts/check_anchor_health.py`; ordering-invariant ro-query (0 INBOUND events dated after their count anchor); `python3 scripts/validate_kaspi_order_sync_freshness.py` after each apply.
Acceptance criteria: ordering invariant 0 violations; both counts imported with batch records; snapshot ≥ today−1 + daily; counted-family delta ≤ YAML tolerance; 0 ungoverned clamps standing; confidence score published per SKU/size.
Stop conditions: replay negative on a counted SKU → quarantine + continue; INBOUND receipt data unavailable for a 2026 arrival → park that arrival with KZT exposure, import counts with explicit supersession note (the governed alternative the audit allows).
Return contract: common + ledger/snapshot/count three-way reconciliation table.

---

## PKT-RETURNS (Codex 5.5)

/goal
Title: Returns loop: pickup predicate + QC writer + re-entry/loss wiring + comeback telemetry
Repo: ~/Docs/Autonomous_business
Branch/worktree: <RUNTIME>
Objective: G-RET-01..02 green (G-RET-03 publishes after 30d).
Context: 0 of 291 RETURNED orders ever flagged returned_to_warehouse; return_qc_event empty forever; 12 June returns with zero re-entry (CN-019). The ledger consumer is already wired (audit) — the predicate + QC writer are the gaps. QC-fail branch per YAML OD-026 (default: loss event + DEFECT shelf + monthly lot decision). Physical QC is owner/staff-performed — the system records it; telemetry-only fallback if OD-006 deferred.
Must-read: green_gates G-RET-*; the pickup/return code paths; return_qc_event schema; CN-017/018/019/062.
Allowed: predicate fix + QC writer code; governed event writes; green_path_run/.
Forbidden: retroactive fabrication of QC events for historical returns (telemetry starts at restoration; historical band stays BOUNDED-ESTIMATE).
Write permission: PATCH_ALLOWED + APPLY_ALLOWED_AFTER_GATE.
Commands: `python3 scripts/validate_returns_economics_audit.py`; coverage ro-query (flag coverage of post-restoration RETURNED orders).
Acceptance criteria: 100% of newly-RETURNED orders flagged within SLA; QC events flowing; pass→re-entry + fail→loss wiring proven on first real returns; validator exit 0.
Stop conditions: no physical QC happening after 14d (owner-side workflow not adopted) → park G-RET-02 with note; telemetry continues.
Return contract: common + first-returns walkthrough evidence.

---

## PKT-ADS (Codex 5.5)

/goal
Title: Ads truth: canonical backfill + refresh restart + CRR/zero-GMV daily check + campaign⇄SKU map
Repo: ~/Docs/Autonomous_business
Branch/worktree: <RUNTIME>
Objective: G-ADS-01..03 green.
Context: Watcher healthy through today (CN-044); canonical dead since 2026-03-03; refresh runs stopped 2026-05-11; 1,408,496 KZT missing band (CN-045). Backfill 2026-03-04→present from kaspi_marketing.sqlite via the sidecar staging path (the audit's ads_spend_daily.csv pattern). Kill/fix thresholds per YAML OD-019.params (default kill: 14d CRR >35% AND contribution <0 → auto-pause; fix band 20–35%); report-only if OD-019 deferred. 2794142 dispositioned BY THE RULE (currently 82.8% June CRR, CN-046).
Must-read: green_gates G-ADS-*; ads canonical schemas + ads_source_refresh_runs; the watcher DB (mode=ro); CN-044/045/046.
Allowed: staging + governed canonical backfill; refresh job restart; the daily check job; green_path_run/.
Forbidden: campaign mutations beyond the OD-019 rule + the standing LINE31 guard; overwriting canonical history without staging diff.
Write permission: APPLY_ALLOWED_AFTER_GATE.
Commands: staging diff vs canonical; `python3 scripts/validate_ads_spend_reality.py`; `python3 scripts/validate_ads_sidecar_readiness.py`; `python3 scripts/validate_ads_offer_universe_coverage.py`; `python3 scripts/validate_ads_source_packet_contract.py`.
Acceptance criteria: canonical max(date) ≥ today−2 standing; backfilled total reconciles to watcher ±1%; daily CRR report producing; campaign⇄SKU map covers active campaigns; first rule-based dispositions logged (incl. 2794142).
Stop conditions: watcher⇄canonical schema mismatch → staging-only + park canonical write with mapping proposal.
Return contract: common + backfill reconciliation + first CRR report.

---

## PKT-QUAR (Codex 5.5; Fable assist on ambiguous rows)

/goal
Title: Quarantine triage + exception drain + new-order quarantine writers + exposure metric
Repo: ~/Docs/Autonomous_business
Branch/worktree: <RUNTIME>
Objective: G-QUAR-01..04 + G-SCHED-05 green.
Context: 297 static rows (252 header-gap + 23 identity + 22 workbook; CN-020) + 9 OPEN exceptions (CN-022) + 657 never-quarantined newer orders (CN-021) + op-stock job's 2,310 exceptions (CN-058). Disposition defaults per YAML OD-025 (default mode: rule-table closes; ALT-1/DEFER → worksheet mode, nothing closes). Run AFTER PKT-LINES (backfill auto-resolves many header-gaps). Gross/net legs NEVER merge.
Must-read: green_gates G-QUAR-*; the 3 quarantine schemas + exception_queue; OD-025 rule table in the decision pack; CN-020/021/022.
Allowed: governed quarantine status updates per the rule table; exception resolutions; the exposure-metric job; green_path_run/.
Forbidden: deleting quarantine rows; merging gross/net; closing anything outside the rule table (ambiguous → Fable-assist list, then park leftovers).
Write permission: APPLY_ALLOWED_AFTER_GATE.
Commands: `python3 scripts/validate_exceptions_schema.py`; `python3 scripts/validate_exception_queue_db.py`; per-table before/after counts.
Acceptance criteria: 0 active untriaged rows (or worksheet delivered if DEFER); 657 newer orders dispositioned; 0 OPEN exceptions >30d; daily exposure metric line publishing; op-stock job exit 0 or its exceptions folded into the triage.
Stop conditions: a quarantine row implies order-truth corruption beyond its table → park with exposure (never "fix" order rows here).
Return contract: common + disposition census (closed/resolved/parked by reason).

---

## PKT-RESID (Codex 5.5; S-effort; Opus review MANDATORY; any time after Phase 0)

/goal
Title: Residual settlement — single supervised apply, scoped
Repo: ~/Docs/Autonomous_business
Branch/worktree: <RUNTIME>
Objective: G-RESID-01 green (drains 132 of the 150 strict-gate items, CN-051).
Context: Exactly 120 orders / 425,015.24 KZT verified live (CN-023); script reconcile_on_delivery_settlement.py never applied (58d, CN-024). Re-baseline the set at entry; expect ~120 ±June drift.
Must-read: green_gates G-RESID-01; the script; CN-023/024; go/no-go row from PKT-READY.
Allowed: the script's governed apply; green_path_run/.
Forbidden: anything else.
Write permission: APPLY_ALLOWED_AFTER_GATE (OD-015.params.residual_apply true/RECOMMENDED).
Commands: dry-run → diff vs the re-baselined residual set (±2%) → Opus review → apply; `python3 scripts/check_on_delivery_residuals.py`; `python3 scripts/validate_on_delivery_freeze.py`; `python3 scripts/validate_cashflow_invariants.py`.
Acceptance criteria: residual_count=0; nightly checker passes next run; profit overstatement corrected (≈397,094.01 + cancel/return legs).
Stop conditions: diff contains ANY order outside the re-baselined set → halt + STOP-THE-LINE if unexplainable.
Return contract: common + before/after residual report.
