"""
Inventory Parameters — Single Source of Truth

All parameters match Master_Inventory_Rules_v6.md exactly.
This module is auto-synced from Master Rules. DO NOT edit values here directly.

Reference: Master_Inventory_Rules_v6.md
- §4.1: Global Defaults (L, R, B, z, TV, σ_factor, VAT_rate)
- §4.2: ROIC Gates & Capital Allocation
- §4.3: New Item Capital Limit
- §4.4: Size Mix Guardrails (CL only)
- §4.5: New SKU Risk Factors

Last synced: 2025-12-12 from v6.0
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ProductType(Enum):
    """Product type codes per Master Rules §1.1"""
    CL = "CL"    # Clothes — active on Kaspi + WB
    ELS = "ELS"  # Electronics — active on Kaspi only (higher risk)
    FUR = "FUR"  # Furniture — not selling yet


class Channel(Enum):
    """Sales channels per Master Rules §3"""
    KASPI = "Kaspi"
    WB = "WB"


# Singleton instance
_PARAMS_INSTANCE: Optional['InventoryParams'] = None


@dataclass(frozen=True)
class InventoryParams:
    """
    Immutable inventory parameters from Master_Inventory_Rules_v6.md.
    
    All values are Master-owned unless noted as channel-specific.
    Channel overrides (commission, delivery, payout) are NOT in this file —
    they live in channel-specific config or are passed at runtime.
    """

    # ==========================================================================
    # §4.1 Global Defaults (Master-Owned)
    # ==========================================================================
    
    L: int = 21              # Lead time: China → Astana (days)
    R: int = 10              # Review period (days)
    B: int = 14              # Buffer floor / safety days
    z: float = 1.65          # Z-score for 95% service level
    TV: float = 0.23         # Size-mix volatility floor (TV_mix_floor)
    sigma_factor: float = 0.4  # σ = D_30 × 0.4
    
    # VAT is Master-owned — channels inherit, never override
    VAT_rate: float = 0.03   # 3% current (4% from 2026-01-01)

    # ==========================================================================
    # §4.2 ROIC Gates & Capital Allocation
    # ==========================================================================
    
    # Approval thresholds
    ROIC_auto_approve: float = 0.20      # ≥20%: ORDER_FULL
    ROIC_flag_threshold: float = 0.10    # 10-20%: ORDER_WITH_FLAG; <10%: REVIEW_REQUIRED
    
    # Capital allocation smoothing (when constrained)
    # Gaussian-weighted redistribution on tail, capped at 15%
    capital_smoothing_max_pct: float = 0.15  # Max 15% redistribution to tail

    # ==========================================================================
    # §4.3 New Item Capital Limit
    # ==========================================================================
    
    # Applies to NEW SKU_keys only (not currently in catalog)
    # Existing SKUs have no individual cap — governed by ROIC ranking
    max_new_SKU_capital_pct: float = 0.20  # No new SKU > 20% of deployed capital

    # ==========================================================================
    # §4.4 Size Mix Guardrails (Product_Type: CL only)
    # ==========================================================================
    
    # These apply ONLY to Clothes (CL). ELS/FUR have no size variants.
    size_mix_floor: float = 0.03  # 3% minimum per size
    size_mix_cap: float = 0.40    # 40% maximum per size

    # ==========================================================================
    # §4.5 New SKU Risk Factors
    # ==========================================================================
    
    # Base factors by sales history (days)
    new_SKU_0d_factor: float = 0.50   # Never sold: 50% of calculated qty
    new_SKU_30d_factor: float = 0.75  # <30 days: 75%
    new_SKU_60d_factor: float = 0.85  # 30-60 days: 85%
    new_SKU_90d_factor: float = 0.95  # 60-90 days: 95%
    # ≥90 days: 1.00 (full quantity)
    
    # Product_Type risk multipliers (applied ON TOP of history factor)
    ELS_risk: float = 0.50  # Electronics: higher obsolescence/demand risk
    CL_risk: float = 1.00   # Clothes: no additional risk multiplier
    FUR_risk: float = 1.00  # Furniture: TBD (not active)


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
        >>> params.ROIC_auto_approve
        0.2
    """
    global _PARAMS_INSTANCE
    if _PARAMS_INSTANCE is None:
        _PARAMS_INSTANCE = InventoryParams()
    return _PARAMS_INSTANCE


def reset_params() -> None:
    """Reset the singleton instance (for testing purposes)."""
    global _PARAMS_INSTANCE
    _PARAMS_INSTANCE = None


