Phase: Design
Focus: Translate Kaspi’s “price list” (Excel/XML) Q&A into an agent-ready technical spec + integration notes for automated stock/price/preorder sync

# Kaspi Shop — Price / Stock / Preorder Sync via Price List (Excel/XML)
Doc: Kaspi_price_stock_sync_QA_EN.md  
Source: Kaspi official seller-cabinet Q&A (provided by Adil)  
Date: 2026-01-28  
Audience: Repo agents implementing automation (Codex / Claude)

## 0) What this is (and what it is not)

Kaspi Shop supports **updating product availability (stock), price, and pre-order lead time** using a **Price List** (“Прайс-лист”) that is uploaded in the **seller cabinet web UI**.

Kaspi provides two formats:
- **Excel**: manual upload (simpler, limited)
- **XML**: manual upload **or** **automatic hourly fetch** from a URL (best for automation)

This mechanism is **file-based sync** (not the Orders API). For our repo, treat it as an **export feed** we generate from DB, then host.

---

## 1) Core capabilities

### 1.1 Set product to pre-order (when out of stock)
If a product is out of stock, you can still list it as **available** with a **preOrder** lead time (in days) so buyers can place a pre-order.

- Pre-order lead time must be **≤ 30 calendar days**.
- **Do not edit the product card manually** to enable pre-order; do it via the price list, otherwise buyers may not be able to place pre-orders.

### 1.2 Update stock per warehouse / pickup point
You can publish stock by warehouse (“PP1–PP5” in Excel, or `storeId` in XML).
- Buyers cannot order more than published stock.
- You can publish:
  - numeric quantities (recommended)
  - or `yes/no` in Excel for basic availability

### 1.3 Update prices
- If the price is the same everywhere: publish a single `<price>`.
- If prices differ by city: publish `<cityprices><cityprice cityId=...>...</cityprice></cityprices>`.

**Format constraints**
- Prices are **KZT**.
- No decimals, spaces, or extra symbols in city price values (integers only).

---

## 2) Excel price list (manual only)

### 2.1 How to upload
Seller cabinet (web) → **Products / Price List** → download template or export catalog → fill → upload.

After upload, the catalog is updated in **~15 minutes**.

### 2.2 Required columns
The file must contain (and keep) these columns:
- `SKU` — your internal merchant SKU
- `model` — product name / variant
- `brand` — brand/manufacturer; if no brand required, use “No brand” equivalent per Kaspi guidance
- `price` — price in KZT
- `PP1`, `PP2`, `PP3`, `PP4`, `PP5` — warehouse identifiers (must exist even if unused; leave extra blank)
- `preorder` — number of days (≤ 30) to add as lead time for pickup/delivery; blank if not pre-order

### 2.3 Excel formatting rules (strict)
To avoid upload errors:
- Do not change number of sheets
- Put products on the first sheet
- Do not delete/create columns, do not rename headers
- Do not use Tab indentation
- Do not insert line breaks inside cells

### 2.4 Excel limitations (when Excel becomes unavailable)
Excel export/edit is not available if:
- You have different prices / different preorder by city
- You have more than 5 warehouses
- Warehouse names differ from PP1–PP5
→ Use XML.

---

## 3) XML price list (manual upload OR automatic)

### 3.1 Manual XML upload
Seller cabinet (web) → Products → Upload Price List → Upload manually.

### 3.2 Automatic XML upload (recommended for automation)
1) Host your XML on an **http/https** server (static file is enough).  
2) Seller cabinet (web) → Products → Upload Price List → **Automatic upload** → paste the URL.  
3) Kaspi fetches the file **every 60 minutes** *if the file changed*.

**Important operational behavior**
- Products present in your catalog but missing from your file may be removed from sale / moved into “unrecognized/unlinked” workflows depending on your cabinet state.
- If you previously added/uploaded products manually, you must keep them in the XML feed if you want them to remain active.

---

## 4) XML schema overview (what agents must generate)

