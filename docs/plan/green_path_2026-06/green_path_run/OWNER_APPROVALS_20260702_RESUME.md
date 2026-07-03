# Owner Approval Intake — 2026-07-02 Resume (Session #2, part 1)

Recorded by orchestrator from owner INLINE annotations (`*A:` marks) in
OWNER_DECISION_PACK_2_20260702_DRAFT.md, observed 2026-07-02 ~18:0x +05. Append-only; verbatim
owner text quoted; orchestrator interpretation flags marked [INTERP]. Part 2 (OD2-D/E/F/G/H)
pending — owner did not annotate those sections yet.

## OD2-A — Cash floor / OPEX adoption (G-SCHED-02 lane) — APPROVED WITH EDITS

- A1 variant: owner wrote "v2." → **V2: KaspiGOLD_KZ (GOLD_store-d) at 80,000 KZT/mo** included.
- A2 policy: owner wrote "(b) Adjust policy multipliers in config/cashflow_scenarios.yaml
  1.5→1.15 ≈ 3.62-3.65M — passes today" → **conservative multiplier 1.5 → 1.15** (base 1.0 and
  abs 500,000 unchanged). Sanctioned path per DECISIONS.md 2026-01-27; owning doc updates first;
  recorded as owner policy with this intake as the decision record.
- A3.1 KaspiGOLD_Uni: "yes" → dated declining ADDITIONS schedule overrides flat 170,000
  (first unpaid 2026-07-21 = 166,000).
- A3.2 GOLD_Acmewear (KaspiGOLD_OF): owner wrote "lets use 126,693 for now (later tomorrow i
  will give more precise schedule. - do not block because of that." → **interim monthly
  obligation = 126,693 KZT/mo**, owner will supply a precise schedule ~2026-07-03; lane must
  NOT block on it. [INTERP: 126,693 was presented in the pack as the conservative-floor impact
  figure of the Δ; owner designated it as the interim monthly amount — adopted as such; flagged
  REVISIT_20260703_OWNER_SCHEDULE. At multiplier 1.15 the difference vs either sheet figure does
  not change preflight pass/fail materially.]
- A3.3 Internet pay-day 27: "confirmed".
- A3.4 LLM_6/LLM_7 excluded (CLOSED wins over include=YES): "confirmed".
- A3.5 Gym_memberships: owner wrote "30,000 confirmed from june thats the new cost" →
  **CORRECTION: use 30,000 KZT/mo (source value), NOT 90,000** — new cost effective June.
- A3.6 employee_1 + MELVIS(tax) excluded: "confirmed."
- A3.7 BCC 5M: "confirmed." → account = Universal; dates kept distinct (2026-04-11 screenshot
  evidence / 2026-04-04 owner-stated context); pay-day 9 drives cashflow.

Effect on floor (indicative; exact numbers recomputed by the apply lane): V2 basis 2,720,785
− 60,000 (Gym 90k→30k) − 49,818 (GOLD_OF 176,511→126,693) ≈ **opex_monthly 2,610,967**;
conservative floor @1.15 ≈ **3,502,612** vs conservative min cash 3,668,632.39 → **expected to
PASS honestly**; base floor ≈ 2,610,967 vs base min cash 3,800,484 → PASS.

Authorized next step: PKT-CASHFLOOR-APPLY (Stage B) — owning docs first, owner-decision JSON
record, date-scoped commitments replace (>= 2026-07-02, history preserved), config/opex
regenerate from the owner workbook + these edits, cashflow_scenarios.yaml conservative
multiplier 1.15, copied-DB rehearsal, env-gated production apply with backup + SHA guard,
honest EOD dry-run transcript. Runs in the night write window after the fresh backup.

## OD2-B — G-PRICE-03 disposition — (a) APPROVED + BRAND PRICING POLICY RECORDED

