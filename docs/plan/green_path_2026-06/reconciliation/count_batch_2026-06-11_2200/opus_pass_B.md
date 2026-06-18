# Warehouse Stock Count — Independent Transcription (OPUS PASS B)

**Count event:** 2026-06-11 22:00 +05 (Asia/Almaty), taken AFTER that day's daily shipping.
**Source folder:** `images/11.06.2026_22_00_00_after_daily_shipping/`
**Images:** 12 (all transcribed)
**Pass:** B of 3 (independent — no other pass consulted)
**Transcription order:** reverse-alphabetical filename (t-shirts first → 3_in_1_kids last)
**Reading method:** each image read bottom-to-top first, then re-verified top-to-bottom.

## Notation legend (owner-authoritative)
- **Dot-separated digits** (`1.1`, `2.1.1`) = component units to SUM → ADDITION on top of system estimated stock at this timestamp (restored canceled/returned orders back to sellable; source order IDs unrecoverable).
- **Number + right arrow** (`12→`) = FULL updated stock for that exact product/color/size at this timestamp → fully supersedes all prior snapshots for that size.
- **Empty size** (`S- ` nothing after dash) = NOT_CAPTURED → prior freshest snapshot stays authoritative.
- Filename hints semantics, but **INK WINS** over filename; conflicts flagged inline.

---

## IMAGE 1 — `t-shirts_white_and_t-shirts_black.JPG`

**(1) Product / color identification + raw label**
- Black-ink header: `Футболки коротким рукавом` (= T-shirts, short sleeve).
- Two sub-sections, each underlined: `белые` (white) and `черные` (black).
- Red-pen label: `ALL ADDITIONS` → all rows are dot/plain additions. No arrows present → consistent with filename.
- SKU family: short-sleeve t-shirts (generic men t-shirt family). White and Black colorways.

**(2) Transcription table**

| size | RAW ink | units | semantic | confidence |
|------|---------|------:|----------|------------|
| **WHITE (белые)** | | | | |
| L | `L - 5` | 5 | ADDITION | HIGH |
| XL | `XL - 1` | 1 | ADDITION | HIGH |
| 2XL | `2XL - 1` | 1 | ADDITION | HIGH |
| **BLACK (черные)** | | | | |
| L | `L - 3` | 3 | ADDITION | HIGH |
| XL | `XL - 2` | 2 | ADDITION | HIGH |

All values single digits, clear separation from dash. No ambiguity.

**(3) YAML**
```yaml
image: t-shirts_white_and_t-shirts_black.JPG
product_label_raw: "Футболки коротким рукавом / белые / черные | ALL ADDITIONS"
sku_guess: "MEN_TSHIRT_SHORTSLEEVE_WHITE / MEN_TSHIRT_SHORTSLEEVE_BLACK"
rows:
  - {size: L,   color: white, raw: "L - 5",   units: 5, semantic: ADDITION, confidence: HIGH}
  - {size: XL,  color: white, raw: "XL - 1",  units: 1, semantic: ADDITION, confidence: HIGH}
  - {size: 2XL, color: white, raw: "2XL - 1", units: 1, semantic: ADDITION, confidence: HIGH}
  - {size: L,   color: black, raw: "L - 3",   units: 3, semantic: ADDITION, confidence: HIGH}
  - {size: XL,  color: black, raw: "XL - 2",  units: 2, semantic: ADDITION, confidence: HIGH}
```

---

## IMAGE 2 — `line61_additions.JPG`

**(1) Product / color identification + raw label**
- Top header in blue ink: `6/1` (employee shorthand for **61** = SUIT-61). No color word visible → SUIT-61 default color (per canonical key `CL_NEW-CLO2_MEN_SUIT-61_BLACK`).
- Filename = `line61_additions` → all rows additions. INK CONFIRMS: every row is dot-separated with an employee-written `= N` sum on the right. No arrows.
- The employee pre-computed the sums in pen; I independently re-sum each below.

**(2) Transcription table** (read bottom→top, then verified top→bottom)

| size | RAW ink | my sum | employee `=` | units | semantic | confidence |
|------|---------|-------:|-------------:|------:|----------|------------|
| S   | `S - 1.`            | 1            | =1  | 1  | ADDITION | HIGH |
| M   | `M - 1`             | 1            | =1  | 1  | ADDITION | HIGH (1 in blue ink) |
| L   | `L - 3.3`           | 3+3=6        | =6  | 6  | ADDITION | HIGH |
| XL  | `XL - 6.7`          | 6+7=13       | =13 | 13 | ADDITION | HIGH |
| 2XL | `2XL - 3.7.`        | 3+7=10       | =10 | 10 | ADDITION | HIGH |
| 3XL | `3XL - 1.5.`        | 1+5=6        | =6  | 6  | ADDITION | HIGH |
| 4XL | `4XL - 1.2.`        | 1+2=3        | =3  | 3  | ADDITION | HIGH |

My independent sums match the employee's `=` annotations on all 7 rows. No conflicts.
- Minor: S value `1.` — single digit 1 with trailing dot (not `1.1`); employee `=1` confirms it is just 1.
- XL `6.7`: alternative read of first digit could be `6` vs `0`, but `=13` (6+7) confirms 6. HIGH.
- 2XL `3.7.`: `7` vs `1` for second digit — employee `=10` confirms 3+7. HIGH.

