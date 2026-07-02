"""Normalize owner OPEX/loan workbook inputs into Stage-A proposal artifacts."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from openpyxl import load_workbook


COMMITMENT_COLUMNS = [
    "commit_date",
    "commit_type",
    "amount_kzt",
    "scenario_tag",
    "ref_id",
    "notes",
]

VARIANT_DEFINITIONS: dict[str, dict[str, Any]] = {
    "V1_sheet100k": {
        "label": "Sheet value 100,000",
        "gold_store-d_mode": "sheet",
        "owner_action_required": True,
    },
    "V2_owner80k": {
        "label": "Owner loan figure 80,000",
        "gold_store-d_mode": "loan_owner",
        "owner_action_required": True,
    },
    "V3_excluded": {
        "label": "Excluded",
        "gold_store-d_mode": "excluded",
        "owner_action_required": True,
    },
}

ABSOLUTE_CASH_FLOOR_KZT = 500_000.0
BASE_FLOOR_MULT = 1.0
CONSERVATIVE_FLOOR_MULT = 1.5
DEFAULT_HORIZON_DAYS = 365
ASSUMED_INTERNET_DAY = 27


class OpexOwnerInputError(RuntimeError):
    """Raised when the owner workbook cannot be normalized safely."""


@dataclass(frozen=True)
class NormalizedOpexLine:
    row_number: int
    name: str
    action: str
    include_in_cashflow: str
    included: bool
    schedule: str
    day: int | None
    source_monthly_kzt: float | None
    owner_monthly_kzt: float | None
    monthly_amount_kzt: float
    amount_authority: str
    account: str
    expense_type: str
    months_left: int | None
    principal_left_kzt: float | None
    flags: tuple[str, ...]
    provenance: dict[str, Any]
    owner_action_required: bool = False


@dataclass(frozen=True)
class NormalizedLoan:
    row_number: int
    loan_name: str
    action: str
    source_status: str
    bank: str
    account: str
    opex_name: str
    payment_day: int | None
    next_due: str | None
    source_monthly_payment_kzt: float | None
    owner_monthly_payment_kzt: float | None
    monthly_payment_kzt: float
    principal_kzt: float | None
    balance_now_source_kzt: float | None
    months_total: int | None
    last_schedule_date: str | None
    include_in_cashflow: str
    included: bool
    flags: tuple[str, ...]
    provenance: dict[str, Any]
    owner_action_required: bool = False


def _json_default(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, tuple):
        return list(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, default=_json_default) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_provenance(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path.resolve()),
        "sha256": _sha256(path),
        "size_bytes": stat.st_size,
        "mtime_utc": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
    }


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _upper(value: Any) -> str:
    return _as_text(value).upper()


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return float(value)
    text = str(value).replace(",", "").replace(" ", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _as_int(value: Any) -> int | None:
    amount = _as_float(value)
    if amount is None:
        return None
    return int(amount)


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def _add_months(value: date, months: int) -> date:
    year = value.year + (value.month - 1 + months) // 12
    month = (value.month - 1 + months) % 12 + 1
    day = value.day
    while True:
        try:
            return date(year, month, day)
        except ValueError:
            day -= 1


def _safe_day_in_month(base: date, day_of_month: int) -> date:
    day = max(1, min(31, int(day_of_month)))
    while True:
        try:
            return date(base.year, base.month, day)
        except ValueError:
            day -= 1


def _date_range(start: date, end: date) -> Iterable[date]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def _month_starts(start: date, end: date) -> Iterable[date]:
    current = date(start.year, start.month, 1)
    while current <= end:
        yield current
        current = _add_months(current, 1)


def _row_dict(ws: Any, header_row: int, row_number: int) -> dict[str, Any]:
    headers = [ws.cell(header_row, col).value for col in range(1, ws.max_column + 1)]
    values = [ws.cell(row_number, col).value for col in range(1, ws.max_column + 1)]
    row: dict[str, Any] = {}
    for header, value in zip(headers, values):
        if header is None:
            continue
        key = str(header).strip()
        if key:
            row[key] = value
    return row


def _iter_table_rows(ws: Any, header_row: int) -> Iterable[tuple[int, dict[str, Any]]]:
    for row_number in range(header_row + 1, ws.max_row + 1):
        row = _row_dict(ws, header_row, row_number)
        if any(value is not None for value in row.values()):
            yield row_number, row


def _is_blank_owner_add_row(row: dict[str, Any], name_key: str) -> bool:
    return _upper(row.get("owner_action")) == "ADD" and not _as_text(row.get(name_key))


def _is_excluded(action: str, include_flag: str) -> bool:
    if action in {"STOP", "CLOSED", "CLOSE"}:
        return True
    if include_flag == "NO":
        return True
    if include_flag == "REVIEW":
        return True
    return False


def _amount_authority(owner_value: Any, source_value: Any) -> tuple[float, str]:
    owner = _as_float(owner_value)
    source = _as_float(source_value)
    if owner is not None:
        return owner, "owner_monthly_kzt"
    if source is not None:
        return source, "source_monthly_kzt"
    return 0.0, "missing"


def _common_amount_flags(owner_value: Any, source_value: Any) -> list[str]:
    owner = _as_float(owner_value)
    source = _as_float(source_value)
    if owner is not None and source is not None and abs(owner - source) > 0.01:
        return ["OWNER_SOURCE_DELTA"]
    return []


def _parse_opex_sheet(ws: Any) -> tuple[list[NormalizedOpexLine], dict[str, Any]]:
    lines: list[NormalizedOpexLine] = []
    skipped_blank_add_rows = 0
    for row_number, row in _iter_table_rows(ws, 6):
        if _is_blank_owner_add_row(row, "expense_name"):
            skipped_blank_add_rows += 1
            continue
        name = _as_text(row.get("expense_name"))
        if not name:
            continue
        action = _upper(row.get("owner_action")) or "KEEP"
        include_flag = _upper(row.get("include_in_cashflow")) or "YES"
        schedule = _as_text(row.get("schedule")).lower() or "monthly"
        flags = _common_amount_flags(row.get("owner_monthly_kzt"), row.get("source_monthly_kzt"))
        included = not _is_excluded(action, include_flag)
        if action in {"STOP", "CLOSED", "CLOSE"}:
            flags.append(f"EXCLUDED_BY_OWNER_ACTION_{action}")
            if include_flag != "NO":
                flags.append("OWNER_ACTION_OVERRIDES_INCLUDE_FLAG")
        elif include_flag == "NO":
            flags.append("EXCLUDED_BY_INCLUDE_NO")
        elif include_flag == "REVIEW":
            flags.append("REVIEW_INCLUDE_FLAG")

        day: int | None = None
        if schedule == "daily":
            flags.append("DAILY_MONTHLY_DIV_30")
        else:
            day = _as_int(row.get("payment_day_of_month"))
            if day is None and included:
                day = ASSUMED_INTERNET_DAY
                flags.append("ASSUMED_DAY_27")

        amount, authority = _amount_authority(row.get("owner_monthly_kzt"), row.get("source_monthly_kzt"))
        expense_type = _as_text(row.get("expense_type"))
        if expense_type.lower() == "lawn":
            flags.append("LOAN_CLASS_EMBEDDED_AS_OPEX")

        owner_action_required = include_flag == "REVIEW"
        lines.append(
            NormalizedOpexLine(
                row_number=row_number,
                name=name,
                action=action,
                include_in_cashflow=include_flag,
                included=included,
                schedule=schedule,
                day=day,
                source_monthly_kzt=_as_float(row.get("source_monthly_kzt")),
                owner_monthly_kzt=_as_float(row.get("owner_monthly_kzt")),
                monthly_amount_kzt=amount,
                amount_authority=authority,
                account=_as_text(row.get("account")),
                expense_type=expense_type,
                months_left=_as_int(row.get("months_left")),
                principal_left_kzt=_as_float(row.get("principal_left_kzt")),
                flags=tuple(dict.fromkeys(flags)),
                provenance={
                    "sheet": "OPEX_INPUT",
                    "row": row_number,
                    "source_ref": _as_text(row.get("source_ref")),
                    "owner_notes": _as_text(row.get("owner_notes")),
                    "review_priority": _as_text(row.get("review_priority")),
                },
                owner_action_required=owner_action_required,
            )
        )
    return lines, {"blank_add_rows_skipped": skipped_blank_add_rows}


def _parse_loans_sheet(ws: Any) -> tuple[list[NormalizedLoan], dict[str, Any]]:
    loans: list[NormalizedLoan] = []
    skipped_blank_add_rows = 0
    for row_number, row in _iter_table_rows(ws, 6):
        if _is_blank_owner_add_row(row, "loan_name"):
            skipped_blank_add_rows += 1
            continue
        loan_name = _as_text(row.get("loan_name"))
        if not loan_name:
            continue
        action = _upper(row.get("owner_action")) or "KEEP"
        include_flag = _upper(row.get("include_in_cashflow")) or "YES"
        flags = _common_amount_flags(
            row.get("owner_monthly_payment_kzt"),
            row.get("source_monthly_payment_kzt"),
        )
        included = not _is_excluded(action, include_flag)
        if action in {"STOP", "CLOSED", "CLOSE"}:
            flags.append(f"EXCLUDED_BY_OWNER_ACTION_{action}")
            if include_flag != "NO":
                flags.append("OWNER_ACTION_OVERRIDES_INCLUDE_FLAG")
        elif include_flag == "NO":
            flags.append("EXCLUDED_BY_INCLUDE_NO")
        elif include_flag == "REVIEW":
            flags.append("REVIEW_INCLUDE_FLAG")
        if _as_text(row.get("bank")).upper() == "BCC" and _as_text(row.get("account")).upper() == "UNIVERSAL":
            flags.append("BCC_ACCOUNT_UNIVERSAL_CONFIRM")

        amount, _authority = _amount_authority(
            row.get("owner_monthly_payment_kzt"),
            row.get("source_monthly_payment_kzt"),
        )
        owner_action_required = include_flag == "REVIEW" or "BCC_ACCOUNT_UNIVERSAL_CONFIRM" in flags
        loans.append(
            NormalizedLoan(
                row_number=row_number,
                loan_name=loan_name,
                action=action,
                source_status=_as_text(row.get("source_status")),
                bank=_as_text(row.get("bank")),
                account=_as_text(row.get("account")),
                opex_name=_as_text(row.get("opex_name")),
                payment_day=_as_int(row.get("source_payment_day")),
                next_due=(
                    next_due.isoformat()
                    if (next_due := _as_date(row.get("next_due_date_after_2026_07_02")))
                    else None
                ),
                source_monthly_payment_kzt=_as_float(row.get("source_monthly_payment_kzt")),
                owner_monthly_payment_kzt=_as_float(row.get("owner_monthly_payment_kzt")),
                monthly_payment_kzt=amount,
                principal_kzt=_as_float(row.get("principal_kzt")),
                balance_now_source_kzt=_as_float(row.get("balance_now_source_kzt")),
                months_total=_as_int(row.get("months_total")),
                last_schedule_date=(
                    last_date.isoformat() if (last_date := _as_date(row.get("last_schedule_date"))) else None
                ),
                include_in_cashflow=include_flag,
                included=included,
                flags=tuple(dict.fromkeys(flags)),
                provenance={
                    "sheet": "LOANS_INPUT",
                    "row": row_number,
                    "source_ref": _as_text(row.get("source_ref")),
                    "owner_notes": _as_text(row.get("owner_notes")),
                    "review_priority": _as_text(row.get("review_priority")),
                },
                owner_action_required=owner_action_required,
            )
        )
    return loans, {"blank_add_rows_skipped": skipped_blank_add_rows}


def _parse_kaspi_gold_uni_schedule(ws: Any, as_of: date) -> dict[str, Any]:
    if _as_text(ws.cell(2, 1).value) != "KaspiGOLD_Uni":
        return {"name": "KaspiGOLD_Uni", "rows": [], "warnings": ["KASPI_GOLD_UNI_BLOCK_MISSING"]}

    start_date = _as_date(ws.cell(2, 6).value)
    if start_date is None:
        raise OpexOwnerInputError("KaspiGOLD_Uni additions block is missing anchor date")
    rows = []
    first_unpaid_seen = False
    macbook_notes: list[str] = []
    for row_number in range(2, 37):
        amount = _as_float(ws.cell(row_number, 7).value)
        status = _upper(ws.cell(row_number, 8).value)
        note = _as_text(ws.cell(row_number, 9).value)
        if amount is None and not status and not note:
            continue
        scheduled_date = _add_months(start_date, row_number - 2)
        cashflow_date = scheduled_date
        if status == "UNPAID" and not first_unpaid_seen:
            first_unpaid_seen = True
            if scheduled_date == date(2026, 7, 20):
                cashflow_date = date(2026, 7, 21)
        if "macbook" in note.lower():
            macbook_notes.append(note)
        rows.append(
            {
                "sheet": "ADDITIONS",
                "row": row_number,
                "scheduled_date": scheduled_date.isoformat(),
                "cashflow_date": cashflow_date.isoformat(),
                "payment_day": 20,
                "amount_kzt": round(float(amount or 0.0), 2),
                "status": status,
                "notes": note,
            }
    )
    unpaid = [row for row in rows if row["status"] == "UNPAID" and row["cashflow_date"] >= as_of.isoformat()]

    return {
        "name": "KaspiGOLD_Uni",
        "opex_name": "GOLD_universal",
        "bank": "Kaspi_Gold",
        "account": "Universal",
        "anchor_date": start_date.isoformat(),
        "payment_day": 20,
        "first_unpaid_cashflow_date": unpaid[0]["cashflow_date"] if unpaid else None,
        "macbook_note_provenance": macbook_notes,
        "rows": rows,
    }


def _parse_bcc_5m_schedule(ws: Any, horizon_end: date) -> dict[str, Any]:
    block_row = 38
    name = _as_text(ws.cell(block_row, 1).value)
    if not name.startswith("BCC_5M_CASH"):
        return {"name": "BCC_5M_CASH_OPP_2026_F_L_001517", "rows": [], "warnings": ["BCC_5M_BLOCK_MISSING"]}

    explicit_rows = []
    for row_number in range(39, 47):
        payment_date = _as_date(ws.cell(row_number, 6).value)
        amount = _as_float(ws.cell(row_number, 7).value)
        if payment_date is None or amount is None:
            continue
        explicit_rows.append(
            {
                "sheet": "ADDITIONS",
                "row": row_number,
                "cashflow_date": payment_date.isoformat(),
                "payment_day": 9,
                "amount_kzt": round(float(amount), 2),
                "status": _upper(ws.cell(row_number, 8).value),
                "notes": _as_text(ws.cell(row_number, 9).value),
                "source": "explicit_sheet_schedule",
            }
        )

    facts: dict[str, Any] = {}
    for row_number in range(48, 57):
        key = _as_text(ws.cell(row_number, 6).value)
        value = ws.cell(row_number, 7).value
        if not key:
            continue
        parsed_date = _as_date(value)
        facts[key] = parsed_date.isoformat() if parsed_date else value

    monthly_payment = _as_float(facts.get("contract_amount_kzt"))
    explicit_payment = explicit_rows[0]["amount_kzt"] if explicit_rows else 166451.0
    term_months = int(_as_float(facts.get("term_months")) or 60)
    first_payment_date = _as_date(explicit_rows[0]["cashflow_date"] if explicit_rows else None) or date(2026, 5, 9)
    generated_rows = []
    explicit_by_date = {row["cashflow_date"]: row for row in explicit_rows}
    for idx in range(term_months):
        payment_date = _add_months(first_payment_date, idx)
        if payment_date > horizon_end and payment_date.isoformat() not in explicit_by_date:
            continue
        if payment_date.isoformat() in explicit_by_date:
            generated_rows.append(explicit_by_date[payment_date.isoformat()])
        else:
            generated_rows.append(
                {
                    "sheet": "ADDITIONS",
                    "row": None,
                    "cashflow_date": payment_date.isoformat(),
                    "payment_day": 9,
                    "amount_kzt": round(float(explicit_payment), 2),
                    "status": "GENERATED_TO_HORIZON",
                    "notes": "extended from BCC 5M term_months using safe pay day 9",
                    "source": "generated_from_term",
                }
            )

    return {
        "name": name,
        "opex_name": "BCC_universal_5M",
        "bank": "BCC",
        "account": "Universal",
        "contract_no": facts.get("contract_number"),
        "monthly_payment_kzt": round(float(explicit_payment), 2),
        "contract_amount_kzt": facts.get("contract_amount_kzt"),
        "outstanding_principal_kzt": facts.get("outstanding_principal_kzt"),
        "term_months": term_months,
        "safe_pay_day": 9,
        "screenshot_date_received": facts.get("screenshot_date_received"),
        "owner_stated_taken_date": facts.get("owner_stated_taken_date"),
        "end_date": facts.get("end_date"),
        "facts": facts,
        "rows": generated_rows,
        "explicit_rows": explicit_rows,
        "unused_internal_check_monthly_payment_source": monthly_payment,
    }


def _parse_additions_sheet(ws: Any, as_of: date, horizon_end: date) -> dict[str, Any]:
    return {
        "kaspi_gold_uni": _parse_kaspi_gold_uni_schedule(ws, as_of),
        "bcc_5m": _parse_bcc_5m_schedule(ws, horizon_end),
    }


def _replace_opex_line(
    line: NormalizedOpexLine,
    *,
    flags: Iterable[str] | None = None,
    owner_action_required: bool | None = None,
) -> NormalizedOpexLine:
    merged_flags = tuple(dict.fromkeys([*line.flags, *(flags or [])]))
    return NormalizedOpexLine(
        row_number=line.row_number,
        name=line.name,
        action=line.action,
        include_in_cashflow=line.include_in_cashflow,
        included=line.included,
        schedule=line.schedule,
        day=line.day,
        source_monthly_kzt=line.source_monthly_kzt,
        owner_monthly_kzt=line.owner_monthly_kzt,
        monthly_amount_kzt=line.monthly_amount_kzt,
        amount_authority=line.amount_authority,
        account=line.account,
        expense_type=line.expense_type,
        months_left=line.months_left,
        principal_left_kzt=line.principal_left_kzt,
        flags=merged_flags,
        provenance=line.provenance,
        owner_action_required=line.owner_action_required
        if owner_action_required is None
        else owner_action_required,
    )


def _replace_loan(
    loan: NormalizedLoan,
    *,
    flags: Iterable[str] | None = None,
    owner_action_required: bool | None = None,
) -> NormalizedLoan:
    merged_flags = tuple(dict.fromkeys([*loan.flags, *(flags or [])]))
    return NormalizedLoan(
        row_number=loan.row_number,
        loan_name=loan.loan_name,
        action=loan.action,
        source_status=loan.source_status,
        bank=loan.bank,
        account=loan.account,
        opex_name=loan.opex_name,
        payment_day=loan.payment_day,
        next_due=loan.next_due,
        source_monthly_payment_kzt=loan.source_monthly_payment_kzt,
        owner_monthly_payment_kzt=loan.owner_monthly_payment_kzt,
        monthly_payment_kzt=loan.monthly_payment_kzt,
        principal_kzt=loan.principal_kzt,
        balance_now_source_kzt=loan.balance_now_source_kzt,
        months_total=loan.months_total,
        last_schedule_date=loan.last_schedule_date,
        include_in_cashflow=loan.include_in_cashflow,
        included=loan.included,
        flags=merged_flags,
        provenance=loan.provenance,
        owner_action_required=loan.owner_action_required
        if owner_action_required is None
        else owner_action_required,
    )


def _apply_cross_checks(
    opex_lines: list[NormalizedOpexLine],
    loans: list[NormalizedLoan],
    schedules: dict[str, Any],
) -> tuple[list[NormalizedOpexLine], list[NormalizedLoan], list[dict[str, Any]]]:
    loans_by_opex = {loan.opex_name: loan for loan in loans if loan.opex_name and loan.opex_name != "-"}
    crosschecks: list[dict[str, Any]] = []
    updated_lines: list[NormalizedOpexLine] = []
    updated_loans_by_name: dict[str, NormalizedLoan] = {loan.loan_name: loan for loan in loans}

    for line in opex_lines:
        loan = loans_by_opex.get(line.name)
        flags: list[str] = []
        owner_required = line.owner_action_required
        if line.name in {"GOLD_universal", "BCC_universal_5M"}:
            flags.append("ADDITIONS_DATED_SCHEDULE_OVERRIDE")
        if line.name == "GOLD_store-d":
            flags.append("REVIEW_VARIANTS_REQUIRED")
            owner_required = True
        if loan:
            delta = line.monthly_amount_kzt - loan.monthly_payment_kzt
            check_flags: list[str] = []
            if abs(delta) > 0.01:
                check_flags.append("OPEX_LOANS_AMOUNT_DELTA")
            if line.name == "GOLD_Acmewear" and abs(delta) > 0.01:
                check_flags.append("GOLD_ACMEWEAR_MISMATCH_OWNER_QUESTION")
                flags.append("GOLD_ACMEWEAR_MISMATCH_OWNER_QUESTION")
                owner_required = True
            if line.name == "GOLD_store-d" and loan.include_in_cashflow == "REVIEW":
                check_flags.append("GOLD_11KZ_REVIEW_VARIANTS")
                updated_loans_by_name[loan.loan_name] = _replace_loan(
                    loan,
                    flags=["GOLD_11KZ_REVIEW_VARIANTS"],
                    owner_action_required=True,
                )
            crosschecks.append(
                {
                    "opex_name": line.name,
                    "opex_row": line.row_number,
                    "loan_name": loan.loan_name,
                    "loan_row": loan.row_number,
                    "opex_amount_kzt": round(line.monthly_amount_kzt, 2),
                    "loan_owner_payment_kzt": round(loan.monthly_payment_kzt, 2),
                    "delta_kzt": round(delta, 2),
                    "flags": check_flags,
                }
            )
        updated_lines.append(_replace_opex_line(line, flags=flags, owner_action_required=owner_required))

    if schedules["kaspi_gold_uni"]["rows"]:
        first_unpaid = schedules["kaspi_gold_uni"].get("first_unpaid_cashflow_date")
        crosschecks.append(
            {
                "opex_name": "GOLD_universal",
                "loan_name": "KaspiGOLD_Uni",
                "flags": ["ADDITIONS_DATED_SCHEDULE_OVERRIDE"],
                "detail": f"KaspiGOLD_Uni dated schedule overrides flat monthly; first unpaid {first_unpaid}",
            }
        )
    if schedules["bcc_5m"]["rows"]:
        crosschecks.append(
            {
                "opex_name": "BCC_universal_5M",
                "loan_name": schedules["bcc_5m"].get("name"),
                "flags": ["ADDITIONS_DATED_SCHEDULE_OVERRIDE", "BCC_ACCOUNT_UNIVERSAL_CONFIRM"],
                "detail": "BCC 5M schedule uses safe pay day 9 and keeps screenshot/context dates distinct",
            }
        )

    return updated_lines, list(updated_loans_by_name.values()), crosschecks


def _assert_macbook_invariant(
    opex_lines: list[NormalizedOpexLine],
    loans: list[NormalizedLoan],
    schedules: dict[str, Any],
) -> None:
    named_hits = []
    for line in opex_lines:
        if "macbook" in line.name.lower():
            named_hits.append({"sheet": "OPEX_INPUT", "row": line.row_number, "name": line.name})
    for loan in loans:
        if "macbook" in loan.loan_name.lower() or "macbook" in loan.opex_name.lower():
            named_hits.append({"sheet": "LOANS_INPUT", "row": loan.row_number, "name": loan.loan_name})
    if named_hits:
        raise OpexOwnerInputError(f"MacBook invariant failed; separate MacBook rows found: {named_hits}")

    notes = schedules.get("kaspi_gold_uni", {}).get("macbook_note_provenance") or []
    if not notes:
        raise OpexOwnerInputError("MacBook invariant failed; expected included-note provenance is missing")


def normalize_workbook(workbook_path: Path, as_of: date, horizon_days: int = DEFAULT_HORIZON_DAYS) -> dict[str, Any]:
    if not workbook_path.exists():
        raise FileNotFoundError(f"workbook not found: {workbook_path}")
    horizon_end = as_of + timedelta(days=horizon_days - 1)
    try:
        workbook = load_workbook(workbook_path, read_only=True, data_only=True)
    except Exception as exc:  # pragma: no cover - exercised through CLI stopline
        raise OpexOwnerInputError(f"workbook unreadable: {workbook_path}") from exc

    required_sheets = {"OPEX_INPUT", "LOANS_INPUT", "ADDITIONS"}
    missing = sorted(required_sheets - set(workbook.sheetnames))
    if missing:
        raise OpexOwnerInputError(f"workbook missing required sheets: {missing}")

    opex_lines, opex_meta = _parse_opex_sheet(workbook["OPEX_INPUT"])
    loans, loans_meta = _parse_loans_sheet(workbook["LOANS_INPUT"])
    schedules = _parse_additions_sheet(workbook["ADDITIONS"], as_of, horizon_end)
    _assert_macbook_invariant(opex_lines, loans, schedules)
    opex_lines, loans, crosschecks = _apply_cross_checks(opex_lines, loans, schedules)

    return {
        "as_of": as_of.isoformat(),
        "horizon_days": horizon_days,
        "horizon_end": horizon_end.isoformat(),
        "workbook_path": str(workbook_path.resolve()),
        "sheet_names": workbook.sheetnames,
        "sheet_row_counts": {
            "OPEX_INPUT": workbook["OPEX_INPUT"].max_row - 6,
            "LOANS_INPUT": workbook["LOANS_INPUT"].max_row - 6,
            "ADDITIONS": workbook["ADDITIONS"].max_row,
        },
        "parse_meta": {
            "opex": opex_meta,
            "loans": loans_meta,
        },
        "opex_lines": opex_lines,
        "loans": loans,
        "loan_schedules": schedules,
        "crosschecks": crosschecks,
    }


def _line_to_dict(line: NormalizedOpexLine) -> dict[str, Any]:
    return {
        "row_number": line.row_number,
        "name": line.name,
        "action": line.action,
        "include_in_cashflow": line.include_in_cashflow,
        "included": line.included,
        "schedule": line.schedule,
        "payment_day_of_month": line.day,
        "source_monthly_kzt": line.source_monthly_kzt,
        "owner_monthly_kzt": line.owner_monthly_kzt,
        "monthly_amount_kzt": round(line.monthly_amount_kzt, 2),
        "amount_authority": line.amount_authority,
        "account": line.account,
        "expense_type": line.expense_type,
        "months_left": line.months_left,
        "principal_left_kzt": line.principal_left_kzt,
        "flags": list(line.flags),
        "owner_action_required": line.owner_action_required,
        "provenance": line.provenance,
    }


def _loan_to_dict(loan: NormalizedLoan) -> dict[str, Any]:
    return {
        "row_number": loan.row_number,
        "loan_name": loan.loan_name,
        "action": loan.action,
        "source_status": loan.source_status,
        "bank": loan.bank,
        "account": loan.account,
        "opex_name": loan.opex_name,
        "payment_day": loan.payment_day,
        "next_due": loan.next_due,
        "source_monthly_payment_kzt": loan.source_monthly_payment_kzt,
        "owner_monthly_payment_kzt": loan.owner_monthly_payment_kzt,
        "monthly_payment_kzt": round(loan.monthly_payment_kzt, 2),
        "principal_kzt": loan.principal_kzt,
        "balance_now_source_kzt": loan.balance_now_source_kzt,
        "months_total": loan.months_total,
        "last_schedule_date": loan.last_schedule_date,
        "include_in_cashflow": loan.include_in_cashflow,
        "included": loan.included,
        "flags": list(loan.flags),
        "owner_action_required": loan.owner_action_required,
        "provenance": loan.provenance,
    }


def normalized_opex_dicts(normalized: dict[str, Any]) -> list[dict[str, Any]]:
    return [_line_to_dict(line) for line in normalized["opex_lines"]]


def normalized_loan_dicts(normalized: dict[str, Any]) -> list[dict[str, Any]]:
    return [_loan_to_dict(loan) for loan in normalized["loans"]]


def _format_ref(as_of: date, ordinal: int) -> str:
    return f"OPEX_OWNER_{as_of.strftime('%Y%m%d')}_{ordinal:02d}"


def _commitment_notes(line: NormalizedOpexLine, variant_id: str, source: str) -> str:
    flags = ",".join(line.flags) if line.flags else "none"
    return (
        f"{line.expense_type}: {line.name}; owner_input={line.provenance.get('sheet')} row {line.row_number}; "
        f"variant={variant_id}; source={source}; flags={flags}"
    )


def _row_end(as_of: date, horizon_end: date, months_left: int | None) -> date:
    if months_left and months_left > 0:
        return min(horizon_end, _add_months(as_of, months_left) - timedelta(days=1))
    return horizon_end


def _scheduled_rows_for_line(
    line: NormalizedOpexLine,
    *,
    as_of: date,
    horizon_end: date,
    ref_id: str,
    variant_id: str,
    amount_override: float | None = None,
) -> list[dict[str, Any]]:
    amount = float(line.monthly_amount_kzt if amount_override is None else amount_override)
    if amount <= 0:
        return []
    row_end = _row_end(as_of, horizon_end, line.months_left)
    rows: list[dict[str, Any]] = []
    if line.schedule == "daily":
        daily = round(amount / 30.0, 2)
        for day in _date_range(as_of, row_end):
            rows.append(
                {
                    "commit_date": day.isoformat(),
                    "commit_type": "OPEX",
                    "amount_kzt": daily,
                    "scenario_tag": variant_id,
                    "ref_id": ref_id,
                    "notes": _commitment_notes(line, variant_id, "daily_monthly_div_30"),
                }
            )
        return rows

    if line.day is None:
        return []
    for month_start in _month_starts(as_of, row_end):
        commit_date = _safe_day_in_month(month_start, line.day)
        if commit_date < as_of or commit_date > row_end:
            continue
        rows.append(
            {
                "commit_date": commit_date.isoformat(),
                "commit_type": "OPEX",
                "amount_kzt": round(amount, 2),
                "scenario_tag": variant_id,
                "ref_id": ref_id,
                "notes": _commitment_notes(line, variant_id, "monthly_owner_input"),
            }
        )
    return rows


def _schedule_override_rows(
    line: NormalizedOpexLine,
    schedules: dict[str, Any],
    *,
    as_of: date,
    horizon_end: date,
    ref_id: str,
    variant_id: str,
) -> list[dict[str, Any]] | None:
    if line.name == "GOLD_universal":
        rows = []
        for item in schedules["kaspi_gold_uni"]["rows"]:
            commit_date = date.fromisoformat(item["cashflow_date"])
            if commit_date < as_of or commit_date > horizon_end or item["status"] != "UNPAID":
                continue
            rows.append(
                {
                    "commit_date": commit_date.isoformat(),
                    "commit_type": "OPEX",
                    "amount_kzt": round(float(item["amount_kzt"]), 2),
                    "scenario_tag": variant_id,
                    "ref_id": ref_id,
                    "notes": _commitment_notes(line, variant_id, "kaspi_gold_uni_dated_schedule"),
                }
            )
        return rows
    if line.name == "BCC_universal_5M":
        rows = []
        for item in schedules["bcc_5m"]["rows"]:
            commit_date = date.fromisoformat(item["cashflow_date"])
            if commit_date < as_of or commit_date > horizon_end:
                continue
            if item["status"] == "PAID":
                continue
            rows.append(
                {
                    "commit_date": commit_date.isoformat(),
                    "commit_type": "OPEX",
                    "amount_kzt": round(float(item["amount_kzt"]), 2),
                    "scenario_tag": variant_id,
                    "ref_id": ref_id,
                    "notes": _commitment_notes(line, variant_id, "bcc_5m_dated_schedule"),
                }
            )
        return rows
    return None


def build_variant_commitments(
    normalized: dict[str, Any],
    variant_id: str,
    *,
    as_of: date,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
    scenario_tag: str | None = None,
) -> list[dict[str, Any]]:
    if variant_id not in VARIANT_DEFINITIONS:
        raise ValueError(f"unknown variant_id: {variant_id}")
    horizon_end = as_of + timedelta(days=horizon_days - 1)
    opex_lines: list[NormalizedOpexLine] = normalized["opex_lines"]
    loans_by_opex = {loan.opex_name: loan for loan in normalized["loans"] if loan.opex_name}
    rows: list[dict[str, Any]] = []
    scenario = scenario_tag or variant_id
    refs = {line.name: _format_ref(as_of, idx) for idx, line in enumerate(opex_lines, start=1)}
    for line in opex_lines:
        if not line.included and line.name != "GOLD_store-d":
            continue
        if line.name == "GOLD_store-d":
            mode = VARIANT_DEFINITIONS[variant_id]["gold_store-d_mode"]
            if mode == "excluded":
                continue
            amount_override = line.monthly_amount_kzt
            if mode == "loan_owner":
                loan = loans_by_opex.get("GOLD_store-d")
                if loan is None:
                    raise OpexOwnerInputError("GOLD_store-d review variant needs linked loan row")
                amount_override = loan.monthly_payment_kzt
            rows.extend(
                _scheduled_rows_for_line(
                    line,
                    as_of=as_of,
                    horizon_end=horizon_end,
                    ref_id=refs[line.name],
                    variant_id=scenario,
                    amount_override=amount_override,
                )
            )
            continue

        override_rows = _schedule_override_rows(
            line,
            normalized["loan_schedules"],
            as_of=as_of,
            horizon_end=horizon_end,
            ref_id=refs[line.name],
            variant_id=scenario,
        )
        if override_rows is not None:
            rows.extend(override_rows)
            continue
        rows.extend(
            _scheduled_rows_for_line(
                line,
                as_of=as_of,
                horizon_end=horizon_end,
                ref_id=refs[line.name],
                variant_id=scenario,
            )
        )
    rows.sort(key=lambda row: (row["commit_date"], row["ref_id"], row["amount_kzt"]))
    return rows


def build_all_commitments(normalized: dict[str, Any], as_of: date, horizon_days: int) -> dict[str, list[dict[str, Any]]]:
    return {
        variant_id: build_variant_commitments(
            normalized,
            variant_id,
            as_of=as_of,
            horizon_days=horizon_days,
            scenario_tag="base",
        )
        for variant_id in VARIANT_DEFINITIONS
    }


def _sum_window(rows: list[dict[str, Any]], start: date, end: date) -> float:
    total = 0.0
    for row in rows:
        commit_date = date.fromisoformat(row["commit_date"])
        if start <= commit_date <= end and row["commit_type"] == "OPEX":
            total += float(row["amount_kzt"] or 0.0)
    return round(total, 2)


def _floor_payload(opex_monthly: float) -> dict[str, float]:
    base = max(ABSOLUTE_CASH_FLOOR_KZT, opex_monthly * BASE_FLOOR_MULT)
    conservative = opex_monthly * CONSERVATIVE_FLOOR_MULT + ABSOLUTE_CASH_FLOOR_KZT
    return {
        "opex_monthly_kzt": round(opex_monthly, 2),
        "base_floor_kzt": round(base, 2),
        "conservative_floor_kzt": round(conservative, 2),
    }


def compute_floor_proposal(
    commitments_by_variant: dict[str, list[dict[str, Any]]],
    *,
    as_of: date,
    current_context: dict[str, Any],
    sidecar: dict[str, Any] | None,
) -> dict[str, Any]:
    window_end = as_of + timedelta(days=30)
    variants = {}
    current_opex = float(current_context.get("current_opex_monthly_kzt") or 0.0)
    current_cons = float(current_context.get("current_conservative_floor_kzt") or 0.0)
    for variant_id, rows in commitments_by_variant.items():
        opex_monthly = _sum_window(rows, as_of, window_end)
        floors = _floor_payload(opex_monthly)
        variants[variant_id] = {
            "variant_id": variant_id,
            "label": VARIANT_DEFINITIONS[variant_id]["label"],
            **floors,
            "diff_vs_current_opex_monthly_kzt": round(floors["opex_monthly_kzt"] - current_opex, 2),
            "diff_vs_current_conservative_floor_kzt": round(
                floors["conservative_floor_kzt"] - current_cons,
                2,
            ),
            "owner_action_required": True,
        }

    sidecar_crosscheck = {}
    if sidecar:
        active_opex = float(sidecar.get("active_opex_source_monthly_excluding_stops") or 0.0)
        active_loans = float(sidecar.get("active_loan_payments_source_monthly") or 0.0)
        bcc = 166_451.0
        sidecar_crosscheck = {
            "active_opex_source_monthly_excluding_stops": round(active_opex, 2),
            "active_loan_payments_source_monthly": round(active_loans, 2),
            "bcc_5m_monthly_added_after_sidecar_kzt": bcc,
            "note": (
                "loan total is a cross-check surface; loan-class payments remain embedded in OPEX "
                "and must not be added a second time"
            ),
            "variant_residuals_vs_opex_plus_bcc": {
                variant_id: round(payload["opex_monthly_kzt"] - (active_opex + bcc), 2)
                for variant_id, payload in variants.items()
            },
            "variant_residuals_vs_opex_plus_loan_plus_bcc": {
                variant_id: round(payload["opex_monthly_kzt"] - (active_opex + active_loans + bcc), 2)
                for variant_id, payload in variants.items()
            },
        }

    min_cash = current_context.get("current_conservative_min_cash_kzt")
    min_cash_text = f"current min cash {min_cash}" if min_cash is not None else "current min cash"

    return {
        "as_of": as_of.isoformat(),
        "window_start": as_of.isoformat(),
        "window_end_inclusive": window_end.isoformat(),
        "cashfloor_formula": {
            "base_floor": "max(500000, opex_monthly * 1.0)",
            "conservative_floor": "opex_monthly * 1.5 + 500000",
            "source": "scripts/cashflow_preflight_po.py and scripts/validate_cashfloor.py",
        },
        "current": current_context,
        "variants": variants,
        "sidecar_crosscheck": sidecar_crosscheck,
        "policy_statement": (
            "Stage A does not choose an unblock path. Conservative preflight remains expected to fail "
            f"against {min_cash_text} unless the owner chooses RED, config multiplier changes, or a "
            "documented CASHFLOW_PREFLIGHT_OVERRIDE_REASON."
        ),
    }


def _connect_ro(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path.resolve()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def read_current_context(db_path: Path, as_of: date, preflight_report_path: Path | None = None) -> dict[str, Any]:
    with _connect_ro(db_path) as conn:
        row = conn.execute(
            """
            SELECT SUM(amount_kzt) AS opex_monthly, COUNT(*) AS rows_count
            FROM fact_cashflow_commitments
            WHERE commit_type = 'OPEX'
              AND commit_date BETWEEN ? AND ?
            """,
            (as_of.isoformat(), (as_of + timedelta(days=30)).isoformat()),
        ).fetchone()
        total_row = conn.execute(
            """
            SELECT COUNT(*) AS opex_rows, MIN(commit_date) AS min_date, MAX(commit_date) AS max_date
            FROM fact_cashflow_commitments
            WHERE commit_type = 'OPEX'
            """
        ).fetchone()
    context: dict[str, Any] = {
        "db_path": str(db_path.resolve()),
        "db_open_mode": "sqlite_uri_mode_ro",
        "current_opex_monthly_kzt": round(float(row["opex_monthly"] or 0.0), 2),
        "current_opex_window_rows": int(row["rows_count"] or 0),
        "current_opex_rows": int(total_row["opex_rows"] or 0),
        "current_opex_min_date": total_row["min_date"],
        "current_opex_max_date": total_row["max_date"],
    }
    preflight = _parse_preflight_report(preflight_report_path) if preflight_report_path else {}
    context.update(preflight)
    if "current_conservative_floor_kzt" not in context:
        context.update(
            {
                "current_base_floor_kzt": round(
                    max(ABSOLUTE_CASH_FLOOR_KZT, context["current_opex_monthly_kzt"]),
                    2,
                ),
                "current_conservative_floor_kzt": round(
                    context["current_opex_monthly_kzt"] * CONSERVATIVE_FLOOR_MULT
                    + ABSOLUTE_CASH_FLOOR_KZT,
                    2,
                ),
            }
        )
    return context


def _parse_preflight_report(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    mapping = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        mapping[key.strip()] = value.strip()

    def number(key: str) -> float | None:
        if key not in mapping:
            return None
        try:
            return round(float(mapping[key]), 2)
        except ValueError:
            return None

    parsed: dict[str, Any] = {
        "current_preflight_report_path": str(path.resolve()),
        "current_preflight_status": mapping.get("status"),
        "current_preflight_reason": mapping.get("reason"),
    }
    rename = {
        "base_floor_kzt": "current_base_floor_kzt",
        "base_min_cash_kzt": "current_base_min_cash_kzt",
        "conservative_floor_kzt": "current_conservative_floor_kzt",
        "conservative_min_cash_kzt": "current_conservative_min_cash_kzt",
        "opex_monthly_kzt": "current_preflight_opex_monthly_kzt",
    }
    for old, new in rename.items():
        value = number(old)
        if value is not None:
            parsed[new] = value
    parsed["current_conservative_min_cash_date"] = mapping.get("conservative_min_cash_date")
    parsed["current_base_min_cash_date"] = mapping.get("base_min_cash_date")
    return parsed


def read_json_if_exists(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_commitments_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COMMITMENT_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in COMMITMENT_COLUMNS})


def write_normalized_opex_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "row_number",
        "name",
        "action",
        "include_in_cashflow",
        "included",
        "schedule",
        "payment_day_of_month",
        "source_monthly_kzt",
        "owner_monthly_kzt",
        "monthly_amount_kzt",
        "amount_authority",
        "account",
        "expense_type",
        "months_left",
        "principal_left_kzt",
        "owner_action_required",
        "flags",
        "source_ref",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            flat = dict(row)
            flat["flags"] = ";".join(row["flags"])
            flat["source_ref"] = row.get("provenance", {}).get("source_ref", "")
            writer.writerow({column: flat.get(column, "") for column in fieldnames})


def _render_crosscheck_md(crosschecks: list[dict[str, Any]]) -> str:
    lines = [
        "# OPEX vs Loans Crosscheck",
        "",
        "## Prominent Owner Questions",
        "",
    ]
    gold_acmewear = [row for row in crosschecks if row.get("opex_name") == "GOLD_Acmewear"]
    if gold_acmewear:
        row = gold_acmewear[0]
        impact = abs(float(row["delta_kzt"])) * CONSERVATIVE_FLOOR_MULT
        lines.append(
            f"- GOLD_Acmewear mismatch: OPEX {row['opex_amount_kzt']:.2f} vs loan "
            f"{row['loan_owner_payment_kzt']:.2f}; conservative-floor impact about {impact:.2f} KZT."
        )
    lines.extend(
        [
            "- GOLD_store-d / KaspiGOLD_KZ is REVIEW and must be owner-selected as V1, V2, or V3.",
            "- BCC 5M account is Universal in the workbook and needs owner confirmation.",
            "",
            "## Crosscheck Table",
            "",
            "| opex_name | loan_name | opex_amount_kzt | loan_owner_payment_kzt | delta_kzt | flags |",
            "|---|---|---:|---:|---:|---|",
        ]
    )
    for row in crosschecks:
        if "delta_kzt" not in row:
            continue
        lines.append(
            f"| {row.get('opex_name','')} | {row.get('loan_name','')} | "
            f"{row.get('opex_amount_kzt',0):.2f} | {row.get('loan_owner_payment_kzt',0):.2f} | "
            f"{row.get('delta_kzt',0):.2f} | {', '.join(row.get('flags') or []) or 'none'} |"
        )
    lines.append("")
    return "\n".join(lines)


def _render_floor_md(proposal: dict[str, Any]) -> str:
    lines = [
        "# OPEX Cash-Floor Proposal",
        "",
        "Stage A is no-write. These numbers are a proposal for owner approval only.",
        "",
        "## Current Gate",
        "",
    ]
    current = proposal["current"]
    lines.extend(
        [
            f"- current_opex_monthly_kzt: {current.get('current_opex_monthly_kzt')}",
            f"- current_conservative_floor_kzt: {current.get('current_conservative_floor_kzt')}",
            f"- current_conservative_min_cash_kzt: {current.get('current_conservative_min_cash_kzt')}",
            f"- current_preflight_status: {current.get('current_preflight_status')}",
            f"- current_preflight_reason: {current.get('current_preflight_reason')}",
            "",
            "## Variants",
            "",
            "| variant | opex_monthly_kzt | base_floor_kzt | conservative_floor_kzt | diff_vs_current_cons | owner_action_required |",
            "|---|---:|---:|---:|---:|---|",
        ]
    )
    if current.get("preflight_report_conflict_note"):
        lines.insert(11, f"- preflight_report_conflict_note: {current['preflight_report_conflict_note']}")
    for variant_id, variant in proposal["variants"].items():
        lines.append(
            f"| {variant_id} | {variant['opex_monthly_kzt']:.2f} | "
            f"{variant['base_floor_kzt']:.2f} | {variant['conservative_floor_kzt']:.2f} | "
            f"{variant['diff_vs_current_conservative_floor_kzt']:.2f} | yes |"
        )
    lines.extend(
        [
            "",
            "## Sidecar Crosscheck",
            "",
        ]
    )
    sidecar = proposal.get("sidecar_crosscheck") or {}
    if sidecar:
        lines.extend(
            [
                f"- active_opex_source_monthly_excluding_stops: {sidecar.get('active_opex_source_monthly_excluding_stops')}",
                f"- active_loan_payments_source_monthly: {sidecar.get('active_loan_payments_source_monthly')}",
                f"- bcc_5m_monthly_added_after_sidecar_kzt: {sidecar.get('bcc_5m_monthly_added_after_sidecar_kzt')}",
                f"- interpretation: {sidecar.get('note')}",
            ]
        )
    lines.extend(
        [
            "",
            "## Policy Statement",
            "",
            proposal["policy_statement"],
            "",
        ]
    )
    return "\n".join(lines)


def _render_open_questions_md() -> str:
    questions = [
        "KaspiGOLD_KZ / GOLD_store-d: choose schedule/inclusion variant V1 sheet 100,000, V2 owner 80,000, or V3 excluded.",
        "GOLD_Acmewear: confirm OPEX 176,511/month vs LOANS 92,049/month.",
        "KaspiGOLD_Uni: confirm dated declining ADDITIONS schedule should override the flat OPEX row.",
        "Internet: confirm assumed payment day 27.",
        "LLM_6 and LLM_7: confirm CLOSED plus include YES should stay excluded.",
        "Gym_memberships: confirm owner amount 90,000 vs source 30,000.",
        "BCC 5M: confirm date anchors stay screenshot 2026-04-11 and owner-stated 2026-04-04, and account remains Universal.",
        "G-SCHED-02: choose unblock policy: keep RED, adjust cashflow_scenarios.yaml multipliers, or document CASHFLOW_PREFLIGHT_OVERRIDE_REASON.",
    ]
    lines = ["# Open Questions", ""]
    for idx, question in enumerate(questions, start=1):
        lines.append(f"{idx}. {question}")
    lines.append("")
    return "\n".join(lines)


def _render_return_md(
    *,
    out_dir: Path,
    normalized: dict[str, Any],
    proposal: dict[str, Any],
    files_created: list[str],
    files_inspected: list[str],
    commands_run: list[dict[str, Any]] | None = None,
    db_sha_before: str | None = None,
    db_sha_after: str | None = None,
    gate: str = "GREEN",
) -> str:
    commands_run = commands_run or []
    opex_rows = normalized_opex_dicts(normalized)
    loan_rows = normalized_loan_dicts(normalized)
    excluded = [row["name"] for row in opex_rows if not row["included"]]
    flagged = [row["name"] for row in opex_rows if row["flags"]]
    lines = [
        "# PKT-OPEX-NORM Return",
        "",
        "Actions summary:",
        "- Parsed owner OPEX/loan workbook read-only.",
        "- Normalized OPEX lines, loans, dated loan schedules, proposed commitments, floor variants, crosschecks, and open questions.",
        "- No DB/config/docs/workbook/external apply was performed.",
        "",
        "Files created:",
    ]
    for path in files_created:
        lines.append(f"- {path}")
    lines.extend(["", "Files inspected:"])
    for path in files_inspected:
        lines.append(f"- {path}")
    lines.extend(["", "Commands run:"])
    if commands_run:
        for command in commands_run:
            lines.append(f"- exit {command.get('exit_code')}: {command.get('cmd')}")
    else:
        lines.append("- Filled by final operator closeout after verification commands.")
    lines.extend(
        [
            "",
            "Parsed row counts:",
            f"- OPEX_INPUT rows after header: {normalized['sheet_row_counts']['OPEX_INPUT']}",
            f"- LOANS_INPUT rows after header: {normalized['sheet_row_counts']['LOANS_INPUT']}",
            f"- ADDITIONS rows: {normalized['sheet_row_counts']['ADDITIONS']}",
            f"- normalized OPEX lines: {len(opex_rows)}",
            f"- normalized loans: {len(loan_rows)}",
            "",
            "Excluded OPEX rows:",
        ]
    )
    for name in excluded:
        lines.append(f"- {name}")
    lines.extend(["", "Flagged OPEX rows:"])
    for name in flagged:
        lines.append(f"- {name}")
    lines.extend(
        [
            "",
            "Floor table:",
            "",
            "| variant | opex_monthly_kzt | base_floor_kzt | conservative_floor_kzt |",
            "|---|---:|---:|---:|",
        ]
    )
    for variant_id, variant in proposal["variants"].items():
        lines.append(
            f"| {variant_id} | {variant['opex_monthly_kzt']:.2f} | "
            f"{variant['base_floor_kzt']:.2f} | {variant['conservative_floor_kzt']:.2f} |"
        )
    lines.extend(
        [
            "",
            "Open questions:",
            "- See open_questions.md.",
            "",
            "Remaining risks:",
            "- Stage A proposes numbers only; Stage B still needs owner approval and governed apply.",
            "- Conservative preflight remains expected to fail against current min cash unless owner chooses a policy path.",
            "",
            "Rollback note:",
            f"- Remove the new code/test files and evidence directory: {out_dir}",
            "",
            "No-write statement:",
            "- DB/config/docs/workbook/Google/Telegram/Kaspi/Repricer/price/stock/LaunchAgent/cash/PO/external surfaces were untouched by this normalizer.",
            f"- db_sha_before: {db_sha_before or 'recorded separately'}",
            f"- db_sha_after: {db_sha_after or 'recorded after verification'}",
            "",
            f"Gate: {gate}",
        ]
    )
    return "\n".join(lines) + "\n"


def build_workbook_provenance(workbook_path: Path, sidecar_paths: Iterable[Path]) -> dict[str, Any]:
    return {
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "workbook": _file_provenance(workbook_path),
        "sidecars": [_file_provenance(path) for path in sidecar_paths if path.exists()],
    }


def write_evidence_packet(
    *,
    normalized: dict[str, Any],
    commitments_by_variant: dict[str, list[dict[str, Any]]],
    floor_proposal: dict[str, Any],
    workbook_path: Path,
    sidecar_paths: list[Path],
    output_dir: Path,
    files_inspected: list[str],
    commands_run: list[dict[str, Any]] | None = None,
    db_sha_before: str | None = None,
    db_sha_after: str | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    files_created: list[str] = []

    opex_rows = normalized_opex_dicts(normalized)
    loans = normalized_loan_dicts(normalized)

    normalized_json = output_dir / "normalized_opex_lines.json"
    _write_json(normalized_json, opex_rows)
    files_created.append(str(normalized_json))
    normalized_csv = output_dir / "normalized_opex_lines.csv"
    write_normalized_opex_csv(normalized_csv, opex_rows)
    files_created.append(str(normalized_csv))

    loans_json = output_dir / "normalized_loans.json"
    _write_json(loans_json, loans)
    files_created.append(str(loans_json))

    schedules_json = output_dir / "loan_schedules.json"
    _write_json(schedules_json, normalized["loan_schedules"])
    files_created.append(str(schedules_json))

    crosscheck_md = output_dir / "opex_vs_loans_crosscheck.md"
    crosscheck_md.write_text(_render_crosscheck_md(normalized["crosschecks"]), encoding="utf-8")
    files_created.append(str(crosscheck_md))

    combined_rows: list[dict[str, Any]] = []
    for variant_id in VARIANT_DEFINITIONS:
        variant_rows = build_variant_commitments(
            normalized,
            variant_id,
            as_of=date.fromisoformat(normalized["as_of"]),
            horizon_days=int(normalized["horizon_days"]),
            scenario_tag=variant_id,
        )
        combined_rows.extend(variant_rows)
        variant_csv = output_dir / f"proposed_commitments_{variant_id}.csv"
        write_commitments_csv(variant_csv, commitments_by_variant[variant_id])
        files_created.append(str(variant_csv))

    proposed_csv = output_dir / "proposed_commitments.csv"
    write_commitments_csv(proposed_csv, sorted(combined_rows, key=lambda row: (row["scenario_tag"], row["commit_date"], row["ref_id"])))
    files_created.append(str(proposed_csv))

    proposal_json = output_dir / "floor_proposal.json"
    _write_json(proposal_json, floor_proposal)
    files_created.append(str(proposal_json))
    proposal_md = output_dir / "floor_proposal.md"
    proposal_md.write_text(_render_floor_md(floor_proposal), encoding="utf-8")
    files_created.append(str(proposal_md))

    questions_md = output_dir / "open_questions.md"
    questions_md.write_text(_render_open_questions_md(), encoding="utf-8")
    files_created.append(str(questions_md))

    provenance_json = output_dir / "workbook_provenance.json"
    _write_json(provenance_json, build_workbook_provenance(workbook_path, sidecar_paths))
    files_created.append(str(provenance_json))

    return_md = output_dir / "RETURN.md"
    return_md.write_text(
        _render_return_md(
            out_dir=output_dir,
            normalized=normalized,
            proposal=floor_proposal,
            files_created=files_created + [str(return_md)],
            files_inspected=files_inspected,
            commands_run=commands_run,
            db_sha_before=db_sha_before,
            db_sha_after=db_sha_after,
        ),
        encoding="utf-8",
    )
    files_created.append(str(return_md))

    return {
        "output_dir": str(output_dir),
        "files_created": files_created,
        "variant_row_counts": {variant: len(rows) for variant, rows in commitments_by_variant.items()},
        "combined_row_count": len(combined_rows),
    }