### 4.1 Root structure
```xml
<?xml version="1.0" encoding="utf-8"?>
<kaspi_catalog
  date="string"
  xmlns="kaspiShopping"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="kaspiShopping http://kaspi.kz/kaspishopping.xsd">

  <company>CompanyName</company>
  <merchantid>CompanyID</merchantid>

  <offers>
    <offer sku="YOUR_SKU">
      <model>Product name</model>
      <brand>Brand</brand>

      <availabilities>
        <availability available="yes" storeId="PP1" preOrder="3" stockCount="234"/>
      </availabilities>

      <price>193000</price>
      <!-- OR <cityprices>...</cityprices> -->
    </offer>
  </offers>
</kaspi_catalog>

4.2 offer

offer@sku (required): merchant SKU

Must be unique within the file

Typically digits/latin; max length in the guidance: 20 chars

4.3 Availability / stock / pre-order

Inside <availabilities> you publish one or more:

<availability
  available="yes|no"
  storeId="WAREHOUSE_CODE"
  preOrder="N"          <!-- optional; omit if not pre-order -->
  stockCount="INTEGER"  <!-- stock level -->
/>


Rules:

preOrder must be ≤ 30 days

You can publish different preOrder for the same SKU only if selling from warehouses in different cities

If warehouses are in the same city, the preOrder must be the same for all warehouses in that city

4.4 Price formats

Single price for all cities

<price oldprice="optionalInteger">193000</price>


Different prices per city

<cityprices>
  <cityprice cityId="750000000" oldprice="optionalInteger">193000</cityprice>
  <cityprice cityId="710000000">195000</cityprice>
</cityprices>


cityId is a city code. Kaspi guidance: obtain city codes via Kaspi API “cities” lookup in Shop tools.

5) XML encoding requirements (common failure mode)

File must be UTF-8

Escape these characters in text nodes (e.g., product name):

" → &quot;

& → &amp;

> → &gt;

< → &lt;

' → &apos;

6) “Unlinked products” workflow (product goes to sale only after linking)

After uploading a price list, items may appear under “Unrecognized products → Unlinked”.
To list them:

Link to an existing Kaspi product card (fast; ~15 minutes)

Or create a new product card (review up to 3 business days)

Or upload a template ZIP with images + attributes (bulk creation)

Automation note: our feed generator must not assume a SKU is sellable unless it is already linked in Kaspi.

7) Integration plan for OUR repo (agents)
7.1 Architecture (separate from Orders API)

Implement as an export module. Do NOT mix with core/sync/order_sync_engine.py.

Recommended structure:

core/integrations/kaspi_pricelist/

pricelist_models.py (typed structures)

xml_renderer.py (deterministic XML generation)

validators.py (hard validation)

scripts/generate_kaspi_pricelist_xml.py

reads DB → builds offers → validates → writes XML

exports/kaspi_pricelist/{STORE_CODE}/kaspi_catalog.xml (or similar)

Hosting: S3/CloudFront / Nginx static / any HTTPS URL

7.2 Multi-store reality

Each Kaspi merchant account/store likely needs its own:

merchantid

set of warehouse storeIds

URL feed

So generate one XML per store:

UNIVERSAL

STOREB

ACMEWEAR
(and any others later)

7.3 Data mapping (minimum)

For each merchant SKU in a store:

sku → our merchant SKU (must match what Kaspi expects; do not invent)

model / brand → from our product master data

price → from our pricing engine output

stockCount per warehouse → from inventory snapshots (or calculated available-to-sell)

preOrder:

set only when stock is 0 but inbound is expected

cap to 30

7.4 Capital-protection guardrails (strongly recommended)

A broken feed can:

delist products

publish wrong prices

publish wrong stock → oversell

So implement safety gates:

Default dry-run: generate XML + diff report only

Require explicit enable flag to publish: ENABLE_KASPI_PRICELIST_PUBLISH=1

“Max delta” rules (block unless overridden):

price change > X% day-over-day

stock drop to 0 for top SKUs

“Allowlist first” rollout: start with 50 SKUs only

8) Test plan (agents must write tests first)
8.1 Unit tests (required)

XML renders valid UTF-8 and escapes special characters

Offer sku uniqueness enforced

preOrder validation: absent or integer in [1..30]

stockCount validation: integer ≥ 0

Price validation: integer ≥ 0; cityprice requires cityId

If both <price> and <cityprices> provided → fail

8.2 Golden-file tests (recommended)

Given a small fixture input (2 SKUs, 2 warehouses), compare output XML to a committed golden file.

8.3 Integration test (local)

Run generator against a small DB fixture (or seeded sqlite) and ensure:

deterministic output

no missing required fields

diff report is produced

9) Operational runbook (minimum)

Download current Kaspi catalog XML (from cabinet) and store as baseline.

Generate our XML in dry-run, compare:

SKU count

price diffs

stock diffs

Publish feed URL for one store (UNIVERSAL) and verify in cabinet after next hourly fetch.

Only then roll to STOREB, ACMEWEAR.

Appendix A — XML example (single price)
<offer sku="232130213">
  <model>iPhone 5s white 32gb</model>
  <brand>Apple</brand>
  <availabilities>
    <availability available="yes" storeId="PP1" preOrder="3" stockCount="234"/>
    <availability available="yes" storeId="PP2" preOrder="20" stockCount="234"/>
  </availabilities>
  <price>193000</price>
</offer>

Appendix B — XML example (city prices)
<offer sku="232130223">
  <model>iPhone 6s white 32gb</model>
  <brand>Apple</brand>
  <availabilities>
    <availability available="yes" storeId="PP1" preOrder="3" stockCount="234"/>
  </availabilities>
  <cityprices>
    <cityprice cityId="750000000">193000</cityprice>
    <cityprice cityId="710000000">195000</cityprice>
  </cityprices>
</offer>


Next Actions:
1. read ~/Docs/Autonomous_business/docs/api_docs/formatted/KASPI_PRICE_STOCK_SYNC_VIA_PRICELIST.md (or similar) and link it from `/docs/KASPI_API_INTEGRATION.md`.
2. Agent task framing: implement generator + validators + tests **first**, then add safe publishing workflow (dry-run → diff → enable flag).