# KASPI Price/Stock Sync Plan (Pricelist XML)

Date: 2026-01-27

## Purpose

Implement a safe, file‑based Kaspi price/stock/preorder sync using the XML pricelist mechanism. The system must be deterministic, validated, and gated before publishing.

Primary spec: `docs/api_docs/formatted/KASPI_PRICE_STOCK_SYNC_VIA_PRICELIST.md`

## Scope

In‑repo generator + validators + tests first. Publishing is gated and optional. No coupling to Orders API. No Excel upload automation.

## Success criteria (verifiable)

- Unit tests cover validators, XML rendering, generator output, and publish gating.
- Dry‑run produces deterministic XML + diff report for a fixture DB.
- Publish requires explicit env flag + `--publish`.
- Output locations are stable: `exports/kaspi_pricelist/<STORE>/kaspi_catalog.xml` + `diff_report.md`.

## Phases

### Phase 1 — Models + Validators (tests first)

**Goal:** data structures + strict validation rules.

Deliverables
- `core/integrations/kaspi_pricelist/pricelist_models.py`
- `core/integrations/kaspi_pricelist/validators.py`
- Unit tests for validation rules

Validation tests (must pass before Phase 2)
- Offer requires `sku`, `model`, `brand`, and either `price` or `cityprices`.
- `preOrder` must be integer in 1..30 when present.
- `stockCount` must be integer ≥ 0.
- `price` and `cityprices` are mutually exclusive.
- SKU uniqueness enforced.

### Phase 2 — XML Renderer (tests first)

**Goal:** deterministic XML rendering that meets encoding/escaping rules.

Deliverables
- `core/integrations/kaspi_pricelist/xml_renderer.py`
- Golden file tests for deterministic output

Validation tests (must pass before Phase 3)
- XML is UTF‑8 and escapes special characters.
- Stable ordering (by SKU, then availability storeId).
- Output matches golden fixture for a small catalog.

### Phase 3 — Generator (tests first)

**Goal:** build catalog from DB + write XML + diff report.

Deliverables
- `scripts/generate_kaspi_pricelist_xml.py`
- `core/integrations/kaspi_pricelist/generator.py`

Validation tests (must pass before Phase 4)
- Fixture DB → deterministic XML output.
- Diff report includes counts of added/removed/changed offers.
- Generator fails closed on missing required fields.

### Phase 4 — Safe Publishing (tests first)

**Goal:** gated publishing workflow (dry‑run by default).

Deliverables
- Publish gating in generator CLI

Validation tests
- `--publish` fails unless `ENABLE_KASPI_PRICELIST_PUBLISH=1`.
- Dry‑run never writes publish target.

## Rollout plan (safe)

1) Generate dry‑run XML for UNIVERSAL only.
2) Compare against current catalog and review diff report.
3) Publish UNIVERSAL feed (hourly fetch in cabinet).
4) Roll to STOREB and ACMEWEAR after confirming results.

## Open decisions

- Final source for `brand` if missing (default vs required).
- Warehouse storeIds per store (config needed).