**(3) YAML**
```yaml
image: line61_additions.JPG
product_label_raw: "6/1 (SUIT-61)"
sku_guess: "CL_NEW-CLO2_MEN_SUIT-61_BLACK"
rows:
  - {size: S,   raw: "S - 1.",     units: 1,  semantic: ADDITION, confidence: HIGH}
  - {size: M,   raw: "M - 1",      units: 1,  semantic: ADDITION, confidence: HIGH}
  - {size: L,   raw: "L - 3.3",    units: 6,  semantic: ADDITION, confidence: HIGH}
  - {size: XL,  raw: "XL - 6.7",   units: 13, semantic: ADDITION, confidence: HIGH}
  - {size: 2XL, raw: "2XL - 3.7.", units: 10, semantic: ADDITION, confidence: HIGH}
  - {size: 3XL, raw: "3XL - 1.5.", units: 6,  semantic: ADDITION, confidence: HIGH}
  - {size: 4XL, raw: "4XL - 1.2.", units: 3,  semantic: ADDITION, confidence: HIGH}
```

---

## IMAGE 3 — `spider_rush_addition.JPG`

**(1) Product / color identification + raw label**
- Blue ink: `Спайдер` (= "Spider"). Single line below: `M - 1`.
- Filename `spider_rush_addition` → addition. INK CONFIRMS: plain single value, no arrow.
- SKU family: Spider (canonical roll-up lists "Spider black" → `CL_..._SPIDER_BLACK`). No color word on card → assume the single Spider colorway (black).

**(2) Transcription table**

| size | RAW ink | units | semantic | confidence |
|------|---------|------:|----------|------------|
| M | `M - 1` | 1 | ADDITION | HIGH |

**(3) YAML**
```yaml
image: spider_rush_addition.JPG
product_label_raw: "Спайдер"
sku_guess: "SPIDER_BLACK (men spider family)"
rows:
  - {size: M, raw: "M - 1", units: 1, semantic: ADDITION, confidence: HIGH}
```

---

## IMAGE 4 — `rush_white_and_rush_black.JPG`

**(1) Product / color identification + raw label**
- Black-ink header: `Футболки длинным рукавом` (= T-shirts, LONG sleeve; "rush" = long-sleeve tee per filename).
- Two underlined sub-sections: `белые` (white) and `черные` (black).
- Red-pen label: `ALL ADDITIONS`. No arrows → consistent with filename.
- SKU family: long-sleeve t-shirt ("rush") white / black.

**(2) Transcription table** (read bottom→top, then top→bottom)

| size | RAW ink | units | semantic | confidence |
|------|---------|------:|----------|------------|
| **WHITE (белые)** | | | | |
| S   | `S - 1`   | 1 | ADDITION | HIGH |
| M   | `M - 1`   | 1 | ADDITION | HIGH |
| L   | `L - 2`   | 2 | ADDITION | HIGH |
| 2XL | `2XL - 1` | 1 | ADDITION | HIGH |
| 3XL | `3XL - 1` | 1 | ADDITION | HIGH |
| **BLACK (черные)** | | | | |
| L   | `L - 1`   | 1 | ADDITION | HIGH |
| XL  | `XL - 1`  | 1 | ADDITION | HIGH |

All single digits, clean. No XL in white block; no S/M/2XL/3XL in black block (those rows simply absent on this card, not blank-dash → treat as not listed = no addition for those size/color cells).

**(3) YAML**
```yaml
image: rush_white_and_rush_black.JPG
product_label_raw: "Футболки длинным рукавом / белые / черные | ALL ADDITIONS"
sku_guess: "MEN_TSHIRT_LONGSLEEVE_WHITE / MEN_TSHIRT_LONGSLEEVE_BLACK (rush)"
rows:
  - {size: S,   color: white, raw: "S - 1",   units: 1, semantic: ADDITION, confidence: HIGH}
  - {size: M,   color: white, raw: "M - 1",   units: 1, semantic: ADDITION, confidence: HIGH}
  - {size: L,   color: white, raw: "L - 2",   units: 2, semantic: ADDITION, confidence: HIGH}
  - {size: 2XL, color: white, raw: "2XL - 1", units: 1, semantic: ADDITION, confidence: HIGH}
  - {size: 3XL, color: white, raw: "3XL - 1", units: 1, semantic: ADDITION, confidence: HIGH}
  - {size: L,   color: black, raw: "L - 1",   units: 1, semantic: ADDITION, confidence: HIGH}
  - {size: XL,  color: black, raw: "XL - 1",  units: 1, semantic: ADDITION, confidence: HIGH}
```

---

## IMAGE 5 — `line52_additions_but-S-full.JPG`

**(1) Product / color identification + raw label**
- Blue ink header: `ПРИНТ` (= PRINT → LINE52). No color word → canonical `CL_OC_MEN_LINE52_BLACK`.
- Filename `line52_additions_but-S-full` → S row is a FULL supersede, others additions.
- **INK CONFIRMS the hint:** `S - 72 →` has a clear right-pointing black arrow (FULL_SUPERSEDE). All other rows are dot-additions with employee `= N` sums. **No conflict.**
- Note: rows are written in a non-standard order on the card (S, L, M, XL, 3XL, 2XL, 4XL).

