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
