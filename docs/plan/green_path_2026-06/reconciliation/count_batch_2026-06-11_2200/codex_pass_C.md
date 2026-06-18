One convention in the tables: when an image contains multiple color/product scopes, I prefix the `size` cell with that scope.

No hard ink/filename conflicts detected. Soft caveat: a few addition-scoped images use plain `-1`/`-2` ink instead of dot notation; I mark those as ADDITION only where the filename or red `ALL ADDITIONS` scope supports it.

**1. 3_in_1_kids_complete_stock_snapshot.JPG**
Product identification: 3-in-1 kids  
Raw label text: `3/1 →`; counts written as size then `шт.`

| size | RAW ink exactly as written | interpreted units | semantic | confidence |
|---|---:|---:|---|---|
| 110/22 | `12 шт.` | 12 | FULL_SUPERSEDE | HIGH |
| 120/24 | `9 шт.` | 9 | FULL_SUPERSEDE | HIGH |
| 150/30 | `28 шт.` | 28 | FULL_SUPERSEDE | HIGH |
| 140/28 | `32 шт.` | 32 | FULL_SUPERSEDE | HIGH |
| 130/26 | `54 шт.` | 54 | FULL_SUPERSEDE | HIGH |

```yaml
image: "3_in_1_kids_complete_stock_snapshot.JPG"
product_label_raw: "3/1 →"
sku_guess: "3_in_1_kids"
rows:
  - {size: "110/22", raw: "12 шт.", units: 12, semantic: "FULL_SUPERSEDE", confidence: "HIGH"}
  - {size: "120/24", raw: "9 шт.", units: 9, semantic: "FULL_SUPERSEDE", confidence: "HIGH"}
  - {size: "150/30", raw: "28 шт.", units: 28, semantic: "FULL_SUPERSEDE", confidence: "HIGH"}
  - {size: "140/28", raw: "32 шт.", units: 32, semantic: "FULL_SUPERSEDE", confidence: "HIGH"}
  - {size: "130/26", raw: "54 шт.", units: 54, semantic: "FULL_SUPERSEDE", confidence: "HIGH"}
```

**2. 3_in_1_with_logotypes_complete_stock_snapshot.JPG**
Product identification: 3-in-1 with logotypes  
Raw label text: `3/1 →`

| size | RAW ink exactly as written | interpreted units | semantic | confidence |
|---|---:|---:|---|---|
| XL | `XL-44` | 44 | FULL_SUPERSEDE | HIGH |
| 2XL | `2XL-55` | 55 | FULL_SUPERSEDE | HIGH |
| 3XL | `3XL-43` | 43 | FULL_SUPERSEDE | HIGH |
| 4XL | `4XL-30` | 30 | FULL_SUPERSEDE | HIGH |
| L | `L-20` | 20 | FULL_SUPERSEDE | HIGH |

```yaml
image: "3_in_1_with_logotypes_complete_stock_snapshot.JPG"
product_label_raw: "3/1 →"
sku_guess: "3_in_1_with_logotypes"
rows:
  - {size: "XL", raw: "XL-44", units: 44, semantic: "FULL_SUPERSEDE", confidence: "HIGH"}
  - {size: "2XL", raw: "2XL-55", units: 55, semantic: "FULL_SUPERSEDE", confidence: "HIGH"}
  - {size: "3XL", raw: "3XL-43", units: 43, semantic: "FULL_SUPERSEDE", confidence: "HIGH"}
  - {size: "4XL", raw: "4XL-30", units: 30, semantic: "FULL_SUPERSEDE", confidence: "HIGH"}
  - {size: "L", raw: "L-20", units: 20, semantic: "FULL_SUPERSEDE", confidence: "HIGH"}
```

**3. HUS_addition.JPG**
Product identification: HUS  
Raw label text: `ХУС` / could visually read as `XYC`

| size | RAW ink exactly as written | interpreted units | semantic | confidence |
|---|---:|---:|---|---|
| XL | `XL-1` | 1 | ADDITION | MED: addition inferred from filename; no dots/ALL ADDITIONS ink |
| 2XL | `2XL-1` | 1 | ADDITION | MED: addition inferred from filename; no dots/ALL ADDITIONS ink |

```yaml
image: "HUS_addition.JPG"
product_label_raw: "ХУС"
sku_guess: "HUS"
rows:
  - {size: "XL", raw: "XL-1", units: 1, semantic: "ADDITION", confidence: "MED"}
  - {size: "2XL", raw: "2XL-1", units: 1, semantic: "ADDITION", confidence: "MED"}
```

