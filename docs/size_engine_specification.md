# size_engine Specification (Adult Men, China → MY_SIZE)

**Version:** 1.0  
**Date:** 2025-12-07  
**Scope:** Adult men's clothing only (kids and women excluded)

---

## 1. Overview & Business Context

Products in this system use **Chinese size standards**, but the primary customer base is in **Kazakhstan and Russia (KZ/RU)**. Chinese sizing runs smaller than European/Russian sizing, creating a mapping challenge when customers provide their body measurements.

The `size_engine` determines the optimal `MY_SIZE` (internal size code) based on three inputs: the **offer size** from the Kaspi listing, customer **height**, and customer **weight**. The goal is to **minimize returns and customer dissatisfaction** by shipping the size most likely to fit.

**Key business constraint:** If we ship a size different from what the customer explicitly ordered (`offer_size`), and the customer wanted that exact size, the probability of return/refund increases significantly. Therefore, when customer parameters fall in **borderline/overlapping ranges**, the `offer_size` serves as a tiebreaker—we honor the customer's deliberate choice.

The algorithm must be **deterministic and predictable** so that developers can implement it without ambiguity and customer service can explain sizing decisions consistently.

---

## 2. Inputs & Outputs

### 2.1 Inputs

| Input | Type | Description | Example |
|-------|------|-------------|---------|
| `KASPI_OFFER_NAME` | String | Full product name from Kaspi listing, contains size info | `"Комплект Antec RASH-921 Рашгард 5 в 1 черный 44/46"` |
| `offer_size` | String | Extracted size portion from `KASPI_OFFER_NAME` | `"44/46"` |
| `height_cm` | Integer (nullable) | Customer height in centimeters | `181` |
| `weight_kg` | Integer (nullable) | Customer weight in kilograms | `79` |

### 2.2 Outputs

| Output | Type | Description | Example |
|--------|------|-------------|---------|
| `final_MY_SIZE` | String | The size to ship | `"2XL"` |
| `MY_SIZE_HEIGHT` | String | Size derived from height alone | `"2XL"` |
| `MY_SIZE_WEIGHT` | String | Size derived from weight alone | `"XL"` |
| `offer_size_MY_SIZE` | String | Size family of the offer | `"L"` |

---

## 3. Data Model

### 3.1 MY_SIZE Families & Synonyms

Each `MY_SIZE` has a **rank** for comparison. Lower rank = smaller size.

| Rank | MY_SIZE | Equivalent Values (all map to this MY_SIZE) |
|------|---------|---------------------------------------------|
| 1 | XS | `XS`, `38`, `40`, `XXS`, `2XS` |
| 2 | S | `S`, `42` |
| 3 | M | `M`, `44` |
| 4 | L | `L`, `46` |
| 5 | XL | `XL`, `48`, `50` |
| 6 | 2XL | `2XL`, `XXL`, `52` |
| 7 | 3XL | `3XL`, `XXXL`, `54` |
| 8 | 4XL | `4XL`, `XXXXL`, `5XL`, `6XL`, `7XL`, `8XL`, `56`, `58`, `60`, `62`, `64` |

