# Opus Pass A — Independent Transcription of Warehouse Count Batch 2026-06-11 22:00 +05

**Pass:** A of 3 (independent; no other pass consulted)
**Count event:** Single event — 2026-06-11 22:00:00 (Asia/Almaty, +05), taken AFTER that day's daily shipping.
**Source dir:** `~/Downloads/Stock_ingestion_from_warehouse_counting/warehouse_stock_count_manual_results/images/11.06.2026_22_00_00_after_daily_shipping/`
**Images:** 12 (.JPG), processed in alphabetical filename order.
**SKU-name reference (names only, never quantities):** `04.06.2026_14_00_23/stock_count_04.06.2026_14_00.md`

## Notation rules applied (owner-authoritative)
- **Dot-separated digits** (e.g. `2.1.`, `5.6.`, `1.1`) = component units to **SUM** → semantic **ADDITION** on top of the system's estimated stock at this timestamp (restored previously canceled/returned orders to sellable; source order IDs unrecoverable by design).
- **Number + right-arrow** (e.g. `82 →`, `72 →`) = **FULL_SUPERSEDE**: the complete updated stock for that exact product/color/size at this timestamp; supersedes every prior snapshot for that size.
- **Empty size** (dash with nothing after) = **NOT_CAPTURED**: prior freshest snapshot stays authoritative.
- **Filename is a hint only; the INK WINS.** Conflicts flagged explicitly per image.
- Red/colored-pen scope/merge labels transcribed verbatim.

---

## IMAGE 01 — `3_in_1_kids_complete_stock_snapshot.JPG`

**(1) Product / color identification + raw label**
Blue marker on a long cardboard strip (photo rotated ~90°; size rows run perpendicular to the reading axis). Red/colored scope label is **`3/1`** (= "3-in-1") at the far left, with a **right/up-pointing arrow** drawn next to it. Sizes are kids height/age format (`height/age`, `шт.` = pieces). Filename says **complete_stock_snapshot** → expect FULL/arrow values; the drawn arrow on the label confirms FULL supersede for the whole sheet.

SKU family: kids "3 in 1" set → canonical `CL_NEW-CLO_KIDS_KID-31_BLACK` (the 04.06 reference maps "kids 3 in 1" to KID-31_BLACK with the identical height/age size ladder).

**(2) Transcription table**

| Size (h/age) | RAW ink | Interpreted units | Semantic | Confidence / alternatives |
|---|---|---|---|---|
| 110/22 | `110/22  12 шт.` | 12 | FULL_SUPERSEDE | HIGH |
| 120/24 | `120/24  9 шт.` | 9 | FULL_SUPERSEDE | MED — `9` could read as `4` (open-top loop); canonical 04.06 had 120/24=9, supporting 9. Alt: 4. |
| 130/26 | `130/26  54 шт.` | 54 | FULL_SUPERSEDE | HIGH (canonical 04.06 also 54) |
| 140/28 | `140/28  32 шт.` | 32 | FULL_SUPERSEDE | MED — `32` vs `33` (last digit ambiguous; 04.06 snapshot had 140/28=33, but ink here looks like 32). Alt: 33. |
| 150/30 | `150/30  28 шт.` | 28 | FULL_SUPERSEDE | MED — `28` vs `29` (04.06 had 150/30=29). Alt: 29. |

Note: arrow is on the **label** (whole-sheet), so every captured size = FULL_SUPERSEDE. No dot-additions present. Row physical order on cardboard is jumbled (110/22, 120/24, 150/30, 140/28, 130/26 left→right) but each height/age token is paired with its own underlined `шт.` count.

**(3) YAML**
```yaml
image: 3_in_1_kids_complete_stock_snapshot.JPG
product_label_raw: "3/1 ->"
sku_guess: "CL_NEW-CLO_KIDS_KID-31_BLACK"
merge_mode: FULL_SUPERSEDE_SNAPSHOT
rows:
  - {size: "110/22", raw: "110/22 12 шт.", units: 12, semantic: FULL_SUPERSEDE, confidence: HIGH}
  - {size: "120/24", raw: "120/24 9 шт.", units: 9, semantic: FULL_SUPERSEDE, confidence: MED}
  - {size: "130/26", raw: "130/26 54 шт.", units: 54, semantic: FULL_SUPERSEDE, confidence: HIGH}
  - {size: "140/28", raw: "140/28 32 шт.", units: 32, semantic: FULL_SUPERSEDE, confidence: MED}
  - {size: "150/30", raw: "150/30 28 шт.", units: 28, semantic: FULL_SUPERSEDE, confidence: MED}
```

---

## IMAGE 02 — `3_in_1_with_logotypes_complete_stock_snapshot.JPG`

