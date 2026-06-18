# Count batch 2026-06-11 22:00 +05 — CANONICAL CONSENSUS (3-pass OCR reconciliation)

**Event**: single count, 2026-06-11 22:00 +05, taken AFTER that day's daily shipping (ink timestamp on `berserk_t-shirts.JPG`: «11.06.26г. время 22ч.00»).
**Passes**: opus_pass_A.md (alphabetical), opus_pass_B.md (reverse + bottom-up), codex_pass_C.md (independent CLI) — mutually blind.
**Owner override**: `owner_overrides.yaml` — kids 120/24 = 9 (thumb occlusion resolved by owner reading the physical sheet).
**Consensus rule**: 2-of-3 agreement; owner override outranks all passes; residual alternatives listed in §3 (none blocking).
**Semantics** (owner-authoritative): ADDITION = restored canceled/returned units, order IDs unrecoverable → import as governed re-entry events, reason `RESTORED_CANCEL_RETURN_NO_ORDER_LINK`, anchored at 2026-06-11 22:00, ON TOP of the system's estimated stock at that timestamp. FULL_SUPERSEDE = complete stock for that size at that timestamp, replaces all prior. NOT_CAPTURED = prior freshest snapshot stays authoritative.

## 1. Consensus values (machine-readable)

```yaml
batch:
  event_ts: "2026-06-11 22:00 +05"
  anchor: after_daily_shipping_2026-06-11
  semantics_version: owner_session_2026-06-13
products:
  - label_raw: "3/1 (kids strip, header arrow)"
    family_guess: CL_NEW-CLO_KIDS_KID-31_BLACK
    image: 3_in_1_kids_complete_stock_snapshot.JPG
    mode: FULL_SUPERSEDE_SNAPSHOT
    rows:
      - {size: "110/22", units: 12, votes: "3/3", confidence: HIGH}
      - {size: "120/24", units: 9,  votes: "A+C+OWNER", confidence: OWNER_CONFIRMED}
      - {size: "130/26", units: 54, votes: "A+C (B low-conf mispairing)", confidence: HIGH}
      - {size: "140/28", units: 32, votes: "A+C", confidence: MED, alt: 33}
      - {size: "150/30", units: 28, votes: "A+C", confidence: MED, alt: 29}
    snapshot_total: 135   # vs 137 on 06-04 — coherent post-shipping drift
  - label_raw: "3/1 → (with logotypes)"
    family_guess: "3_in_1_with_logotypes (mapping flag F-1: may be DISTINCT from 06-04 'UNMAPPED_3_IN_1_MEN_SETS')"
    image: 3_in_1_with_logotypes_complete_stock_snapshot.JPG
    mode: FULL_SUPERSEDE_SNAPSHOT
    rows:
      - {size: L,   units: 20, votes: "3/3", confidence: HIGH}
      - {size: XL,  units: 44, votes: "3/3", confidence: HIGH}
      - {size: 2XL, units: 55, votes: "3/3", confidence: HIGH}
      - {size: 3XL, units: 43, votes: "3/3", confidence: HIGH}
      - {size: 4XL, units: 30, votes: "3/3", confidence: HIGH}
      - {size: S, semantic: NOT_CAPTURED}
      - {size: M, semantic: NOT_CAPTURED}
    snapshot_total_listed: 192
  - label_raw: "ХУС"
    family_guess: HUS51_GREEN (color inferred, not in ink)
    image: HUS_addition.JPG
    mode: ADDITION
    rows:
      - {size: XL,  units: 1, votes: "3/3", confidence: HIGH}
      - {size: 2XL, units: 1, votes: "3/3", confidence: HIGH}
  - label_raw: "РОМБ + red tags =XL =2XL =28 + ALL ADDITIONS"
    family_guess: "CL_NEW-CLO_MEN_ROMBIK_BLACK (+ kids ROMBIK row 140/28)"
    image: Rombik_men_and_kids_all-addtions.JPG
    mode: ADDITION
    rows:
      - {size: S,        units: 1, votes: "3/3", confidence: HIGH, note: "shared men/kids S pool per 06-04 convention"}
      - {size: XL,       units: 3, votes: "3/3", confidence: HIGH, raw: "2.1.=3"}
      - {size: 2XL,      units: 2, votes: "3/3", confidence: HIGH, raw: "2.=2"}
      - {size: "140/28", units: 2, votes: "3/3", confidence: HIGH, raw: "1.1=2", scope: kids_rombik}
      - {size: M,   semantic: NOT_CAPTURED}
      - {size: L,   semantic: NOT_CAPTURED}
      - {size: 3XL, semantic: NOT_CAPTURED, note: "A saw struck dash (alt: intended 0) — 2/3 read clean empty"}
      - {size: 4XL, semantic: NOT_CAPTURED}
  - label_raw: "черн. белый (arrow on S row only)"
    family_guess: CL_OC_MEN_LINE51_WHITE (LINE51 black/white set)
    image: line51_additions_but-S-full.JPG
    mode: MIXED_S_FULL_REST_ADDITION
    rows:
      - {size: S,   units: 82, semantic: FULL_SUPERSEDE, votes: "3/3 (all MED: ink blot precedes 82)", confidence: MED_CONSENSUS, alt: "leading digit under blot (low likelihood)"}
      - {size: M,   units: 2, semantic: ADDITION, votes: "3/3", confidence: HIGH}
      - {size: L,   units: 6, semantic: ADDITION, votes: "3/3", confidence: HIGH, raw: "4.2.=6"}
      - {size: XL,  units: 7, semantic: ADDITION, votes: "3/3", confidence: HIGH, raw: "2.5.=7"}
      - {size: 2XL, units: 4, semantic: ADDITION, votes: "3/3", confidence: HIGH, raw: "2.2.=4"}
      - {size: 3XL, units: 1, semantic: ADDITION, votes: "3/3", confidence: HIGH}
      - {size: 4XL, units: 1, semantic: ADDITION, votes: "3/3", confidence: HIGH}
  - label_raw: "Берсерк белый/черный длинный рукав + ALL ADDITIONS"
    family_guess: BERSERK_RUSH_WHITE / BERSERK_RUSH_BLACK
    image: berserk_rush.JPG
    mode: ADDITION
    rows:
      - {color: white, size: XL,  units: 2, votes: "3/3", confidence: HIGH}
      - {color: white, size: 2XL, units: 1, votes: "3/3", confidence: HIGH}
      - {color: black, size: L,   units: 2, votes: "3/3", confidence: HIGH}
      - {color: black, size: XL,  units: 1, votes: "3/3", confidence: HIGH}
      - {color: black, size: 2XL, units: 1, votes: "3/3", confidence: HIGH}
  - label_raw: "Берсерк белый/черный коротки рукав + ALL ADDITIONS + ink timestamp 11.06.26 22ч00"
    family_guess: BERSERK_SHORTSLEEVE_WHITE / BERSERK_SHORTSLEEVE_BLACK ("Berserk sleeveless" family in 06-04 roll-up)
    image: berserk_t-shirts.JPG
    mode: ADDITION
    rows:
      - {color: white, size: S,  units: 1, votes: "3/3", confidence: HIGH}
      - {color: white, size: L,  units: 1, votes: "3/3", confidence: HIGH}
      - {color: white, size: XL, units: 1, votes: "3/3", confidence: HIGH}
      - {color: black, size: M,  units: 1, votes: "3/3", confidence: HIGH}
      - {color: black, size: XL, units: 1, votes: "3/3", confidence: HIGH}
  - label_raw: "ПРИНТ (arrow on S row only)"
    family_guess: CL_OC_MEN_LINE52_BLACK
    image: line52_additions_but-S-full.JPG
    mode: MIXED_S_FULL_REST_ADDITION
    rows:
      - {size: S,   units: 72, semantic: FULL_SUPERSEDE, votes: "3/3", confidence: HIGH}
      - {size: M,   units: 5,  semantic: ADDITION, votes: "3/3", confidence: HIGH, raw: "2.3.=5"}
      - {size: L,   units: 11, semantic: ADDITION, votes: "3/3", confidence: HIGH, raw: "5.6.=11"}
      - {size: XL,  units: 12, semantic: ADDITION, votes: "3/3", confidence: HIGH, raw: "5.7.=12"}
      - {size: 2XL, units: 20, semantic: ADDITION, votes: "3/3", confidence: MED, raw: "(struck token)10.10.=20", note: "employee =20 legible; struck token = self-correction"}
      - {size: 3XL, units: 13, semantic: ADDITION, votes: "3/3", confidence: HIGH, raw: "5.8=13"}
      - {size: 4XL, units: 1,  semantic: ADDITION, votes: "3/3", confidence: HIGH}
  - label_raw: "Футболки длинным рукавом / белые / черные + ALL ADDITIONS"
    family_guess: "RUSH_WHITE / RUSH_BLACK (mapping flag F-2)"
    image: rush_white_and_rush_black.JPG
    mode: ADDITION
    rows:
      - {color: white, size: S,   units: 1, votes: "3/3", confidence: HIGH}
      - {color: white, size: M,   units: 1, votes: "3/3", confidence: HIGH}
      - {color: white, size: L,   units: 2, votes: "3/3", confidence: HIGH}
      - {color: white, size: 2XL, units: 1, votes: "3/3", confidence: HIGH}
      - {color: white, size: 3XL, units: 1, votes: "3/3", confidence: HIGH}
      - {color: black, size: L,   units: 1, votes: "3/3", confidence: HIGH}
      - {color: black, size: XL,  units: 1, votes: "3/3", confidence: HIGH}
  - label_raw: "Спайдер"
    family_guess: SPIDER_BLACK (color inferred; filename word 'rush' NOT in ink)
    image: spider_rush_addition.JPG
    mode: ADDITION
    rows:
      - {size: M, units: 1, votes: "3/3", confidence: HIGH}
  - label_raw: "6/1"
    family_guess: CL_NEW-CLO2_MEN_SUIT-61_BLACK
    image: line61_additions.JPG
    mode: ADDITION   # no arrow anywhere; S row carries a dot → ADDITION (all 3 passes agree)
    rows:
      - {size: S,   units: 1,  votes: "3/3", confidence: HIGH}
      - {size: M,   units: 1,  votes: "3/3", confidence: HIGH}
      - {size: L,   units: 6,  votes: "3/3", confidence: HIGH, raw: "3.3=6"}
      - {size: XL,  units: 13, votes: "3/3", confidence: HIGH, raw: "6.7=13"}
      - {size: 2XL, units: 10, votes: "3/3", confidence: HIGH, raw: "3.7.=10"}
      - {size: 3XL, units: 6,  votes: "3/3", confidence: HIGH, raw: "1.5.=6"}
      - {size: 4XL, units: 3,  votes: "3/3", confidence: HIGH, raw: "1.2.=3"}
  - label_raw: "Футболки коротким рукавом / белые / черные + ALL ADDITIONS"
    family_guess: "T-SHIRT short-sleeve WHITE / BLACK (mapping flag F-3)"
    image: t-shirts_white_and_t-shirts_black.JPG
    mode: ADDITION
    rows:
      - {color: white, size: L,   units: 5, votes: "3/3", confidence: HIGH}
      - {color: white, size: XL,  units: 1, votes: "3/3", confidence: HIGH}
      - {color: white, size: 2XL, units: 1, votes: "3/3", confidence: HIGH}
      - {color: black, size: L,   units: 3, votes: "3/3", confidence: HIGH}
      - {color: black, size: XL,  units: 2, votes: "3/3", confidence: HIGH}
totals:
  additions_grand_total: 166   # pass A reported 165 via an arithmetic slip in its own roll-up (its t-shirt rows sum 12, it wrote 11); row-level values identical across passes
  full_supersede_rows: 12      # line52 S=72, line51 S=82, 3-in-1 logotypes L/XL/2XL/3XL/4XL, kids 110/22, 120/24, 130/26, 140/28, 150/30
  not_captured_cells: 8        # rombik M/L/3XL/4XL; 3-in-1 logotypes S/M; (kids/none others)
```