**4. Rombik_men_and_kids_all-addtions.JPG**
Product identification: Rombik, men and kids  
Raw label text: `РОМБ`; red labels: `=XL`, `=2XL`, `=28`, `ALL ADDITIONS`

| size | RAW ink exactly as written | interpreted units | semantic | confidence |
|---|---:|---:|---|---|
| S | `S-1 = 1` | 1 | ADDITION | MED: plain number, but scoped by red ALL ADDITIONS |
| M | `M-` | null | NOT_CAPTURED | HIGH |
| L | `L-` | null | NOT_CAPTURED | HIGH |
| XL | `XL-2.1. = 3` red `=XL` | 3 | ADDITION | HIGH |
| 2XL | `2XL-2. = 2` red `=2XL` | 2 | ADDITION | HIGH |
| 3XL | `3XL-` | null | NOT_CAPTURED | HIGH |
| 4XL | `4XL-` | null | NOT_CAPTURED | HIGH |
| 140/28 | `140/28-1.1. = 2` red `=28` | 2 | ADDITION | MED: size partly obscured, red `=28` confirms 28 |

```yaml
image: "Rombik_men_and_kids_all-addtions.JPG"
product_label_raw: "РОМБ; red: =XL; =2XL; =28; ALL ADDITIONS"
sku_guess: "Rombik"
rows:
  - {size: "S", raw: "S-1 = 1", units: 1, semantic: "ADDITION", confidence: "MED"}
  - {size: "M", raw: "M-", units: null, semantic: "NOT_CAPTURED", confidence: "HIGH"}
  - {size: "L", raw: "L-", units: null, semantic: "NOT_CAPTURED", confidence: "HIGH"}
  - {size: "XL", raw: "XL-2.1. = 3; red =XL", units: 3, semantic: "ADDITION", confidence: "HIGH"}
  - {size: "2XL", raw: "2XL-2. = 2; red =2XL", units: 2, semantic: "ADDITION", confidence: "HIGH"}
  - {size: "3XL", raw: "3XL-", units: null, semantic: "NOT_CAPTURED", confidence: "HIGH"}
  - {size: "4XL", raw: "4XL-", units: null, semantic: "NOT_CAPTURED", confidence: "HIGH"}
  - {size: "140/28", raw: "140/28-1.1. = 2; red =28", units: 2, semantic: "ADDITION", confidence: "MED"}
```

**5. line51_additions_but-S-full.JPG**
Product identification: LINE51, black-white  
Raw label text: `черн.белый`; right arrow

| size | RAW ink exactly as written | interpreted units | semantic | confidence |
|---|---:|---:|---|---|
| S | `S-82 →` | 82 | FULL_SUPERSEDE | MED: first digit smudged; likely 82 |
| M | `M-2. = 2` | 2 | ADDITION | HIGH |
| L | `L-4.2. = 6` | 6 | ADDITION | HIGH |
| XL | `XL-2.5. = 7` | 7 | ADDITION | HIGH |
| 2XL | `2XL-2.2. = 4` | 4 | ADDITION | HIGH |
| 3XL | `3XL-1. = 1` | 1 | ADDITION | HIGH |
| 4XL | `4XL-1. = 1` | 1 | ADDITION | HIGH |

```yaml
image: "line51_additions_but-S-full.JPG"
product_label_raw: "черн.белый →"
sku_guess: "LINE51"
rows:
  - {size: "S", raw: "S-82 →", units: 82, semantic: "FULL_SUPERSEDE", confidence: "MED"}
  - {size: "M", raw: "M-2. = 2", units: 2, semantic: "ADDITION", confidence: "HIGH"}
  - {size: "L", raw: "L-4.2. = 6", units: 6, semantic: "ADDITION", confidence: "HIGH"}
  - {size: "XL", raw: "XL-2.5. = 7", units: 7, semantic: "ADDITION", confidence: "HIGH"}
  - {size: "2XL", raw: "2XL-2.2. = 4", units: 4, semantic: "ADDITION", confidence: "HIGH"}
  - {size: "3XL", raw: "3XL-1. = 1", units: 1, semantic: "ADDITION", confidence: "HIGH"}
  - {size: "4XL", raw: "4XL-1. = 1", units: 1, semantic: "ADDITION", confidence: "HIGH"}
```