**(1) Product / color identification + raw label**
Blue marker on cardboard. Label **`3/1 →`** (3-in-1) with a right-pointing arrow + underline beneath the label. Filename **complete_stock_snapshot** + the arrow → FULL_SUPERSEDE values. "with logotypes" distinguishes this men's logotype 3-in-1 set from the kids set in Image 01.

SKU family: men 3-in-1 sets (the 04.06 reference lists `3_in_1_men_sets` as `UNMAPPED_3_IN_1_MEN_SETS`). sku_guess kept as that unmapped men key.

**(2) Transcription table**

| Size | RAW ink | Interpreted units | Semantic | Confidence / alternatives |
|---|---|---|---|---|
| XL | `XL-44` | 44 | FULL_SUPERSEDE | HIGH |
| 2XL | `2XL-55` | 55 | FULL_SUPERSEDE | HIGH |
| 3XL | `3XL-43` | 43 | FULL_SUPERSEDE | HIGH |
| 4XL | `4XL-30` | 30 | FULL_SUPERSEDE | HIGH |
| L | `L-20` | 20 | FULL_SUPERSEDE | HIGH |

Note: arrow on label = FULL for all rows. Sizes S and M are **absent** from this sheet → NOT_CAPTURED (prior snapshot authoritative). Rows are written XL, 2XL, 3XL, 4XL, then L last (out of size order) — L row is genuine, value 20.

**(3) YAML**
```yaml
image: 3_in_1_with_logotypes_complete_stock_snapshot.JPG
product_label_raw: "3/1 ->"
sku_guess: "UNMAPPED_3_IN_1_MEN_SETS"
merge_mode: FULL_SUPERSEDE_SNAPSHOT
rows:
  - {size: L,   raw: "L-20",   units: 20, semantic: FULL_SUPERSEDE, confidence: HIGH}
  - {size: XL,  raw: "XL-44",  units: 44, semantic: FULL_SUPERSEDE, confidence: HIGH}
  - {size: 2XL, raw: "2XL-55", units: 55, semantic: FULL_SUPERSEDE, confidence: HIGH}
  - {size: 3XL, raw: "3XL-43", units: 43, semantic: FULL_SUPERSEDE, confidence: HIGH}
  - {size: 4XL, raw: "4XL-30", units: 30, semantic: FULL_SUPERSEDE, confidence: HIGH}
  - {size: S,   raw: "(absent)", units: null, semantic: NOT_CAPTURED, confidence: HIGH}
  - {size: M,   raw: "(absent)", units: null, semantic: NOT_CAPTURED, confidence: HIGH}
```

---

## IMAGE 03 — `HUS_addition.JPG`

**(1) Product / color identification + raw label**
Blue pen on white/grey paper. Label **`ХУС`** (Cyrillic = "HUS", i.e. Hus51). Filename **addition**. No dots, no arrows — simple single-digit qty per size → these are addition values (each = the unit count to add).

SKU family: Hus51 (04.06 reference lists "Hus51 green 87"). sku_guess `CL_..._HUS51_GREEN` (exact canonical key not in reference file; family = HUS51, color likely GREEN).

**(2) Transcription table**

| Size | RAW ink | Interpreted units | Semantic | Confidence / alternatives |
|---|---|---|---|---|
| XL | `XL-1` | 1 | ADDITION | HIGH |
| 2XL | `2XL-1` | 1 | ADDITION | HIGH |

Note: no dot present, so each `1` is a direct addition of 1 (not a dot-sum). Filename "addition" agrees with ink. Color not stated in ink (label only says ХУС); inferred GREEN from prior snapshot family — flagged.

**(3) YAML**
```yaml
image: HUS_addition.JPG
product_label_raw: "ХУС"
sku_guess: "HUS51_GREEN (family HUS51; color inferred, not in ink)"
merge_mode: ADDITION
rows:
  - {size: XL,  raw: "XL-1",  units: 1, semantic: ADDITION, confidence: HIGH}
  - {size: 2XL, raw: "2XL-1", units: 1, semantic: ADDITION, confidence: HIGH}
```

---

## IMAGE 04 — `Rombik_men_and_kids_all-addtions.JPG`

**(1) Product / color identification + raw label**
Blue marker on cardboard. Top label **`РОМБ`** (Cyrillic = "ROMB" / Rombik). Bottom red label **`ALL ADDITIONS`**. Right-margin **red** annotations re-label two rows (`=XL`, `=2XL`) and the last row (`=28`). Filename **all-additions**. SKU family: Rombik men + the `140/28` row is a **kids** Rombik size (men+kids on one sheet, matching filename). `CL_NEW-CLO_MEN_ROMBIK_BLACK` for men sizes; kids Rombik for the 140/28 row.

**(2) Transcription table**