**(2) Transcription table** (read bottom→top, then top→bottom)

| size | RAW ink | my sum | employee `=` | units | semantic | confidence |
|------|---------|-------:|-------------:|------:|----------|------------|
| S   | `S - 72 →`            | n/a (arrow) | — | 72 | **FULL_SUPERSEDE** | HIGH |
| M   | `M - 2.3.`           | 2+3=5       | =5  | 5  | ADDITION | HIGH |
| L   | `L - 5.6.`           | 5+6=11      | =11 | 11 | ADDITION | HIGH |
| XL  | `XL - 5.7.`          | 5+7=12      | =12 | 12 | ADDITION | HIGH |
| 2XL | `2XL - [strike]10.10.`| 10+10=20   | =20 | 20 | ADDITION | **MED** |
| 3XL | `3XL - 5.8`          | 5+8=13      | =13 | 13 | ADDITION | HIGH |
| 4XL | `4XL - 1.`           | 1           | =1  | 1  | ADDITION | HIGH |

Notes / alternatives:
- **S `72`**: digits clear; alt `12`? No — first digit is a clear `7`, and the arrow + filename agree it is a full count of 72. HIGH FULL_SUPERSEDE.
- **2XL** `2XL - [scribble]10.10. = 20`: there is a struck-out/scribbled token immediately after the dash, then `10.10.`. Employee `=20` = 10+10, so the scribble is a self-correction and the two live components are 10 and 10. Units=20. Marked **MED** only because of the crossed-out token (could the intended value be different?), but the `=20` annotation is legible and self-consistent → 20 is the best reading. Alt (if scribble is a third live component): could be >20 — LOW-likelihood.
- L `5.6.` `=11` confirms; M `2.3.` `=5` confirms; XL `5.7.` `=12` confirms; 3XL `5.8` `=13` confirms. All HIGH.

**(3) YAML**
```yaml
image: line52_additions_but-S-full.JPG
product_label_raw: "ПРИНТ (LINE52) | S row arrow = full supersede"
sku_guess: "CL_OC_MEN_LINE52_BLACK"
rows:
  - {size: S,   raw: "S - 72 →",            units: 72, semantic: FULL_SUPERSEDE, confidence: HIGH}
  - {size: M,   raw: "M - 2.3.",            units: 5,  semantic: ADDITION, confidence: HIGH}
  - {size: L,   raw: "L - 5.6.",            units: 11, semantic: ADDITION, confidence: HIGH}
  - {size: XL,  raw: "XL - 5.7.",           units: 12, semantic: ADDITION, confidence: HIGH}
  - {size: 2XL, raw: "2XL - [strike]10.10.", units: 20, semantic: ADDITION, confidence: MED}
  - {size: 3XL, raw: "3XL - 5.8",           units: 13, semantic: ADDITION, confidence: HIGH}
  - {size: 4XL, raw: "4XL - 1.",            units: 1,  semantic: ADDITION, confidence: HIGH}
```

---

## IMAGE 6 — `berserk_t-shirts.JPG`

**(1) Product / color identification + raw label**
- Top-right black ink: `11.06.26г. время 22ч.00` → confirms the count event timestamp (2026-06-11 22:00).
- Section 1 header: `Берсерк белый коротки рукав` (= Berserk WHITE short sleeve).
- Section 2 header: `Берсерк черный коротки рукав` (= Berserk BLACK short sleeve).
- Red-pen label: `ALL ADDITIONS`. No arrows → consistent with filename.
- SKU family: "Berserk sleeveless/short" white & black (roll-up: "Berserk sleeveless white + black").

**(2) Transcription table** (read bottom→top, then top→bottom)

| size | RAW ink | units | semantic | confidence |
|------|---------|------:|----------|------------|
| **BERSERK WHITE (белый) — short sleeve** | | | | |
| S  | `S - 1`  | 1 | ADDITION | HIGH |
| L  | `L - 1`  | 1 | ADDITION | HIGH |
| XL | `XL - 1` | 1 | ADDITION | HIGH |
| **BERSERK BLACK (черный) — short sleeve** | | | | |
| M  | `M - 1`  | 1 | ADDITION | HIGH |
| XL | `XL - 1` | 1 | ADDITION | HIGH |

All single digits. Clean.

**(3) YAML**
```yaml
image: berserk_t-shirts.JPG
product_label_raw: "Берсерк белый коротки рукав / Берсерк черный коротки рукав | 11.06.26 22ч00 | ALL ADDITIONS"
sku_guess: "BERSERK_SHORTSLEEVE_WHITE / BERSERK_SHORTSLEEVE_BLACK"
rows:
  - {size: S,  color: white, raw: "S - 1",  units: 1, semantic: ADDITION, confidence: HIGH}
  - {size: L,  color: white, raw: "L - 1",  units: 1, semantic: ADDITION, confidence: HIGH}
  - {size: XL, color: white, raw: "XL - 1", units: 1, semantic: ADDITION, confidence: HIGH}
  - {size: M,  color: black, raw: "M - 1",  units: 1, semantic: ADDITION, confidence: HIGH}
  - {size: XL, color: black, raw: "XL - 1", units: 1, semantic: ADDITION, confidence: HIGH}
```

---

## IMAGE 7 — `berserk_rush.JPG`

