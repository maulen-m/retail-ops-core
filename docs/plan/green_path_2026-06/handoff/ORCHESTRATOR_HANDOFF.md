# ORCHESTRATOR HANDOFF — Path-to-100%-GREEN program (Autonomous_business + Web_automation)

**You are reading the single entry point for resuming this program in a fresh chat.** Read it top-to-bottom once, then act per §7. Everything you need is here or pointed to from here. Written 2026-06-13 by the outgoing Fable 5 orchestrator (session cb0f4768) at the Phase-1 → Phase-2 boundary.

---

## §0 How to use this document

**Read order on resume (≈20 min):**
1. This file, top-to-bottom.
2. `OWNER_DECISIONS_RECORDED.yaml` — the binding decisions (you consume THIS, never pack prose).
3. `green_path_run/scoreboard.csv` + `green_path_run/STATUS.md` — exactly where execution stands.
4. `MASTER_REMEDIATION_PLAN.md` — operating rules, workstreams, rollback map, acceptance.
5. `starter_pack/03_packets_phase2.md` — your next dispatch packets.
6. Skim `handoff/SESSION_LOG_2026-06-12_to_13.md` for the full chronology.

**Your first 5 actions on resume (detail in §7):**
1. Re-baseline: read-only re-derive the current state (git/DB/scoreboard) — planning numbers only size work; every lane re-derives inputs at start.
2. Confirm the alert path is still live (Telegram) and backup is current (`20260613_034450`).
3. Create the AB run dir `AB/.claude/orchestrator_runs/<ts>_green_path/` and take the AB write lease.
4. Dispatch the first Phase-2 lane: **PKT-LINES** (entries backfill — the 657-order hole) as a Codex `/goal` lane, dry-run → review → apply (OD-015).
5. Then proceed down the Phase-2 dependency chain (§7).

**Workspace root** (durable canonical): `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/`
**Repo mirror** (same files): `~/Docs/Autonomous_business/docs/plan/green_path_2026-06/`

---

## §1 Identity & non-negotiables

**You are the single write-capable Fable 5 orchestrator** for this program over two repos: **AB** = `~/Docs/Autonomous_business` (the truth DB `db/app.db`, scripts, validators, scheduler) and **WA** = `~/Docs/Web_automation` (marketing/offer watchers, `data/*.sqlite`). The owner approved a **3-day compression** (max 3 days / 1-2 takes), fully autonomous and Fable-supervised end-to-end, owner involved only at acceptance + the pre-listed touchpoints (§4).

**Hard rules (violating any is a STOP-THE-LINE or a program error):**
- **Backup-first is absolute.** No repo/DB/workbook/config write without a current verified backup (done: `20260613_034450`). The DB is hot — `sqlite3 .backup` only, never file-copy. Ingestion (`kaspi-import-v2`, `com.webautomation.*`) must survive every change (re-run `validate_kaspi_order_sync_freshness.py` after any scheduler/DB change; keep exit 0).
- **Single-writer invariant (EXT-A02).** Exactly ONE write-capable orchestrator (you). One write lease per repo at a time, logged in `green_path_run/lease_log.md`. All sub-agents are read-only EXCEPT the one Codex lane you've granted the lease, scoped to its allowed paths. Never run two writers on the same repo/DB.
- **STOP-THE-LINE is the ONLY owner ping.** Conditions: backup/restore failure · a write-diff with rows no policy covers AND that blocks >50% of remaining work · evidence of data loss · any secret exposure · any live external action outside an approved envelope. Everything else parks in `green_path_run/DEFERRED_QUEUE.md` and surfaces at acceptance. Heartbeat = one short Telegram status at each phase boundary (no response expected).
- **No Meta/Instagram ads, any product, ever (AMD-02).** Kaspi ads console is the only ads surface in scope. The Kaspi cabinet UI is owner-only — you have and want no cabinet credentials.
- **Auto-PO stays governed-OFF (OD-009).** Do not restart it. Manual purchasing continues; stop-buy gates are advisory on manual POs.
- **Never reclassify a red strict-gate class to advisory (OD-016).** Red classes drain only by fixing root causes. A new failure class mid-program → its lane stops + parks with KZT exposure; other lanes continue.
- **No below-floor sales** except via pre-listed per-tranche exception rows (OD-032). **No business-rule invention** — every rule change traces to a recorded decision (OD-xxx / AMD-xx) or a repo contract doc, and the owning doc is updated first (G-REPO-02). **No git history rewrites.**
- **Precedence:** if `OWNER_DECISIONS_RECORDED.yaml` and any prose disagree, **the YAML wins**. If a repo contract (`AGENTS.md`, `WRITE_APPLY_RUNBOOK.md`, `WRITE_SIDE_GATING_CONTRACT.md`, cashflow/PO/lifecycle contracts) is stricter, **the contract wins**.
- **Secrets:** presence-checks only, never print/log token/key values; no secrets or PII in any artifact, packet, or log.

---

## §2 Backstory in brief (how we got here)

