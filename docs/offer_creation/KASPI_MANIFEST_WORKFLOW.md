# Kaspi Manifest Workflow

## Purpose
This is the canonical workflow for future Kaspi offer creation.
The agent should prefer a product/color `offer_manifest.yaml` over a long manual prompt.
The manifest/build scripts are helpers; the governing workflow is still a strict checklist tied to the live Kaspi template.

## Canonical Root
All live offer work now belongs under:

`~/Docs/Business2/Content/Content_db_1/Kaspi/Product_offers`

Old external ZIP-only root is deprecated for active workflow ownership.

## Main Command
```bash
python3 scripts/build_kaspi_offer_from_manifest.py \
  --manifest /absolute/path/to/offer_manifest.yaml \
  --apply
```

Optional workbook append:
```bash
python3 scripts/build_kaspi_offer_from_manifest.py \
  --manifest /absolute/path/to/offer_manifest.yaml \
  --apply \
  --apply-workbook
```

## Execution Contract
1. Read manifest.
2. Copy description into product root.
3. Copy category templates into `templates/`.
4. Copy + trace source images.
5. Rename selected images into `1..N`.
6. Split non-upload images into `images_part_2/`.
7. Build each category package:
   - fill XLSM rows
   - copy `images/<image_code>/1..5`
   - write `ROW_MAPPING.csv`
   - write `BUILD_LOG.md`
   - create ZIP
8. Run technical package validation:
   - `python3 scripts/validate_kaspi_offer_package.py --package-dir <DIR> --zip <ZIP>`
9. Run the XLSM gate in the right mode:
   - repeat color / same proven category:
     - `python3 scripts/validate_kaspi_offer_template.py --xlsm <FILE> --category <CATEGORY> --store <STORE> --mode fast`
   - new product / proven category:
     - `... --mode balanced`
   - new category / refreshed template / row-level rejection debugging:
     - `... --mode strict`
10. Generate workbook ingest payload JSON.
11. If requested, append workbook mapping rows.

## Template freshness rule
- Re-download templates from Kaspi merchant UI periodically.
- Category contracts can change, and stale templates may be rejected.
- For LINE31 on 2026-03-19, template freshness was not the suspected cause because the templates had been downloaded just a few hours earlier; the package layout was the primary mismatch.

## Why This Is Better
- No repeated explanation for every product/color.
- Future agents work from manifest + docs, not from chat memory.
- Product-specific identity rules live with the product itself.
- Dual-category workflows become repeatable.
- Workbook ingest becomes deterministic.

## Current Reference Implementation
- CLI: `~/Docs/Autonomous_business/scripts/build_kaspi_offer_from_manifest.py`
- Core module: `~/Docs/Autonomous_business/core/ops/kaspi_offer_manifest.py`
- Schema doc: `~/Docs/Autonomous_business/docs/offer_creation/OFFER_MANIFEST_SCHEMA.md`
- First live manifest: `~/Docs/Business2/Content/Content_db_1/Kaspi/Product_offers/LINE31/Starry_Black/offer_manifest.yaml`