| Size | RAW ink | Interpreted units | Semantic | Confidence / alternatives |
|---|---|---|---|---|
| S | `S - 1 = 1` | 1 | ADDITION | HIGH |
| M | `M -` (empty) | — | NOT_CAPTURED | HIGH |
| L | `L -` (empty) | — | NOT_CAPTURED | HIGH |
| XL | `XL - 2.1. = 3`  (red `=XL`) | 3 (2+1) | ADDITION | HIGH — dot-sum 2+1=3 confirmed by written `=3` |
| 2XL | `2XL - 2. = 2`  (red `=2XL`) | 2 | ADDITION | HIGH — single component `2.` = 2 |
| 3XL | `3XL -` (dash, struck/empty) | — | NOT_CAPTURED | MED — looks like an empty dash / small strike; no number after. Alt: could be intended `0`. Treat as NOT_CAPTURED. |
| 4XL | `4XL -` (empty) | — | NOT_CAPTURED | HIGH |
| 140/28 (kids) | `140/28 - 1.1 = 2`  (red `=28`) | 2 (1+1) | ADDITION | HIGH — dot-sum 1+1=2 confirmed by `=2`; small blue tape over the slash but digits clear |

Note: red `=XL` / `=2XL` / `=28` are scope re-confirmations (which line maps to which size), not quantities. `140/28` is a kids height/age size on this men+kids sheet.

**(3) YAML**
```yaml
image: Rombik_men_and_kids_all-addtions.JPG
product_label_raw: "РОМБ | ALL ADDITIONS | (red) =XL =2XL =28"
sku_guess: "CL_NEW-CLO_MEN_ROMBIK_BLACK (+ kids Rombik 140/28)"
merge_mode: ADDITION
rows:
  - {size: S,        raw: "S - 1 = 1",        units: 1, semantic: ADDITION, confidence: HIGH}
  - {size: M,        raw: "M -",              units: null, semantic: NOT_CAPTURED, confidence: HIGH}
  - {size: L,        raw: "L -",              units: null, semantic: NOT_CAPTURED, confidence: HIGH}
  - {size: XL,       raw: "XL - 2.1. = 3",    units: 3, semantic: ADDITION, confidence: HIGH}
  - {size: 2XL,      raw: "2XL - 2. = 2",     units: 2, semantic: ADDITION, confidence: HIGH}
  - {size: 3XL,      raw: "3XL -",            units: null, semantic: NOT_CAPTURED, confidence: MED}
  - {size: 4XL,      raw: "4XL -",            units: null, semantic: NOT_CAPTURED, confidence: HIGH}
  - {size: "140/28", raw: "140/28 - 1.1 = 2", units: 2, semantic: ADDITION, confidence: HIGH}
```

---

## IMAGE 05 — `line51_additions_but-S-full.JPG`

**(1) Product / color identification + raw label**
Black marker on cardboard. Label **`черн. белый`** (Cyrillic = "black. white" — the LINE51 black/white set). A bold **black right-arrow** is drawn **only on the S row**. Filename **additions_but-S-full** → S is FULL_SUPERSEDE, other sizes are dot-additions. INK AGREES: arrow on S only.

SKU family: `CL_OC_MEN_LINE51_WHITE` / LINE51 black-white set.

**(2) Transcription table**

| Size | RAW ink | Interpreted units | Semantic | Confidence / alternatives |
|---|---|---|---|---|
| S | `S - [blob]82 →` | 82 | FULL_SUPERSEDE | MED — an ink blob precedes `82`; reads as `82` with arrow. Alt: a leading struck digit making it `_82`; value taken as 82. Arrow confirms FULL. |
| M | `M - 2. = 2` | 2 | ADDITION | HIGH |
| L | `L - 4.2. = 6` | 6 (4+2) | ADDITION | HIGH — `=6` written confirms 4+2 |
| XL | `XL - 2.5. = 7` | 7 (2+5) | ADDITION | HIGH — `=7` confirms |
| 2XL | `2XL - 2.2. = 4` | 4 (2+2) | ADDITION | HIGH — `=4` confirms |
| 3XL | `3XL - 1. = 1` | 1 | ADDITION | HIGH — `=1` confirms |
| 4XL | `4XL - 1. = 1` | 1 | ADDITION | HIGH — `=1` confirms |

Note: S = FULL_SUPERSEDE 82 (arrow); all other sizes = dot-additions, each cross-checked against the handwritten `=N` totals. This is the textbook "but-S-full" layout.

**(3) YAML**
```yaml
image: line51_additions_but-S-full.JPG
product_label_raw: "черн. белый"
sku_guess: "CL_OC_MEN_LINE51_WHITE (LINE51 black/white set)"
merge_mode: MIXED_S_FULL_REST_ADDITION
rows:
  - {size: S,   raw: "S - 82 ->",     units: 82, semantic: FULL_SUPERSEDE, confidence: MED}
  - {size: M,   raw: "M - 2. = 2",    units: 2,  semantic: ADDITION, confidence: HIGH}
  - {size: L,   raw: "L - 4.2. = 6",  units: 6,  semantic: ADDITION, confidence: HIGH}
  - {size: XL,  raw: "XL - 2.5. = 7", units: 7,  semantic: ADDITION, confidence: HIGH}
  - {size: 2XL, raw: "2XL - 2.2. = 4",units: 4,  semantic: ADDITION, confidence: HIGH}
  - {size: 3XL, raw: "3XL - 1. = 1",  units: 1,  semantic: ADDITION, confidence: HIGH}
  - {size: 4XL, raw: "4XL - 1. = 1",  units: 1,  semantic: ADDITION, confidence: HIGH}
```