## 2. Cross-pass verdict

Row-level agreement was 3/3 on every cell except the kids strip, where pass B mispaired rotated size/qty tokens and flagged itself LOW; passes A and C agree exactly and the owner confirmed the one occluded cell (120/24=9). B's "six tokens for five sizes" resolves as its own double-count of the cut-edge «54». No filename↔ink semantic conflicts anywhere (both `but-S-full` arrows confirmed; both snapshot header-arrows confirmed; all addition cards arrow-free).

## 3. Residual cells for passive owner glance (NONE blocking; ledger reconciliation will catch 1-unit residues)

| Cell | Taken | Alt | Why |
|---|---|---|---|
| LINE51 S | **82** FULL | leading digit under ink blot | 3/3 read 82; same-photo correlated risk; high stakes (S re-enters the count-gated LINE51 tranche basis) |
| kids 140/28 | **32** FULL | 33 | last-digit ambiguity; 06-04 had 33 → either 1 shipped or misread |
| kids 150/30 | **28** FULL | 29 | same pattern; 06-04 had 29 |
| LINE52 2XL | **+20** | >20 if struck token were live | employee «=20» + components 10+10 agree |
| ROMBIK 3XL | NOT_CAPTURED | intended 0 | 2/3 read clean empty dash |

## 4. Family-mapping flags → PKT-STOCK (dim_sku resolution at import time, not OCR's call)