**6. berserk_rush.JPG**
Product identification: Berserk long sleeve, white and black  
Raw label text: `Берсерк белый длинный рукав`; `Берсерк черный длинный рукав`; red `ALL ADDITIONS`

| size | RAW ink exactly as written | interpreted units | semantic | confidence |
|---|---:|---:|---|---|
| белый / XL | `XL-2` | 2 | ADDITION | HIGH |
| белый / 2XL | `2XL-1` | 1 | ADDITION | HIGH |
| черный / L | `L-2` | 2 | ADDITION | HIGH |
| черный / XL | `XL-1` | 1 | ADDITION | HIGH |
| черный / 2XL | `2XL-1` | 1 | ADDITION | HIGH |

```yaml
image: "berserk_rush.JPG"
product_label_raw: "Берсерк белый длинный рукав; Берсерк черный длинный рукав; red: ALL ADDITIONS"
sku_guess: "Berserk long sleeve"
rows:
  - {size: "белый / XL", raw: "XL-2", units: 2, semantic: "ADDITION", confidence: "HIGH"}
  - {size: "белый / 2XL", raw: "2XL-1", units: 1, semantic: "ADDITION", confidence: "HIGH"}
  - {size: "черный / L", raw: "L-2", units: 2, semantic: "ADDITION", confidence: "HIGH"}
  - {size: "черный / XL", raw: "XL-1", units: 1, semantic: "ADDITION", confidence: "HIGH"}
  - {size: "черный / 2XL", raw: "2XL-1", units: 1, semantic: "ADDITION", confidence: "HIGH"}
```

**7. berserk_t-shirts.JPG**
Product identification: Berserk short sleeve, white and black  
Raw label text: `11.06.26г. время 22ч.00`; `Берсерк белый коротки рукав`; `Берсерк черный коротки рукав`; red `ALL ADDITIONS`

| size | RAW ink exactly as written | interpreted units | semantic | confidence |
|---|---:|---:|---|---|
| белый / S | `S-1` | 1 | ADDITION | HIGH |
| белый / L | `L-1` | 1 | ADDITION | HIGH |
| белый / XL | `XL-1` | 1 | ADDITION | HIGH |
| черный / M | `M-1` | 1 | ADDITION | HIGH |
| черный / XL | `XL-1` | 1 | ADDITION | HIGH |

```yaml
image: "berserk_t-shirts.JPG"
product_label_raw: "11.06.26г. время 22ч.00; Берсерк белый коротки рукав; Берсерк черный коротки рукав; red: ALL ADDITIONS"
sku_guess: "Berserk short sleeve"
rows:
  - {size: "белый / S", raw: "S-1", units: 1, semantic: "ADDITION", confidence: "HIGH"}
  - {size: "белый / L", raw: "L-1", units: 1, semantic: "ADDITION", confidence: "HIGH"}
  - {size: "белый / XL", raw: "XL-1", units: 1, semantic: "ADDITION", confidence: "HIGH"}
  - {size: "черный / M", raw: "M-1", units: 1, semantic: "ADDITION", confidence: "HIGH"}
  - {size: "черный / XL", raw: "XL-1", units: 1, semantic: "ADDITION", confidence: "HIGH"}
```

**8. line52_additions_but-S-full.JPG**
Product identification: LINE52  
Raw label text: `ПРИНТ`; right arrow

| size | RAW ink exactly as written | interpreted units | semantic | confidence |
|---|---:|---:|---|---|
| S | `S-72 →` | 72 | FULL_SUPERSEDE | HIGH |
| L | `L-5.6. = 11` | 11 | ADDITION | HIGH |
| M | `M-2.3. = 5` | 5 | ADDITION | HIGH |
| XL | `XL-5.7. = 12` | 12 | ADDITION | HIGH |
| 3XL | `3XL-5.8 = 13` | 13 | ADDITION | HIGH |
| 2XL | `2XL-10.10. = 20` | 20 | ADDITION | MED: leading `10` area has overwrite/correction |
| 4XL | `4XL-1. = 1` | 1 | ADDITION | HIGH |

