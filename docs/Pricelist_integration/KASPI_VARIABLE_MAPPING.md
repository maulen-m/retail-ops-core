# Kaspi Variable Mapping (UI/API ↔ XML Pricelist ↔ DB ↔ CRM Workbook)

Sources:
- XML examples: `docs/Pricelist_integration/Manual_Pricelist_example_*.xml`
- CRM workbook: `excel_ui/SALES_KSP_CRM_V3.xlsx`

Note: Example XML files may represent only active or only disabled items for a store, so treat them as **warehouse ID references**, not complete catalogs.

## Mapping Table

| Concept | Kaspi system (UI/API/exports) | XML pricelist | DB (table.column) | CRM workbook (sheet: column) | Notes |
|---|---|---|---|---|---|
| Merchant ID | Merchant UID in Kaspi cabinet | `<merchantid>` | `config/kaspi_stores.yaml: merchant_uid` | n/a | Child element in XML (not root attr). |
| Company | Store/company label | `<company>` | `config/kaspi_pricelist.yaml: company` | n/a | Example XML uses merchant id as company string. |
| Warehouse / pickup point | Kaspi warehouse (PP1/PP2) | `<availability storeId="...">` | `config/kaspi_accounts.yaml: warehouses[]` | `SALES_KSP_CRM_1: Склад передачи КД` | Example XML shows storeId values like `30000002_PP1`. |
| Kaspi article (seller SKU) | Артикул продавца / SKU_ID_KSP | `<offer sku="...">` | `fact_sales_raw.kaspi_article` | `SALES_KSP_CRM_1: SKU_ID_KSP` | Primary identifier in Kaspi pricelist. |
| Kaspi offer name | Название товара в Kaspi Магазине | n/a | `fact_sales_raw.kaspi_offer` / `fact_sales.kaspi_offer_name` | `SALES_KSP_CRM_1: KASPI_OFFER_NAME` | Full listing name; stable per offer. |
| Kaspi name core | Normalized core name | n/a | derived in pipeline | `SALES_KSP_CRM_1: Kaspi_name_core` / `Sku_Map_CRM_01: Kaspi_name_core` | Used for size/sku mapping fallback. |
| Internal SKU key | Internal product key | n/a | `dim_sku.sku_key` | `SALES_KSP_CRM_1: SKU_key` / `M02_SKU_CATALOG_NC: SKU_key` | Style-level identifier. |
| Internal SKU ID | Internal size SKU | n/a | `dim_sku_size.sku_id` | `SALES_KSP_CRM_1: SKU_ID` / `M02_SKU_CATALOG_NC: SKU_ID` | Size-level identifier. |
| Size | Size token (e.g., 3XL, 54) | n/a | `dim_sku_size.my_size` | `SALES_KSP_CRM_1: MY_SIZE` | Parsed from article/offer when missing. |
| Model | Product model | `<model>` | `dim_sku.model` | `M02_SKU_CATALOG_NC: Model` | XML model can be verbose (vendor text). |
| Brand | Brand name | `<brand>` | `dim_sku.brand` (if present) | `M02_SKU_CATALOG_NC: Brand` | XML examples often have empty brand. |
| Price (global) | Base offer price | `<price>` | `dim_sku.avg_sell_price_kzt_used` | `SALES_KSP_CRM_1: Sell_price_kzt` | XML supports `<price>` if same in all cities. |
| Price (city) | City price | `<cityprice cityId="...">` | n/a | n/a | Examples use city price (e.g., cityId 710000000). |
| Stock count | Stock per warehouse | `stockCount` attr | `fact_inventory_snapshot_size.current_stock` | `SALES_KSP_CRM_1: Quantity` | XML uses floats; we write ints. |
| Preorder days | Preorder lead time | `preOrder` attr | config + inbound logic | `SALES_KSP_CRM_1: PLANNED_SHIPPING_DATE` | Allowed when stock = 0 and inbound expected. |
| Availability flag | On sale flag | `available="yes|no"` | derived | `Sku_Map_CRM_01: On_sale` | XML availability should reflect sale status. |
| Order ID | Kaspi order ID | n/a | `fact_sales_raw.order_id` / `fact_orders_kaspi.order_id` | `SALES_KSP_CRM_1: OrderID` / `№ заказа` | Primary order identifier. |
| Order date | Kaspi order creation date | n/a | `fact_sales_raw.order_date` | `SALES_KSP_CRM_1: Date` / `Дата поступления заказа` | Stored as ISO date. |
| Order status | Kaspi status | n/a | `fact_sales_raw.order_status` / `fact_orders_kaspi.kaspi_status` | `SALES_KSP_CRM_1: Статус` | Used for lifecycle. |
| Delivery fee (seller) | Стоимость доставки для продавца | n/a | `fact_sales_raw.delivery_fee_seller` | `SALES_KSP_CRM_1: Стоимость доставки для продавца` | Used in net revenue. |
| Delivery fee (buyer) | Стоимость доставки для покупателя | n/a | `fact_sales_raw.delivery_fee_buyer` | `SALES_KSP_CRM_1: Стоимость доставки для покупателя` | Informational. |

## Warehouse IDs from XML examples

From `Manual_Pricelist_example_*.xml`:
- UNIVERSAL (30000001): `30000001_PP1`
- ACMEWEAR (30137883): `30137883_PP1`
- 11KZ (30290083): `30290083_PP1`
- MELVIS (30362323): `30362323_PP1`
- STOREB (30000002): `30000002_PP1`, `30000002_PP2`
