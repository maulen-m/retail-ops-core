import sqlite3
import subprocess

def _po_row(report_text: str, po_id: str) -> str:
    for line in report_text.splitlines():
        if line.startswith(f"|{po_id}"):
            return line
    raise AssertionError(f"Missing row for {po_id}")


def test_po_status_uses_exchanger_timeline_when_explicit_allocations_missing(tmp_path):
    db_path = tmp_path / "app.db"
    out_path = tmp_path / "PO_PAYMENT_STATUS.md"

    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS dim_fx_rates (
            effective_date TEXT PRIMARY KEY,
            usdt_kzt REAL,
            usdt_cny REAL
        );
        CREATE TABLE IF NOT EXISTS po_header (
            po_id TEXT PRIMARY KEY,
            message_date TEXT,
            total_cost_cny REAL
        );
        CREATE TABLE IF NOT EXISTS po_line (
            po_id TEXT,
            order_qty REAL,
            unit_cost_cny REAL
        );
        CREATE TABLE IF NOT EXISTS po_funding_plan (
            po_id TEXT PRIMARY KEY,
            message_date TEXT,
            total_cny REAL,
            total_usdt REAL,
            source TEXT
        );
        CREATE TABLE IF NOT EXISTS po_exchanger_allocations (
            allocation_id INTEGER PRIMARY KEY AUTOINCREMENT,
            po_id TEXT,
            exchanger_order_id TEXT,
            amount_usdt REAL,
            amount_cny REAL,
            source TEXT
        );
        CREATE TABLE IF NOT EXISTS exchanger_orders (
            exchanger_order_id TEXT PRIMARY KEY,
            exchanger TEXT,
            order_id TEXT,
            status TEXT,
            direction TEXT,
            amount_usdt REAL,
            amount_cny REAL,
            rate_usdt_cny REAL,
            deposit_address TEXT,
            receiver_account TEXT,
            message_id TEXT,
            message_date TEXT,
            subject TEXT,
            raw_json TEXT,
            source TEXT
        );
        """
    )
    conn.execute(
        """
        INSERT INTO dim_fx_rates (
            effective_date, usdt_kzt, usdt_cny
        ) VALUES (?, ?, ?)
        """,
        ("2026-01-01", 500.0, 6.5),
    )
    conn.execute(
        """
        INSERT INTO po_funding_plan (po_id, message_date, total_cny, total_usdt, source)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("PO-1", "2026-01-01T00:00:00+00:00", 1000.0, 153.85, "TEST"),
    )
    conn.execute(
        """
        INSERT INTO exchanger_orders (
            exchanger_order_id, exchanger, order_id, status, direction,
            amount_usdt, amount_cny, rate_usdt_cny, deposit_address,
            receiver_account, message_id, message_date, subject, raw_json, source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "ex-1",
            "BTCChange24",
            "111",
            "COMPLETED",
            "Tether TRC20 -> WeChat",
            150.0,
            1000.0,
            6.6666667,
            "TADDR",
            "wechat",
            "msg-1",
            "2026-01-02T12:00:00+00:00",
            "Success done",
            "{}",
            "GMAIL",
        ),
    )
    conn.commit()
    conn.close()

    result = subprocess.run(
        [
            "python3",
            "scripts/generate_po_payment_status.py",
            "--db",
            str(db_path),
            "--output",
            str(out_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    text = out_path.read_text(encoding="utf-8")
    row = _po_row(text, "PO-1")
    # Columns: PO, Message_Date, Total_CNY, Paid_CNY, Left_CNY, ...
    cells = [c.strip() for c in row.split("|")[1:-1]]
    assert cells[2] == "1000.00"
    assert cells[3] == "1000.00"
    assert cells[4] == "0.00"
