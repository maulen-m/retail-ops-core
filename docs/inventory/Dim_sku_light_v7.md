# Dim_sku_light_v7 - Autonomous_business Consumer Pointer

**Status:** active fallback-planning pointer for Autonomous_business.
**Scope:** repo-local consumer guidance for stock/cost repair surfaces.
**Canonical source:** `~/Cowork/Projects/Sourcing-Research/docs/inventory/Dim_sku_light_v7.md`
**Must conform to:** `docs/inventory/Master_Inventory_Rules_v9.md` and `docs/protocol/active/PO_making_logic_v3.md`

This repo does not own the full `Dim_sku_light_v7` content. The source-owner
document lives in the Sourcing-Research repo and remains the planning-anchor
authority when stronger operational truth is unavailable.

Consumer rules in Autonomous_business:

- Treat `Dim_sku_light_v7` as a fallback planning anchor, not operational truth.
- Prefer DB truth, inbound truth, and owner-approved current workbooks before this file.
- For landed COGS in repo-local repair surfaces, supplier FX precedence is:
  - routed `CNY_KZT = USDT_KZT / USDT_CNY` from `dim_fx_rates` or derived FX surfaces
  - else owner-approved fallback `CNY_KZT = 73`
- Do not silently promote `75` or `78` as active landed-cost truth. If legacy
  estimates are consumed, preserve an explicit legacy-fallback label.
