"""
Size Probability Engine (Phase 9.5 Part 2 - TASK-136).

Implements 4-tier size determination cascade:
1. Customer-Provided: Height/weight → size chart → exact size
2. Offer-Level Mode: Most common size for specific kaspi_offer_name
3. Style-Level Mode: Most common size for sku_key across all offers
4. Product Type Default: Generic defaults (T-shirts: L, Pants: 32)

Usage:
    from core.calc.size_probability import (
        determine_size,
        calc_offer_size_mode,
        calc_style_size_mode,
    )

    # Auto-assign size using cascade
    size, source, confidence = determine_size(
        order={'kaspi_offer_name': 'PRO COMBAT 240079', 'sku_key': 'ELS_OC_MEN_PROCOMBAT_BLACK'},
        customer_height=175,
        customer_weight=80,
    )
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from core.db import get_db
from core.parsers.kaspi_parser import _extract_size as _extract_size_token
from core.utils.sku_normalize import infer_size_from_sku_id, normalize_size


logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

DB_PATH = Path(__file__).parent.parent.parent / "db" / "app.db"

# Confidence thresholds
OFFER_MIN_SAMPLES = 5
OFFER_HIGH_CONFIDENCE = 0.60
STYLE_MIN_SAMPLES = 10
STYLE_HIGH_CONFIDENCE = 0.40
MEDIUM_CONFIDENCE_MIN = 0.40

# Size chart: height/weight -> size (simplified, can be loaded from Excel)
SIZE_CHART = {
    # (height_min, height_max, weight_min, weight_max) -> size
    'CL': [
        (155, 165, 45, 55, 'S'),
        (160, 170, 55, 65, 'M'),
        (165, 180, 65, 80, 'L'),
        (170, 185, 75, 90, 'XL'),
        (175, 190, 85, 105, '2XL'),
        (180, 195, 95, 115, '3XL'),
        (185, 200, 105, 130, '4XL'),
    ],
    'ELS': [  # Sportswear - tends to run tighter
        (155, 165, 45, 55, 'S'),
        (160, 170, 50, 60, 'M'),
        (165, 175, 60, 70, 'L'),
        (170, 185, 65, 85, 'XL'),
        (175, 190, 80, 100, '2XL'),
        (180, 195, 90, 115, '3XL'),
        (185, 200, 105, 130, '4XL'),
    ],
    'KIDS': [
        (110, 120, 18, 24, '24'),
        (115, 125, 20, 28, '26'),
        (120, 130, 24, 32, '28'),
        (125, 140, 28, 38, '30'),
        (135, 150, 32, 45, '32'),
        (145, 160, 40, 55, '34'),
    ],
}

# Default sizes by product type
PRODUCT_TYPE_DEFAULTS = {
    'CL': 'L',
    'ELS': 'L',
    'FUR': 'L',
    'KIDS': '28',
    'WB': 'L',
}


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class SizeProbability:
    """Size probability result."""
    mode_size: str
    mode_share: float
    sample_count: int
    confidence: str  # HIGH, MEDIUM, LOW
    size_distribution: dict  # {size: share}


@dataclass
class SizeResult:
    """Result of size determination."""
    size: str
    source: str  # CUSTOMER, OFFER_MODE, STYLE_MODE, DEFAULT
    confidence: str  # HIGH, MEDIUM, LOW
    probability: Optional[SizeProbability] = None


def infer_declared_order_size(order: dict) -> tuple[Optional[str], Optional[str]]:
    """
    Infer explicit size already declared by the order itself.

    This is different from historical "probable size" logic: if the merchant
    article / sku_id / live Kaspi offer text already encodes a concrete size
    variant like `4XL_58`, we should surface that exact declared size instead
    of falling all the way to generic product defaults like `L`.

    Resolution order:
    1. `sku_id` suffix
    2. `kaspi_article`
    3. `kaspi_offer_name`
    """
    product_type = order.get('product_type', 'CL')

    sku_id_size = infer_size_from_sku_id(order.get('sku_id'))
    if sku_id_size:
        normalized = normalize_size(sku_id_size, product_type) or sku_id_size
        if normalized:
            return normalized, 'SKU_ID'

    kaspi_article = order.get('kaspi_article')
    if kaspi_article:
        article_size = normalize_size(_extract_size_token(str(kaspi_article)), product_type)
        if article_size:
            return article_size, 'KASPI_ARTICLE'

    kaspi_offer_name = order.get('kaspi_offer_name')
    if kaspi_offer_name:
        offer_size = normalize_size(_extract_size_token(str(kaspi_offer_name)), product_type)
        if offer_size:
            return offer_size, 'KASPI_OFFER'

    return None, None


# =============================================================================
# SIZE FROM CUSTOMER PARAMS
# =============================================================================

def calc_size_from_params(
    height_cm: int,
    weight_kg: int,
    product_type: str = 'CL',
) -> Optional[str]:
    """
    Calculate size from customer height/weight using size chart.

    Args:
        height_cm: Customer height in cm
        weight_kg: Customer weight in kg
        product_type: Product type for size chart (CL, ELS, KIDS)

    Returns:
        Size string (S, M, L, XL, etc.) or None if no match
    """
    chart = SIZE_CHART.get(product_type, SIZE_CHART.get('CL', []))

    for h_min, h_max, w_min, w_max, size in chart:
        if h_min <= height_cm <= h_max and w_min <= weight_kg <= w_max:
            return size

    # Fallback: find closest match by height
    best_size = None
    best_distance = float('inf')

    for h_min, h_max, w_min, w_max, size in chart:
        h_mid = (h_min + h_max) / 2
        distance = abs(height_cm - h_mid)
        if distance < best_distance:
            best_distance = distance
            best_size = size

    return best_size


# =============================================================================
# OFFER-LEVEL MODE
# =============================================================================

def calc_offer_size_mode(
    kaspi_offer_name: str,
    db_path: Path = None,
) -> Optional[SizeProbability]:
    """
    Calculate mode size for specific kaspi_offer_name from historical sales.

    Args:
        kaspi_offer_name: Kaspi listing name
        db_path: Database path

    Returns:
        SizeProbability or None if insufficient data
    """
    db_path = db_path or DB_PATH

    with get_db(db_path) as conn:
        # Get size distribution for this offer
        rows = conn.execute(
            """
            SELECT my_size, SUM(quantity) as total_qty
            FROM fact_sales
            WHERE kaspi_offer_name = ?
              AND my_size IS NOT NULL
              AND my_size != ''
            GROUP BY my_size
            ORDER BY total_qty DESC
            """,
            (kaspi_offer_name,)
        ).fetchall()

        if not rows:
            return None

        # Calculate totals
        total = sum(row['total_qty'] for row in rows)
        if total < OFFER_MIN_SAMPLES:
            return None

        # Get mode (most common)
        mode_size = rows[0]['my_size']
        mode_qty = rows[0]['total_qty']
        mode_share = mode_qty / total

        # Build distribution
        distribution = {row['my_size']: row['total_qty'] / total for row in rows}

        # Determine confidence
        if mode_share >= OFFER_HIGH_CONFIDENCE:
            confidence = 'HIGH'
        elif mode_share >= MEDIUM_CONFIDENCE_MIN:
            confidence = 'MEDIUM'
        else:
            confidence = 'LOW'

        return SizeProbability(
            mode_size=mode_size,
            mode_share=mode_share,
            sample_count=total,
            confidence=confidence,
            size_distribution=distribution,
        )


# =============================================================================
# STYLE-LEVEL MODE
# =============================================================================

def calc_style_size_mode(
    sku_key: str,
    db_path: Path = None,
) -> Optional[SizeProbability]:
    """
    Calculate mode size for sku_key across all offers.

    Args:
        sku_key: Style-level SKU key
        db_path: Database path

    Returns:
        SizeProbability or None if insufficient data
    """
    db_path = db_path or DB_PATH

    with get_db(db_path) as conn:
        # Get size distribution for this style
        rows = conn.execute(
            """
            SELECT my_size, SUM(quantity) as total_qty
            FROM fact_sales
            WHERE sku_key = ?
              AND my_size IS NOT NULL
              AND my_size != ''
            GROUP BY my_size
            ORDER BY total_qty DESC
            """,
            (sku_key,)
        ).fetchall()

        if not rows:
            return None

        # Calculate totals
        total = sum(row['total_qty'] for row in rows)
        if total < STYLE_MIN_SAMPLES:
            return None

        # Get mode
        mode_size = rows[0]['my_size']
        mode_qty = rows[0]['total_qty']
        mode_share = mode_qty / total

        # Build distribution
        distribution = {row['my_size']: row['total_qty'] / total for row in rows}

        # Determine confidence (lower threshold for style level)
        if mode_share >= STYLE_HIGH_CONFIDENCE:
            confidence = 'HIGH' if mode_share >= 0.50 else 'MEDIUM'
        else:
            confidence = 'LOW'

        return SizeProbability(
            mode_size=mode_size,
            mode_share=mode_share,
            sample_count=total,
            confidence=confidence,
            size_distribution=distribution,
        )


# =============================================================================
# PRODUCT TYPE DEFAULT
# =============================================================================

def get_product_type_default(
    product_type: str,
    db_path: Path = None,
) -> Tuple[str, SizeProbability]:
    """
    Get default size for product type.

    First checks dim_size_probability for stored defaults,
    then falls back to hardcoded PRODUCT_TYPE_DEFAULTS.

    Args:
        product_type: Product type (CL, ELS, FUR, KIDS)
        db_path: Database path

    Returns:
        Tuple of (size, SizeProbability)
    """
    db_path = db_path or DB_PATH

    # Try database first
    with get_db(db_path) as conn:
        row = conn.execute(
            """
            SELECT mode_size, mode_share, sample_count, confidence, size_distribution
            FROM dim_size_probability
            WHERE level = 'PRODUCT_TYPE' AND key_value = ?
            """,
            (product_type,)
        ).fetchone()

        if row:
            distribution = {}
            if row['size_distribution']:
                try:
                    distribution = json.loads(row['size_distribution'])
                except json.JSONDecodeError:
                    pass

            prob = SizeProbability(
                mode_size=row['mode_size'],
                mode_share=row['mode_share'],
                sample_count=row['sample_count'],
                confidence=row['confidence'],
                size_distribution=distribution,
            )
            return row['mode_size'], prob

    # Fallback to hardcoded defaults
    size = PRODUCT_TYPE_DEFAULTS.get(product_type, 'L')
    prob = SizeProbability(
        mode_size=size,
        mode_share=0.35,
        sample_count=0,
        confidence='LOW',
        size_distribution={size: 0.35},
    )
    return size, prob


# =============================================================================
# MAIN DETERMINATION FUNCTION
# =============================================================================

def determine_size(
    order: dict,
    customer_height: Optional[int] = None,
    customer_weight: Optional[int] = None,
    db_path: Path = None,
) -> SizeResult:
    """
    Determine size using 4-tier cascade.

    Cascade Order:
    1. Customer-Provided: If height/weight given, use size chart
    2. Declared Order Size: Explicit size encoded in sku_id / article / offer
    3. Offer-Level Mode: Most common size for this kaspi_offer_name
    4. Style-Level Mode: Most common size for this sku_key
    5. Product Type Default: Generic default for product type

    Args:
        order: Dict with kaspi_offer_name, sku_key, product_type
        customer_height: Customer height in cm (optional)
        customer_weight: Customer weight in kg (optional)
        db_path: Database path

    Returns:
        SizeResult with size, source, and confidence
    """
    db_path = db_path or DB_PATH

    kaspi_offer_name = order.get('kaspi_offer_name')
    sku_key = order.get('sku_key')
    product_type = order.get('product_type', 'CL')

    # Tier 1: Customer-provided params
    if customer_height and customer_weight:
        size = calc_size_from_params(customer_height, customer_weight, product_type)
        if size:
            logger.debug(f"Size from customer params: {size}")
            size = normalize_size(size, product_type) or size
            return SizeResult(
                size=size,
                source='CUSTOMER',
                confidence='HIGH',
            )

    # Tier 2: Explicit declared size from the order variant itself.
    declared_size, declared_source = infer_declared_order_size(order)
    if declared_size:
        logger.debug(f"Size from declared order variant ({declared_source}): {declared_size}")
        size = normalize_size(declared_size, product_type) or declared_size
        return SizeResult(
            size=size,
            source='DECLARED_ORDER',
            confidence='HIGH',
        )

    # Tier 3: Offer-level mode
    if kaspi_offer_name:
        prob = calc_offer_size_mode(kaspi_offer_name, db_path)
        if prob and prob.sample_count >= OFFER_MIN_SAMPLES:
            logger.debug(
                f"Size from offer mode: {prob.mode_size} "
                f"({prob.mode_share:.1%}, n={prob.sample_count})"
            )
            size = normalize_size(prob.mode_size, product_type) or prob.mode_size
            return SizeResult(
                size=size,
                source='OFFER_MODE',
                confidence=prob.confidence,
                probability=prob,
            )

    # Tier 4: Style-level mode
    if sku_key:
        prob = calc_style_size_mode(sku_key, db_path)
        if prob and prob.sample_count >= STYLE_MIN_SAMPLES:
            logger.debug(
                f"Size from style mode: {prob.mode_size} "
                f"({prob.mode_share:.1%}, n={prob.sample_count})"
            )
            size = normalize_size(prob.mode_size, product_type) or prob.mode_size
            return SizeResult(
                size=size,
                source='STYLE_MODE',
                confidence=prob.confidence,
                probability=prob,
            )

    # Tier 5: Product type default
    size, prob = get_product_type_default(product_type, db_path)
    logger.debug(f"Size from product type default: {size}")
    size = normalize_size(size, product_type) or size
    return SizeResult(
        size=size,
        source='DEFAULT',
        confidence='LOW',
        probability=prob,
    )


# =============================================================================
# DATABASE OPERATIONS
# =============================================================================

def save_size_probability(
    level: str,
    key_value: str,
    prob: SizeProbability,
    db_path: Path = None,
):
    """
    Save size probability to dim_size_probability.

    Args:
        level: OFFER, STYLE, or PRODUCT_TYPE
        key_value: kaspi_offer_name, sku_key, or product_type
        prob: SizeProbability to save
        db_path: Database path
    """
    db_path = db_path or DB_PATH

    with get_db(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO dim_size_probability
            (level, key_value, mode_size, mode_share, sample_count, confidence, size_distribution)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                level,
                key_value,
                prob.mode_size,
                prob.mode_share,
                prob.sample_count,
                prob.confidence,
                json.dumps(prob.size_distribution) if prob.size_distribution else None,
            )
        )


def get_stored_probability(
    level: str,
    key_value: str,
    db_path: Path = None,
) -> Optional[SizeProbability]:
    """
    Get stored probability from dim_size_probability.

    Args:
        level: OFFER, STYLE, or PRODUCT_TYPE
        key_value: kaspi_offer_name, sku_key, or product_type
        db_path: Database path

    Returns:
        SizeProbability or None
    """
    db_path = db_path or DB_PATH

    with get_db(db_path) as conn:
        row = conn.execute(
            """
            SELECT mode_size, mode_share, sample_count, confidence, size_distribution
            FROM dim_size_probability
            WHERE level = ? AND key_value = ?
            """,
            (level, key_value)
        ).fetchone()

        if not row:
            return None

        distribution = {}
        if row['size_distribution']:
            try:
                distribution = json.loads(row['size_distribution'])
            except json.JSONDecodeError:
                pass

        return SizeProbability(
            mode_size=row['mode_size'],
            mode_share=row['mode_share'],
            sample_count=row['sample_count'],
            confidence=row['confidence'],
            size_distribution=distribution,
        )


def get_coverage_stats(db_path: Path = None) -> dict:
    """
    Get size probability coverage statistics.

    Returns:
        Dict with counts and coverage percentages
    """
    db_path = db_path or DB_PATH

    with get_db(db_path) as conn:
        # Count stored probabilities by level
        level_counts = {}
        rows = conn.execute(
            """
            SELECT level, COUNT(*) as cnt
            FROM dim_size_probability
            GROUP BY level
            """
        ).fetchall()
        for row in rows:
            level_counts[row['level']] = row['cnt']

        # Count unique kaspi_offer_names with data
        total_offers = conn.execute(
            """
            SELECT COUNT(DISTINCT kaspi_offer_name)
            FROM fact_sales
            WHERE kaspi_offer_name IS NOT NULL
            """
        ).fetchone()[0]

        covered_offers = level_counts.get('OFFER', 0)

        # Count unique sku_keys with data
        total_styles = conn.execute(
            """
            SELECT COUNT(DISTINCT sku_key)
            FROM fact_sales
            WHERE sku_key IS NOT NULL
            """
        ).fetchone()[0]

        covered_styles = level_counts.get('STYLE', 0)

        return {
            'by_level': level_counts,
            'total_offers': total_offers,
            'covered_offers': covered_offers,
            'offer_coverage': covered_offers / total_offers if total_offers > 0 else 0,
            'total_styles': total_styles,
            'covered_styles': covered_styles,
            'style_coverage': covered_styles / total_styles if total_styles > 0 else 0,
        }


# =============================================================================
# CLI TEST
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("Size Probability Engine Test")
    print("=" * 60)

    # Test offer mode
    print("\n[Test 1] Offer-level mode:")
    offer_name = "Спортивный костюм PRO COMBAT 240079 черный L"
    prob = calc_offer_size_mode(offer_name)
    if prob:
        print(f"  Offer: {offer_name[:50]}...")
        print(f"  Mode: {prob.mode_size} ({prob.mode_share:.1%})")
        print(f"  Samples: {prob.sample_count}")
        print(f"  Confidence: {prob.confidence}")
    else:
        print(f"  No data for: {offer_name[:50]}...")

    # Test style mode
    print("\n[Test 2] Style-level mode:")
    sku_key = "ELS_OC_MEN_PROCOMBAT_BLACK"
    prob = calc_style_size_mode(sku_key)
    if prob:
        print(f"  SKU: {sku_key}")
        print(f"  Mode: {prob.mode_size} ({prob.mode_share:.1%})")
        print(f"  Samples: {prob.sample_count}")
        print(f"  Confidence: {prob.confidence}")
    else:
        print(f"  No data for: {sku_key}")

    # Test cascade
    print("\n[Test 3] Size determination cascade:")
    order = {
        'kaspi_offer_name': 'Спортивный костюм PRO COMBAT 240079 черный L',
        'sku_key': 'ELS_OC_MEN_PROCOMBAT_BLACK',
        'product_type': 'ELS',
    }
    result = determine_size(order)
    print(f"  Size: {result.size}")
    print(f"  Source: {result.source}")
    print(f"  Confidence: {result.confidence}")

    # Test with customer params
    print("\n[Test 4] With customer params:")
    result = determine_size(order, customer_height=175, customer_weight=80)
    print(f"  Size: {result.size}")
    print(f"  Source: {result.source}")
    print(f"  Confidence: {result.confidence}")

    # Coverage stats
    print("\n[Test 5] Coverage statistics:")
    stats = get_coverage_stats()
    print(f"  Total offers: {stats['total_offers']}")
    print(f"  Covered offers: {stats['covered_offers']} ({stats['offer_coverage']:.1%})")
    print(f"  Total styles: {stats['total_styles']}")
    print(f"  Covered styles: {stats['covered_styles']} ({stats['style_coverage']:.1%})")

    print("\n" + "=" * 60)
    print("Test complete!")
    print("=" * 60)
