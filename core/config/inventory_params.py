"""
TASK-150: Centralized Inventory Parameters

All parameters match Master_Inventory_Rules_v9.md exactly.
This is the single source of truth for inventory calculations.

Parameters:
- L, R, B, z, TV: From Master Rules Section 4.1
- sigma_factor: From Master Rules Section 5.1
- Size mix guardrails: 3% floor, 40% cap
- ROIC thresholds: 20% full approval, 10% flag threshold
- New SKU factors: Age-based demand adjustments
"""

from dataclasses import dataclass
from typing import Optional

# Singleton instance
_PARAMS_INSTANCE: Optional['InventoryParams'] = None


@dataclass(frozen=True)
class InventoryParams:
    """
    Immutable inventory parameters.

    All values from Master_Inventory_Rules_v9.md:
    - Section 4.1: Global Defaults (L, R, B, z, TV)
    - Section 5.1: Demand & Volatility (sigma_factor)

    Phase 9.6 additions:
    - Size mix guardrails (3% floor, 40% cap)
    - ROIC gate thresholds (20%, 10%)
    - New SKU age factors (0.75, 0.85, 0.95)
    """

    # === Core Parameters (Master Rules Section 4.1) ===
    L: int = 21           # Lead time in days
    R: int = 10           # Review period in days
    B: int = 14           # Buffer factor for floor stock (days)
    z: float = 1.65       # Z-score for 95% service level
    TV: float = 0.23      # Mix variability factor (Target Variability)

    # === Volatility (Master Rules Section 5.1) ===
    sigma_factor: float = 0.4   # sigma = D30 * 0.4

    # === Size Mix Guardrails (Phase 9.6) ===
    min_size_mix: float = 0.03  # 3% floor per size
    max_size_mix: float = 0.40  # 40% cap per size

    # === ROIC Gate Thresholds (Phase 9.6) ===
    roic_full_approval: float = 0.20   # >= 20%: ORDER_FULL
    roic_flag_threshold: float = 0.10  # 10-20%: ORDER_WITH_FLAG, <10%: REVIEW_REQUIRED

    # === New SKU Age Factors (Phase 9.6) ===
    # Reduce order quantities for SKUs with limited history
    new_sku_30d_factor: float = 0.75   # <30 days history: 75%
    new_sku_60d_factor: float = 0.85   # 30-60 days: 85%
    new_sku_90d_factor: float = 0.95   # 60-90 days: 95%
    # >= 90 days: 100% (no adjustment)


# Default parameters instance
PARAMS = InventoryParams()


def get_params() -> InventoryParams:
    """
    Get the singleton inventory parameters instance.

    Returns:
        InventoryParams: The global parameters instance

    Example:
        >>> params = get_params()
        >>> params.L
        21
        >>> params.z
        1.65
    """
    global _PARAMS_INSTANCE
    if _PARAMS_INSTANCE is None:
        _PARAMS_INSTANCE = InventoryParams()
    return _PARAMS_INSTANCE


def reset_params() -> None:
    """
    Reset the singleton instance (for testing purposes).
    """
    global _PARAMS_INSTANCE
    _PARAMS_INSTANCE = None


if __name__ == "__main__":
    # Quick verification
    params = get_params()
    print("Inventory Parameters (from Master_Inventory_Rules_v9.md)")
    print("=" * 60)
    print(f"  L (Lead time):         {params.L} days")
    print(f"  R (Review period):     {params.R} days")
    print(f"  B (Buffer factor):     {params.B} days")
    print(f"  z (Service level):     {params.z} (95%)")
    print(f"  TV (Mix variability):  {params.TV}")
    print(f"  sigma_factor:          {params.sigma_factor}")
    print()
    print("Size Mix Guardrails:")
    print(f"  min_size_mix:          {params.min_size_mix} (3%)")
    print(f"  max_size_mix:          {params.max_size_mix} (40%)")
    print()
    print("ROIC Gate Thresholds:")
    print(f"  roic_full_approval:    {params.roic_full_approval} (20%)")
    print(f"  roic_flag_threshold:   {params.roic_flag_threshold} (10%)")
    print()
    print("New SKU Age Factors:")
    print(f"  <30 days:              {params.new_sku_30d_factor}")
    print(f"  30-60 days:            {params.new_sku_60d_factor}")
    print(f"  60-90 days:            {params.new_sku_90d_factor}")

    # Verify singleton
    params2 = get_params()
    print()
    print(f"Singleton check: {params is params2}")