```yaml
image: "line52_additions_but-S-full.JPG"
product_label_raw: "ПРИНТ →"
sku_guess: "LINE52"
rows:
  - {size: "S", raw: "S-72 →", units: 72, semantic: "FULL_SUPERSEDE", confidence: "HIGH"}
  - {size: "L", raw: "L-5.6. = 11", units: 11, semantic: "ADDITION", confidence: "HIGH"}
  - {size: "M", raw: "M-2.3. = 5", units: 5, semantic: "ADDITION", confidence: "HIGH"}
  - {size: "XL", raw: "XL-5.7. = 12", units: 12, semantic: "ADDITION", confidence: "HIGH"}
  - {size: "3XL", raw: "3XL-5.8 = 13", units: 13, semantic: "ADDITION", confidence: "HIGH"}
  - {size: "2XL", raw: "2XL-10.10. = 20", units: 20, semantic: "ADDITION", confidence: "MED"}
  - {size: "4XL", raw: "4XL-1. = 1", units: 1, semantic: "ADDITION", confidence: "HIGH"}
```

**9. rush_white_and_rush_black.JPG**
Product identification: long-sleeve T-shirts, white and black  
Raw label text: `Футболки длинным рукавом`; `белые`; `черные`; red `ALL ADDITIONS`

| size | RAW ink exactly as written | interpreted units | semantic | confidence |
|---|---:|---:|---|---|
| белые / S | `S-1` | 1 | ADDITION | HIGH |
| белые / M | `M-1` | 1 | ADDITION | HIGH |
| белые / L | `L-2` | 2 | ADDITION | HIGH |
| белые / 2XL | `2XL-1` | 1 | ADDITION | HIGH |
| белые / 3XL | `3XL-1` | 1 | ADDITION | HIGH |
| черные / L | `L-1` | 1 | ADDITION | HIGH |
| черные / XL | `XL-1` | 1 | ADDITION | HIGH |

```yaml
image: "rush_white_and_rush_black.JPG"
product_label_raw: "Футболки длинным рукавом; белые; черные; red: ALL ADDITIONS"
sku_guess: "long_sleeve_tshirts_white_black"
rows:
  - {size: "белые / S", raw: "S-1", units: 1, semantic: "ADDITION", confidence: "HIGH"}
  - {size: "белые / M", raw: "M-1", units: 1, semantic: "ADDITION", confidence: "HIGH"}
  - {size: "белые / L", raw: "L-2", units: 2, semantic: "ADDITION", confidence: "HIGH"}
  - {size: "белые / 2XL", raw: "2XL-1", units: 1, semantic: "ADDITION", confidence: "HIGH"}
  - {size: "белые / 3XL", raw: "3XL-1", units: 1, semantic: "ADDITION", confidence: "HIGH"}
  - {size: "черные / L", raw: "L-1", units: 1, semantic: "ADDITION", confidence: "HIGH"}
  - {size: "черные / XL", raw: "XL-1", units: 1, semantic: "ADDITION", confidence: "HIGH"}
```

**10. spider_rush_addition.JPG**
Product identification: Spider  
Raw label text: `Спайдер`

| size | RAW ink exactly as written | interpreted units | semantic | confidence |
|---|---:|---:|---|---|
| M | `M-1` | 1 | ADDITION | MED: addition inferred from filename; no dots/ALL ADDITIONS ink |

```yaml
image: "spider_rush_addition.JPG"
product_label_raw: "Спайдер"
sku_guess: "Spider"
rows:
  - {size: "M", raw: "M-1", units: 1, semantic: "ADDITION", confidence: "MED"}
```

**11. line61_additions.JPG**
Product identification: LINE61  
Raw label text: `6/1`

| size | RAW ink exactly as written | interpreted units | semantic | confidence |
|---|---:|---:|---|---|
| S | `S-1. = 1` | 1 | ADDITION | HIGH |
| M | `M-1 = 1` | 1 | ADDITION | HIGH |
| L | `L-3.3 = 6` | 6 | ADDITION | HIGH |
| XL | `XL-6.7 = 13` | 13 | ADDITION | HIGH |
| 2XL | `2XL-3.7 = 10` | 10 | ADDITION | HIGH |
| 3XL | `3XL-1.5 = 6` | 6 | ADDITION | HIGH |
| 4XL | `4XL-1.2 = 3` | 3 | ADDITION | HIGH |