1. **The audit (2026-06-11).** A capital-efficiency + truth-decay audit of the Kaspi operation produced a 17-entry inefficiency register (INEF-01..17), a 12,908-word paper, and an Oracle pack. Core finding: the books have silently decayed — sales recorded without cost (COGS translator collapsed), stock fabricated by negative-clamps, cash model 11× off bank, dead scheduler/alerting, frozen inventory earning nothing. Evidence: `_workspaces/2026-06-11_ppch_audit/`.
2. **The expert answer.** Sent to external expert "CodeCaptain": 0 REFUTE / 11 CONFIRM / 6-7 ADJUST (all toward the paper's amended bands) + extensions (Phase -1 backup mandate, reordered roadmap, PPCH v1 metric stack, T0–T5 liquidation ladder, OD-001..012 decision register). Path: `2026-06-11/231306_TASK-000_capital-efficiency-truth-decay-audit/Answer/`.
3. **Reconciliation (four-bucket triage).** Confirmed diagnoses recorded; adjustments re-derived LIVE against the DB (the expert had no DB access); extensions adopted as the program spine; 6 expert defects caught not inherited. One canonical source for every number: `reconciliation/canonical_numbers.csv` (66 rows) + `reconciliation/dispositions.csv` (86) + `reconciliation/EXPERT_RECONCILIATION.md`. Three adversarial QA passes (`qa/qa_verdicts.md`).
4. **The 71-gate green matrix.** `green_gates.csv` (71 gates, 61 HARD / 10 ADVISORY; every `verify_cmd` drawn from AB's real ~130-validator inventory) + `GREEN_STATE_GATE_MATRIX.md`. **100% GREEN = all HARD gates green + every ADVISORY green-or-owner-waived + deferred queue empty/within fallback.** "Governed OFF" counts green (e.g. auto-PO deliberately off behind gates).
5. **Owner session (2026-06-12/13).** 30 decisions + 11 amendments recorded in `OWNER_DECISIONS_RECORDED.yaml`; all data drops validated live. See §4.
6. **3-day compression + execution start.** Phase -1/0/1 executed (§5). Paused here for this handoff.

---

## §3 The plan (phases, workstreams, compression)

**Phases (canonical vocabulary, the expert's reorder):**
- **Phase -1 — Save the game:** backup/freeze/restore-test before any write. ✅ DONE.
- **Phase 0 — Check the tools:** dry-run inventory, go/no-go table, rollback rehearsals. ✅ DONE.
- **Phase 1 — Restore the pulse:** scheduler repair, alerting revival, offsite backup. ✅ DONE.
- **Phase 2 — Make the books true (THE CORE, 32 gates):** entries backfill, COGS, FX, cash anchor, stock truth (inbound + counts + clamps), returns loop, ads truth, quarantine, residuals. ◀ **NEXT.**
- **Phase 3 — Turn truth into money (16 gates):** v7 floor ratification, leak stop, dark-family relists, liquidation tranche-1 + envelope, storefront (incl. G-LINE31-01).
- **Phase 4 — Make it stay fixed (6 gates):** auto-PO governance, PPCH v1 dashboard, labor telemetry, weekly digest, standing-gate watchdog.
- **Phase 5 — Final inspection (1 gate):** score all 71, acceptance handoff.

**21 workstreams** (full table + dependency graph + effort + routing in `MASTER_REMEDIATION_PLAN.md` §3): WS-LINE31GUARD, WS-BCK, WS-READY, WS-INFRA, WS-LINES, WS-PROFIT, WS-FX, WS-CASH, WS-STOCK, WS-RETURNS, WS-ADS, WS-QUAR, WS-RESID, WS-PRICE, WS-RELIST, WS-LIQ, WS-STOREFRONT, WS-OPS-TELEMETRY, WS-PO-GOV, WS-METRICS, WS-ACCEPT.

**3-day compression model (owner-approved):** agent WORK compresses into 3 takes (T1 = Phase 1+2; T2 = Phase 3+4; T3 = Phase 5). **Market-physics STANDING gates cannot compress** — 7-consecutive-clean-day stock reconciliation (G-STOCK-03 → clamp re-enable), 14-day CRR windows (G-ADS-02), tranche dwell 7/10/14 days. By day 3 these are **ARMED + measuring**; they self-green afterward via a **standing-gate watchdog** (a cron/launchd job, built in Phase 4, that re-scores them daily and Telegrams when each flips — zero human, zero orchestrator). So: **day-3 deliverable = all WORK done + all point-in-time gates green + standing gates armed-on-track + acceptance package; literal 100%-green scoreboard self-completes ~1–2 weeks later.**

**Routing:** Codex 5.5 x-high for backend lanes (`/goal` packets); Fable 5 for judgment lanes (floor economics, tranche economics, metric spec); Opus 4.8 for adversarial review of every write diff (template `starter_pack/05_review_packet_template.md`). Mechanics in §9.

---

## §4 Owner session outcome (the binding inputs)

**All 30 decisions are in `OWNER_DECISIONS_RECORDED.yaml`** (append-only; amendments = new entries, never edits). Headline: 26 RECOMMENDED-as-written + 4 ALT-CUSTOM. **Read the YAML for params; this is the orientation.**

**The 4 ALT-CUSTOM (read these carefully):**
- **OD-002 cash** → workbook `Inbound_calendar_V10.002.xlsx :: Cash_Balances :: column M` (ts 2026-06-13 01:01, grand 3,937,364 KZT-eq / 5,437,364 with reserve, binance_p2p FX). In-flight: SHR receipts 19+20 (¥7k+¥10k) make true SHR remaining ¥44,101; PO-1B ¥12k paid / ~¥17,621 Binance outflow pending — the cash lane must pre-register that outflow when explaining the 65.1M divergence.
- **OD-004 counts** → four-layer precedence (06-11 22:00 OCR batch ▶ 06-04 photo batch ▶ 06-04 pre_shipments artifact ▶ 05-30 batch), imported AFTER inbound booking. OCR batch reconciled in `reconciliation/count_batch_2026-06-11_2200/count_batch_canonical_DRAFT.md`.
- **OD-024 offsite** → `~/Backups/green_path/` + `/Volumes/Migration_Staging_Overflow/green_path_backups/` (both write-tested; standing job now automates the copy).
- **OD-008 LINE31 guard** → RECOMMENDED **+ Kaspi-console-only constraint** → resolved-by-structure (AMD-11, §8).

**Amendments AMD-01..11** (YAML `amendments:` block) — the load-bearing ones:
- **AMD-01** the 580 unbooked LINE31 sets are the concrete INBOUND work-list: PO-1A 338 @2026-05-24 (S24 M131 L77 XL76 2XL30), PO-1O 242 @2026-06-11 (S17 M90 L53 XL57 2XL25), ARC-1 shortage correction (book 795 → received 637/638), plus the apply-pending CSV `exports/validation/product_truth_yellow_to_apply_ready_20260529_123827/line31_apply_ready_stock_split.csv` (436 physical / 348 sellable @05-29). Inbounds_sheet has NO arrivals after 2026-03-02 — the booking gap is LINE31-only per evidence but PKT-STOCK re-verifies.
- **AMD-02** Meta/IG ads untouchable, Kaspi only.
- **AMD-03** `acmewear_direct_crm` sells via external IG/Meta traffic FROM THE SAME warehouse → WS-STOCK must (a) read-only discover its outbound/shipment records, (b) ensure CRM-channel decrements reach the stock ledger or negative drift returns. Physical counts are channel-agnostic ground truth.
- **AMD-04** read-only source repos: `~/Cowork/Projects/Sourcing-Research`, `~/Cowork/Projects/E-commerce`, `~/Docs/acmewear_direct_crm`, and the vibe_code_PO workbook.
- **AMD-05** Whale Blue 50 sets: owner created Kaspi offers 2026-06-12 (moderation) → storefront lane VERIFIES live, doesn't create.
- **AMD-06** new colors (Bean Paste/Pomelo/Eggplant + Iris via PO-1B): owner sends assets ~2026-06-18 from `/Volumes/Migration_Staging_Overflow/content_offload/.../LINE31_ST_MOBILE_COLOR_ADD_V1` → ingest then; gated, non-blocking.
- **AMD-07** OCR batch protocol (3 passes → reconcile → `RESTORED_CANCEL_RETURN_NO_ORDER_LINK` re-entry events; LINE51 S from the 06-11 batch).
- **AMD-08** PO-1B 507-set pipeline registration (¥29,621 gross, ¥12k paid, ~¥17,621 Binance from 06-13; rework-fee risk = log unless it blocks).
- **AMD-09** second Telegram pair `*_WAYBILL` available for routing.
- **AMD-10** freeze-window slipped → launch-triggered (already executed).
- **AMD-11** LINE31 guard satisfied-by-structure (§8).

**OWNER-DEPENDENT LIST (everything that needs the human — pre-listed so the rest is autonomous):**
1. **Keep the Mac awake, powered, online** during takes (run `caffeinate` alongside).
2. **Optional 60-sec cabinet click**: pause Kaspi campaign `2794142` (men's 3-in-1 LS, June CRR 82.8%, OD-019 kill band). Auto-applies once ads truth restores anyway.
3. **Physical world (normal ops, non-blocking)**: fulfill the 4 accepted LINE31 2XL orders from arrived stock (do NOT cancel — stock exists); staff does physical QC on returns as the queue forms (system records; un-inspected items park PENDING).
4. **Owner's own money moves** (pre-registered, not program-blocking): PO-1B ~¥17,621 Binance transfer.
5. **New-color assets** (~2026-06-18, owner trigger) — blocks nothing.
6. **Day-3 acceptance read** (~20-30 min): final handoff + any v7 floors that moved >5% (wave-2 list) + waiver decisions on the deferred queue.
7. Nothing else. Telegram proven (msg 1819), counts covered, LINE51 needs no new count, backups done.

---

## §5 What is DONE (Phase -1 / 0 / 1)

Scoreboard: `green_path_run/scoreboard.csv`. Run records: `green_path_run/`. Full chronology: `handoff/SESSION_LOG_2026-06-12_to_13.md`.

- **Phase -1 backup — GREEN.** Backup id `20260613_034450`, 9.26 GB / 1,024 files at `~/Backups/green_path/20260613_034450/` + external copy. Online `sqlite3 .backup` of 5 live DBs, both repos (excl runtime/exports/.venv), workbooks (incl. receipts), 30 plists, secrets (chmod 700, redacted manifest), runtime_logs, selected exports. **Restore tests 3/3 PASS.** Gates G-BCK-01/02/03, G-ORD-04 GREEN; G-BCK-04 GREEN (standing job). First repo write done: program docs → `AB/docs/plan/green_path_2026-06/` (untracked).
- **Phase 0 readiness — DONE.** `green_path_run/go_no_go.md` (every write script: command, gates, dry-run, rollback, GO/NO/REDESIGN), `write_candidates.json`, 188 dry-run outputs. **Both never-tested rollbacks rehearsed PASS** (`rehearsal_cash_anchor.log`, `rehearsal_stock_anchor.log` — counts returned to pre-state). Baseline guards catalogued (`baseline_guards.md`; 1 pre-existing pytest failure noted, not fixed).
- **Phase 1 scheduler — PARTIAL (correct).** Interpreter layer fixed (kaspi-marketing-hourly 1→0, crm-db-sync repointed off the dep-less python3.14). **9 jobs PARKED on business-DATA causes** (not infra) — each unblocks in Phase 2 (see DEFERRED_QUEUE). EOD dry-run rc1 = data gates → apply correctly blocked. Ingestion untouched, freshness exit 0. Detail: `green_path_run/return_codex_sched.md`. Gates G-SCHED-01 PARTIAL, G-SCHED-02 dry-run captured.
- **Phase 1 alerting — GREEN.** Telegram env plumbed to 19 live LaunchAgents (presence only); **forced-failure proof api_ok:true**; standing offsite job `com.example.green-path-offsite-backup` (daily 05:30) installed + verified. Detail: `/tmp/green_path_scratch/alert_out/alert_report.md` (also see §6 + Appendix B). Gates G-ALERT-01 GREEN, G-ALERT-02 window started.

**No governed Phase-2 DB write has occurred** (confirmed in Appendix C). You are on a clean Phase-2 starting line.

---

## §6 System changes already made + rollback map (you are NOT on a clean slate)

The execution made **real, intentional, recorded changes** to the live macOS system and the AB repo. Full verified ledger in **Appendix B**. Summary:

**Plists modified — 19 distinct live `~/Library/LaunchAgents/` files** (verified, Appendix B):
- 2 ProgramArguments repointed to AB `.venv/bin/python` (SCHED lane): `com.example.kaspi-marketing-hourly`, `com.example.crm-db-sync` — these 2 are ALSO in the 19 below (they got both changes; 19 distinct files total, not 21).
- 19 env-plumbed with TELEGRAM_* `EnvironmentVariables` (ALERT lane; ProgramArguments untouched): single-truth-preflight, end-of-day, kaspi-daily-ops-report, crm-db-sync, exchange-import, the 5 google-ops-board jobs, kaspi-waybill-deadline, waybill-telegram-control, kaspi-shipped-truth-sync, operational-stock-daily-truth, kaspi-marketing-ads, kaspi-marketing-hourly, on-delivery-residuals, gmail-pubsub, gmail-watch-refresh.

**New files created in AB repo:** `config/com.example.green-path-offsite-backup.plist`, `scripts/run_green_path_offsite_backup.sh`. **New live launchd job:** `com.example.green-path-offsite-backup` (daily 05:30). **Program docs** copied to `AB/docs/plan/green_path_2026-06/` (untracked).

**Backups:** `~/Backups/green_path/20260613_034450/` (full, 9.26GB) + external copy on Migration_Staging_Overflow; plus fresh plist backups before the ALERT patch at `20260613_051444` + `20260613_051544`.

**Rollback (RB-PLIST):** restore the matching plist from `~/Backups/green_path/20260613_034450/plists/` then `launchctl bootout gui/$(id -u) <plist>; launchctl bootstrap gui/$(id -u) <plist>`. RB-DB / RB-CASH-ANCHOR / RB-STOCK-ANCHOR (for Phase 2) are in `MASTER_REMEDIATION_PLAN.md` §4; the two anchor rollbacks are rehearsed (Phase 0 logs).

**Housekeeping:** leftover external-volume probe files `/Volumes/Migration_Staging_Overflow/green_path_backups/.codex_mkdir_test_*` + `.codex_write_test_*` — delete at convenience. Legacy backup jobs `external-database-backup` + `table-delta-backup` left as superseded-pending-owner-review (don't fix/delete without owner).

---

## §7 What is NEXT — the exact resume sequence

**Re-baseline first** (planning numbers only sized the work; tranche membership flipped twice in 48h during planning): each lane re-derives its inputs read-only at start. Then run Phase 2 in this dependency order. Packets: `starter_pack/03_packets_phase2.md`. Each lane: take AB lease → Codex `/goal` dry-run → Opus review of the diff → you ACCEPT → apply (env-gated) → update scoreboard → release lease. Heartbeat at the phase boundary.

**TAKE 1 — Phase 2 (the core; ~32 gates):**
1. **PKT-LINES (WS-LINES)** — backfill the **657-order entries hole** (line-entries writer self-revived 06-11 but left the gap). Restores per-order line detail. Unblocks COGS + quarantine. Gates G-LINES-*.
2. **PKT-PROFIT (WS-PROFIT)** — **COGS backfill apply** (pre-authorized OD-015) over the ~4,692 completed orders missing cost legs; then P&L restatement (`RESTATED_2026-06`, OD-014; April's 4,856,291 @ 100% margin fiction). Gates G-COGS-01/02/03.
3. **PKT-FX (WS-FX)** — import FX into `dim_fx_rates` (owner actual binance_p2p/bank rates, weekly automation; OD-013), one COGS authority doc replacing the 3 LINE52 constants. Precedes v7 floor work. Gate G-FX-02.
4. **PKT-CASH (WS-CASH)** — cash anchor from `Cash_Balances` column M (OD-002), **explain the 65.1M model-vs-bank divergence**, pre-register the PO-1B Binance outflow + SHR ¥44,101. Rehearsed rollback RB-CASH-ANCHOR. Gates G-CASH-01/02.
5. **PKT-STOCK (WS-STOCK)** — **strict absolute order: INBOUND booking → counts → snapshot → clamps.** Book the 580 LINE31 sets + ARC-1 correction (AMD-01); import the 4 count layers in OD-004 precedence (incl. the OCR batch `count_batch_canonical_DRAFT.md` — additions as `RESTORED_CANCEL_RETURN_NO_ORDER_LINK`, resolve family-mapping flags F-1/2/3 at dim_sku); wire CRM-channel decrements (AMD-03); clamps stay disabled (OD-017); start the 7-clean-day reconciliation streak (G-STOCK-03). Note **LINE51 S=82 re-sizes the LINE51 tranche** (much smaller than the audit's 5.10M). Gates G-STOCK-01..05.
6. **PKT-RETURNS (WS-RETURNS)** — full returns loop (OD-006): pickup predicate → 7-day QC → re-entry; QC-fail → loss + DEFECT shelf (OD-026). Gates G-RET-*.
7. **PKT-ADS (WS-ADS)** — ads truth restore; apply OD-019 threshold kill rule to all campaigns incl. 2794142. Kaspi only. Gates G-ADS-*.
8. **PKT-QUAR (WS-QUAR)** — quarantine disposition rule-table (OD-025) over the 297 stale + new rows. Gates G-QUAR-*.
9. **PKT-RESID (WS-RESID)** — residual settlement apply, scoped to the verified 120-order / 425,015.24 set (OD-015). Gate G-RESID-01.
After Phase 2: the EOD + the 9 parked scheduler jobs should clear their data gates → re-verify them green (closes G-SCHED-01 fully + G-SCHED-02 apply).

**TAKE 2 — Phase 3 + 4** (`starter_pack/04_packets_phase3_4_5.md`):
- **PKT-PRICE (WS-PRICE)** — v7 floor ratification (FX-checked, OD-003; dual-path if FX deferred), stop the 12,839 KZT/30d leak. Gates G-PRICE-*.
- **PKT-RELIST (WS-RELIST)** — dark-family relists RUSH_WHITE + T-SHIRT_BLACK size-scoped (OD-033), Kaspi only.
- **PKT-LIQ (WS-LIQ)** — liquidation tranche-1 (11 families/1,003u/1,387,464, re-derived fresh; OD-011) under the T1-T3 ladder (OD-005); tranche-2+ envelope ≤5M excl. LINE51 (OD-018); LINE51 its own tranche after its count is imported (G-LIQ-04, now openable — LINE51 S=82 landed).
- **PKT-STOREFRONT (WS-STOREFRONT)** — verify Whale Blue offers live (AMD-05); the **G-LINE31-01 daily spend-vs-stock cross-check job** (the standing LINE31 per-size guard); ingest new colors when owner sends (~06-18).
- **PKT-OPS (WS-OPS-TELEMETRY)** — labor telemetry at ASSUMED 5,000 KZT/h (OD-030); weekly owner digest.
- **PKT-POGOV (WS-PO-GOV)** — auto-PO governance locks (OD-009); stop-buy advisory gates.
- **PKT-METRICS (WS-METRICS)** — PPCH v1 dashboard (OD-010), v0.75 interim, retire v0. **Build the standing-gate watchdog here** (the cron that auto-greens the streak gates).

**TAKE 3 — Phase 5:**
- **PKT-ACCEPT (WS-ACCEPT)** — score all 71 gates, before/after, deferred-queue review, waiver list, final handoff (`MASTER_REMEDIATION_PLAN.md` §7). This is the owner's second/final touchpoint.

---

## §8 Known issues / gotchas / traps

- **python3.14 brew trap (CN-048/049):** `/opt/homebrew/bin/python3` is a dep-less python3.14 — jobs die on `import yaml`. ALWAYS use `AB/.venv/bin/python` (3.12.x, has deps). Never rely on system python3. (Already fixed for 2 jobs; watch for it elsewhere.)
- **Codex `-i` swallows the positional prompt:** when running `codex exec` with image flags, pipe the prompt via **stdin** (`... < prompt.md`), don't pass it positionally.
- **Codex sandbox levels:** READ-ONLY lanes → `--sandbox read-only`; scratch-write → `--sandbox workspace-write`; lanes needing `launchctl`/Volumes → `--sandbox danger-full-access`. Always `--skip-git-repo-check` and `-C <repo>`.
- **Single-lease discipline:** never grant two write lanes on the same repo. Read-only analysis can overlap freely. Log every grant/release.
- **The 9 parked scheduler jobs are blocked on DATA, not infra** — do NOT "fix" them in an infra lane; they clear when their Phase-2 data gate clears (DEFERRED_QUEUE lists each + its unblock). EOD apply is pre-authorized but correctly blocked until entries+COGS+freeze clear.
- **Family-mapping flags F-1/2/3** (OCR batch): the logotype 3-in-1 may be a DIFFERENT product than the 06-04 set (its 2XL/3XL/4XL rose, 4XL appeared); «Футболки длин/кор рукав» = RUSH/T-SHIRT families distinct from Berserk — resolve at dim_sku import, not by guessing.
- **OCR residual cells** (LINE51 S=82, kids 140/28=32-vs-33, 150/30=28-vs-29, line52 2XL=20, rombik 3XL not-captured): consensus values taken; ledger reconciliation catches ±1 residue; passive owner glance at acceptance.
- **The big truths Phase 2 must fix:** 657-order entries hole; 580 unbooked LINE31 sets; ~4,692 COGS-less completed orders; 65.1M cash divergence; +14,672 clamp-fabricated phantom units (clamps dormant since 05-30, ungoverned — keep disabled); strict gate RED 150 items +35/day; LINE51 S=82 re-sizing.
- **Plan/session limits (OD-028):** no overage purchases. If Claude/Codex windows exhaust, pause the take and resume on reset — that's the one thing that can stretch "3 days," and it's a billing boundary not a design flaw. 4h/lane cap then park; retry-once.
- **app.db is 259MB and hot;** WA has many `repricer_items_*` snapshot DBs — the LIVE ones are `app.db`, `kaspi_marketing.sqlite`, `repricer_items.sqlite`, `repricer_unified_truth.sqlite`, `kaspi_snapshots/snapshot.sqlite`. The orders fact table is **`fact_orders_kaspi`** (35,302 rows, fresh today); line detail = `fact_order_entries_kaspi`. The three Phase-2 governed-write tables are `stock_anchor`, `stock_adjustment_batch`, `cashflow_cash_anchor` (each holds only 2026-04/05 baseline rows — confirmed no 06-13 write).
- **acmewear_direct_crm DOUBLE-COUNT RISK (refines AMD-03):** the CRM's `StockMovement` table is its movement truth, but the CRM is contractually FORBIDDEN from writing to Kaspi/Repricer/AB; the cross-repo path `AB/docs/contracts/CROSS_REPO_BUSINESS_EVENT_BRIDGE_V1.md` is **read-only/provenance-only** (prepares review packets, never decrements stock). So direct-funnel (Instagram LINE51/LINE61) sales consume the SAME physical warehouse units the Kaspi book counts but are NOT auto-subtracted. The book is wrong in BOTH directions: +580 LINE31 un-added AND direct-funnel sales un-subtracted. WS-STOCK must reconcile via a manual/bridge-mediated, write-gated step — physical counts are the channel-agnostic ground truth that closes both.
- **`lint_docs.sh` false-positive (known, do NOT "fix"):** the baseline `lint_docs` guard FAILS on the banned pattern `\b856\b` — triggered by the legitimate canonical number "4,856,291" (April's 100%-margin fiction, CN-027) inside the program docs now in `AB/docs/plan/green_path_2026-06/`. Pre-existing/expected; never alter the canonical number to satisfy the linter. Likewise `pytest -q` baseline = 49 failed / 3371 passed (pre-existing, catalogued in `baseline_guards.md`) — not program regressions.
- **Plan-dir YAML was resynced at handoff:** the AB `docs/plan/green_path_2026-06/` copy was briefly stale (missing AMD-11, copied as the first repo write before AMD-11 was appended). It is now resynced to the workspace (authoritative) copy. Always treat the **workspace** `OWNER_DECISIONS_RECORDED.yaml` as authoritative.
- **External mirror is on `/Volumes/Migration_Staging_Overflow/`** (NOT `/Volumes/Migration_Staging/`, which is empty). The standing offsite job targets Overflow.

---

## §9 Mechanics (how to operate)

**Dispatch a Codex `/goal` lane (proven pattern):**
```
cat > /tmp/green_path_scratch/PKT_X.md <<'EOF'
/goal
Title: ...
Repo: ~/Docs/Autonomous_business   (you hold the AB lease)
Objective: gates G-...
... (allowed/forbidden paths, dry-run→gate→apply, validation, rollback ref, stop conditions, return contract) ...
EOF
nohup sh -c 'codex exec --skip-git-repo-check -C ~/Docs/Autonomous_business --sandbox danger-full-access < /tmp/green_path_scratch/PKT_X.md > /tmp/green_path_scratch/x_out/stdout.md 2> /tmp/green_path_scratch/x_out/stderr.log' >/dev/null 2>&1 & echo PID=$!
```
Watch with a background `pgrep -f "codex exec"` loop; integrate the return against acceptance criteria → ACCEPT / ACCEPT_WITH_FOLLOWUP / REJECT_AND_REWORK / BLOCKED. The packets in `starter_pack/03..04` are the source text — fill `<RUNTIME>` slots (branch, dates, lease).

**Opus review of a write diff:** use `starter_pack/05_review_packet_template.md` (default-REJECT, 8 checks) — spawn an Opus agent on the dry-run diff before any apply.

**Run dir / scoreboard / heartbeat:** create `AB/.claude/orchestrator_runs/<ts>_green_path/` per the global protocol (00_run_plan, 01_backup_plan, dispatch/return per packet, integration_log, validation_log, final_handoff). Keep updating `green_path_run/scoreboard.csv` (gate_id,state,evidence,dated) and `green_path_run/STATUS.md`. DEFERRED_QUEUE at `green_path_run/DEFERRED_QUEUE.md`. Telegram heartbeat at each phase boundary (the alert module is live; main pair proven, `*_WAYBILL` pair available).

**Apply gate (OD-015):** dry-run diff must match the scoped set within ±2%, backup current, alert path live → then apply; any out-of-scope row → STOP-THE-LINE.

---

## §10 Key-file index

(Full per-file inventory in **Appendix A**.) Top of the tree:
- `OWNER_DECISIONS_RECORDED.yaml` — binding decisions (consume this).
- `MASTER_REMEDIATION_PLAN.md` — rules, workstreams, rollback map, acceptance.
- `green_gates.csv` + `GREEN_STATE_GATE_MATRIX.md` — the 71-gate definition of done.
- `reconciliation/canonical_numbers.csv` + `dispositions.csv` + `EXPERT_RECONCILIATION.md` — every number, one source.
- `reconciliation/count_batch_2026-06-11_2200/count_batch_canonical_DRAFT.md` (+ 3 passes + owner_overrides) — the OCR'd count batch.
- `starter_pack/00_README.md` → `01_orchestrator_prompt.md` → `02/03/04_packets_*.md` → `05_review_packet_template.md` — your launch surface.
- `green_path_run/` — live execution state (scoreboard, STATUS, lease_log, DEFERRED_QUEUE, go_no_go, write_candidates, rehearsal logs, lane returns, line31_prechange_export).
- `handoff/ORCHESTRATOR_HANDOFF.md` (this) + `SESSION_LOG_2026-06-12_to_13.md` + `START_HERE.md`.
- `RUN_MANIFEST.md` — full audit trail.

---

## §11 Glossary

- **INEF-01..17** — the audit's inefficiency register entries. **OD-xxx** — owner decisions (in YAML). **AMD-xx** — session amendments (in YAML). **G-XXX-nn** — green gates (in green_gates.csv). **WS-XXX** — workstreams. **CN-xxx** — canonical numbers.
- **PPCH** — Profit-Per-Capital-Hour, the headline metric (v0 overstated ~2-3×; v0.75 honest interim; v1 = net contribution per capital-hour, owner headline once Phase-2 truth lands).
- **Tranche** — a batch of frozen SKUs released for markdown under the T0–T5 ladder. **T0** = stock-confidence check; **T1-T3** = 0-5/10-15/20-30% depth; **T4/T5** parked wave-1.
- **LINE31** — women's 3-piece sport set (supplier Tracy/Juyitang). **PO-1A** = first 450 (338 non-olive arrived). **PO-1O** = 242 Cardamom/Olive (arrived, sellable). **PO-1B** = 507 branded (in production). **ARC-1** = the older Feb batch ("April leftovers").
- **SHR** — the men's-apparel supplier (debt-repayment supplier in the cash log). **EOD** — the `end-of-day` scheduled job (profit/close pipeline). **Clamp** — the negative-stock auto-correction that fabricated +14,672 phantom units.
- **STOP-THE-LINE** — the only owner-ping condition set. **Heartbeat** — passive phase-boundary status, no response expected.

---

## Appendix A — Per-file artifact inventory (verified read-only sweep)

**Authority chain:** `OWNER_DECISIONS_RECORDED.yaml` (decisions) → `green_gates.csv` (done) → `reconciliation/canonical_numbers.csv` (numbers, planning-only) → `MASTER_REMEDIATION_PLAN.md` (how) → `starter_pack/` (dispatch). Repo contracts override where stricter.

**Top level** `_workspaces/2026-06-12_green_path/`
| file | bytes/lines | what it is |
|---|---|---|
| `RUN_MANIFEST.md` | 6KB/30 | chronological spine: build log + owner session + OCR + execution + program state |
| `MASTER_REMEDIATION_PLAN.md` | 15.9KB/114 | operating rules §1, ambiguity protocol §2, 21 workstreams §3, RB-* rollback §4, routing §5, walkthrough §6, closeout §7 |
| `green_gates.csv` | 30.5KB/72 | 71 gates × 17 cols (61 HARD/10 ADVISORY); verify_cmd + deps + rollback per gate = definition of done |
| `GREEN_STATE_GATE_MATRIX.md` | 8.4KB/73 | 100%-green formula, census by phase, scoring procedure (Phase 5) |
| `OWNER_DECISION_PACK.md` | 27.3KB/230 | human rationale for the 30 decisions — BACKGROUND only, agents never consume it |
| `OWNER_DECISIONS_RECORDED.yaml` | 18.1KB/219 | THE decision source: 30 ODs + AMD-01..11. Consume this only. Append-only. |

**`reconciliation/`**
| file | bytes/lines | what it is |
|---|---|---|
| `canonical_numbers.csv` | 21.7KB/67 | 66 CN facts, one figure/claim w/ basis+confidence+drift — PLANNING values, re-baseline live |
| `EXPERT_RECONCILIATION.md` | 8.9KB/60 | expert-answer verdict + 8-item post-audit drift report + pinned defns |
| `dispositions.csv` | 27KB/87 | 86 dispositions (17 INEF + 12 OD + 35 EXT + 10 RISK + 6 DEF + 6 ASK) → gate/WS/OD |
| `count_batch_2026-06-11_2200/count_batch_canonical_DRAFT.md` | 12.4KB/174 | THE reconciled OCR count: 166 additions + 12 supersede + 8 not-captured; import semantics; F-1/2/3 flags |
| `…/opus_pass_A.md`,`opus_pass_B.md`,`codex_pass_C.md` | 30.6/34.2/16.6KB | 3 blind OCR passes (evidence; B self-flagged kids-strip) |
| `…/owner_overrides.yaml` | 0.6KB/11 | owner ground truth: kids 120/24=9 (outranks OCR) |

**`starter_pack/`** — `00_README.md` (launch index + sequence diagram + 7 common rules) · `01_orchestrator_prompt.md` (the orchestrator's own startup prompt + HARD start-gate) · `02_packets_phase_neg1_0_1.md` (5 packets, done) · `03_packets_phase2.md` (9 packets, NEXT) · `04_packets_phase3_4_5.md` (8 packets) · `05_review_packet_template.md` (Opus default-REJECT review, 8 checks).

**`green_path_run/`** (LIVE execution state) — `STATUS.md`, `scoreboard.csv` (gate states), `00_run_plan.md` (TAKE-1 compression plan + routing overrides), `lease_log.md`, `DEFERRED_QUEUE.md` (parked items + unblocks), `.run_ts` (=20260613_034450), `01_backup_plan.md` (+launchctl census), `baseline_guards.md` (pytest 49-fail + lint_docs fail = pre-existing), `return_codex_sched.md` (per-job root-cause table), `rehearsal_cash_anchor.log` + `rehearsal_stock_anchor.log` (RB rehearsals PASS), `go_no_go.md` + `write_candidates.json` (~100 write scripts mapped), `line31_prechange_export_20260613_034450.json` (RB-ADS artifact).

**`qa/qa_verdicts.md`** — the 3 adversarial QA passes (already reconciled circular-dep, FX dual-path, census, 71/71 gate⇄packet bijection).

**If you read only 5:** RUN_MANIFEST.md · green_path_run/{STATUS,scoreboard} · OWNER_DECISIONS_RECORDED.yaml · green_gates.csv · MASTER_REMEDIATION_PLAN.md + starter_pack/00_README.md.

**Stale/superseded (by design, no contradictions):** OWNER_DECISION_PACK.md is background-only (YAML is consumable); canonical_numbers.csv = planning-only (re-baseline live; some CN rows self-marked superseded, e.g. CN-033 tranche-1-legacy DEPRECATED → CN-032); baseline_guards' 2 failures are pre-existing not regressions. No internal contradictions across plan/matrix/gates/YAML (3 QA passes already reconciled them; DEFERRED_QUEUE structurally clean at start).

## Appendix B — System-mutation + rollback ledger (verified live 2026-06-13)

**This machine is NOT a clean slate.** 19 distinct live LaunchAgent plists modified, 1 new launchd job, 3 new repo/system files, 9.3 GiB backups ×2 volumes, 2 leftover probe files. All reversible. Source reports: `green_path_run/return_codex_sched.md`, `/tmp/green_path_scratch/alert_out/alert_report.md`.

**1) Plists MODIFIED** (live `~/Library/LaunchAgents/`; rollback = restore file from RB-source then `launchctl bootout gui/$(id -u) <plist>; launchctl bootstrap gui/$(id -u) <plist>`):

| label | change | RB-source |
|---|---|---|
| `com.example.kaspi-marketing-hourly` | interpreter→.venv **+** TELEGRAM env | `~/Backups/green_path/20260613_034450/plists/` |
| `com.example.crm-db-sync` | interpreter→.venv (PATH venv-first) **+** TELEGRAM env | `…/20260613_034450/plists/` |
| `single-truth-preflight`, `com.autonomous-business.end-of-day`, `kaspi-daily-ops-report`, `exchange-import`, `google-ops-board-publish`, `google-ops-board-prewindow-health`, `google-ops-board-size-writeback`, `google-ops-board-closeout-watch`, `google-ops-board-closeout-caffeinate`, `kaspi-waybill-deadline`, `waybill-telegram-control` | TELEGRAM env only | `…/20260613_051444/plists_alert_phase1/` |
| `kaspi-shipped-truth-sync`, `operational-stock-daily-truth`, `kaspi-marketing-ads`, `on-delivery-residuals`, `gmail-pubsub`, `gmail-watch-refresh` | TELEGRAM env only | `…/20260613_051544/plists_alert_phase1_remaining/` |

Live verify: 19/19 carry the TELEGRAM_BOT_TOKEN key (presence-only; values never read); the 2 repointed jobs show venv interpreter live while their `…034450` backups retain the original `/opt/homebrew/bin/python3` → rollback intact. **NOT modified** (confirmed): `kaspi-import-v2`, all `com.webautomation.*`, `external-database-backup`, `table-delta-backup` (+ the 9 SCHED-parked jobs got no plist change).

**2) NEW files** — `AB/config/com.example.green-path-offsite-backup.plist` (source), `AB/scripts/run_green_path_offsite_backup.sh` (wrapper, 2106B), `~/Library/LaunchAgents/com.example.green-path-offsite-backup.plist` (live, 1089B). Operational: `AB/runtime_logs/green_path_offsite.log`.

**3) NEW launchd job** `com.example.green-path-offsite-backup` — daily 05:30 (RunAtLoad=0), `/bin/bash`→wrapper, currently `runs=3 / last exit 0` (GREEN). Removal: bootout + `rm` the live plist + the 2 repo files.

**4) Backups** (local + identical external mirror on `/Volumes/Migration_Staging_Overflow/green_path_backups/`):
- `…/green_path/20260613_034450/` — **9.3 GiB**, manifest `BACKUP_MANIFEST_20260613_034450.json` (205,946 B). Full pre-run checkpoint (db/git/listings/plists[30]/repo/secrets[700]/workbooks). **RB-PLIST source for the 2 interpreter repoints + every job's baseline.**
- `…/20260613_051444/plists_alert_phase1/` (48 KiB, 12 plists) + `…/20260613_051544/plists_alert_phase1_remaining/` (28 KiB, 7 plists) — env-plumb pre-patch copies.

**5) Leftover probe files to clean** (safe): `rmdir /Volumes/Migration_Staging_Overflow/green_path_backups/.codex_mkdir_test_70757 && rm /Volumes/Migration_Staging_Overflow/green_path_backups/.codex_write_test_70759`.

**6) Residual non-green live exit codes are PRE-EXISTING** business/data or external-volume failures the run intentionally parked (e.g. `crm-db-sync` 78 EX_CONFIG, `external-database-backup`/`exchange-import`/`gmail-*` 78, `table-delta-backup` 2) — NOT regressions from these mutations. All secret checks presence-only.

## Appendix C — Live ground-truth snapshot (verified read-only 2026-06-13)

**HEADLINE: Has any governed Phase-2 DB write occurred? → NO (confirmed).** `stock_anchor` / `stock_adjustment_batch` / `cashflow_cash_anchor` each hold 0 rows dated 2026-06-13 (only 2026-04/05 baselines: 1 / 1 / 5 rows). No `app_db_before_*` backup after 05:00 on 06-13. You are on a clean Phase-2 starting line.

**Git:** AB `codex/TASK-webui-archive-single-truth-v1` @ `39cbdbf4` (332 dirty/untracked lines — includes our doc copies + 2 new files); WA `main` @ `d9d3f4b9` (155). No commit made.

**app.db** (`AB/db/app.db`, 134 tables): orders fact = **`fact_orders_kaspi`** — 35,302 rows, MAX(created_at)=2026-06-13 10:42:34, MAX(imported_at)=06-13 06:00:33; ingestion fresh (≈last cycle 11:00). Line detail `fact_order_entries_kaspi` = 21,783 rows. `kaspi_order_sync_log` latest `20260613_110032` (STOREB fetched 36 / ins 1 / upd 35; MELVIS+11KZ 0).

**WA DBs:** `kaspi_marketing.sqlite` campaign_daily_current MAX(date)=2026-06-13 (current); `repricer_items.sqlite` main table = 329 rows.

**Backups:** newest pre-write checkpoint `~/Backups/green_path/20260613_034450/` (manifest 205,946 B) — present LOCAL **and** external `/Volumes/Migration_Staging_Overflow/green_path_backups/20260613_034450/` (manifest byte-size matched; real, not stub). ⚠️ `/Volumes/Migration_Staging/green_path_backups/` is EMPTY — the live mirror is **Overflow**. (The 13:45 `app_db_before_workbook_catalog_map_sync_…sqlite` rotation is the unrelated daily catalog-sync, not a Phase-2 write.)

**Freshness validator** (`scripts/validate_kaspi_order_sync_freshness.py`): UNIVERSAL/STOREB/ACMEWEAR all ~2.8h, **EXIT=0**.

**Bottom line:** pipelines live + fresh; both repos uncommitted/dirty (pre-write); verified pre-write checkpoint exists ×2 volumes; no governed Phase-2 write — expected ready-but-untouched state.