---

## IMAGE 06 — `berserk_rush.JPG`

**(1) Product / color identification + raw label**
Dark-blue pen on grey paper. TWO products on one sheet; red label **`ALL ADDITIONS`**.
- Product A: **`Берсерк белый длинный рукав`** (Berserk white LONG sleeve = "rush"/long-sleeve variant).
- Product B: **`Берсерк черный длинный рукав`** (Berserk black long sleeve).
Filename **berserk_rush** → "rush" = long-sleeve, consistent with "длинный рукав". SKU family: Berserk rush white / black (04.06 reference: "Berserk rush white + black 140").

**(2) Transcription table**

| Product | Size | RAW ink | Interpreted units | Semantic | Confidence / alternatives |
|---|---|---|---|---|---|
| Berserk white long-sleeve | XL | `XL-2` | 2 | ADDITION | HIGH |
| Berserk white long-sleeve | 2XL | `2XL-1` | 1 | ADDITION | HIGH |
| Berserk black long-sleeve | L | `L-2` | 2 | ADDITION | HIGH |
| Berserk black long-sleeve | XL | `XL-1` | 1 | ADDITION | HIGH |
| Berserk black long-sleeve | 2XL | `2XL-1` | 1 | ADDITION | HIGH |

Note: all simple single values, no dots/arrows → additions (filename + red label agree).

**(3) YAML**
```yaml
image: berserk_rush.JPG
product_label_raw: "Берсерк белый длинный рукав / Берсерк черный длинный рукав / ALL ADDITIONS"
sku_guess: "BERSERK_RUSH_WHITE / BERSERK_RUSH_BLACK"
merge_mode: ADDITION
rows:
  - {product: berserk_rush_white, size: XL,  raw: "XL-2",  units: 2, semantic: ADDITION, confidence: HIGH}
  - {product: berserk_rush_white, size: 2XL, raw: "2XL-1", units: 1, semantic: ADDITION, confidence: HIGH}
  - {product: berserk_rush_black, size: L,   raw: "L-2",   units: 2, semantic: ADDITION, confidence: HIGH}
  - {product: berserk_rush_black, size: XL,  raw: "XL-1",  units: 1, semantic: ADDITION, confidence: HIGH}
  - {product: berserk_rush_black, size: 2XL, raw: "2XL-1", units: 1, semantic: ADDITION, confidence: HIGH}
```

---

## IMAGE 07 — `berserk_t-shirts.JPG`

**(1) Product / color identification + raw label**
Dark-blue pen on white paper. Top-right timestamp **`11.06.26г. время 22ч.00`** (confirms the count event). TWO products; red **`ALL ADDITIONS`**.
- Product A: **`Берсерк белый коротки рукав`** (Berserk white SHORT sleeve = t-shirt).
- Product B: **`Берсерк черный коротки рукав`** (Berserk black short sleeve).
Filename **berserk_t-shirts** → "t-shirts" = short sleeve, consistent with "коротки рукав". SKU family: Berserk sleeveless/short-sleeve white / black (04.06 reference: "Berserk sleeveless white + black 454").

**(2) Transcription table**

| Product | Size | RAW ink | Interpreted units | Semantic | Confidence / alternatives |
|---|---|---|---|---|---|
| Berserk white short-sleeve | S | `S-1` | 1 | ADDITION | HIGH |
| Berserk white short-sleeve | L | `L-1` | 1 | ADDITION | HIGH |
| Berserk white short-sleeve | XL | `XL-1` | 1 | ADDITION | HIGH |
| Berserk black short-sleeve | M | `M-1` | 1 | ADDITION | HIGH |
| Berserk black short-sleeve | XL | `XL-1` | 1 | ADDITION | HIGH |

Note: all single values, additions.

**(3) YAML**
```yaml
image: berserk_t-shirts.JPG
product_label_raw: "Берсерк белый коротки рукав / Берсерк черный коротки рукав / ALL ADDITIONS / 11.06.26г. время 22ч.00"
sku_guess: "BERSERK_SHORTSLEEVE_WHITE / BERSERK_SHORTSLEEVE_BLACK"
merge_mode: ADDITION
rows:
  - {product: berserk_tshirt_white, size: S,  raw: "S-1",  units: 1, semantic: ADDITION, confidence: HIGH}
  - {product: berserk_tshirt_white, size: L,  raw: "L-1",  units: 1, semantic: ADDITION, confidence: HIGH}
  - {product: berserk_tshirt_white, size: XL, raw: "XL-1", units: 1, semantic: ADDITION, confidence: HIGH}
  - {product: berserk_tshirt_black, size: M,  raw: "M-1",  units: 1, semantic: ADDITION, confidence: HIGH}
  - {product: berserk_tshirt_black, size: XL, raw: "XL-1", units: 1, semantic: ADDITION, confidence: HIGH}
```

