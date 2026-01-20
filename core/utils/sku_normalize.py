#!/usr/bin/env python3
"""
SKU Key Normalization Utility

Handles mapping between different SKU key conventions:
- Stock file uses: CL_NK_MEN_LINE51_WHITE
- Anchor/targets use: CL_OC_MEN_LINE51_WHITE

This prevents mismatches when joining data from different sources.
"""

# Mapping from source convention to canonical convention
SKU_PREFIX_MAPPINGS = {
    'CL_NK_': 'CL_OC_',  # Stock file -> Anchor/Target convention
}

def normalize_sku_key(sku_key: str) -> str:
    """
    Normalize SKU key to canonical form (anchor/target convention).

    Args:
        sku_key: Raw SKU key from any source

    Returns:
        Normalized SKU key matching anchor file convention

    Example:
        >>> normalize_sku_key('CL_NK_MEN_LINE51_WHITE')
        'CL_OC_MEN_LINE51_WHITE'
    """
    if not sku_key:
        return sku_key

    for old_prefix, new_prefix in SKU_PREFIX_MAPPINGS.items():
        if sku_key.startswith(old_prefix):
            return sku_key.replace(old_prefix, new_prefix, 1)

    return sku_key


def denormalize_sku_key(sku_key: str, target_convention: str = 'CL_NK_') -> str:
    """
    Convert canonical SKU key back to specific source convention.

    Args:
        sku_key: Normalized SKU key
        target_convention: Target prefix to use

    Returns:
        SKU key in target convention
    """
    if not sku_key:
        return sku_key

    # Find canonical prefix
    for old_prefix, canonical in SKU_PREFIX_MAPPINGS.items():
        if sku_key.startswith(canonical):
            return sku_key.replace(canonical, target_convention, 1)

    return sku_key


# Valid size codes (for filtering invalid data)
VALID_SIZES = {
    # Letter sizes
    'XS', 'S', 'M', 'L', 'XL', '2XL', '3XL', '4XL', '5XL',
    # Numeric sizes (pants/shorts)
    '22', '24', '26', '28', '30', '32', '34', '36', '38', '40', '42',
    # One-size items (electronics, accessories)
    'ONE_SIZE', 'ONESIZE', 'OS',
}

SIZE_SYNONYMS = {
    'ONESIZE': 'ONE_SIZE',
    'ONE SIZE': 'ONE_SIZE',
    'OS': 'ONE_SIZE',
    'O/S': 'ONE_SIZE',
    'XXL': '2XL',
    'XXXL': '3XL',
    'XXXXL': '4XL',
    '2XLB': '2XL',
    '2XL\u0411': '2XL',
    '3XLB': '3XL',
    '3XL\u0411': '3XL',
    '4XLB': '4XL',
    '4XL\u0411': '4XL',
}

ADULT_CL_NUMERIC_SYNONYMS = {
    '42': 'S',
    '44': 'M',
    '46': 'L',
    '48': 'XL',
    '50': 'XL',
    '52': '2XL',
    '54': '3XL',
    '56': '4XL',
    '58': '4XL',
    '60': '4XL',
}


def normalize_size(size, product_type: str = None, synonyms: dict[str, str] | None = None) -> str:
    """
    Normalize size value to standard format.

    Handles:
    - None/empty -> 'ONE_SIZE' for electronics
    - Numeric -> string
    - Case normalization

    Args:
        size: Raw size value (string, int, or None)
        product_type: Product type code (ELS, CL, etc.)

    Returns:
        Normalized size string or None if invalid
    """
    # Handle None/empty for electronics
    if size is None or str(size).strip() in ('', '0', 'None', 'nan'):
        if product_type and product_type.upper() in ('ELS', 'ELEC', 'ELECTRONICS'):
            return 'ONE_SIZE'
        return None

    size_str = str(size).strip().upper()
    size_clean = "".join(size_str.split()).replace("-", "")

    if synonyms and size_clean in synonyms:
        size_clean = synonyms[size_clean]
    if product_type and product_type.upper().startswith("CL"):
        if size_clean in ADULT_CL_NUMERIC_SYNONYMS:
            size_clean = ADULT_CL_NUMERIC_SYNONYMS[size_clean]
    if size_clean in SIZE_SYNONYMS:
        size_clean = SIZE_SYNONYMS[size_clean]

    if size_clean in VALID_SIZES:
        return size_clean

    return size_clean or None


def infer_size_from_sku_id(sku_id: str | None) -> str | None:
    """
    Infer size token from a sku_id suffix.

    Example: CL_LINE52_BLACK_M -> M
    """
    if not sku_id:
        return None
    raw = str(sku_id).strip()
    if "_" not in raw:
        return None
    _, suffix = raw.rsplit("_", 1)
    suffix = suffix.strip()
    normalized = normalize_size(suffix)
    if not normalized:
        return None
    if normalized not in VALID_SIZES:
        return None
    return normalized


def normalize_sku_id(sku_id: str | None, sku_key_hint: str | None = None) -> str | None:
    """
    Normalize sku_id to canonical form: <normalized_sku_key>_<normalized_size>.

    If size cannot be inferred, returns normalized sku_key only.
    """
    if not sku_id and not sku_key_hint:
        return None

    raw = str(sku_id).strip() if sku_id else ""
    raw = " ".join(raw.split())
    raw = raw.upper()

    size = infer_size_from_sku_id(raw)
    base = raw
    if size and "_" in raw:
        base = raw.rsplit("_", 1)[0]

    if sku_key_hint:
        base = normalize_sku_key(str(sku_key_hint).strip())
    else:
        base = normalize_sku_key(base)

    if size:
        return f"{base}_{size}"
    return base


if __name__ == "__main__":
    # Quick test
    test_cases = [
        ('CL_NK_MEN_LINE51_WHITE', 'CL_OC_MEN_LINE51_WHITE'),
        ('CL_OC_MEN_LINE52_BLACK', 'CL_OC_MEN_LINE52_BLACK'),
        ('ELS_PRINTER_EPSON_L132_BLACK', 'ELS_PRINTER_EPSON_L132_BLACK'),
    ]

    print("SKU Key Normalization Tests:")
    for input_key, expected in test_cases:
        result = normalize_sku_key(input_key)
        status = "PASS" if result == expected else "FAIL"
        print(f"  {status} {input_key} -> {result}")

    print("\nSize Normalization Tests:")
    size_tests = [
        (None, 'ELS', 'ONE_SIZE'),
        ('3XL', 'CL', '3XL'),
        ('32', 'CL', '32'),
        ('', 'CL', None),
    ]
    for size, pt, expected in size_tests:
        result = normalize_size(size, pt)
        status = "PASS" if result == expected else "FAIL"
        print(f"  {status} ({size}, {pt}) -> {result}")
