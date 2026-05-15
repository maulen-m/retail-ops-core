# Master Inventory Rules v9 - Autonomous_business Consumer Pointer

**Status:** active consumer pointer for Autonomous_business.
**Scope:** Kaspi-only operations in this repo.
**Canonical source:** `~/Cowork/Projects/Sourcing-Research/docs/inventory/Master_Inventory_Rules_v9.md`
**PO algorithm source:** `docs/protocol/active/PO_making_logic_v3.md`

Autonomous_business consumes the v9 inventory authority from the E-commerce
source-owner repo. This local file exists so repo-local agents, validators, and
scripts have a stable active path without reintroducing v8 as the default.

Rules:

- Do not treat `docs/inventory/Master_Inventory_Rules_v8.md` as current formula authority.
- Do not duplicate universal inventory formulas here.
- Keep this repo Kaspi-only; future-channel language remains in the E-commerce source doc.
- If formulas or parameters change, update the E-commerce source doc first, then update
  any local consumer parser or compatibility anchor below.

## Compatibility Anchors

Some Autonomous_business scripts read a small parameter marker from this file.
The value below preserves the existing capital-protection behavior while pointing
the authoritative rule owner to the E-commerce v9 document.

| Parameter | Value | Notes |
|---|---:|---|
| `Max_new_SKU_capital_pct` | 20% | Compatibility anchor for local PO proposal generation; authority remains the Sourcing-Research v9 source. |
| `Supplier_FX_precedence` | Routed FX first | For landed COGS in this repo: use `CNY_KZT = USDT_KZT / USDT_CNY` from `dim_fx_rates` / derived FX surfaces when available. |
| `Supplier_FX_fallback_CNY_KZT` | 73 | Owner-approved fallback when routed supplier FX is unavailable. Legacy `75/78` may appear in archived estimates only when explicitly labeled legacy fallback. |