```yaml
image: "line61_additions.JPG"
product_label_raw: "6/1"
sku_guess: "LINE61"
rows:
  - {size: "S", raw: "S-1. = 1", units: 1, semantic: "ADDITION", confidence: "HIGH"}
  - {size: "M", raw: "M-1 = 1", units: 1, semantic: "ADDITION", confidence: "HIGH"}
  - {size: "L", raw: "L-3.3 = 6", units: 6, semantic: "ADDITION", confidence: "HIGH"}
  - {size: "XL", raw: "XL-6.7 = 13", units: 13, semantic: "ADDITION", confidence: "HIGH"}
  - {size: "2XL", raw: "2XL-3.7 = 10", units: 10, semantic: "ADDITION", confidence: "HIGH"}
  - {size: "3XL", raw: "3XL-1.5 = 6", units: 6, semantic: "ADDITION", confidence: "HIGH"}
  - {size: "4XL", raw: "4XL-1.2 = 3", units: 3, semantic: "ADDITION", confidence: "HIGH"}
```

**12. t-shirts_white_and_t-shirts_black.JPG**
Product identification: short-sleeve T-shirts, white and black  
Raw label text: `Футболки коротким рукавом`; `белые`; `черные`; red `ALL ADDITIONS`

| size | RAW ink exactly as written | interpreted units | semantic | confidence |
|---|---:|---:|---|---|
| белые / L | `L-5` | 5 | ADDITION | HIGH |
| белые / XL | `XL-1` | 1 | ADDITION | HIGH |
| белые / 2XL | `2XL-1` | 1 | ADDITION | HIGH |
| черные / L | `L-3` | 3 | ADDITION | HIGH |
| черные / XL | `XL-2` | 2 | ADDITION | HIGH |

```yaml
image: "t-shirts_white_and_t-shirts_black.JPG"
product_label_raw: "Футболки коротким рукавом; белые; черные; red: ALL ADDITIONS"
sku_guess: "short_sleeve_tshirts_white_black"
rows:
  - {size: "белые / L", raw: "L-5", units: 5, semantic: "ADDITION", confidence: "HIGH"}
  - {size: "белые / XL", raw: "XL-1", units: 1, semantic: "ADDITION", confidence: "HIGH"}
  - {size: "белые / 2XL", raw: "2XL-1", units: 1, semantic: "ADDITION", confidence: "HIGH"}
  - {size: "черные / L", raw: "L-3", units: 3, semantic: "ADDITION", confidence: "HIGH"}
  - {size: "черные / XL", raw: "XL-2", units: 2, semantic: "ADDITION", confidence: "HIGH"}
```

**Batch Roll-Up**

| product / scope | additions total | full supersede values |
|---|---:|---|
| 3-in-1 kids | 0 | 110/22=12, 120/24=9, 150/30=28, 140/28=32, 130/26=54 |
| 3-in-1 with logotypes | 0 | XL=44, 2XL=55, 3XL=43, 4XL=30, L=20 |
| HUS / ХУС | 2 | none |
| Rombik | 8 | none |
| LINE51 черн.белый | 21 | S=82 |
| Berserk белый длинный рукав | 3 | none |
| Berserk черный длинный рукав | 4 | none |
| Berserk белый коротки рукав | 3 | none |
| Berserk черный коротки рукав | 2 | none |
| LINE52 | 62 | S=72 |
| Футболки длинным рукавом, белые | 6 | none |
| Футболки длинным рукавом, черные | 2 | none |
| Спайдер | 1 | none |
| LINE61 | 40 | none |
| Футболки коротким рукавом, белые | 7 | none |
| Футболки коротким рукавом, черные | 5 | none |

All additions total across batch: `166`.

**MED/LOW Confidence Cells**

- `HUS_addition.JPG` label: `ХУС` may visually read as `XYC`.
- `HUS_addition.JPG` XL `XL-1`: units clear, but ADDITION semantic inferred from filename only.
- `HUS_addition.JPG` 2XL `2XL-1`: units clear, but ADDITION semantic inferred from filename only.
- `Rombik_men_and_kids_all-addtions.JPG` S `S-1 = 1`: plain number, ADDITION semantic from red `ALL ADDITIONS`.
- `Rombik_men_and_kids_all-addtions.JPG` 140/28 `140/28-1.1. = 2`: size partly obscured; red `=28` supports 140/28.
- `line51_additions_but-S-full.JPG` S `S-82 →`: first digit is smudged/overwritten; best reading is 82.
- `line52_additions_but-S-full.JPG` 2XL `2XL-10.10. = 20`: leading `10` area has overwrite/correction; written total 20 is clear.
- `spider_rush_addition.JPG` M `M-1`: units clear, but ADDITION semantic inferred from filename only.
