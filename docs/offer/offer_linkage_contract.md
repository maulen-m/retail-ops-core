# Offer Linkage Contract

Purpose: block publish paths when offer mapping is unresolved, ambiguous, or not bidirectionally traceable.

## Strict rule set
- Any row in `fact_offer_stock_mapper_current` with `mapping_method='unresolved'` fails strict validation.
- Any row with `is_ambiguous=1` fails strict validation.
- Any resolved mapping must have a reverse reference in `dim_kaspi_article_map` (`offer token -> sku_key`).

## Gate command

```bash
python3 scripts/validate_offer_linkage.py --db db/app.db
```

Exit codes:
- `0`: contract satisfied.
- `1`: unresolved/ambiguous/bidirectional violations detected.

## Strict integration
`python3 scripts/validate_params.py --strict` runs the linkage validator.

- Default behavior: informational (does not block strict chain while legacy unresolved rows are being remediated).
- Fail-closed mode: set `AB_REQUIRE_OFFER_LINKAGE_STRICT=1` to convert any linkage violation into a strict gate failure.

## Operator response
1. Rebuild mapper (`scripts/build_offer_stock_mapper.py`) after source updates.
2. Fix article map gaps in controlled mapping pipeline.
3. Re-run `scripts/validate_offer_linkage.py` until `ok=true`.
4. Re-run strict chain before publishing.