**(1) Product / color identification + raw label**
- Section 1 header: `Берсерк белый длинный рукав` (= Berserk WHITE LONG sleeve / "rush").
- Section 2 header: `Берсерк черный длинный рукав` (= Berserk BLACK long sleeve).
- Red-pen label: `ALL ADDITIONS`. No arrows → consistent with filename.
- SKU family: "Berserk rush white + black" (long-sleeve Berserk).

**(2) Transcription table** (read bottom→top, then top→bottom)

| size | RAW ink | units | semantic | confidence |
|------|---------|------:|----------|------------|
| **BERSERK WHITE (белый) — long sleeve (rush)** | | | | |
| XL  | `XL - 2`  | 2 | ADDITION | HIGH |
| 2XL | `2XL - 1` | 1 | ADDITION | HIGH |
| **BERSERK BLACK (черный) — long sleeve (rush)** | | | | |
| L   | `L - 2`   | 2 | ADDITION | HIGH |
| XL  | `XL - 1`  | 1 | ADDITION | HIGH |
| 2XL | `2XL - 1` | 1 | ADDITION | HIGH |

All single digits. Clean.

**(3) YAML**
```yaml
image: berserk_rush.JPG
product_label_raw: "Берсерк белый длинный рукав / Берсерк черный длинный рукав | ALL ADDITIONS"
sku_guess: "BERSERK_RUSH_WHITE / BERSERK_RUSH_BLACK (long sleeve)"
rows:
  - {size: XL,  color: white, raw: "XL - 2",  units: 2, semantic: ADDITION, confidence: HIGH}
  - {size: 2XL, color: white, raw: "2XL - 1", units: 1, semantic: ADDITION, confidence: HIGH}
  - {size: L,   color: black, raw: "L - 2",   units: 2, semantic: ADDITION, confidence: HIGH}
  - {size: XL,  color: black, raw: "XL - 1",  units: 1, semantic: ADDITION, confidence: HIGH}
  - {size: 2XL, color: black, raw: "2XL - 1", units: 1, semantic: ADDITION, confidence: HIGH}
```

---

## IMAGE 8 — `line51_additions_but-S-full.JPG`

**(1) Product / color identification + raw label**
- Black-ink header: `черн. белый` (= "black. white") → the LINE51 black/white SET family (canonical `CL_OC_MEN_LINE51_WHITE` / LINE51 black-white family).
- Filename `line51_additions_but-S-full` → S full supersede, others additions.
- **INK CONFIRMS:** `S - [blot]82 →` has a clear right-pointing black arrow (FULL_SUPERSEDE). All other rows are dot-additions with employee `= N` sums. **No conflict.**

**(2) Transcription table** (read bottom→top, then top→bottom)

| size | RAW ink | my sum | employee `=` | units | semantic | confidence |
|------|---------|-------:|-------------:|------:|----------|------------|
| S   | `S - [blot]82 →`   | n/a (arrow) | — | 82 | **FULL_SUPERSEDE** | **MED** |
| M   | `M - 2.`           | 2           | =2 | 2 | ADDITION | HIGH |
| L   | `L - 4.2.`         | 4+2=6       | =6 | 6 | ADDITION | HIGH |
| XL  | `XL - 2.5.`        | 2+5=7       | =7 | 7 | ADDITION | HIGH |
| 2XL | `2XL - 2.2.`       | 2+2=4       | =4 | 4 | ADDITION | HIGH |
| 3XL | `3XL - 1.`         | 1           | =1 | 1 | ADDITION | HIGH |
| 4XL | `4XL - 1.`         | 1           | =1 | 1 | ADDITION | HIGH |

Notes / alternatives:
- **S `82`** marked **MED**: there is an ink blot/scribble immediately before the `82`. The two clear digits read `82`; the arrow makes it a full supersede. Alt readings of the blotted lead: could the blot hide a leading digit making it `182`/`282`? Low likelihood (blot looks like a struck false-start, and `82` sits cleanly after it), but flagged because the blot is directly on the number. Best reading: **82**. Alt: `82` vs (blot+`82`).
- M `2.` `=2`: single component 2 (the second dot has no second digit). HIGH.
- L `4.2.` `=6` confirms 4+2. XL `2.5.` `=7` confirms 2+5 (first digit `2` vs `7`? `=7`→2+5 fits, so 2). 2XL `2.2.` `=4` confirms. 3XL/4XL `1.` `=1` each. All HIGH.

**(3) YAML**
```yaml
image: line51_additions_but-S-full.JPG
product_label_raw: "черн. белый (LINE51 black/white set) | S row arrow = full supersede"
sku_guess: "CL_OC_MEN_LINE51_WHITE (LINE51 black-white family)"
rows:
  - {size: S,   raw: "S - [blot]82 →", units: 82, semantic: FULL_SUPERSEDE, confidence: MED}
  - {size: M,   raw: "M - 2.",         units: 2,  semantic: ADDITION, confidence: HIGH}
  - {size: L,   raw: "L - 4.2.",       units: 6,  semantic: ADDITION, confidence: HIGH}
  - {size: XL,  raw: "XL - 2.5.",      units: 7,  semantic: ADDITION, confidence: HIGH}
  - {size: 2XL, raw: "2XL - 2.2.",     units: 4,  semantic: ADDITION, confidence: HIGH}
  - {size: 3XL, raw: "3XL - 1.",       units: 1,  semantic: ADDITION, confidence: HIGH}
  - {size: 4XL, raw: "4XL - 1.",       units: 1,  semantic: ADDITION, confidence: HIGH}
```