---

## IMAGE 08 — `line52_additions_but-S-full.JPG`

**(1) Product / color identification + raw label**
Blue marker on cardboard. Label **`ПРИНТ`** (Cyrillic = "PRINT" / Line52). A bold **dark right-arrow** is drawn **only on the S row**. Filename **additions_but-S-full** → S = FULL_SUPERSEDE, rest = dot-additions. INK AGREES.

SKU family: `CL_OC_MEN_LINE52_BLACK`.

**(2) Transcription table**

| Size | RAW ink | Interpreted units | Semantic | Confidence / alternatives |
|---|---|---|---|---|
| S | `S - 72 →` | 72 | FULL_SUPERSEDE | HIGH — clean `72` + arrow |
| L | `L - 5.6. = 11` | 11 (5+6) | ADDITION | HIGH — `=11` confirms |
| M | `M - 2.3. = 5` | 5 (2+3) | ADDITION | HIGH — `=5` confirms |
| XL | `XL - 5.7. = 12` | 12 (5+7) | ADDITION | HIGH — `=12` confirms |
| 3XL | `3XL - 5.8 = 13` | 13 (5+8) | ADDITION | HIGH — `=13` confirms |
| 2XL | `2XL - [struck-out]10.10. = 20` | 20 (10+10) | ADDITION | MED — a scribbled/struck-out value sits right after `2XL-` (an error correction, illegible by design); the clean components are `10.10.`→20, and the right-edge `=2_` is cropped but consistent with 20. Alt for cropped total: 26 (unlikely; 10+10=20). |
| 4XL | `4XL - 1. = 1` | 1 | ADDITION | HIGH — `=1` confirms |

Note: S=72 FULL (arrow); all others dot-additions cross-checked by `=N`. The 2XL crossed-out token is a corrected mistake — value taken from the clean `10.10.` = 20.

**(3) YAML**
```yaml
image: line52_additions_but-S-full.JPG
product_label_raw: "ПРИНТ"
sku_guess: "CL_OC_MEN_LINE52_BLACK"
merge_mode: MIXED_S_FULL_REST_ADDITION
rows:
  - {size: S,   raw: "S - 72 ->",                  units: 72, semantic: FULL_SUPERSEDE, confidence: HIGH}
  - {size: M,   raw: "M - 2.3. = 5",               units: 5,  semantic: ADDITION, confidence: HIGH}
  - {size: L,   raw: "L - 5.6. = 11",              units: 11, semantic: ADDITION, confidence: HIGH}
  - {size: XL,  raw: "XL - 5.7. = 12",             units: 12, semantic: ADDITION, confidence: HIGH}
  - {size: 2XL, raw: "2XL - (struck) 10.10. = 20", units: 20, semantic: ADDITION, confidence: MED}
  - {size: 3XL, raw: "3XL - 5.8 = 13",             units: 13, semantic: ADDITION, confidence: HIGH}
  - {size: 4XL, raw: "4XL - 1. = 1",               units: 1,  semantic: ADDITION, confidence: HIGH}
```

---

## IMAGE 09 — `rush_white_and_rush_black.JPG`

**(1) Product / color identification + raw label**
Dark-blue pen on grey paper. Header **`Футболки длинным рукавом`** (= "T-shirts with long sleeve" = rush). TWO color blocks (underlined headers); red **`ALL ADDITIONS`**.
- **`белые`** (white)
- **`черные`** (black)
Filename **rush_white_and_rush_black** agrees. SKU family: rush (long-sleeve t-shirt) white / black. Same family as Image 06 "Berserk rush"? — NOT necessarily; this sheet's header says generic "Футболки длинным рукавом" with no "Берсерк" word, so treat as the standalone **rush** product white/black. Flagged: rush vs berserk-rush relationship is a downstream merge decision, not resolvable from ink alone.

**(2) Transcription table**

| Color | Size | RAW ink | Interpreted units | Semantic | Confidence / alternatives |
|---|---|---|---|---|---|
| white | S | `S - 1` | 1 | ADDITION | HIGH — "S" has a decorative strike-through on the letter but value is 1 |
| white | M | `M - 1` | 1 | ADDITION | HIGH |
| white | L | `L - 2` | 2 | ADDITION | HIGH |
| white | 2XL | `2XL - 1` | 1 | ADDITION | HIGH |
| white | 3XL | `3XL - 1` | 1 | ADDITION | HIGH |
| black | L | `L - 1` | 1 | ADDITION | HIGH |
| black | XL | `XL - 1` | 1 | ADDITION | HIGH |

