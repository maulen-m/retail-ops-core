# Profit Realism Contract

Purpose: prevent publication of misleading profit metrics when COGS/offer prerequisites are unresolved.

## Hard rules
- If unresolved COGS rows exist in publication window, strict validation must fail.
- Profit fields in PO dashboard SKU rows must be locked (`profit_publishable=false`) and numeric profit/ROIC/margin fields must be `null` for unresolved rows.
- Business-insides profit metrics must be `N/A` when unresolved COGS rows are present.

## Validators

```bash
python3 scripts/validate_cogs_integrity.py
python3 scripts/validate_profit_publication_integrity.py
```

`validate_params --strict` executes both validators.

## Recovery sequence
1. Resolve missing COGS inputs (base cost + weight/fx/delivery factors) at source.
2. Rebuild truth views / PO dashboard payload.
3. Regenerate business-insides snapshot.
4. Re-run strict chain.

No publish operation is allowed while this contract is red.