---

## IMAGE 9 — `Rombik_men_and_kids_all-addtions.JPG`

**(1) Product / color identification + raw label**
- Blue ink header: `РОМБ` (= ROMBIK → `CL_NEW-CLO_MEN_ROMBIK_BLACK`; shared S pool men/kids; plus a kids `140/28` row at the bottom → `CL_NEW-CLO_KIDS_KID-31` shares Rombik).
- Red-pen label (bottom): `ALL ADDITIONS`. Red `XL` and `2XL` annotations on the right margin re-tag those two addition rows (employee clarifying which sizes they belong to). Red `=28` annotation tags the kids `140/28` row.
- **Mixed card:** several sizes carry values; several are written as `M-`, `L-`, `3XL-`, `4XL-` with NOTHING after the dash → **NOT_CAPTURED** (per owner rule, prior snapshot stays authoritative for these).

**(2) Transcription table** (read bottom→top, then top→bottom)

| size | RAW ink | my sum | employee `=` | units | semantic | confidence |
|------|---------|-------:|-------------:|------:|----------|------------|
| S   | `S - 1 = 1`        | 1     | =1 | 1 | ADDITION | HIGH |
| M   | `M -` (empty)      | —     | —  | — | **NOT_CAPTURED** | HIGH |
| L   | `L -` (empty)      | —     | —  | — | **NOT_CAPTURED** | HIGH |
| XL  | `XL - 2.1. = 3`    | 2+1=3 | =3 | 3 | ADDITION | HIGH |
| 2XL | `2XL - 2. = 2`     | 2     | =2 | 2 | ADDITION | HIGH |
| 3XL | `3XL -` (empty)    | —     | —  | — | **NOT_CAPTURED** | HIGH |
| 4XL | `4XL -` (empty)    | —     | —  | — | **NOT_CAPTURED** | HIGH |
| **KIDS** 140/28 | `140/28 - 1.1 = 2` | 1+1=2 | =2 | 2 | ADDITION | **MED** |