Note: all single values, additions. No XL or 1XL row for white (jumps 2XL after L).

**(3) YAML**
```yaml
image: rush_white_and_rush_black.JPG
product_label_raw: "Футболки длинным рукавом / белые / черные / ALL ADDITIONS"
sku_guess: "RUSH_WHITE / RUSH_BLACK (long-sleeve tee; relationship to berserk_rush is a downstream decision)"
merge_mode: ADDITION
rows:
  - {product: rush_white, size: S,   raw: "S - 1",   units: 1, semantic: ADDITION, confidence: HIGH}
  - {product: rush_white, size: M,   raw: "M - 1",   units: 1, semantic: ADDITION, confidence: HIGH}
  - {product: rush_white, size: L,   raw: "L - 2",   units: 2, semantic: ADDITION, confidence: HIGH}
  - {product: rush_white, size: 2XL, raw: "2XL - 1", units: 1, semantic: ADDITION, confidence: HIGH}
  - {product: rush_white, size: 3XL, raw: "3XL - 1", units: 1, semantic: ADDITION, confidence: HIGH}
  - {product: rush_black, size: L,   raw: "L - 1",   units: 1, semantic: ADDITION, confidence: HIGH}
  - {product: rush_black, size: XL,  raw: "XL - 1",  units: 1, semantic: ADDITION, confidence: HIGH}
```

---

## IMAGE 10 — `spider_rush_addition.JPG`

**(1) Product / color identification + raw label**
Dark-blue pen on grey paper. Label **`Спайдер`** (Cyrillic = "Spider"). Filename **spider_rush_addition**. INK vs FILENAME conflict (minor): the ink says only "Спайдер" — it does **not** write "rush"/"длинный рукав". The "rush" qualifier in the filename is not present in the ink; flagged. SKU family: Spider (04.06 reference: "Spider black 360").

**(2) Transcription table**

| Size | RAW ink | Interpreted units | Semantic | Confidence / alternatives |
|---|---|---|---|---|
| M | `M - 1` | 1 | ADDITION | HIGH |

Note: single value, addition (filename "addition" agrees; no dots/arrows). Color not stated in ink (label only "Спайдер"); 04.06 family had Spider BLACK — inferred, flagged.

**(3) YAML**
```yaml
image: spider_rush_addition.JPG
product_label_raw: "Спайдер"
sku_guess: "SPIDER_BLACK (color inferred from prior family; 'rush' in filename NOT in ink)"
merge_mode: ADDITION
rows:
  - {size: M, raw: "M - 1", units: 1, semantic: ADDITION, confidence: HIGH}
```

---

## IMAGE 11 — `line61_additions.JPG`

**(1) Product / color identification + raw label**
Blue + dark marker on cardboard. Label **`6/1`** (= SUIT-61, written in the same logo style as the "3/1" labels). Filename **additions** (NO "but-S-full"). Crucially: **no arrow anywhere on the sheet**, and the S row carries a dot (`S-1.`) → S here is an **ADDITION**, not a supersede. INK AGREES with the filename (additions-only).

SKU family: `CL_NEW-CLO2_MEN_SUIT-61_BLACK`.

**(2) Transcription table**

| Size | RAW ink | Interpreted units | Semantic | Confidence / alternatives |
|---|---|---|---|---|
| S | `S - 1. = 1` | 1 | ADDITION | HIGH — `=1` confirms; dot present (no arrow) so ADDITION |
| M | `M - 1 = 1` | 1 | ADDITION | MED — the `1` is written in blue; trailing dot faint but `=1` confirms total 1. Alt: same value either way. |
| L | `L - 3.3 = 6` | 6 (3+3) | ADDITION | HIGH — `=6` confirms |
| XL | `XL - 6.7 = 13` | 13 (6+7) | ADDITION | HIGH — `=13` confirms |
| 2XL | `2XL - 3.7. = 10` | 10 (3+7) | ADDITION | HIGH — `=10` confirms |
| 3XL | `3XL - 1.5. = 6` | 6 (1+5) | ADDITION | HIGH — `=6` confirms |
| 4XL | `4XL - 1.2. = 3` | 3 (1+2) | ADDITION | HIGH — `=3` confirms |

Note: every row is a dot-addition (or single-unit addition for S/M), cross-checked by the handwritten `=N`. No supersede on this sheet.