Owner chose (a) floor-exception authority, verbatim policy: "note taht all acmewear in sale
products like line31, line61, line51 and their subbundle childs (except for line61 subbundle ls31
blk (same as rush 3in1 set product, tights, longsleeve, shorts) shoudlnt be touched by price
lowering for agressive price strategies, because that's our own brand store where we position
things under the brand strategies and the prices can be changed and evaluated but in a
different way. They should be evaluated under the acmewear brand approach - since there's
multiple factors like external Instagram ads, traffic, external funnels of Instagram, internal
marketing etc. This is non-generic products. while universal and storeb are selling generic
commodity like clothes products. in acmewear store product offers on marketplace - that's our
exclusive product offerings. None of the other sellers are competing with us on that offers
because that is our registered KZ Countrywide brand trademark while for the Universal and M
Group stores there is multiple competing sellers under same generic product offers. that's why
price controlling there is much more important in a real-time frequency."

[INTERP → implementation rule for the owning doc + config:]
- ACMEWEAR-store offers (LINE31, LINE61, LINE51 + sub-bundle children) = STRATEGIC_BRAND_PRICING
  class: excluded from aggressive/automated price-lowering and from G-PRICE-03 leak scoring via
  recorded per-row floor-exception authority (like the LINE parent-floor authority). Price
  changes there remain owner/brand-lane decisions only.
- EXCEPTION: LINE61 sub-bundle **LS31 BLK** (= RUSH 3-in-1 set product: tights, longsleeve,
  shorts) is NOT protected — it stays under normal floor enforcement.
- UNIVERSAL + STOREB offers = generic commodity class: full floor enforcement + real-time price
  control priority.
No live price writes authorized by this item; scoring-authority + doc/config change only.

## OD2-C — G-DARK-01 write lane — APPROVED WITH STOCK-VERIFICATION CONDITION

Owner: "Approve, make sure they where specified in any of ocr snapshots records, source of
ocr: ~/Downloads/Stock_ingestion_from_warehouse_counting/warehouse_stock_count_manual_results".
→ Exact-row relist/mapping WRITE lane approved (guarded WA path: fresh preflight → dry-run →
upload → readback + Repricer refresh) **with precondition**: each candidate SKU/size
(RUSH_WHITE S/M/3XL, T-SHIRT_BLACK L; RUSH_WHITE L off) must be cross-verified against the OCR
warehouse-count records at the path above before any upload; sizes not evidenced in OCR records
are excluded from the upload set and returned as follow-ups.

## PART 2 — recorded 2026-07-02 ~20:25 +05 from owner inline annotations ("all answered")

### OD2-D — Tranche-1: GO WITH RE-ADAPTED, DATA-DRIVEN STEP SIZING
Owner verbatim: "(a) GO — start after tonight's truth repair + a fresh stock register. Since we
have already delayed the launch of this price changes phase for multiple days, what would be
the ideal way to slightly readapt our approach for efficiency? By analyzing previous day's data
and using better reevaluation of what type of price changes we actually need to move the
needle, and if it's more than 5-10% then we can do that as well because I highly suspect that
5-10% does anything of a value to waste 7 days on, there has to be more meaningful steps like
15-25-30%..etc,."
[INTERP → recorded as ladder amendment AMD-OD005-20260702 (append-only, supersedes entry-depth
only):] Tranche-1 entry depth becomes DATA-DRIVEN per family: the lane first produces a
needle-moving analysis from recent sales/velocity data and proposes per-family FIRST-step
depths which MAY enter directly at 15/25/30% (T2/T3 depths) instead of T1 0-5%. UNCHANGED hard
bounds: binding floor (no below-floor rows except pre-listed OD-032 exceptions), OD-018
envelope (cumulative book-value cap 5,000,000 KZT, max tier T3 ≈ 30%, auto-stop rules),
one-lead-store rule, stock-confidence gating, full 5-field row provenance, dwell windows still
apply BETWEEN subsequent escalations, ACMEWEAR-brand exclusions per OD2-B (LS31-BLK eligible),
LINE51 own-tranche rule. Owner sees the per-family depth proposal inside the tranche file at
orchestrator review before upload (falls out of (a); no extra owner gate required).

### OD2-E — Return QC facts: window 2026-07-18 → 2026-07-30
Owner: "07-18 to 30th july period." → G-RET-02 chain closes inside that window; CSV intake
template staged in advance; acceptance calendar plans HARD-gate close within July.

### OD2-F — Advisory waivers: APPROVED as recommended
Owner pasted the recommendation as the answer → the three 30d advisory gates (G-RET-03,
G-DARK-02, G-OPS-01) get recorded WAIVED-at-acceptance with revisit dates; target acceptance
mid-to-late July (return-QC window above may set the exact date).

### OD2-G — Write windows: AMENDED to 20:00–15:00
Owner: "writes only in 20:00-15:00 windows with governed pause/resume" → supersedes the 06-13
addendum boundary (was 20:00–14:00). Protected daily-ops window becomes 15:00–20:00 Asia/Almaty.
Heartbeat evidence in ACTIVE mode on non-write days; the 9 parked exit-78 jobs get per-job
disposition at acceptance (unchanged).

### OD2-H — WA dirty tree: (a) curated green-path lane commit
Owner: "(a) curate greenpath-relevant changes into a lane commit + leave the rest untouched."
→ Orchestrator curates ONLY green-path-relevant WA changes into a clean commit on the WA
greenpath branch; the remaining ~500 files stay byte-untouched.

### ADDENDUM ~20:45 — owner supplied a FRESH cash snapshot for the re-anchor
Owner restored the iCloud-evicted workbook and added a new Cash_Balances snapshot column
labeled `02.07.2026_19_55_38` in Inbound_calendar_V10.002.xlsx (verified read-only: header row
4, column 15, 17 numeric account rows, naive sum 5,706,888 KZT-eq pending governed
operating/reserve parsing). This is the anchor source for the G-CASH-01/02 re-anchor in
PKT-CASHFLOOR-APPLY step 0 (label pinned in the packet).

### ADDENDUM ~21:2x — CRM WORKBOOK REPAIR APPROVED
Owner replied "yes, repair" to the proposed repair of the corrupt excel_ui/SALES_KSP_CRM_V3.xlsx
(truncated 289,127-byte stub since 2026-06-29 17:14, disk-full mid-write). Approved scope, full
option: preserve the stub as evidence → restore the wrapper's own pre-append snapshot
.SALES_KSP_CRM_V3.xlsx.pre_append_snapshot.70440.1782734942593054000 (2026-06-29 17:08,
5,528,561 bytes) → replay 2026-06-29→07-02 rows from DB truth via the established append path
per Excel_UI_Contract_for_CRM_V1.md, PREVIEW-FIRST, idempotent (no duplicate OrderID+store
rows) → re-run CRM integrity validation. Workbook-surface authorization is limited to exactly
this file and this repair; no other workbook writes authorized.

### Session #2 COMPLETE — all 8 sections answered. Authorized lanes now: cash-floor Stage-B
apply (A), price-exception scoring authority (B), dark-offer exact-row lane w/ OCR condition
(C), tranche-1 with data-driven entry depths (D), QC intake staging (E), WA curated commit (H).
Still every write behind backup-first, dry-run/diff, env gates, readback, orchestrator review.

## Forbidden surfaces note
This intake authorizes: the cash-floor Stage-B apply chain (docs/config/DB commitments via
gated writers), the price-exception scoring change (docs/config), and the dark-offer exact-row
lane (Kaspi merchant relist surface) under its stated condition — each still behind
backup-first, dry-run/diff, env gates, readback, and orchestrator review. No other production
DB write, workbook write, Google Sheet edit, Telegram send, Kaspi merchant/UI/API write,
Repricer write, price upload, stock write, LaunchAgent change, customer/operator-message write,
cash movement, PO, purchase, or external write is authorized by this intake.

---

## ADDENDUM 2026-07-03 15:10 +05 — OWNER MORNING PANEL P1–P8 ANSWERED ("All answered, let's go!")

Owner annotated OWNER_MORNING_PANEL_20260703.md inline (`*A:`) and confirmed in chat. Verbatim:

- **P1 floor policy** — `*A:(a) .` → Apply corrected OPEX truth; approved 1.15× multiplier stands; G-SCHED-02 stays HONEST RED until tranche proceeds/collections lift min-cash above 3,502,612. Policy code: ACCEPT_RED_UNTIL_CASH. [INTERP: option (a) as written in panel; EOD-under-honest-fail behavior to be verified tonight and reported — no silent override.]
- **P2 KO_CLEAR COGS** — `*A:(a).` → Parent-COGS inheritance LINE51_WHITE → CL_OC_MEN_LINE51_WHITE_KO_CLEAR_2XL authorized (order 972820718, 9,063 KZT).
- **P3 GOLD_Acmewear** — `*A: keep interim` → 126,693 KZT/mo stays with OWNER_INTERIM_REVISIT flag; no schedule integration lane.
- **P4 generic floor-fix** — `*A: (a) approve exact-row lane.` → Live price-lift to v7 floor for leaking generic UNIVERSAL/STOREB rows (53u at last reading, fresh dry-run re-derives); LS31-BLK carve-out NOT lifted; staged dry-run → orchestrator row review → upload w/ rollback + readback.
- **P5 CRM bridge (AMD-03)** — `*A:(a) confirm + one-off decrement now, bridge proposal to follow` → 3 direct-CRM buyouts (65,980 KZT) confirmed; governed one-off stock_ledger decrement tonight; standing bridge = design proposal only.
- **P6 fresh count** — `*A:(c) date: 10.7.2026 jule 10th.` → Physical count 2026-07-10 (tranche-candidate families + RUSH/T-SHIRT, OD-004 photo protocol). Count anchors → G-STOCK-03/04/05; tranche-1 stage-1 dispatch 07-10/11 per OD2-D GO.
- **P7 RUSH_WHITE M** — `*A: if we have stock <=15 units on that size - then no need to create it, but if we do create it  we need to always specify our brand name ACMEWEAR - so that later all of our created uploaded own offers are able to become exclusive under our own seller rights and no one else can compete with us on price on those product offers. That's mandatory..` → TWO STANDING RULES: (R1) size stock ≤15 → no offer creation for that size; (R2) MANDATORY: every own-created/uploaded offer specifies brand ACMEWEAR (seller-rights exclusivity path). Applied: RUSH_WHITE M stock_ledger balance = 14 ≤ 15 → M offer NO-CREATE; dark-lane M question CLOSED.
- **P8 marketing login** — owner DELETED the P8 section while annotating (file 86→78 lines); no text answer. [INTERP: treated as likely-logged-in; verification = dispatch marketing remainder fetch 06-19→07-03 now; if marketing_login_failed recurs → one-line re-ask. Recorded honestly as deletion, not as an explicit confirmation.]
- **Section-2 NEW DIRECTIVE (size truth)** — appended by owner to the dark-offer FYI bullet, verbatim: `due to the platform difference of size specifications, there are multiple inconsistencies in what the customer sees and what we actually see in our system as final ordered size. That's why we always ask height and weight parameters of each customer personally. And in CRM, Google board sheet always specify the final allocated size or additionally height weight parameters if we have enough time. So for probable size, size probability should be calculated via our historical order sendings data inference. So that if we always send size L to the product offer that actually shows size S, that means it's probably size L, and has to be properly updated from time to time in the probable size column in our Google boardsheet and within the system upstream as well.` → Recorded as owner directive PROBABLE-SIZE-INFERENCE: backlog analytics/design lane (historical order-sendings inference → Google board probable-size column + upstream), not gate-blocking. ACMEWEAR-store row 349 stays as-is and folds into this lane.

Execution schedule per approved post-panel plan: read-only prep now (15:00–20:00 ops window); write lanes tonight 20:08+ serialized; count intake 07-10.

### ADDENDUM 2026-07-03 15:12 +05 — OWNER WINDOW OVERRIDE
Verbatim (chat): `we have time to work with order processing automations paused until 17pm today - override`
→ Daily-ops (order-processing automations) may be paused NOW until 17:00 today; write lanes authorized in this window. Hard commitment: daily-ops resumed 10/10 BEFORE 17:00 (guard cron armed); DB-writing lanes must complete or stop at a step boundary by ~16:50. Remaining lanes roll to the 20:08 night window as planned.
