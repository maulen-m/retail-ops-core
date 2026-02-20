#!/usr/bin/env python3
"""
Import Kaspi Pay MT940 statements into fact_cashflow_events.

Default: DRY RUN. Apply requires ENABLE_CASHFLOW_WRITE=1 and --apply.
Produces backfill report + reconciliation CSV.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import re
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_STATEMENTS = Path(
    "~/Documents/useful tables/Main crm spreadsheets/main tables/External_database/"
    "kaspi_pay/statements/kaspi_stores"
)
DEFAULT_ACCOUNTS = PROJECT_ROOT / "config" / "kaspi_pay_accounts.yaml"
DEFAULT_CODES = PROJECT_ROOT / "config" / "kaspi_mt940_codes.yaml"
EXPORT_DIR = PROJECT_ROOT / "exports"
BACKUP_DIR = PROJECT_ROOT / "backups"


@dataclass
class StatementBalances:
    opening: float
    closing: float
    opening_date: Optional[str]
    closing_date: Optional[str]


@dataclass
class StatementTxn:
    value_date: str
    dc_mark: str
    amount_kzt: float
    code_86: Optional[str]
    description: str
    customer_ref: Optional[str]
    bank_ref: Optional[str]


def _backup_file(path: Path) -> None:
    if not path.exists():
        return
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"{path.stem}.{stamp}{path.suffix}"
    shutil.copy2(path, dest)


def _safe_write_text(path: Path, text: str) -> None:
    _backup_file(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _safe_write_csv(path: Path, headers: list[str], rows: list[list[object]]) -> None:
    _backup_file(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(headers)
        writer.writerows(rows)
    tmp.replace(path)


def _parse_yy_mm_dd(token: str) -> Optional[str]:
    if not token or len(token) != 6:
        return None
    try:
        year = int(token[0:2])
        month = int(token[2:4])
        day = int(token[4:6])
        year += 2000 if year < 70 else 1900
        return date(year, month, day).isoformat()
    except Exception:
        return None


def _parse_amount(token: str) -> float:
    return float(token.replace(".", "").replace(",", "."))


def _parse_balance_line(line: str) -> Optional[tuple[float, Optional[str]]]:
    match = re.match(r":6[02]F:([DC])(\d{6})([A-Z]{3})([0-9,]+)", line)
    if not match:
        return None
    dc = match.group(1)
    date_token = match.group(2)
    amount = _parse_amount(match.group(4))
    signed = amount if dc == "C" else -amount
    return signed, _parse_yy_mm_dd(date_token)


def _parse_61_line(line: str) -> Optional[StatementTxn]:
    match = re.match(r":61:(\d{6})(\d{4})?([DC])([A-Z])?([0-9,]+)(.*)", line)
    if not match:
        return None
    value_date = _parse_yy_mm_dd(match.group(1))
    if not value_date:
        return None
    dc_mark = match.group(3)
    amount = _parse_amount(match.group(5))
    amount = amount if dc_mark == "C" else -amount
    rest = match.group(6) or ""
    customer_ref = None
    bank_ref = None
    if "//" in rest:
        left, right = rest.split("//", 1)
        bank_ref = right.strip() or None
        digits = re.findall(r"\d+", left)
        customer_ref = digits[-1] if digits else None
    else:
        digits = re.findall(r"\d+", rest)
        customer_ref = digits[-1] if digits else None
    return StatementTxn(
        value_date=value_date,
        dc_mark=dc_mark,
        amount_kzt=amount,
        code_86=None,
        description="",
        customer_ref=customer_ref,
        bank_ref=bank_ref,
    )


def _clean_86_text(text: str) -> str:
    cleaned = re.sub(r"\?\d{2}", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _parse_86_line(line: str) -> tuple[Optional[str], str]:
    payload = line[4:] if line.startswith(":86:") else line
    payload = payload.strip()
    code = None
    match = re.match(r"(\d{3})", payload)
    if match:
        code = match.group(1)
    return code, _clean_86_text(payload)


def _extract_account_id(line: str) -> Optional[str]:
    raw = line.split(":", 1)[-1].strip()
    if "/" in raw:
        return raw.split("/")[-1].strip()
    return raw or None


def _looks_like_mt940(text: str) -> bool:
    return ":61:" in text and ":86:" in text and ":25:" in text


def parse_mt940_file(path: Path) -> tuple[str | None, StatementBalances | None, list[StatementTxn]]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    if not _looks_like_mt940(text):
        return None, None, []
    lines = [line.rstrip("\n") for line in text.splitlines()]

    account_id = None
    opening = None
    opening_date = None
    closing = None
    closing_date = None
    txns: list[StatementTxn] = []

    current_txn: StatementTxn | None = None
    desc_parts: list[str] = []
    in_86 = False

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith(":25:"):
            account_id = _extract_account_id(line)
            in_86 = False
            continue
        if line.startswith(":60F:"):
            parsed = _parse_balance_line(line)
            if parsed:
                opening, opening_date = parsed
            in_86 = False
            continue
        if line.startswith(":62F:"):
            parsed = _parse_balance_line(line)
            if parsed:
                closing, closing_date = parsed
            in_86 = False
            continue
        if line.startswith(":61:"):
            if current_txn:
                current_txn.description = " ".join(desc_parts).strip()
                txns.append(current_txn)
            current_txn = _parse_61_line(line)
            desc_parts = []
            in_86 = False
            continue
        if line.startswith(":86:"):
            if current_txn is None:
                continue
            code, desc = _parse_86_line(line)
            if code and not current_txn.code_86:
                current_txn.code_86 = code
            if desc:
                desc_parts.append(desc)
            in_86 = True
            continue
        if line.startswith(":"):
            in_86 = False
            continue
        if in_86 and current_txn:
            desc = _clean_86_text(line)
            if desc:
                desc_parts.append(desc)

    if current_txn:
        current_txn.description = " ".join(desc_parts).strip()
        txns.append(current_txn)

    balances = None
    if opening is not None and closing is not None:
        balances = StatementBalances(
            opening=opening,
            closing=closing,
            opening_date=opening_date,
            closing_date=closing_date,
        )
    return account_id, balances, txns


def _event_hash(event: dict) -> str:
    parts = [
        str(event.get("event_date") or ""),
        str(event.get("event_type") or ""),
        str(event.get("account") or ""),
        f"{float(event.get('amount_kzt') or 0.0):.4f}",
        str(event.get("store_code") or ""),
        str(event.get("sku_key") or ""),
        str(event.get("sku_id") or ""),
        str(event.get("ref_type") or ""),
        str(event.get("ref_id") or ""),
        str(event.get("source") or ""),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def load_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _category_for_code(code: Optional[str], code_map: dict) -> str:
    if not code:
        return code_map.get("default_category", "UNKNOWN")
    return code_map.get("codes", {}).get(code, code_map.get("default_category", "UNKNOWN"))


def _event_type_for(category: str, dc_mark: str) -> str:
    if category == "PAYOUT_RECEIVED" and dc_mark == "D":
        return "REFUND"
    return category


def import_mt940(
    statements_dir: Path,
    accounts_config: Path,
    codes_config: Path,
    db_path: Path,
    apply: bool,
    run_id: str,
    label: str | None,
    tolerance: float,
) -> int:
    if not statements_dir.exists():
        raise FileNotFoundError(f"Statements dir not found: {statements_dir}")
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    accounts = load_yaml(accounts_config).get("stores", {})
    code_map = load_yaml(codes_config)

    files = [p for p in statements_dir.rglob("*.txt")]
    if not files:
        raise FileNotFoundError(f"No statement files found under {statements_dir}")

    events: list[dict] = []
    recon_rows: list[list[object]] = []
    report_counts: dict[tuple[str, str, str], int] = {}
    unknown_samples: dict[str, list[str]] = {}
    min_date = None
    max_date = None

    for file_path in files:
        account_id, balances, txns = parse_mt940_file(file_path)
        if not account_id:
            continue
        store_code = None
        for store, meta in accounts.items():
            if str(meta.get("account_id")).strip() == account_id:
                store_code = store
                break

        for txn in txns:
            category = _category_for_code(txn.code_86, code_map)
            event_type = _event_type_for(category, txn.dc_mark)
            ref_id = txn.bank_ref or txn.customer_ref or ""
            ref_id = f"{account_id}:{ref_id}" if ref_id else account_id
            notes = f"code_86={txn.code_86 or ''}; dc={txn.dc_mark}; acct={account_id}; desc={txn.description}"

            events.append(
                {
                    "event_date": txn.value_date,
                    "event_ts": None,
                    "event_type": event_type,
                    "account": "CASH",
                    "amount_kzt": round(txn.amount_kzt, 2),
                    "store_code": store_code,
                    "sku_key": None,
                    "sku_id": None,
                    "ref_type": "MT940",
                    "ref_id": ref_id,
                    "notes": notes,
                    "source": "STATEMENT_ACTUAL",
                    "run_id": run_id,
                }
            )

            key = (store_code or "UNKNOWN", txn.code_86 or "NONE", category)
            report_counts[key] = report_counts.get(key, 0) + 1
            if category == "UNKNOWN":
                samples = unknown_samples.setdefault(txn.code_86 or "NONE", [])
                if txn.description and len(samples) < 5 and txn.description not in samples:
                    samples.append(txn.description)

            if txn.value_date:
                d = date.fromisoformat(txn.value_date)
                min_date = d if min_date is None else min(min_date, d)
                max_date = d if max_date is None else max(max_date, d)

        if balances:
            if balances.opening_date:
                events.append(
                    {
                        "event_date": balances.opening_date,
                        "event_ts": None,
                        "event_type": "CASH_OPENING",
                        "account": "CASH",
                        "amount_kzt": round(balances.opening, 2),
                        "store_code": store_code,
                        "sku_key": None,
                        "sku_id": None,
                        "ref_type": "MT940_OPENING",
                        "ref_id": account_id,
                        "notes": f"opening_balance acct={account_id}",
                        "source": "STATEMENT_ACTUAL",
                        "run_id": run_id,
                    }
                )
            txn_sum = sum(t.amount_kzt for t in txns)
            recon_error = round((balances.opening + txn_sum) - balances.closing, 2)
            recon_rows.append(
                [
                    account_id,
                    store_code or "",
                    balances.opening_date or "",
                    balances.closing_date or "",
                    round(balances.opening, 2),
                    round(txn_sum, 2),
                    round(balances.closing, 2),
                    recon_error,
                ]
            )

    if not events:
        raise RuntimeError("No MT940 transactions parsed.")

    label = label or (max_date.isoformat() if max_date else datetime.now().strftime("%Y-%m-%d"))
    report_path = EXPORT_DIR / f"mt940_backfill_report_{label}.md"
    recon_path = EXPORT_DIR / f"mt940_cash_recon_{label}.csv"

    recon_headers = [
        "account_id",
        "store_code",
        "opening_date",
        "closing_date",
        "opening_balance",
        "txn_sum",
        "closing_balance",
        "recon_error",
    ]
    _safe_write_csv(recon_path, recon_headers, recon_rows)

    lines = [
        "# MT940 Backfill Report",
        "",
        f"Statements folder: {statements_dir}",
        f"Accounts config: {accounts_config}",
        f"Codes config: {codes_config}",
    ]
    if min_date and max_date:
        lines.append(f"Date range: {min_date.isoformat()} → {max_date.isoformat()}")
    lines.append("")
    lines.append("## Counts by account/code/category")
    lines.append("")
    lines.append("| store_code | code_86 | category | count |")
    lines.append("| --- | --- | --- | ---: |")
    for (store_code, code, category), count in sorted(report_counts.items()):
        lines.append(f"| {store_code} | {code} | {category} | {count} |")

    if unknown_samples:
        lines.append("")
        lines.append("## Unknown code samples")
        for code, samples in sorted(unknown_samples.items()):
            lines.append(f"- {code}:")
            for sample in samples:
                lines.append(f"  - {sample}")

    _safe_write_text(report_path, "\n".join(lines) + "\n")

    recon_failures = []
    for row in recon_rows:
        closing = float(row[6] or 0.0)
        recon_error = float(row[-1] or 0.0)
        allowed = abs(closing) * tolerance
        if abs(recon_error) > allowed:
            recon_failures.append(row)
    if recon_failures:
        print(f"FAIL: {len(recon_failures)} account recon errors exceed tolerance_pct {tolerance}")
        return 1

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        if conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='fact_cashflow_events'"
        ).fetchone() is None:
            raise RuntimeError("fact_cashflow_events missing; run migrate_018_cashflow_calendar.py")

        for event in events:
            event["event_hash"] = _event_hash(event)

        hashes = [e["event_hash"] for e in events]
        existing_hashes = set()
        if hashes:
            placeholders = ",".join("?" * len(hashes))
            existing_hashes = {
                row[0]
                for row in conn.execute(
                    f"SELECT event_hash FROM fact_cashflow_events WHERE event_hash IN ({placeholders})",
                    hashes,
                ).fetchall()
            }

        new_events = [e for e in events if e["event_hash"] not in existing_hashes]
        print(f"Parsed events: {len(events)}")
        print(f"New events: {len(new_events)} (existing skipped: {len(events) - len(new_events)})")
        print(f"Report: {report_path}")
        print(f"Recon: {recon_path}")

        if apply:
            if os.environ.get("ENABLE_CASHFLOW_WRITE") != "1":
                raise RuntimeError("ENABLE_CASHFLOW_WRITE=1 is required to apply cashflow writes.")
            for e in new_events:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO fact_cashflow_events (
                        event_date, event_ts, event_type, account, amount_kzt, store_code, sku_key, sku_id,
                        ref_type, ref_id, notes, source, run_id, event_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        e["event_date"],
                        e["event_ts"],
                        e["event_type"],
                        e["account"],
                        e["amount_kzt"],
                        e.get("store_code"),
                        e.get("sku_key"),
                        e.get("sku_id"),
                        e.get("ref_type"),
                        e.get("ref_id"),
                        e.get("notes"),
                        e.get("source"),
                        e.get("run_id"),
                        e.get("event_hash"),
                    ),
                )
            conn.commit()
            print("APPLY: inserted MT940 events.")
        else:
            print("DRY RUN: no DB writes.")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Import Kaspi Pay MT940 statements")
    parser.add_argument("--statements-dir", type=Path, default=DEFAULT_STATEMENTS)
    parser.add_argument("--accounts-config", type=Path, default=DEFAULT_ACCOUNTS)
    parser.add_argument("--codes-config", type=Path, default=DEFAULT_CODES)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--apply", action="store_true", help="Write to DB (requires ENABLE_CASHFLOW_WRITE=1)")
    parser.add_argument("--run-id", type=str, default=None)
    parser.add_argument("--report-label", type=str, default=None)
    parser.add_argument("--tolerance", type=float, default=0.05)
    args = parser.parse_args()

    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    return import_mt940(
        statements_dir=args.statements_dir,
        accounts_config=args.accounts_config,
        codes_config=args.codes_config,
        db_path=args.db,
        apply=args.apply,
        run_id=run_id,
        label=args.report_label,
        tolerance=args.tolerance,
    )


if __name__ == "__main__":
    raise SystemExit(main())