- **F-1**: «3/1 with logotypes» FULL snapshot (192 across L–4XL) vs 06-04 «3_in_1_men_sets» (273; S58 M30 L45 XL65 2XL47 3XL28, 4XL absent) — 2XL/3XL rose and 4XL appeared, so this may be a DIFFERENT product (logotype variant) rather than a supersede of the 06-04 set. Resolve against dim_sku/offer catalog before applying as supersede.
- **F-2**: «Футболки длинным рукавом» = RUSH family per filename (RUSH_WHITE +6 incl. S1 M1 L2 2XL1 3XL1; RUSH_BLACK +2) — note RUSH_WHITE is an OD-033 relist family; these restored units raise its sellable base.
- **F-3**: «Футболки коротким рукавом» = T-SHIRT family per filename (WHITE +7, BLACK +5) — T-SHIRT_BLACK is the other OD-033 relist family. Distinct from «Берсерк коротки рукав» (separate sheet, explicit Берсерк ink) and likely distinct from NIKE-SHIRT (which has its own 06-04 matrix) — confirm in dim_sku.
- Color inferences (HUS→green, Spider→black) from the 06-04 family table, not ink.

## 5. Import order (binds into OD-004 precedence chain)

INBOUND booking (PO-1A, PO-1O, ARC-1 correction) → 05-30 batch → 06-04 artifact → 06-04 photo batch (per its merge rules) → **THIS batch last** (FULL_SUPERSEDE rows replace; ADDITION rows add as `RESTORED_CANCEL_RETURN_NO_ORDER_LINK` re-entry events; NOT_CAPTURED rows untouched) → then snapshot/ledger reconciliation (G-STOCK-03) over the result.
