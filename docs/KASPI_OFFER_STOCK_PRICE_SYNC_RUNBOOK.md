# Kaspi Offer Stock+Price Sync Runbook

Date: 2026-02-18

## Goal

Run centralized offer stock/price control via pricelist XML for `UNIVERSAL` and `STOREB`, with:
- deterministic offer->size mapping
- fail-closed validation
- allowlist-gated pricelist generation/publish

## Commands

### 1) Build mapper table

```bash
python scripts/build_offer_stock_mapper.py \
  --store UNIVERSAL \
  --store STOREB \
  --window-days 90
```

Creates/refreshes `fact_offer_stock_mapper_current` in `db/app.db`.

### 2) Validate mapper quality

```bash
python scripts/validate_offer_stock_sync.py \
  --store UNIVERSAL \
  --store STOREB \
  --max-unresolved 0 \
  --min-confident-rate 0.95
```

### 3) Dry-run sync (generate XML only)

```bash
python scripts/run_offer_stock_price_sync.py \
  --store UNIVERSAL \
  --store STOREB \
  --mode dry-run \
  --min-confidence MEDIUM \
  --window-days 90
```

Outputs:
- XML per store: `exports/kaspi_pricelist/<STORE>/kaspi_catalog.xml`
- diff report: `exports/kaspi_pricelist/<STORE>/diff_report.md`
- effective allowlists: `exports/kaspi_pricelist/allowlists/*_mapper_allowlist.txt`

### 4) Publish sync (S3/CloudFront)

```bash
ENABLE_KASPI_PRICELIST_PUBLISH=1 \
python scripts/run_offer_stock_price_sync.py \
  --store UNIVERSAL \
  --store STOREB \
  --mode publish \
  --bucket <your-s3-bucket> \
  --prefix kaspi/pricelist \
  --min-confidence MEDIUM \
  --window-days 90
```

Optional hash/url verification per store:

```bash
--verify-url UNIVERSAL=https://<cdn>/UNIVERSAL/kaspi_catalog.xml \
--verify-url STOREB=https://<cdn>/STOREB/kaspi_catalog.xml
```

## Mapping precedence

1. `article_map_sku_id`
2. `article_map_article_size`
3. `article_map_sku_key_single`
4. `offer_size_stats`
5. `recent_sales_offer_mode` (windowed)
6. `size_probability_offer`
7. `size_probability_style`
8. `unresolved`

`run_offer_stock_price_sync.py` includes only non-ambiguous, non-unresolved rows in effective allowlists.

## Safety defaults

- publish is blocked unless `ENABLE_KASPI_PRICELIST_PUBLISH=1`
- default minimum mapping confidence: `MEDIUM`
- default validation gates:
  - `max_unresolved=0`
  - `min_confident_rate=0.95`

