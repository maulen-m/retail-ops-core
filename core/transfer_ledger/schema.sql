-- Transfer ledger schema
CREATE TABLE IF NOT EXISTS transfer_ledger (
    entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_date TEXT NOT NULL,
    amount REAL NOT NULL,
    currency TEXT NOT NULL,
    amount_kzt REAL NOT NULL,
    fx_rate_to_kzt REAL NOT NULL,
    fx_source TEXT NOT NULL DEFAULT 'MANUAL',
    reference_type TEXT NOT NULL,
    reference_id TEXT NOT NULL,
    from_account TEXT,
    to_account TEXT,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_transfer_ledger_date
    ON transfer_ledger(entry_date DESC);

CREATE INDEX IF NOT EXISTS idx_transfer_ledger_ref
    ON transfer_ledger(reference_type, reference_id);

-- Raw Binance C2C/P2P orders
CREATE TABLE IF NOT EXISTS binance_c2c_orders (
    order_number TEXT PRIMARY KEY,
    adv_no TEXT,
    trade_type TEXT NOT NULL,
    asset TEXT NOT NULL,
    fiat TEXT NOT NULL,
    fiat_amount REAL NOT NULL,
    crypto_amount REAL NOT NULL,
    unit_price REAL NOT NULL,
    order_status TEXT NOT NULL,
    create_time TEXT NOT NULL,
    commission TEXT,
    counterparty TEXT,
    advertisement_role TEXT,
    raw_json TEXT,
    source TEXT DEFAULT 'BINANCE_P2P',
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_binance_c2c_orders_time
    ON binance_c2c_orders(create_time DESC);

-- Binance withdrawals (e.g., USDT TRC20)
CREATE TABLE IF NOT EXISTS binance_withdrawals (
    withdraw_id TEXT PRIMARY KEY,
    tx_id TEXT,
    coin TEXT NOT NULL,
    network TEXT,
    amount REAL NOT NULL,
    transaction_fee REAL,
    address TEXT,
    address_tag TEXT,
    apply_time TEXT,
    success_time TEXT,
    status TEXT,
    wallet_type TEXT,
    counterparty_label TEXT,
    raw_json TEXT,
    source TEXT DEFAULT 'BINANCE_WITHDRAW',
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_binance_withdrawals_time
    ON binance_withdrawals(apply_time DESC);

-- Allocation of funding entries to internal PO IDs (many-to-many)
CREATE TABLE IF NOT EXISTS po_funding_allocations (
    allocation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    po_id TEXT NOT NULL,
    entry_id INTEGER NOT NULL,
    amount REAL NOT NULL,
    currency TEXT NOT NULL,
    amount_kzt REAL NOT NULL,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_po_funding_po ON po_funding_allocations(po_id);
CREATE INDEX IF NOT EXISTS idx_po_funding_entry ON po_funding_allocations(entry_id);
