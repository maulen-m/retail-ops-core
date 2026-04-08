# Canonical storage for Kaspi offer upload packages

Live offer workflow root:

`~/Docs/Business2/Content/Content_db_1/Kaspi/Product_offers`

## Required structure

```
Product_offers/
  <Product>/
    <Color>/
      offer_manifest.yaml
      sources/
      templates/
      <category>/
        <package_slug>_<timestamp>/
          <fixed XLSM>
          images/
          ROW_MAPPING.csv
          BUILD_LOG.md
          <ZIP>
```

### Example

```
~/Docs/Business2/Content/Content_db_1/Kaspi/Product_offers/LINE31/Starry_Black/
```

## Notes
- Keep timestamps in local time.
- If a package is regenerated, create a new timestamped folder.
- The previous external ZIP-only root is deprecated for active workflow ownership.
- Run pre-upload hard gate before upload:
  - `python3 scripts/validate_kaspi_offer_template.py --xlsm <FILE> --category <CATEGORY> --store <STORE>`
- Run pre-upload technical package gate before upload:
  - `python3 scripts/validate_kaspi_offer_package.py --package-dir <DIR> --zip <ZIP>`
- Prefer manifest-driven builds:
  - `python3 scripts/build_kaspi_offer_from_manifest.py --manifest <FILE> --apply`
- Inside each package, images must be nested as `images/<image_code>/1.png ...`, not flat under `images/`.
