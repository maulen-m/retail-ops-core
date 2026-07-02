# OWNER DECISION PACK #2 — Green-Path resume (2026-07-02) — DRAFT

Status: EVIDENCE-COMPLETE (17:40) — OD2-A from PKT-OPEX-NORM (Gate GREEN); live-state context
from PKT-REBASE (honest re-score: 32 GREEN / 24 RED / 14 ARMED / 1 PARTIAL). Decisions recorded
append-only into OWNER_APPROVALS_20260702_RESUME.md once answered; presentation material only.

REBASELINE ADDENDUM (2026-07-02 17:38): 24 standing regressions since 06-19 are drift, not new
breakage of the June repairs — sales/COGS/cashflow chains stale at 06-16/19, ads canonical
06-16, FX 06-13, cash re-anchor broken (workbook reads as not-a-zip + weekly job exit 1), 34
NEW on-delivery residuals, missing DB view `fact_orders_kaspi__pre_line_grain_migration`
(schema drift from the daily-shipping commit series) breaking 4 validators, offsite backup
rsync exit 23, strict preflight failing. ALL of these fall under already-recorded decisions
(OD-015 apply classes + standing program conventions) → repaired TONIGHT by PKT-STANDING-REFRESH
after the fresh backup, no new decision needed. The items BELOW are the ones that genuinely
need you. Note: fresh under-floor and tranche numbers re-measure after the sales-chain repair;
latest measured figures shown are from 06-19.