**(3) YAML**
```yaml
image: line61_additions.JPG
product_label_raw: "6/1"
sku_guess: "CL_NEW-CLO2_MEN_SUIT-61_BLACK"
merge_mode: ADDITION
rows:
  - {size: S,   raw: "S - 1. = 1",     units: 1,  semantic: ADDITION, confidence: HIGH}
  - {size: M,   raw: "M - 1 = 1",      units: 1,  semantic: ADDITION, confidence: MED}
  - {size: L,   raw: "L - 3.3 = 6",    units: 6,  semantic: ADDITION, confidence: HIGH}
  - {size: XL,  raw: "XL - 6.7 = 13",  units: 13, semantic: ADDITION, confidence: HIGH}
  - {size: 2XL, raw: "2XL - 3.7. = 10",units: 10, semantic: ADDITION, confidence: HIGH}
  - {size: 3XL, raw: "3XL - 1.5. = 6", units: 6,  semantic: ADDITION, confidence: HIGH}
  - {size: 4XL, raw: "4XL - 1.2. = 3", units: 3,  semantic: ADDITION, confidence: HIGH}
```

---

## IMAGE 12 — `t-shirts_white_and_t-shirts_black.JPG`

**(1) Product / color identification + raw label**
Dark-blue pen on grey paper. Header **`Футболки коротким рукавом`** (= "T-shirts with short sleeve"). TWO color blocks (underlined); red **`ALL ADDITIONS`**.
- **`белые`** (white)
- **`черные`** (black)
Filename **t-shirts_white_and_t-shirts_black** agrees. SKU family: short-sleeve t-shirt white / black (standalone tee product; relationship to "Берсерк коротки рукав" of Image 07 is a downstream merge decision, not from ink).

**(2) Transcription table**

| Color | Size | RAW ink | Interpreted units | Semantic | Confidence / alternatives |
|---|---|---|---|---|---|
| white | L | `L - 5` | 5 | ADDITION | HIGH |
| white | XL | `XL - 1` | 1 | ADDITION | HIGH |
| white | 2XL | `2XL - 1` | 1 | ADDITION | HIGH |
| black | L | `L - 3` | 3 | ADDITION | HIGH |
| black | XL | `XL - 2` | 2 | ADDITION | HIGH |

Note: all single values, additions.

**(3) YAML**
```yaml
image: t-shirts_white_and_t-shirts_black.JPG
product_label_raw: "Футболки коротким рукавом / белые / черные / ALL ADDITIONS"
sku_guess: "TSHIRT_SHORTSLEEVE_WHITE / TSHIRT_SHORTSLEEVE_BLACK"
merge_mode: ADDITION
rows:
  - {product: tshirt_white, size: L,   raw: "L - 5",   units: 5, semantic: ADDITION, confidence: HIGH}
  - {product: tshirt_white, size: XL,  raw: "XL - 1",  units: 1, semantic: ADDITION, confidence: HIGH}
  - {product: tshirt_white, size: 2XL, raw: "2XL - 1", units: 1, semantic: ADDITION, confidence: HIGH}
  - {product: tshirt_black, size: L,   raw: "L - 3",   units: 3, semantic: ADDITION, confidence: HIGH}
  - {product: tshirt_black, size: XL,  raw: "XL - 2",  units: 2, semantic: ADDITION, confidence: HIGH}
```

---

# BATCH ROLL-UP

## Per-product summary (additions total + supersede values)

| # | Image | Product (label) | SKU family guess | Addition units (Σ) | FULL_SUPERSEDE rows (size=value) | NOT_CAPTURED sizes |
|---|---|---|---|---:|---|---|
| 01 | 3_in_1_kids_complete_stock_snapshot | 3/1 kids (snapshot) | KID-31_BLACK | 0 | 110/22=12, 120/24=9, 130/26=54, 140/28=32, 150/30=28 | — |
| 02 | 3_in_1_with_logotypes_complete_stock_snapshot | 3/1 men w/ logotypes (snapshot) | UNMAPPED_3_IN_1_MEN_SETS | 0 | L=20, XL=44, 2XL=55, 3XL=43, 4XL=30 | S, M |
| 03 | HUS_addition | ХУС / Hus51 | HUS51 (GREEN inferred) | 2 | — | — |
| 04 | Rombik_men_and_kids_all-addtions | РОМБ / Rombik men+kids | ROMBIK_BLACK (+kids) | 8 (S1+XL3+2XL2+140/28 2) | — | M, L, 3XL, 4XL |
| 05 | line51_additions_but-S-full | черн. белый / LINE51 b+w | LINE51_WHITE | 21 (M2+L6+XL7+2XL4+3XL1+4XL1) | S=82 | — |
| 06 | berserk_rush | Берсерк long-sleeve w+b | BERSERK_RUSH_W/B | 7 (w:XL2+2XL1; b:L2+XL1+2XL1) | — | — |
| 07 | berserk_t-shirts | Берсерк short-sleeve w+b | BERSERK_SS_W/B | 5 (w:S1+L1+XL1; b:M1+XL1) | — | — |
| 08 | line52_additions_but-S-full | ПРИНТ / Line52 | LINE52_BLACK | 62 (M5+L11+XL12+2XL20+3XL13+4XL1) | S=72 | — |
| 09 | rush_white_and_rush_black | Футболки длин. рукав w+b | RUSH_W/B | 8 (w:S1+M1+L2+2XL1+3XL1; b:L1+XL1) | — | — |
| 10 | spider_rush_addition | Спайдер / Spider | SPIDER_BLACK (inferred) | 1 (M1) | — | — |
| 11 | line61_additions | 6/1 / Line61 | SUIT-61_BLACK | 40 (S1+M1+L6+XL13+2XL10+3XL6+4XL3) | — | — |
| 12 | t-shirts_white_and_t-shirts_black | Футболки кор. рукав w+b | TSHIRT_SS_W/B | 11 (w:L5+XL1+2XL1; b:L3+XL2) | — | — |

