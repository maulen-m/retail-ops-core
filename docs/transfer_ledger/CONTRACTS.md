# Transfer Ledger Contracts

## Data invariants
- entry_date is ISO-8601 date (YYYY-MM-DD)
- amount and amount_kzt are signed; outflows use negative amounts
- fx_rate_to_kzt > 0
- currency is one of: KZT, CNY, USD, USDT
- reference_type is one of: PO, CARGO, TRANSFER, ADJUSTMENT, BINANCE_P2P, BINANCE_WITHDRAWAL, BINANCE_WITHDRAWAL_FEE

## API boundaries
- Only `core/transfer_ledger/repository.py` touches SQLite
- Only `core/transfer_ledger/service.py` enforces business rules
- CLI is a thin wrapper around service functions

## BINANCE_P2P entries
- Each trade is recorded as two entries (asset leg + fiat leg)
- BUY: +asset and -fiat
- SELL: -asset and +fiat

## BINANCE_WITHDRAWAL entries
- USDT withdrawals are recorded as outflows (negative USDT)
- Fee is recorded as a separate entry when available

## PO allocations
- Any ledger entry can be allocated to one or many PO IDs
- Allocation records live in `po_funding_allocations`