Rules (same as pack #1): each item has a RECOMMENDED answer; DEFER = pre-stated fallback; no
decision here authorizes any write by itself — every write still goes backup-first, dry-run,
env-gated, with readback.

---

## OD2-A — Cash floor / OPEX truth adoption (unblocks G-SCHED-02 path honestly)

Evidence: exports/validation/opex_owner_input_normalization/2026-07-02/ (Gate: GREEN).

Current gate: conservative min_cash 3,668,632.39 < conservative floor 4,234,749.84 → EOD FAIL.
The floor is derived from OPEX commitments that are 144 days stale (Jan protocol). Your new
workbook makes the floor RISE:

| variant | GOLD_store-d/KaspiGOLD_KZ treatment | opex_monthly | conservative floor |
|---|---|---:|---:|
| V1 | sheet value 100,000/mo | 2,740,785 | 4,611,177.50 |
| V2 | owner loan figure 80,000/mo | 2,720,785 | 4,581,177.50 |
| V3 | excluded from cashflow | 2,640,785 | 4,461,177.50 |

Every variant stays above current min cash → after adopting TRUE obligations the EOD preflight
still fails honestly. Two decisions:

**A1 — adopt which variant?** [RECOMMENDED: V2 (your stated 80,000/mo real payment), unless the
declining schedule matters enough to model month-by-month]
*A: v2.
**A2 — G-SCHED-02 unblock policy (pick one):**
- (a) Keep RED until cash grows above the honest floor (no policy change; acceptance carries an
  explicit open blocker) — most conservative.
- (b) Adjust policy multipliers in config/cashflow_scenarios.yaml (e.g. conservative 1.5→1.25
  ≈ floor 3.9-3.93M — still above-ish/near min cash; 1.5→1.15 ≈ 3.62-3.65M — passes today) —
  the sanctioned path per DECISIONS.md 2026-01-27; owning doc updated first.
- (c) Documented CASHFLOW_PREFLIGHT_OVERRIDE_REASON for EOD (temporary, visible in every run).
[RECOMMENDED: (a) if liquidation tranche-1 (OD2-D) is approved — expected proceeds lift min
cash toward the honest floor; else (b) with an explicit revisit date.]
*A:(b) Adjust policy multipliers in config/cashflow_scenarios.yaml 1.5→1.15 ≈ 3.62-3.65M — passes today
**A3 — workbook detail confirmations (one YES/edit each):**
1. KaspiGOLD_Uni: dated declining ADDITIONS schedule overrides flat 170,000 OPEX row (first
   unpaid 2026-07-21 = 166,000). [RECOMMENDED: yes] *A: yes
2. GOLD_Acmewear MISMATCH: OPEX sheet 176,511/mo vs LOANS sheet 92,049/mo (Δ84,462/mo ≈ 126,693
   of conservative floor). Which is the true monthly cash out? *A:  lets use 126,693 for now (later tomorrow i will give more precise schedule. - do not block because of that.
3. Internet payment day missing → assumed day 27 (Jan protocol value). [RECOMMENDED: confirm] A: confirmed
4. LLM_6 / LLM_7 marked CLOSED but include=YES → treated EXCLUDED. [RECOMMENDED: confirm] A: confirmed
5. Gym_memberships owner 90,000 vs source 30,000 → 90,000 used. [RECOMMENDED: confirm] A: 30,000 confirmed from june thats the new cost.
6. employee_1 and MELVIS(tax) rows parsed as excluded — confirm intended. A: confirmed.
7. BCC 5M: account = Universal (as you started the row); dates kept distinct (screenshot
   2026-04-11 = evidence, owner-stated 2026-04-04 = context; pay-day 9 drives cashflow).
   [RECOMMENDED: confirm] A: confirmed.

On approval → Stage B (PKT-CASHFLOOR-APPLY): owning docs first (KASPI_ORDER_CASHFLOW_TRACKING §
OPEX chain + new OPEX_OWNER_INPUT_CONTRACT), date-scoped commitments replace (>= 2026-07-02,
history preserved for PnL), config/opex regenerate, copied-DB rehearsal, env-gated production
apply with backup + SHA guard, honest EOD dry-run transcript.

---

## OD2-B — G-PRICE-03 disposition (under-floor leak; RED)

Evidence at 06-19: 57 units / 92,508 KZT trailing-7d under v7 floor (fresh number lands with
PKT-REBASE). You refused live price changes for ACMEWEAR compact SUIT rows (intentional
strategy, 06-19 intake) — that stands. Options:
- (a) Record per-row floor-exception authority for the intentional strategic rows (like the
  approved LINE parent-floor authority): owning doc + config scoring change only, no live price
  writes; gate then measures only non-strategic leakage. [RECOMMENDED] A: - (a) confirmed, note taht all acmewear in sale products like line31, line61, line51 and their subbundle childs (except for line61 subbundle ls31 blk (same as rush 3in1 set product, tights, longsleeve, shorts) shoudlnt be touched by price lowering for agressive price strategies, because that's our own brand store where we position things under the brand strategies and the prices can be changed and evaluated but in a different way. They should be evaluated under the acmewear brand approach - since there's multiple factors like external Instagram ads, traffic, external funnels of Instagram, internal marketing etc. This is non-generic products. while universal and storeb are selling generic commodity like clothes products. in acmewear store product offers on marketplace - that's our exclusive product offerings. None of the other sellers are competing with us on that offers because that is our registered KZ Countrywide brand trademark while for the Universal and M Group stores there is multiple competing sellers under same generic product offers. that's why price controlling there is much more important in a real-time frequency.
- (b) Approve scoped live corrections for any NON-strategic under-floor rows found fresh.
- (c) Keep RED knowingly (blocks final acceptance hard-green).

## OD2-C — G-DARK-01 write lane (dark offers; RED)

No-write analysis complete (06-19): RUSH_WHITE S = article/title mapping fix, M = offer
creation (no platform row), 3XL = product-title/family mapping review; T-SHIRT_BLACK L = 4
archive activation candidates; RUSH_WHITE L (stock 0) = deactivate candidate. Options:
- (a) Approve the exact-row WRITE lane (Kaspi merchant surface, guarded WA path: fresh
  preflight → dry-run → upload → readback + Repricer refresh). [RECOMMENDED — restores ~198-254k
  KZT/month serviceable flow estimate] A: Approve, make sure they where specified in any of ocr snapshots records, source of ocr: "~/Downloads/Stock_ingestion_from_warehouse_counting/warehouse_stock_count_manual_results".
- (b) Park dark relist for this acceptance run (gate stays RED, recorded).

## OD2-D — Tranche-1 liquidation go/no-go (G-LIQ-02/03, G-WA-01/02, G-CASH-04 chain)

OD-011 pre-authorized tranche-1 in June; basis has since shifted (fresh candidate at 06-19: 7
families / 423 units / 542,880 KZT known-goods; fresh re-run lands with PKT-REBASE + a new
G-LIQ-01 register ≤2d before sizing). New context: cash 1.57M vs obligations ~2.72M/mo — the
capital-context memo argues for freeing frozen stock. Options:
- (a) GO: execute tranche-1 per ladder (T1 0-5% → dwell 7d → T2 10-15%...), lead-store map
  applied first (turns G-WA-01), first governed Repricer upload with rollback+readback hash
  (turns G-WA-02). [RECOMMENDED]
- (b) GO with reduced/edited family list (you strike rows).
- (c) Park liquidation this run (G-LIQ-02/03 + G-CASH-04 stay blocked, recorded).
A: - (a) GO — start after tonight's truth repair + a fresh stock register. Since we have already delayed the launch of this price changes phase for multiple days, what would be the ideal way to slightly readapt our approach for efficiency? By analyzing previous day's data and using better reevaluation of what type of price changes we actually need to move the needle, and if it's more than 5-10% then we can do that as well because I highly suspect that 5-10% does anything of a value to waste 7 days on, there has to be more meaningful steps like 15-25-30%..etc,.

## OD2-E — Return QC facts (G-RET-02 chain: G-MET-01, G-PO-02/03, G-RET-03)

Your 06-18 estimate: staff physical repackaging ~30 days (≈ 07-18). Confirm: facts arriving
~07-18 / earlier / later? Intake ready: governed QC CSV writer (dry-run default, env-gated,
backup-first) — we prep the CSV template so staff can fill it. No invented facts, ever. A: - 07-18 to 30th july period.

## OD2-F — Time windows + advisory waivers (acceptance calendar)

- G-MET-02 needs 7 consecutive cadence days → earliest ~07-09 if cadence restarts tonight.
- G-LIQ-03 needs dwell windows (7-14d post tranche-1).
- 30d advisory gates: G-RET-03 (QC telemetry), G-DARK-02 (post-relist slope), G-OPS-01
  (incident telemetry 30d). Options per gate: WAIVE at acceptance (recorded, revisit date) or
  WAIT (acceptance ~early August). [RECOMMENDED: waive advisories with revisit dates; target
  acceptance mid-to-late July]. A:  [RECOMMENDED: waive advisories with revisit dates; target
  acceptance mid-to-late July].

## OD2-G — Scheduler/daily-ops evidence mode (G-SCHED-01)

Daily ops have run ACTIVE since 06-19 (your shipping flow). Confirm the operating pattern for
the remaining program: writes only in 20:00-14:00 windows with governed pause/resume;
G-SCHED-01 heartbeat evidence collected in ACTIVE mode on non-write days. Also: the 9 parked
non-daily jobs (exit 78 freeze-gated set) get per-job disposition at acceptance (keep parked /
re-enable) — no change without your call. A: writes only in 20:00-15:00 windows with governed pause/resume

## OD2-H — Web_automation dirty tree (512 files)

WA has 512 uncommitted/untracked files (HEAD 06-21). Triage list lands with PKT-REBASE.
Options: (a) curate greenpath-relevant changes into a lane commit + leave the rest untouched
[RECOMMENDED], (b) leave everything untouched this run (risk: unclear rollback baseline for WA
lanes), (c) you review the triage list first. 
A: (a) curate greenpath-relevant changes into a lane commit + leave the rest untouched.

---

Answer format: reply per item (A1: V2, A2: a, A3: yes×7 / edits, B: a, C: a, D: a, E: 07-18,
F: waive+mid-July, G: confirm, H: a) — I record everything append-only with timestamps, then
dispatch only what the answers authorize.