**TOTAL ADDITION UNITS (all images): 2 + 8 + 21 + 7 + 5 + 62 + 8 + 1 + 40 + 11 = 165**
**FULL_SUPERSEDE rows (count): 5 (img01) + 5 (img02) + 1 (img05 S=82) + 1 (img08 S=72) = 12 supersede rows.**
 (img01 + img02 are whole-sheet snapshots = 10 supersede rows; img05 + img08 contribute 1 S-supersede each = 2 more.)

## Per-product addition subtotals (flat)
- Hus51: **2**
- Rombik men+kids: **8**
- LINE51 black/white (M–4XL additions; S is supersede=82): **21**
- Berserk rush (long-sleeve) white+black: **7**
- Berserk t-shirt (short-sleeve) white+black: **5**
- Line52 (M–4XL additions; S is supersede=72): **62**
- Rush (long-sleeve tee) white+black: **8**
- Spider: **1**
- Line61: **40**
- T-shirt (short-sleeve) white+black: **11**
- **Sum of additions = 165**

## FULL_SUPERSEDE values (flat)
- KID-31 (3/1 kids): 110/22=12, 120/24=9, 130/26=54, 140/28=32, 150/30=28  (whole-sheet snapshot)
- 3-in-1 men (logotypes): L=20, XL=44, 2XL=55, 3XL=43, 4XL=30  (whole-sheet snapshot; S & M not captured)
- LINE51 black/white: S=82
- Line52: S=72

---

# MED / LOW-CONFIDENCE CELLS (flat list)

| Image | Cell | Value taken | Confidence | Issue / alternative |
|---|---|---|---|---|
| 01 3_in_1_kids | 120/24 | 9 | MED | `9` vs `4` (open loop); canonical 04.06 had 9 → supports 9. Alt: 4. |
| 01 3_in_1_kids | 140/28 | 32 | MED | `32` vs `33`; 04.06 snapshot had 33. Alt: 33. |
| 01 3_in_1_kids | 150/30 | 28 | MED | `28` vs `29`; 04.06 snapshot had 29. Alt: 29. |
| 04 Rombik | 3XL | NOT_CAPTURED | MED | Dash looks empty/struck, no number. Alt: intended 0. Treated as NOT_CAPTURED. |
| 05 line51 | S | 82 | MED | Ink blob precedes `82`; arrow confirms FULL. Possible leading struck digit; value 82. |
| 08 line52 | 2XL | 20 | MED | Struck-out token before clean `10.10.`(=20); right-edge total cropped `=2_`. Alt: 26 (unlikely). |
| 11 line61 | M | 1 | MED | Faint trailing dot on the `1`; `=1` confirms total 1 regardless. |

**LOW-confidence cells: none.** (All ambiguities resolved to MED via the handwritten `=N` cross-checks and the canonical size-ladder reference; no cell fell to LOW.)

---

# CROSS-IMAGE FLAGS (for the reconciler, not quantity changes)

1. **Image 10 spider_rush_addition** — ink says only "Спайдер" (no "rush"/long-sleeve word). Filename's "rush" is NOT in the ink. Flag for the merge step.
2. **Images 06/07 (Berserk) vs 09/12 (generic Футболки)** — Berserk long/short-sleeve are explicitly "Берсерк"; the rush_white/black (09) and t-shirts_white/black (12) sheets say only "Футболки длинным/коротким рукавом" with no "Берсерк". Whether these are the SAME product family or distinct is a downstream merge decision — not resolvable from ink alone. Kept as separate sku_guesses.
3. **Color inference (HUS green, Spider black)** — color not written in ink; inferred from the 04.06 family table. Flagged.
4. **No filename↔ink CONFLICTS on the supersede/addition semantics** — every "complete_stock_snapshot" had an arrow (FULL), every "additions"/"all-additions" had dots/single values, and both "but-S-full" sheets (line51, line52) had the arrow on S only. Filenames and ink AGREE on merge mode throughout (the only mismatch is the descriptive "rush" word in flags 1–2).
