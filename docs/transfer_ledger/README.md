# Transfer Ledger

Scope: Track cash transfers and PO-related payments in a single, auditable ledger.

Principles:
- Ledger entries are immutable; corrections are new entries.
- FX rates must be explicit per entry (no hidden defaults).
- Service layer is the only place for business rules.

See CONTRACTS.md for data invariants.

## Binance P2P import
Use `scripts/import_binance_p2p.py` to pull C2C/P2P history into DB and ledger.
The importer writes raw orders to `binance_c2c_orders` and posts ledger entries
for both the crypto leg and the fiat leg.

## Binance withdrawals
Use `scripts/import_binance_withdrawals.py` to pull withdrawal history (e.g., USDT TRC20).
Withdrawals are stored in `binance_withdrawals` and recorded as ledger outflows.

## Binance withdrawal emails (Gmail)
Use `scripts/import_binance_withdrawal_emails.py` to parse Binance withdrawal emails and
backfill missing address/tx_id fields in `binance_withdrawals`.

## Exchanger emails (Gmail)
Use `scripts/import_exchanger_emails.py` to parse exchanger order emails from Gmail
and store them in `exchanger_orders`. Matching withdrawals are auto-labeled when
the deposit address and amount/date align.

Required env vars:
- `GMAIL_USER`
- `GMAIL_APP_PASSWORD`

Optional env vars:
- `GMAIL_MAILBOX` (label/mailbox)
- `GMAIL_QUERY` (Gmail search query)
- `GMAIL_MAILBOX_Binance` (label for Binance withdrawal emails)
- `GMAIL_QUERY_Binance` (query for Binance withdrawal emails)

## Gmail push (option 2, automated)
Configure Gmail API push so new emails trigger automatic sync:
1) `scripts/gmail_watch_setup.py` — registers Gmail watch + stores historyId
2) `scripts/gmail_pubsub_listener.py` — pulls Pub/Sub + runs sync
3) `scripts/gmail_sync_history.py` — reads Gmail history and updates DB

Required env vars:
- `GMAIL_PUSH_PROJECT_ID`
- `GMAIL_PUSH_TOPIC`
- `GMAIL_PUSH_SUBSCRIPTION`
- `GMAIL_OAUTH_CLIENT_JSON` (path to OAuth client JSON)
- `GMAIL_TOKEN_PATH` (token cache; defaults to ~/.config/autonomous_business/gmail_token.json)
- `GMAIL_PUSH_LABELS` (comma-separated; e.g. `Exchangers,Binance`)

Dependencies:
- `google-api-python-client`
- `google-auth-httplib2`
- `google-auth-oauthlib`
- `google-cloud-pubsub`

## Auto FX derivation (USDT/KZT + USDT/CNY)
Use `scripts/derive_fx_rates.py` to compute daily FX from:
- Binance P2P BUY orders (USDT/KZT)
- Exchanger emails (USDT/CNY) — derived as `amount_cny / amount_usdt`

This script upserts `dim_fx_rates` with `usdt_kzt`, `usdt_cny`, and derived `cny_kzt`.
USD/KZT and delivery rate are carried from the latest available row or fall back to defaults.

## Autopilot (zero-touch)
Use `scripts/transfer_ledger_autopilot.py` to run the full pipeline:
1) (Optional) PO plan import
2) Gmail import (exchanger orders)
3) Binance P2P BUY import
4) FX derivation and upsert
5) Binance withdrawals import + ledger entries
6) Binance withdrawal emails import
7) Binance deposits import
8) Binance transfers import
9) Funding balance + snapshots

Generate reports:
- `scripts/generate_transfer_ledger_reports.py --days 120 --current-usdt 2067.37796`

## PO funding plan (Excel)
Use `scripts/import_po_funding_plan.py --xlsx <path>` to import PO totals and message dates
from the Vibecode PO spreadsheet into `po_funding_plan` and `po_header`.
The autopilot will import this if `PO_PLAN_XLSX` or `PO_FUNDING_PLAN_XLSX` is set.

## PO inbound import (Excel)
Use `scripts/import_po_inbound_xlsx.py --xlsx <path> --po-id PO-4` to import line items
into `po_line` and update `po_header` totals for a PO inbound workbook.

## Legacy CNY buy reconciliation
Use `scripts/reconcile_legacy_cny_buy.py --xlsx <PO_storing_Vibecode_1.xlsx>` to map
legacy CNY buy rows to PO IDs and backfill missing exchanger orders (without overriding
existing fetched data).

## PO funding allocations (many-to-many)
Use `transfer_ledger_cli.py allocate-po` to map any ledger entry to an internal PO ID.