**Note:** `XS` is treated as part of the `S` family for extreme range purposes (uses S's height/weight ranges).

### 3.2 Extreme Ranges (Height & Weight)

These ranges define which `MY_SIZE` is appropriate for a given height or weight. **Overlaps are intentional**—they define conflict zones.

| MY_SIZE | Rank | Height Range (cm) | Weight Range (kg) |
|---------|------|-------------------|-------------------|
| S (incl. XS) | 2 | 130–168 | 25–47 |
| M | 3 | 166–173 | 45–60 |
| L | 4 | 171–177 | 60–67 |
| XL | 5 | 176–182 | 65–82 |
| 2XL | 6 | 181–190 | 80–91 |
| 3XL | 7 | 188–195 | 88–110 |
| 4XL | 8 | 194–250 | 109–160 |

### 3.3 Conflict Ranges (Overlaps)

Pre-computed overlapping zones where multiple sizes are valid:

**Height Conflict Ranges:**

| Height Range | Conflict_SIZES_HEIGHT |
|--------------|----------------------|
| 166–168 cm | {S, M} |
| 171–173 cm | {M, L} |
| 176–177 cm | {L, XL} |
| 181–182 cm | {XL, 2XL} |
| 188–190 cm | {2XL, 3XL} |
| 194–195 cm | {3XL, 4XL} |

**Weight Conflict Ranges:**

| Weight Range | Conflict_SIZES_WEIGHT |
|--------------|----------------------|
| 45–47 kg | {S, M} |
| 60 kg | {M, L} |
| 65–67 kg | {L, XL} |
| 80–82 kg | {XL, 2XL} |
| 88–91 kg | {2XL, 3XL} |
| 109–110 kg | {3XL, 4XL} |

---

## 4. Offer Size Parsing

### 4.1 Token Extraction Rules

1. **Extract the size portion** from `KASPI_OFFER_NAME`:
   - Size tokens typically appear at the end of the product name
   - Common patterns: `"... черный 48"`, `"... белый 44/46"`, `"... XL"`, `"... 42-44"`

2. **Split into individual tokens** using separators: `-`, `/`, space
   - Example: `"44/46"` → tokens: `["44", "46"]`
   - Example: `"42-44"` → tokens: `["42", "44"]`
   - Example: `"S/40"` → tokens: `["S", "40"]`

3. **Normalize each token** to uppercase and trim whitespace

### 4.2 Token-to-MY_SIZE Mapping

Map each extracted token to its `MY_SIZE` family:

```
TOKEN_MAP = {
    # XS family (rank 1)
    "38": "XS", "40": "XS", "XS": "XS", "XXS": "XS", "2XS": "XS",
    
    # S family (rank 2)
    "42": "S", "S": "S",
    
    # M family (rank 3)
    "44": "M", "M": "M",
    
    # L family (rank 4)
    "46": "L", "L": "L",
    
    # XL family (rank 5)
    "48": "XL", "50": "XL", "XL": "XL",
    
    # 2XL family (rank 6)
    "52": "2XL", "XXL": "2XL", "2XL": "2XL",
    
    # 3XL family (rank 7)
    "54": "3XL", "XXXL": "3XL", "3XL": "3XL",
    
    # 4XL family (rank 8)
    "56": "4XL", "58": "4XL", "60": "4XL", "62": "4XL", "64": "4XL",
    "XXXXL": "4XL", "4XL": "4XL", "5XL": "4XL", "6XL": "4XL", 
    "7XL": "4XL", "8XL": "4XL"
}
```

### 4.3 Computing offer_size_MY_SIZE

**Rule:** `offer_size_MY_SIZE` = the **maximum** (highest rank) MY_SIZE among all tokens.

**Algorithm:**
```
1. Extract all tokens from offer_size
2. Map each token to its MY_SIZE family
3. Return the MY_SIZE with the highest rank
```

### 4.4 Parsing Examples

**Example 1:** `KASPI_OFFER_NAME = "Комплект Antec RASH-921 Рашгард 5 в 1 черный 44/46"`
- Extracted size portion: `"44/46"`
- Tokens: `["44", "46"]`
- Mapped families: `[M (rank 3), L (rank 4)]`
- `offer_size_MY_SIZE = L` (max rank = 4)

**Example 2:** `KASPI_OFFER_NAME = "Футболка мужская черная 48"`
- Extracted size portion: `"48"`
- Tokens: `["48"]`
- Mapped families: `[XL (rank 5)]`
- `offer_size_MY_SIZE = XL`

**Example 3:** `KASPI_OFFER_NAME = "Костюм спортивный S-XL"`
- Extracted size portion: `"S-XL"`
- Tokens: `["S", "XL"]`
- Mapped families: `[S (rank 2), XL (rank 5)]`
- `offer_size_MY_SIZE = XL` (max rank = 5)

---

## 5. Algorithm Logic

### 5.1 Computing MY_SIZE_HEIGHT

**Input:** `height_cm` (integer or null)

**Steps:**

1. **If height_cm is null:** Skip height-based sizing (return null)

2. **Clamp to valid range:**
   - If `height_cm < 130`: treat as 130 (→ S)
   - If `height_cm > 250`: treat as 250 (→ 4XL)

3. **Find all candidate sizes** whose height range includes `height_cm`:
   ```
   candidates = []
   for each MY_SIZE in [S, M, L, XL, 2XL, 3XL, 4XL]:
       if height_range_min <= height_cm <= height_range_max:
           candidates.append(MY_SIZE)
   ```

4. **If exactly one candidate:** `MY_SIZE_HEIGHT = that candidate`

5. **If multiple candidates (Conflict_range):** Apply Conflict Rule (§5.3)

### 5.2 Computing MY_SIZE_WEIGHT

**Input:** `weight_kg` (integer or null)

**Steps:**

1. **If weight_kg is null:** Skip weight-based sizing (return null)

2. **Clamp to valid range:**
   - If `weight_kg < 25`: treat as 25 (→ S)
   - If `weight_kg > 160`: treat as 160 (→ 4XL)

3. **Find all candidate sizes** whose weight range includes `weight_kg`:
   ```
   candidates = []
   for each MY_SIZE in [S, M, L, XL, 2XL, 3XL, 4XL]:
       if weight_range_min <= weight_kg <= weight_range_max:
           candidates.append(MY_SIZE)
   ```

4. **If exactly one candidate:** `MY_SIZE_WEIGHT = that candidate`

5. **If multiple candidates (Conflict_range):** Apply Conflict Rule (§5.3)

### 5.3 Conflict Rules

When a height or weight value falls in a **Conflict_range** (multiple valid sizes), use `offer_size_MY_SIZE` as a tiebreaker.

#### Case 1: offer_size_MY_SIZE ∈ Conflict_SIZES

> If `offer_size_MY_SIZE` is one of the conflicting sizes, **honor the customer's choice**.

**Rule:** `MY_SIZE_HEIGHT` (or `MY_SIZE_WEIGHT`) = `offer_size_MY_SIZE`

**Rationale:** Customer deliberately selected this size; their body params are borderline; ship what they asked for.

#### Case 2: offer_size_MY_SIZE ∉ Conflict_SIZES

> If `offer_size_MY_SIZE` is NOT one of the conflicting sizes, choose the **nearest** size from the conflict set.

**Rule:** 
```
MY_SIZE = argmin(|rank(candidate) - rank(offer_size_MY_SIZE)|) 
          for candidate in Conflict_SIZES
```

**Tie-breaking:** If two candidates are equidistant, choose the **larger** size (higher rank).

**Rationale:** Customer's offer selection indicates their size preference direction; choose the conflict size closest to that preference.

### 5.4 Final Size Decision

Once `MY_SIZE_HEIGHT` and `MY_SIZE_WEIGHT` are computed:

```
final_MY_SIZE = max(MY_SIZE_HEIGHT, MY_SIZE_WEIGHT)
```

Using rank ordering: `S < M < L < XL < 2XL < 3XL < 4XL`

**Rationale:** When height and weight suggest different sizes, the **larger** size is safer—a slightly loose fit is preferable to a garment that doesn't fit at all.

### 5.5 Complete Algorithm Flowchart

```
START
  │
  ├─→ Parse offer_size from KASPI_OFFER_NAME
  │   └─→ Compute offer_size_MY_SIZE (max of all tokens)
  │
  ├─→ Compute MY_SIZE_HEIGHT
  │   ├─→ If height_cm is null → MY_SIZE_HEIGHT = null
  │   ├─→ Clamp height to [130, 250]
  │   ├─→ Find candidate sizes from height ranges
  │   ├─→ If 1 candidate → MY_SIZE_HEIGHT = candidate
  │   └─→ If multiple → Apply Conflict Rule → MY_SIZE_HEIGHT
  │
  ├─→ Compute MY_SIZE_WEIGHT
  │   ├─→ If weight_kg is null → MY_SIZE_WEIGHT = null
  │   ├─→ Clamp weight to [25, 160]
  │   ├─→ Find candidate sizes from weight ranges
  │   ├─→ If 1 candidate → MY_SIZE_WEIGHT = candidate
  │   └─→ If multiple → Apply Conflict Rule → MY_SIZE_WEIGHT
  │
  └─→ Compute final_MY_SIZE
      ├─→ If both null → final_MY_SIZE = offer_size_MY_SIZE
      ├─→ If height null → final_MY_SIZE = MY_SIZE_WEIGHT
      ├─→ If weight null → final_MY_SIZE = MY_SIZE_HEIGHT
      └─→ Otherwise → final_MY_SIZE = max(MY_SIZE_HEIGHT, MY_SIZE_WEIGHT)
  │
END
```

---

## 6. Edge Cases & Assumptions

### 6.1 Missing Inputs

| Condition | Behavior |
|-----------|----------|
| `height_cm = null` | `final_MY_SIZE = MY_SIZE_WEIGHT` |
| `weight_kg = null` | `final_MY_SIZE = MY_SIZE_HEIGHT` |
| Both null | `final_MY_SIZE = offer_size_MY_SIZE` |

### 6.2 Out-of-Range Values

| Condition | Behavior |
|-----------|----------|
| `height_cm < 130` | Treat as 130 → S |
| `height_cm > 250` | Treat as 250 → 4XL |
| `weight_kg < 25` | Treat as 25 → S |
| `weight_kg > 160` | Treat as 160 → 4XL |

### 6.3 Malformed offer_size

| Condition | Behavior |
|-----------|----------|
| No recognizable size tokens | Log warning; use height/weight only |
| Empty or null offer_size | Use height/weight only; if both null, return error |
| Contains unrecognized tokens (e.g., "MEDIUM") | Ignore unrecognized tokens; use recognized ones |
| All tokens unrecognized | Log error; use height/weight only |

### 6.4 XS Handling

- `XS` maps to rank 1 but uses **S's extreme ranges** (130–168cm, 25–47kg)
- If height/weight analysis yields S, and `offer_size_MY_SIZE = XS`, return `XS`
- Otherwise, return `S` for the S/XS family

### 6.5 Gaps in Ranges

Some height/weight values fall **between** ranges (no single size covers them):

| Height Gap | Resolution |
|------------|------------|
| 169–170 cm | Between S (max 168) and L (min 171) → return M |
| 174–175 cm | Between L (max 177) and XL (min 176) — actually covered by both → Conflict |
| 183–187 cm | Between XL (max 182) and 3XL (min 188) → return 2XL |
| 191–193 cm | Between 2XL (max 190) and 4XL (min 194) → return 3XL |

**Rule for gaps:** Return the size whose range **ends** closest to the value (i.e., round up to the next size).

| Weight Gap | Resolution |
|------------|------------|
| 48–44 kg | Covered by S and M (overlap) → Conflict |
| 61–64 kg | Between L (max 67) — actually within L range |
| 83–87 kg | Between XL (max 82) and 3XL (min 88) → return 2XL |
| 92–108 kg | Between 2XL (max 91) and 4XL (min 109) → return 3XL |

---

## 7. Worked Examples

### Example 1: Order ID 632164244 (Conflict Case 1 — Height)

**Inputs:**
- `KASPI_OFFER_NAME = "Комплект Antec RASH-921 Рашгард 5 в 1 черный 48"`
- `height_cm = 181`
- `weight_kg = 64`

**Step 1: Parse offer_size**
- Extracted: `"48"`
- Tokens: `["48"]`
- Mapped: `[XL]`
- `offer_size_MY_SIZE = XL` (rank 5)

**Step 2: Compute MY_SIZE_HEIGHT**
- 181 cm falls within:
  - XL: 176–182 ✓
  - 2XL: 181–190 ✓
- `Conflict_SIZES_HEIGHT = {XL, 2XL}`
- `offer_size_MY_SIZE = XL` ∈ `{XL, 2XL}` → **Case 1**
- `MY_SIZE_HEIGHT = XL`

**Step 3: Compute MY_SIZE_WEIGHT**
- 64 kg falls within:
  - L: 60–67 ✓
- Single candidate → `MY_SIZE_WEIGHT = L`

**Step 4: Final Decision**
- `final_MY_SIZE = max(XL, L) = XL`

**Result:** Ship size **XL**

---

### Example 2: Order ID 179872684 (Conflict Case 2 — Height)

**Inputs:**
- `KASPI_OFFER_NAME = "Комплект Antec RASH-921 Рашгард 5 в 1 черный 44/46"`
- `height_cm = 188`
- `weight_kg = 79`

**Step 1: Parse offer_size**
- Extracted: `"44/46"`
- Tokens: `["44", "46"]`
- Mapped: `[M, L]`
- `offer_size_MY_SIZE = L` (rank 4, max of M=3 and L=4)

**Step 2: Compute MY_SIZE_HEIGHT**
- 188 cm falls within:
  - 2XL: 181–190 ✓
  - 3XL: 188–195 ✓
- `Conflict_SIZES_HEIGHT = {2XL, 3XL}`
- `offer_size_MY_SIZE = L` ∉ `{2XL, 3XL}` → **Case 2**
- Distance calculation:
  - L (rank 4) to 2XL (rank 6): |4-6| = 2
  - L (rank 4) to 3XL (rank 7): |4-7| = 3
- Nearest = 2XL
- `MY_SIZE_HEIGHT = 2XL`

**Step 3: Compute MY_SIZE_WEIGHT**
- 79 kg falls within:
  - XL: 65–82 ✓
- Single candidate → `MY_SIZE_WEIGHT = XL`

**Step 4: Final Decision**
- `final_MY_SIZE = max(2XL, XL) = 2XL`

**Result:** Ship size **2XL**

---

### Example 3: Weight Conflict Case (Invented)

**Inputs:**
- `KASPI_OFFER_NAME = "Футболка мужская LINE52 черная 52"`
- `height_cm = 178`
- `weight_kg = 89`

**Step 1: Parse offer_size**
- Extracted: `"52"`
- Tokens: `["52"]`
- Mapped: `[2XL]`
- `offer_size_MY_SIZE = 2XL` (rank 6)

**Step 2: Compute MY_SIZE_HEIGHT**
- 178 cm falls within:
  - XL: 176–182 ✓
- Single candidate → `MY_SIZE_HEIGHT = XL`

**Step 3: Compute MY_SIZE_WEIGHT**
- 89 kg falls within:
  - 2XL: 80–91 ✓
  - 3XL: 88–110 ✓
- `Conflict_SIZES_WEIGHT = {2XL, 3XL}`
- `offer_size_MY_SIZE = 2XL` ∈ `{2XL, 3XL}` → **Case 1**
- `MY_SIZE_WEIGHT = 2XL`

**Step 4: Final Decision**
- `final_MY_SIZE = max(XL, 2XL) = 2XL`

**Result:** Ship size **2XL**

**Explanation:** Customer ordered 2XL explicitly. Their weight (89kg) is in the conflict zone between 2XL and 3XL. Since they chose 2XL, we honor that choice. Height (178cm) suggests XL, but 2XL > XL, so final size is 2XL.

---

### Example 4: Both Height and Weight in Conflict (Invented)

**Inputs:**
- `KASPI_OFFER_NAME = "Спортивный костюм Nike черный XL"`
- `height_cm = 181`
- `weight_kg = 81`

**Step 1: Parse offer_size**
- Extracted: `"XL"`
- Tokens: `["XL"]`
- Mapped: `[XL]`
- `offer_size_MY_SIZE = XL` (rank 5)

**Step 2: Compute MY_SIZE_HEIGHT**
- 181 cm falls within:
  - XL: 176–182 ✓
  - 2XL: 181–190 ✓
- `Conflict_SIZES_HEIGHT = {XL, 2XL}`
- `offer_size_MY_SIZE = XL` ∈ `{XL, 2XL}` → **Case 1**
- `MY_SIZE_HEIGHT = XL`

**Step 3: Compute MY_SIZE_WEIGHT**
- 81 kg falls within:
  - XL: 65–82 ✓
  - 2XL: 80–91 ✓
- `Conflict_SIZES_WEIGHT = {XL, 2XL}`
- `offer_size_MY_SIZE = XL` ∈ `{XL, 2XL}` → **Case 1**
- `MY_SIZE_WEIGHT = XL`

**Step 4: Final Decision**
- `final_MY_SIZE = max(XL, XL) = XL`

**Result:** Ship size **XL**

**Explanation:** Customer is borderline on both dimensions (height 181cm, weight 81kg). Both conflicts include XL and 2XL. Customer explicitly chose XL, so we honor that choice for both dimensions. Final size is XL.

---

### Example 5: Missing Weight (Invented)

**Inputs:**
- `KASPI_OFFER_NAME = "Рашгард мужской 46-48"`
- `height_cm = 175`
- `weight_kg = null`

**Step 1: Parse offer_size**
- Extracted: `"46-48"`
- Tokens: `["46", "48"]`
- Mapped: `[L, XL]`
- `offer_size_MY_SIZE = XL` (rank 5)

**Step 2: Compute MY_SIZE_HEIGHT**
- 175 cm falls within:
  - L: 171–177 ✓
- Single candidate → `MY_SIZE_HEIGHT = L`

**Step 3: Compute MY_SIZE_WEIGHT**
- weight_kg = null → `MY_SIZE_WEIGHT = null`

**Step 4: Final Decision**
- Weight is null → `final_MY_SIZE = MY_SIZE_HEIGHT = L`

**Result:** Ship size **L**

---

## 8. Implementation Reference

### 8.1 Python Pseudocode

```python
# Constants
SIZE_RANKS = {"XS": 1, "S": 2, "M": 3, "L": 4, "XL": 5, "2XL": 6, "3XL": 7, "4XL": 8}

HEIGHT_RANGES = {
    "S": (130, 168), "M": (166, 173), "L": (171, 177),
    "XL": (176, 182), "2XL": (181, 190), "3XL": (188, 195), "4XL": (194, 250)
}

WEIGHT_RANGES = {
    "S": (25, 47), "M": (45, 60), "L": (60, 67),
    "XL": (65, 82), "2XL": (80, 91), "3XL": (88, 110), "4XL": (109, 160)
}

def get_candidates(value, ranges):
    """Return all sizes whose range includes the value."""
    return [size for size, (lo, hi) in ranges.items() if lo <= value <= hi]

def apply_conflict_rule(candidates, offer_size_my_size):
    """Apply conflict resolution using offer_size as tiebreaker."""
    if offer_size_my_size in candidates:
        return offer_size_my_size  # Case 1
    
    # Case 2: Find nearest
    offer_rank = SIZE_RANKS.get(offer_size_my_size, 4)
    distances = [(SIZE_RANKS[c], abs(SIZE_RANKS[c] - offer_rank), c) for c in candidates]
    distances.sort(key=lambda x: (x[1], -x[0]))  # Sort by distance, then by rank desc
    return distances[0][2]

def determine_size(height_cm, weight_kg, offer_size_my_size):
    """Main size determination function."""
    
    # Height
    my_size_height = None
    if height_cm is not None:
        height_cm = max(130, min(250, height_cm))  # Clamp
        candidates = get_candidates(height_cm, HEIGHT_RANGES)
        if len(candidates) == 1:
            my_size_height = candidates[0]
        elif len(candidates) > 1:
            my_size_height = apply_conflict_rule(candidates, offer_size_my_size)
    
    # Weight
    my_size_weight = None
    if weight_kg is not None:
        weight_kg = max(25, min(160, weight_kg))  # Clamp
        candidates = get_candidates(weight_kg, WEIGHT_RANGES)
        if len(candidates) == 1:
            my_size_weight = candidates[0]
        elif len(candidates) > 1:
            my_size_weight = apply_conflict_rule(candidates, offer_size_my_size)
    
    # Final decision
    if my_size_height is None and my_size_weight is None:
        return offer_size_my_size
    if my_size_height is None:
        return my_size_weight
    if my_size_weight is None:
        return my_size_height
    
    # Return max
    return my_size_height if SIZE_RANKS[my_size_height] >= SIZE_RANKS[my_size_weight] else my_size_weight
```

### 8.2 SQL Implementation Notes

For batch processing in SQLite/PostgreSQL:

1. Create lookup table `dim_size_ranges` with columns: `my_size`, `rank`, `height_min`, `height_max`, `weight_min`, `weight_max`
2. Create synonym table `dim_size_synonyms` with columns: `token`, `my_size`
3. Use window functions to find candidates and apply conflict logic

---

## 9. Change Log

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-12-07 | Initial specification |

---

*End of specification.*
