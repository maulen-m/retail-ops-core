# Owner QA Inputs - Option C Operational Stock Truth

Captured at: `2026-05-03 20:38:49 +05`

Repo: `~/Docs/Autonomous_business`

Purpose: preserve owner-provided operational truth for the C2/C3 path toward a fully autonomous, decision-grade stock, sales, ads, PO, inbound, and cashflow system.

Secret handling: secrets are referenced by environment variable name only. Do not copy credentials, tokens, passwords, cookies, or session material into this document, tests, reports, commits, or evidence packs.

## 1. Access And Credential Truth

- Kaspi API tokens, merchant-account web UI credentials, and Kaspi internal marketing credentials are provided in `~/Docs/Autonomous_business/.env`.
- Additional required credentials may be looked up cautiously in the neighboring repo env file at `~/Docs/Web_automation/.env`.
- Relevant Kaspi marketing env names include `Kaspi_marketing_login_UNIVERSAL`, `Kaspi_marketing_Password_UNIVERSAL`, ACMEWEAR, and STOREB equivalents.
- STOREB marketing access currently uses the Universal marketing account because the Universal account can act as owner/admin for all stores through the upper-right store switcher in the marketing web UI.

## 2. Store Scope

- All Kaspi stores in scope: `ACMEWEAR`, `Universal`, `STOREB`, `11KZ`, `MELVIS`.
- Currently active stores with positive stock on sale: `ACMEWEAR`, `Universal`, `STOREB`.
- Currently inactive stores: `11KZ`, `MELVIS`.
- Active Kaspi internal ads stores: `ACMEWEAR`, `STOREB`.
- STOREB currently runs Kaspi internal ads on generic `LINE52` product offers with approximately `5,000 KZT/day` total ads cost; actual profit and effectiveness must be reevaluated from source data.
- ACMEWEAR is the owned Kazakhstan trademark/brand store for ACMEWEAR clothing products.
- STOREB and Universal mostly sell generic Kaspi sports-clothing offerings.

## 3. Order Status And Stock Truth

- Pending orders do not reduce stock.
- Dispatched or shipped orders reduce stock.
- Delivered orders remain sold.
- Cancelled orders do not reduce stock unless already shipped and then explicitly reversed.
- Returned orders increase active stock only after QC acceptance.

## 4. Stock Authority

- Current best external expert stock anchor: `~/Docs/Oracle/Autonomous_business/2026-04-24/103302_TASK-000_line51-root-cause-external-second-pass-2026-04-24/expert_answer/24.4.2026/second_pass_stock_value_evaluation_2026-04-24.xlsx`.
- This anchor still does not include the required 20% proportional LINE51 stock reduction.
- Required adjustment: apply the 20% proportional LINE51 stock reduction before rebuilding the current stock position from subsequent events, unless a later approved workflow places the adjustment into a better effective-dated ledger layer.
- All negative active stock values, including Line61 `4XL`, must normalize to zero and raise an exception. Negative values are not trusted as active sellable stock because a large batch of collected returns/cancels remains unrecovered, unrecounted, and employee-unprocessed.
- Collected but not processed returns/cancels are in quarantine mode, not active stock.
- The prior mismatch between two `sku_key` values for the same white T-shirt must be resolved into one merged canonical `sku_key` because the item is identical.

## 5. Financial Truth

- Main formula authority remains `docs/inventory/Master_Inventory_Rules_v9.md`.
- Event-based COGS should come from inbound workbook data or already ingested storage covering purchase orders, received stock, cargo delivery payments, and FX rates.
- Base CNY cost and supplier FX should be reconstructed from repo/worktree logic around Binance P2P KZT to USDT, exchanger transfer to WeChat CNY, and related Gmail exchanger-mail watcher evidence.
- If required cashflow backfill artifacts are missing, cautiously use `~/Docs/wt_cashflow_mt940` only as an initial-population side worktree/source.
- Latest manual bank-account balance ingest: `~/Docs/Autonomous_business/config/bank_accounts_manual_ingest_3.5.2026.yaml`.
- Manual bank-account totals still need to be computed and ingested into DB.
- Unknown COGS blocks profit publication.
- Return/refund cash movement happens from the respective store Kaspi Pay account when the returned order product is received back from courier/intermediary delivery company Zampler.

## 6. Purchase Order, Inbound, Cargo, And Supplier Truth

- Canonical inbound workbook: `~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/Inbound_calendar_V10.002.xlsx`.
- Long-term target: automate this and remove the fragile Excel workbook from the critical pipeline.
- Actual received quantities are entered in the inbound workbook when real Astana warehouse arrival data is confirmed.
- Cargo delivery payments are usually made on the Astana warehouse receipt/takeover date when freight is moved from the Astana cargo company warehouse to the business warehouse/office.
- Sometimes freight takeover and payment can be delayed; the system must preserve separate freight-arrival, payment, and warehouse-takeover dates.
- Supplier payment flow: supplier prepares goods, then payment is made through Binance USDT purchase and exchanger transfer to WeChat CNY. In some cases payment is advanced; in other cases supplier relationship allows delayed payment after receipt and even after sales begin.
- Supplier payment/check images live at `~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/Transactions`.
- Ongoing SHR supplier debt requires recheck; owner-stated current expected total is approximately `122,000 CNY`.
- Already paid SHR amount currently stated by owner: `65,000 CNY`, with evidence under `~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/Transactions/PO_5.1_24.03.2026`.
- ARC supplier transaction evidence is under `~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/Transactions/ARC`.
- Employee approves received quantities after cargo is paid and freight is moved into the business warehouse/office.

## 7. Ads Truth

- Missing required ads data blocks profit computation.
- Current active Kaspi internal ads stores requiring ads coverage: `ACMEWEAR`, `STOREB`.
- STOREB marketing access can use the Universal marketing account and store switcher because Universal has admin access to all stores.
- External ads workflow and data live at `~/Docs/Business_3/Facebook_ads`.
- External ads include Instagram/Meta campaigns that may drive traffic either to Kaspi funnel sales or to a separate local Instagram sales funnel.

## 8. Cashflow Truth

- Bank/cash account list and opening balances are currently manually ingested.
- Owner must ingest balances at least weekly.
- Latest manual ingest path: `~/Docs/Autonomous_business/config/bank_accounts_manual_ingest_3.5.2026.yaml`.
- Kaspi Pay payout timing: after the end customer receives the order, payout is normally received in the respective store Kaspi Pay bank account within about one minute.
- Cargo payment timing is tied to Astana cargo arrival/takeover; delayed takeover/payment must be explicitly dated.
- Current active stock on hand may not be fully paid because SHR supplier obligations remain open.
- Minimum owner cash reserve rule: `1,500,000 KZT` cash on hand at any time.

## 9. Open Policy Decisions Captured For C2

- Decision thresholds must be encoded as policy, not chat memory.
- Manual review ownership must be explicit by exception type.
- Recommended C2/C3 path: first add maintainable policy doc plus machine-readable config and tests; later promote the same policy into an effective-dated DB registry and daily exception workflow.
