# Workbook Catalog Map Sync And Governance Resume — 2026-03-08

## Objective
- Seed all new offer rows from CRM workbook sheet `M02_SKU_CATALOG_NC` into `dim_kaspi_article_map` for all configured stores.
- Ignore workbook store values for target insertion; all offers are future-store eligible.
- Resolve remaining unresolved COGS/publication blockers caused by missing offer mapping.
- Resume the previously blocked governance/economics/publication path after the mapping fix is proven.

## Constraints
- No new WebUI scrape.
- Fail closed.
- No DB writes without backup, env gate, `--apply`, and before/after artifacts.
- Do not hide rows or widen tolerances.

## Findings Locked Before Apply
- Workbook truth columns: `SKU_ID_KSP`, `SKU_key`, `Kaspi_name_core`.
- Importing workbook catalog rows for all stores is safe and materially improves truth coverage.
- `sales_fact_v2` rebuild must resolve `offer_id` via `dim_kaspi_article_map.kaspi_article`.
- Remaining unresolved rows after the first import pass were caused by:
  - generic header fallback (`sku_key=CL`)
  - deterministic article aliases (`K-O`, `TRM`, trailing variant suffixes like `_2`)

## Execution Plan
1. Write tests for workbook import, resolver behavior, daily pipeline contract, parser alias normalization, and generic-header override.
2. Patch importer, parser, rebuild resolver, and daily pipeline wiring.
3. Prove on temp DB:
   - workbook import apply
   - `sales_fact_v2` rebuild apply
   - `validate_cogs_integrity.py` => PASS
   - `validate_profit_publication_integrity.py` => PASS
4. Apply to real DB:
   - backup
   - workbook catalog sync apply
   - `sales_fact_v2` rebuild apply
   - capture before/after evidence
5. Reconcile remaining governance blocker:
   - `reconcile_on_delivery_settlement.py` dry run then apply
6. Resume blocked rollout:
   - `validate_params.py --strict --as-of 2026-03-07`
   - `system_doctor.py --strict --project-root . --as-of 2026-03-07`
   - only then rerun economics/publication/daily automation chain

## Success Criteria
- `validate_cogs_integrity.py --as-of 2026-03-07` PASS
- `validate_profit_publication_integrity.py --as-of 2026-03-07` PASS
- `validate_params.py --strict --as-of 2026-03-07` PASS
- `system_doctor.py --strict --project-root . --as-of 2026-03-07` PASS
- daily pipeline includes workbook catalog sync step before downstream truth/governance
