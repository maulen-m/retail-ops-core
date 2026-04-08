# Kaspi Offer Manifest Schema

## Purpose
This schema defines the manifest-driven workflow for Kaspi offer creation.
The manifest is the durable source of truth for one product + one color option.

Canonical live location:
- `~/Docs/Business2/Content/Content_db_1/Kaspi/Product_offers/<Product>/<Color>/offer_manifest.yaml`

## Goal
One manifest should be enough to:
1. copy and trace source images
2. build category XLSM files
3. build ready-to-upload ZIP packages
4. generate workbook ingest payload
5. optionally append mappings into `SALES_KSP_CRM_V3.xlsx`

## Top-Level Keys

### `schema_version`
Current value:
- `1`

### `product_root`
Absolute path to the canonical product/color root.

### `product`
Required keys:
- `store`
- `brand`
- `base_model`
- `color_slug`
- `color_label`
- `color_kaspi`
- `internal_base_sku_key`
- `kaspi_name_core`
- `display_title`
- `family_id`
- `description_path`
- `vendor_id`
- `product_type`
- `gender`
- `gender_rus`
- `season`
- `base_cost_cny`
- `base_cost_kzt`
- `weight_kg`
- `sell_price_kzt`
- `stock_entered_kzt`

### `images`
Required keys:
- `source_dir`
- `selection_mode`
- `folder_names`
- `upload_count`

Supported `selection_mode`:
- `folder_sequence_first_file`

Current workflow assumption:
- one chosen image per numbered source folder
- first `upload_count` images go into the upload ZIP
- the rest go into `sources/images_part_2`

### `sizes`
Required keys per row:
- `size_label`
- `numeric_size`

Example:
```yaml
sizes:
  - size_label: S
    numeric_size: 44
  - size_label: M
    numeric_size: 46
```

### `categories`
Required keys per category:
- `slug`
- `short_code`
- `template_path`
- `package_slug`
- `zip_slug`
- `group_token`
- `internal_article_pattern`
- `external_sku_pattern`
- `offer_name_pattern`
- `shared_fields`
- `row_fields`

#### Pattern placeholders
Allowed placeholders:
- `{brand}`
- `{base_model}`
- `{color_slug}`
- `{color_label}`
- `{color_kaspi}`
- `{description_text}`
- `{display_title}`
- `{family_id}`
- `{gender}`
- `{gender_rus}`
- `{internal_base_sku_key}`
- `{kaspi_name_core}`
- `{short_code}`
- `{size_label}`
- `{numeric_size}`
- `{internal_article}`
- `{external_sku}`
- `{shared_image_code}`
- `{first_size_label}`
- `{first_numeric_size}`

### `workbook`
Required keys:
- `workbook_path`
- `agent_session_title`

Optional keys:
- `candidate_color`

## Builder Outputs
The manifest builder creates:
- `sources/original_<N>/`
- `sources/renamed_1_<N>/`
- `sources/images_part_2/`
- `sources/IMAGE_MIGRATION_MAP.md`
- `sources/reports/*.json`
- `<category>/<package_slug>_<timestamp>/`
  - fixed XLSM
  - `images/<image_code>/1..5`
  - `ROW_MAPPING.csv`
  - `BUILD_LOG.md`
  - final ZIP

## Validation Policy
The manifest does not replace validation. Default workflow:
- always run `validate_kaspi_offer_package.py`
- run `validate_kaspi_offer_template.py --mode fast` for repeat color variants in a proven category
- escalate to `balanced` or `strict` only when the batch risk is higher

## Workbook Payload Outputs
The manifest workflow also generates:
- `M02_SKU_CATALOG_NC` rows
- `Sku_Map_CRM_01` rows
- `ingest_candidates` rows
- `SIZE_engine_basic` rows
- `SKU_Offer_Map_v2` blocks
- `AGENT_JOURNAL` rows

## Live Reference
First live manifest:
- `~/Docs/Business2/Content/Content_db_1/Kaspi/Product_offers/LINE31/Starry_Black/offer_manifest.yaml`
