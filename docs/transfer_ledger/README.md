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

## Auto FX derivation (USDT/KZT + USDT/CNY)
Use `scripts/derive_fx_rates.py` to compute daily FX from:
- Binance P2P BUY orders (USDT/KZT)
- Exchanger emails (USDT/CNY) — derived as `amount_cny / amount_usdt`

This script upserts `dim_fx_rates` with `usdt_kzt`, `usdt_cny`, and derived `cny_kzt`.
USD/KZT and delivery rate are carried from the latest available row or fall back to defaults.

## PO funding allocations (many-to-many)
Use `transfer_ledger_cli.py allocate-po` to map any ledger entry to an internal PO ID.