Notes / alternatives:
- S `1 = 1`: HIGH.
- XL `2.1. = 3`: two components 2 and 1 → 3. Red margin `XL` re-tags this row. HIGH. (Alt for components: `2.1` could be misread as `2.7`? No — `=3` confirms 2+1.)
- 2XL `2. = 2`: single component 2. Red margin `2XL` re-tags. HIGH.
- **Empty rows** `M- L- 3XL- 4XL-`: dash with no number after → NOT_CAPTURED. HIGH that they are empty (clearly nothing written after the dash).
- **Kids `140/28 - 1.1 = 2`** marked **MED**: a small sticky-note fragment partially overlaps the `140/28` token, and the red `=28` margin note refers to the size code (140/**28**), not a quantity. The components `1.1` (=2) and employee `=2` are legible. Alt: the obscured size code could be `140/26`? Unlikely (red `28` annotation confirms 140/**28**). Units=2. Flagged MED due to the sticky-note occlusion over the size label and the dual meaning of the red "28".

**(3) YAML**
```yaml
image: Rombik_men_and_kids_all-addtions.JPG
product_label_raw: "РОМБ (ROMBIK) | ALL ADDITIONS | red margin tags: XL, 2XL, =28"
sku_guess: "CL_NEW-CLO_MEN_ROMBIK_BLACK (+ shared S pool; kids row -> CL_NEW-CLO_KIDS_KID-31 140/28)"
rows:
  - {size: S,         raw: "S - 1 = 1",       units: 1, semantic: ADDITION,     confidence: HIGH}
  - {size: M,         raw: "M -",             units: 0, semantic: NOT_CAPTURED, confidence: HIGH}
  - {size: L,         raw: "L -",             units: 0, semantic: NOT_CAPTURED, confidence: HIGH}
  - {size: XL,        raw: "XL - 2.1. = 3",   units: 3, semantic: ADDITION,     confidence: HIGH}
  - {size: 2XL,       raw: "2XL - 2. = 2",    units: 2, semantic: ADDITION,     confidence: HIGH}
  - {size: 3XL,       raw: "3XL -",           units: 0, semantic: NOT_CAPTURED, confidence: HIGH}
  - {size: 4XL,       raw: "4XL -",           units: 0, semantic: NOT_CAPTURED, confidence: HIGH}
  - {size: "140/28",  raw: "140/28 - 1.1 = 2", units: 2, semantic: ADDITION,    confidence: MED, note: "kids; sticky-note overlaps size code"}
```

---

## IMAGE 10 — `HUS_addition.JPG`

**(1) Product / color identification + raw label**
- Blue ink header: `ХУС` (= HUS → HUS51; canonical roll-up "Hus51 green").
- Filename `HUS_addition` → additions. INK CONFIRMS: plain single values, no arrow.
- SKU family: HUS51 (green).

**(2) Transcription table** (read bottom→top, then top→bottom)

| size | RAW ink | units | semantic | confidence |
|------|---------|------:|----------|------------|
| XL  | `XL - 1`  | 1 | ADDITION | HIGH |
| 2XL | `2XL - 1` | 1 | ADDITION | HIGH |

Clean single digits.

**(3) YAML**
```yaml
image: HUS_addition.JPG
product_label_raw: "ХУС (HUS51)"
sku_guess: "HUS51_GREEN"
rows:
  - {size: XL,  raw: "XL - 1",  units: 1, semantic: ADDITION, confidence: HIGH}
  - {size: 2XL, raw: "2XL - 1", units: 1, semantic: ADDITION, confidence: HIGH}
```

---

## IMAGE 11 — `3_in_1_with_logotypes_complete_stock_snapshot.JPG`

**(1) Product / color identification + raw label**
- Blue ink header: `3/1 →` (= 3-in-1 MEN sets, with logotypes) followed by a right-pointing arrow, then an underline.
- Filename `3_in_1_..._complete_stock_snapshot` → expect full/arrow values. **INK CONFIRMS:** header carries an arrow → all rows are FULL_SUPERSEDE for the 3-in-1 men sets. No dot-additions present.
- SKU family: 3_in_1_men_sets (the 04.06 reference left it `UNMAPPED_3_IN_1_MEN_SETS`).
- Row order on card is non-standard: XL, 2XL, 3XL, 4XL, then L at the bottom. (No S, M, or 3XL-vs others beyond those listed.)

**(2) Transcription table** (read bottom→top, then top→bottom)

| size | RAW ink | units | semantic | confidence |
|------|---------|------:|----------|------------|
| L   | `L - 20`   | 20 | **FULL_SUPERSEDE** | HIGH |
| XL  | `XL - 44`  | 44 | **FULL_SUPERSEDE** | HIGH |
| 2XL | `2XL - 55` | 55 | **FULL_SUPERSEDE** | HIGH |
| 3XL | `3XL - 43` | 43 | **FULL_SUPERSEDE** | HIGH |
| 4XL | `4XL - 30` | 30 | **FULL_SUPERSEDE** | HIGH |

Notes / alternatives:
- The arrow is on the **header** (`3/1 →`), governing the whole card → every listed size is a full count.
- XL `44`: bold, clear. 2XL `55`: clear. 3XL `43`: clear. 4XL `30`: clear (0 not 6). L `20`: clear.
- Sizes S and M are NOT listed on this card. Because this is a "complete stock snapshot" with a header arrow, the absence of S/M is ambiguous: either those sizes are 0/out-of-range for 3-in-1, or simply not written. Per owner rule, a size with no ink = NOT_CAPTURED (prior snapshot authoritative). Flagged below as a semantic edge case, not an ink ambiguity.

**(3) YAML**
```yaml
image: 3_in_1_with_logotypes_complete_stock_snapshot.JPG
product_label_raw: "3/1 -> (3-in-1 men sets, with logotypes) | complete stock snapshot"
sku_guess: "3_IN_1_MEN_SETS (UNMAPPED_3_IN_1_MEN_SETS)"
rows:
  - {size: L,   raw: "L - 20",   units: 20, semantic: FULL_SUPERSEDE, confidence: HIGH}
  - {size: XL,  raw: "XL - 44",  units: 44, semantic: FULL_SUPERSEDE, confidence: HIGH}
  - {size: 2XL, raw: "2XL - 55", units: 55, semantic: FULL_SUPERSEDE, confidence: HIGH}
  - {size: 3XL, raw: "3XL - 43", units: 43, semantic: FULL_SUPERSEDE, confidence: HIGH}
  - {size: 4XL, raw: "4XL - 30", units: 30, semantic: FULL_SUPERSEDE, confidence: HIGH}
# NOTE: S and M not written on card -> NOT_CAPTURED for those sizes despite snapshot header.
```

---

## IMAGE 12 — `3_in_1_kids_complete_stock_snapshot.JPG`

**(1) Product / color identification + raw label**
- Blue ink header (far-left, written sideways): `3/1 ↗` (= 3-in-1 KIDS, with an up-right arrow). 
- Filename `3_in_1_kids_complete_stock_snapshot` → full/arrow values. **INK CONFIRMS:** header arrow → FULL_SUPERSEDE for all kids sizes. Canonical key `CL_NEW-CLO_KIDS_KID-31_BLACK`.
- **Difficult image:** written on a long cardboard strip held horizontally; all text is rotated ~90° and read bottom-to-top per column, left-to-right across the strip. A thumb/fingers partially occlude the `120/24` area, and the far-right edge is cut. Each size code (`height/age`) is paired with an `N шт.` (units) annotation. Underlines appear beneath several size codes.

**(2) Transcription table** (read across strip left→right; per the owner's bottom-to-top rule applied to the rotated text)

| size (height/age) | RAW ink | units | semantic | confidence |
|-------------------|---------|------:|----------|------------|
| 110/22 | `110/22 — 12 шт.` | 12 | **FULL_SUPERSEDE** | HIGH |
| 120/24 | `120/24 — [occluded] шт.` | ? | **FULL_SUPERSEDE** | **LOW** |
| 150/30 | `150/30 — 9 шт.` | 9 | **FULL_SUPERSEDE** | MED |
| 140/28 | `140/28 — 28 шт.` | 28 | **FULL_SUPERSEDE** | MED |
| 130/26 | `130/26 — 32 шт.` (alt 54) | 32 | **FULL_SUPERSEDE** | **LOW** |
| (far-right edge) | `... 54 шт.` | 54 | **FULL_SUPERSEDE** (size code cut off) | **LOW** |

Detailed ambiguity notes / alternatives (this image is the lowest-confidence of the batch):
- **110/22 = 12 шт.**: clearest pair on the strip; "12 шт." legible directly with the size. HIGH.
- **120/24**: the quantity is OCCLUDED by the holder's thumb (a strike/mark is visible above it but the digits are hidden). I cannot read the units. **LOW / unreadable** — recommend a re-shoot. The 04.06 reference had 120/24 = 9 (do NOT carry that here; this is a fresh full snapshot, value unknown).
- **150/30 = 9 шт.**: "9 шт." legible and grouped with 150/30. MED (the `9` vs `4`/`g`-loop is slightly open; `9` is best). Underlined.
- **140/28 = 28 шт.**: "28 шт." legible. MED — risk of confusing the size-code "28" with the quantity "28" (they coincidentally match here). Best read units=28.
- **130/26**: appears paired with **32 шт.** in the middle-right, BUT there is also a **"54 шт."** token at the far-right cut edge. Two competing readings:
  - (a) 130/26 = 32 шт., and the far-right "54 шт." belongs to a 6th size whose code is cut off; OR
  - (b) 130/26 = 54 шт. (matches 04.06 reference value of 54 for 130/26) and the "32" belongs to 140/28 instead.
  The spatial pairing is genuinely ambiguous because of rotation + the cut edge. I record 130/26 = 32 as primary but flag **LOW**, alt = 54.
- **Far-right "54 шт."**: size code is cut off by the box edge. Cannot confirm which size. **LOW.**
- Canonical kids31 has exactly 5 sizes (110/22, 120/24, 130/26, 140/28, 150/30). I can see all 5 size codes on the strip, yet there appear to be SIX "N шт." style tokens (12, [occluded], 9, 28, 32, 54) once the cut-off right token is counted — i.e. one too many quantities for five sizes. This strongly implies one of {32, 54} is the same size's value double-read, or the occluded 120/24 value is one of them. **The kids quantities (except 110/22) are NOT reliably recoverable from this photo — recommend a re-shoot / second photo of the right half and the thumb-covered 120/24.**

**(3) YAML**
```yaml
image: 3_in_1_kids_complete_stock_snapshot.JPG
product_label_raw: "3/1 ↗ (3-in-1 KIDS) | complete stock snapshot | written sideways on long strip"
sku_guess: "CL_NEW-CLO_KIDS_KID-31_BLACK"
rows:
  - {size: "110/22", raw: "110/22 - 12 шт.",        units: 12,   semantic: FULL_SUPERSEDE, confidence: HIGH}
  - {size: "120/24", raw: "120/24 - [occluded] шт.", units: null, semantic: FULL_SUPERSEDE, confidence: LOW, note: "thumb occludes qty - UNREADABLE, re-shoot"}
  - {size: "150/30", raw: "150/30 - 9 шт.",         units: 9,    semantic: FULL_SUPERSEDE, confidence: MED}
  - {size: "140/28", raw: "140/28 - 28 шт.",        units: 28,   semantic: FULL_SUPERSEDE, confidence: MED, alt_units: null}
  - {size: "130/26", raw: "130/26 - 32 шт.",        units: 32,   semantic: FULL_SUPERSEDE, confidence: LOW, alt_units: 54}
  - {size: "UNKNOWN_right_edge", raw: "... 54 шт.", units: 54,   semantic: FULL_SUPERSEDE, confidence: LOW, note: "size code cut off at box edge; may be the 130/26 value"}
# WARNING: kids quantities (except 110/22) are unreliable in this photo. Six qty-tokens for five canonical sizes. Re-shoot required.
```

---

# BATCH ROLL-UP

## A. Per-product ADDITION totals (units to ADD on top of system estimate)

| Product (color) | Source image | Addition rows (size:units) | Additions total |
|-----------------|--------------|----------------------------|----------------:|
| T-shirt short-sleeve WHITE | img1 | L:5, XL:1, 2XL:1 | 7 |
| T-shirt short-sleeve BLACK | img1 | L:3, XL:2 | 5 |
| SUIT-61 (black) | img2 | S:1, M:1, L:6, XL:13, 2XL:10, 3XL:6, 4XL:3 | 40 |
| Spider (black) | img3 | M:1 | 1 |
| T-shirt long-sleeve "rush" WHITE | img4 | S:1, M:1, L:2, 2XL:1, 3XL:1 | 6 |
| T-shirt long-sleeve "rush" BLACK | img4 | L:1, XL:1 | 2 |
| LINE52 (black) — additions only | img5 | M:5, L:11, XL:12, 2XL:20, 3XL:13, 4XL:1 | 62 |
| Berserk short-sleeve WHITE | img6 | S:1, L:1, XL:1 | 3 |
| Berserk short-sleeve BLACK | img6 | M:1, XL:1 | 2 |
| Berserk rush (long) WHITE | img7 | XL:2, 2XL:1 | 3 |
| Berserk rush (long) BLACK | img7 | L:2, XL:1, 2XL:1 | 4 |
| LINE51 (black/white set) — additions only | img8 | M:2, L:6, XL:7, 2XL:4, 3XL:1, 4XL:1 | 21 |
| ROMBIK (black, men) — additions only | img9 | S:1, XL:3, 2XL:2 | 6 |
| ROMBIK / KIDS 140/28 | img9 | 140/28:2 | 2 |
| HUS51 (green) | img10 | XL:1, 2XL:1 | 2 |
| **ADDITIONS GRAND TOTAL** | | | **166** |

(ADDITIONS grand total breakdown sanity: 7+5+40+1+6+2+62+3+2+3+4+21+6+2+2 = **166**.)

## B. Per-product FULL_SUPERSEDE values (replace prior snapshot for that exact size)

| Product (color) | Source image | Size | Supersede value |
|-----------------|--------------|------|----------------:|
| LINE52 (black) | img5 | S | 72 |
| LINE51 (black/white set) | img8 | S | 82 *(MED — ink blot on number)* |
| 3-in-1 MEN sets | img11 | L | 20 |
| 3-in-1 MEN sets | img11 | XL | 44 |
| 3-in-1 MEN sets | img11 | 2XL | 55 |
| 3-in-1 MEN sets | img11 | 3XL | 43 |
| 3-in-1 MEN sets | img11 | 4XL | 30 |
| 3-in-1 KIDS (kid-31 black) | img12 | 110/22 | 12 |
| 3-in-1 KIDS | img12 | 120/24 | **UNREADABLE** *(LOW — occluded)* |
| 3-in-1 KIDS | img12 | 150/30 | 9 *(MED)* |
| 3-in-1 KIDS | img12 | 140/28 | 28 *(MED)* |
| 3-in-1 KIDS | img12 | 130/26 | 32 *(LOW; alt 54)* |
| 3-in-1 KIDS | img12 | (edge, size cut off) | 54 *(LOW)* |

**Supersede row count:** 13 rows carry an arrow-driven full value (2 single-size S supersedes on line52 & line51 + 5 rows on 3-in-1 men + 6 tokens on 3-in-1 kids). Of these, the 3-in-1-kids rows are low/med reliability.

## C. NOT_CAPTURED rows (prior freshest snapshot remains authoritative)

| Product | Image | Sizes left blank (`size-` with no value) |
|---------|-------|------------------------------------------|
| ROMBIK men (black) | img9 | M, L, 3XL, 4XL |

## D. Semantic edge notes
- **LINE51 S** (img8) is a FULL supersede here (S=82), reversing the 04.06 situation where LINE51 S was "not re-provided". Ink arrow is authoritative.
- **LINE52** (img5): mixed card — S is a full supersede (72) while M–4XL are additions. The 04.06 batch treated line52 as a full "update". Downstream must apply S=72 as replacement AND add the M–4XL deltas on top of the latest line52 per-size totals.
- **3-in-1 MEN** (img11) lists only L/XL/2XL/3XL/4XL — S and M absent (NOT_CAPTURED for those two sizes despite the snapshot label).
- **No filename↔ink conflicts** were found. Every "addition(s)" file contained additions; both "but-S-full" files showed the S-row arrow as promised; both "complete_stock_snapshot" files carried header arrows. INK and FILENAME agree throughout.

---

# FLAT LIST — EVERY MED / LOW CONFIDENCE CELL

| # | Image | Product | Size | Reading | Conf | Alternative / reason |
|---|-------|---------|------|---------|------|----------------------|
| 1 | img5 | LINE52 (black) | 2XL | 20 (10+10) | MED | Struck-out token before `10.10.`; employee `=20` supports 10+10. Alt: >20 if scribble is a live 3rd component. |
| 2 | img8 | LINE51 set | S | 82 (full) | MED | Ink blot directly on the number before `82`. Alt: leading digit hidden → 182/282 (low likelihood). |
| 3 | img9 | ROMBIK/KIDS | 140/28 | 2 (1+1) | MED | Sticky-note fragment overlaps the `140/28` size code; red `=28` is the size suffix not a qty. Components `1.1`→2 legible. |
| 4 | img12 | 3-in-1 KIDS | 120/24 | UNREADABLE | LOW | Thumb occludes the quantity entirely. Re-shoot required. |
| 5 | img12 | 3-in-1 KIDS | 150/30 | 9 | MED | `9` loop slightly open; alt `4`. |
| 6 | img12 | 3-in-1 KIDS | 140/28 | 28 | MED | Qty `28` coincides with size-code `28`; pairing risk. |
| 7 | img12 | 3-in-1 KIDS | 130/26 | 32 | LOW | Alt 54 (matches 04.06 ref); competing `32` vs `54` tokens due to rotation + cut edge. |
| 8 | img12 | 3-in-1 KIDS | (right-edge size cut off) | 54 | LOW | Size code cut off by box edge; may actually be the 130/26 value (double-count risk). |

**Total MED/LOW cells: 8** (3 MED on men/print/beli + kids140/28 MED; 4 LOW/MED concentrated in the 3-in-1 KIDS strip image).

**Single biggest data-quality risk:** Image 12 (3-in-1 kids) — only 110/22=12 is HIGH; the other kids quantities are unreliable (thumb occlusion on 120/24, ambiguous 32-vs-54 pairing, six qty-tokens for five canonical sizes). Recommend a clean re-shoot of that cardboard strip before ingesting kids 3-in-1 full-supersede values.