def get_new_sku_factor(days_of_history: int) -> float:
    """
    Get the new SKU order reduction factor based on sales history.
    
    Args:
        days_of_history: Number of days this SKU has been selling
        
    Returns:
        Factor to multiply calculated order quantity by (0.50 to 1.00)
        
    Reference: Master Rules §4.5.1
    """
    params = get_params()
    
    if days_of_history == 0:
        return params.new_SKU_0d_factor
    elif days_of_history < 30:
        return params.new_SKU_30d_factor
    elif days_of_history < 60:
        return params.new_SKU_60d_factor
    elif days_of_history < 90:
        return params.new_SKU_90d_factor
    else:
        return 1.0


def get_product_type_risk(product_type: ProductType) -> float:
    """
    Get the risk multiplier for a product type.
    
    Args:
        product_type: CL, ELS, or FUR
        
    Returns:
        Risk multiplier (0.50 for ELS, 1.0 for others)
        
    Reference: Master Rules §4.5.2
    """
    params = get_params()
    
    if product_type == ProductType.ELS:
        return params.ELS_risk
    elif product_type == ProductType.CL:
        return params.CL_risk
    elif product_type == ProductType.FUR:
        return params.FUR_risk
    else:
        return 1.0


def get_effective_order_factor(
    days_of_history: int,
    product_type: ProductType
) -> float:
    """
    Get the combined order reduction factor for a SKU.
    
    Combines new SKU history factor with product type risk.
    
    Args:
        days_of_history: Number of days this SKU has been selling
        product_type: CL, ELS, or FUR
        
    Returns:
        Combined factor (e.g., 0.25 for new ELS item)
        
    Example:
        >>> get_effective_order_factor(0, ProductType.ELS)
        0.25  # 0.50 × 0.50
        >>> get_effective_order_factor(0, ProductType.CL)
        0.50  # 0.50 × 1.00
        >>> get_effective_order_factor(45, ProductType.CL)
        0.85  # 0.85 × 1.00
        
    Reference: Master Rules §4.5.3
    """
    history_factor = get_new_sku_factor(days_of_history)
    type_risk = get_product_type_risk(product_type)
    return history_factor * type_risk


def applies_size_mix_guardrails(product_type: ProductType) -> bool:
    """
    Check if size mix guardrails apply to this product type.
    
    Only CL (Clothes) has size variants. ELS/FUR do not.
    
    Reference: Master Rules §4.4
    """
    return product_type == ProductType.CL


if __name__ == "__main__":
    # Quick verification
    params = get_params()
    
    print("=" * 70)
    print("Inventory Parameters — synced from Master_Inventory_Rules_v6.md")
    print("=" * 70)
    
    print("\n§4.1 Global Defaults:")
    print(f"  L (Lead time):         {params.L} days")
    print(f"  R (Review period):     {params.R} days")
    print(f"  B (Buffer factor):     {params.B} days")
    print(f"  z (Service level):     {params.z} (95%)")
    print(f"  TV (Mix variability):  {params.TV}")
    print(f"  σ_factor:              {params.sigma_factor}")
    print(f"  VAT_rate:              {params.VAT_rate} (Master-owned)")
    
    print("\n§4.2 ROIC Gates:")
    print(f"  ROIC_auto_approve:     {params.ROIC_auto_approve} (≥20%: ORDER_FULL)")
    print(f"  ROIC_flag_threshold:   {params.ROIC_flag_threshold} (10-20%: FLAG)")
    print(f"  capital_smoothing:     {params.capital_smoothing_max_pct} (15% max)")
    
    print("\n§4.3 New Item Capital Limit:")
    print(f"  max_new_SKU_capital:   {params.max_new_SKU_capital_pct} (new items only)")
    
    print("\n§4.4 Size Mix Guardrails (CL only):")
    print(f"  size_mix_floor:        {params.size_mix_floor} (3%)")
    print(f"  size_mix_cap:          {params.size_mix_cap} (40%)")
    
    print("\n§4.5 New SKU Risk Factors:")
    print(f"  0 days (never sold):   {params.new_SKU_0d_factor}")
    print(f"  <30 days:              {params.new_SKU_30d_factor}")
    print(f"  30-60 days:            {params.new_SKU_60d_factor}")
    print(f"  60-90 days:            {params.new_SKU_90d_factor}")
    print(f"  ≥90 days:              1.00")
    
    print("\n  Product_Type Risk Multipliers:")
    print(f"    CL (Clothes):        {params.CL_risk}")
    print(f"    ELS (Electronics):   {params.ELS_risk}")
    print(f"    FUR (Furniture):     {params.FUR_risk}")
    
    print("\n§4.5.3 Combined Examples:")
    print(f"  New CL item (0d):      {get_effective_order_factor(0, ProductType.CL)}")
    print(f"  New ELS item (0d):     {get_effective_order_factor(0, ProductType.ELS)}")
    print(f"  CL with 45d history:   {get_effective_order_factor(45, ProductType.CL)}")
    print(f"  ELS with 45d history:  {get_effective_order_factor(45, ProductType.ELS)}")
    
    print("\n" + "=" * 70)
    print("Singleton check:", params is get_params())
