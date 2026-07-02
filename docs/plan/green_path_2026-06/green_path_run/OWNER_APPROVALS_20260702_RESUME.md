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
