from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any
from urllib.parse import quote

import yaml

from core.paths import PROJECT_ROOT


GOOGLE_SHEETS_SCOPES = (
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
)
DEFAULT_CONTRACT_PATH = PROJECT_ROOT / "config" / "google_ops_board.yaml"
OWNERSHIP_MODE_LEGACY_V3 = "legacy_v3"
OWNERSHIP_MODE_SPLIT_V1 = "split_v1"
OWNERSHIP_MODE_PARTIAL = "partial"
SALESRAW_SPLIT_COLUMNS = ("AUTO_SIZE_SUGGESTION",)
RUN_CONTROL_SPLIT_COLUMNS = (
    "employee_ready_observed_at",
    "auto_ready_for_closeout",
    "auto_ready_set_by",
    "auto_ready_set_at",
)
REQUIRED_SPLIT_COLUMNS = {
    "SalesRaw_Today": SALESRAW_SPLIT_COLUMNS,
    "Run_Control": RUN_CONTROL_SPLIT_COLUMNS,
}


@dataclass(frozen=True)
class TabContract:
    name: str
    headers: list[str]
    key_column: str
    editable_columns: list[str]
    ui: dict[str, Any]
    ownership: dict[str, list[str]] = field(default_factory=dict)
    new_row_defaults: dict[str, Any] = field(default_factory=dict)

    @property
    def editable_column_set(self) -> set[str]:
        return set(self.editable_columns)

    def ownership_column_set(self, owner: str) -> set[str]:
        return set(self.ownership.get(owner) or [])

    @property
    def publisher_preserved_column_set(self) -> set[str]:
        configured = self.ownership_column_set("publisher_preserved_columns")
        return configured or self.editable_column_set

    @property
    def publisher_owned_column_set(self) -> set[str]:
        configured = self.ownership_column_set("publisher_owned_columns")
        return configured or (set(self.headers) - self.publisher_preserved_column_set)


@dataclass(frozen=True)
class OpsBoardContract:
    version: int
    sync_mode: str
    spreadsheet_id: str
    write_env_gate: str
    db_write_env_gate: str
    closeout_write_env_gate: str
    service_account_env_vars: list[str]
    tabs: dict[str, TabContract]
    writeback: dict[str, dict[str, Any]]
    same_day_cutoff_default: str = "17:00"
    same_day_cutoff_by_store: dict[str, str] = field(default_factory=dict)
    board_ownership_mode: str = OWNERSHIP_MODE_LEGACY_V3
    effective_resolution: str = "legacy_shared_cells"


def load_ops_board_contract(path: Path | None = None) -> OpsBoardContract:
    contract_path = Path(path or DEFAULT_CONTRACT_PATH)
    data = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    tabs = {
        name: TabContract(
            name=name,
            headers=list(spec["headers"]),
            key_column=str(spec["key_column"]),
            editable_columns=list(spec.get("editable_columns") or []),
            ui=dict(spec.get("ui") or {}),
            ownership={
                str(key): [str(value) for value in (values or [])]
                for key, values in (spec.get("ownership") or {}).items()
            },
            new_row_defaults=dict(spec.get("new_row_defaults") or {}),
        )
        for name, spec in (data.get("tabs") or {}).items()
    }
    return OpsBoardContract(
        version=int(data["version"]),
        sync_mode=str(data["sync_mode"]),
        spreadsheet_id=str(data["spreadsheet_id"]),
        write_env_gate=str(data["write_env_gate"]),
        db_write_env_gate=str(data["db_write_env_gate"]),
        closeout_write_env_gate=str(data["closeout_write_env_gate"]),
        service_account_env_vars=[str(x) for x in data.get("service_account_env_vars") or []],
        tabs=tabs,
        writeback={str(k): dict(v or {}) for k, v in (data.get("writeback") or {}).items()},
        same_day_cutoff_default=str(data.get("same_day_cutoff_default") or "17:00"),
        same_day_cutoff_by_store={
            str(k): str(v) for k, v in (data.get("same_day_cutoff_by_store") or {}).items()
        },
        board_ownership_mode=str(
            data.get("board_ownership_mode") or OWNERSHIP_MODE_LEGACY_V3
        ),
        effective_resolution=str(
            data.get("effective_resolution") or "legacy_shared_cells"
        ),
    )


def contract_for_ownership_mode(
    contract: OpsBoardContract,
    ownership_mode: str,
) -> OpsBoardContract:
    """Return the exact header/default view allowed by the observed Board mode."""
    if ownership_mode == OWNERSHIP_MODE_SPLIT_V1:
        return contract
    if ownership_mode != OWNERSHIP_MODE_LEGACY_V3:
        raise ValueError(f"Unsupported Board ownership mode: {ownership_mode}")
    tabs = dict(contract.tabs)
    for tab_name, split_columns in REQUIRED_SPLIT_COLUMNS.items():
        tab = tabs[tab_name]
        split_set = set(split_columns)
        defaults = {
            key: value
            for key, value in tab.new_row_defaults.items()
            if key not in split_set
        }
        if tab_name == "Run_Control":
            defaults["ready_for_closeout"] = "HOLD"
        tabs[tab_name] = replace(
            tab,
            headers=[header for header in tab.headers if header not in split_set],
            editable_columns=[
                column for column in tab.editable_columns if column not in split_set
            ],
            ownership={},
            new_row_defaults=defaults,
        )
    return replace(
        contract,
        version=3,
        tabs=tabs,
        board_ownership_mode=OWNERSHIP_MODE_LEGACY_V3,
        effective_resolution="legacy_shared_cells",
    )


def resolve_service_account_json(
    explicit_path: Path | None = None,
    contract: OpsBoardContract | None = None,
) -> Path:
    candidates: list[str] = []
    if explicit_path:
        candidates.append(str(explicit_path))
    if contract is not None:
        for env_name in contract.service_account_env_vars:
            value = os.environ.get(env_name)
            if value:
                candidates.append(value)
    else:
        for env_name in ("AB_GOOGLE_SERVICE_ACCOUNT_JSON", "GOOGLE_APPLICATION_CREDENTIALS"):
            value = os.environ.get(env_name)
            if value:
                candidates.append(value)
    for candidate in candidates:
        path = Path(candidate).expanduser()
        if path.exists():
            return path
    raise RuntimeError(
        "Google service-account JSON not found. Provide --service-account-json or set "
        "AB_GOOGLE_SERVICE_ACCOUNT_JSON."
    )


def resolve_spreadsheet_id(
    explicit_id: str | None = None,
    contract: OpsBoardContract | None = None,
) -> str:
    if explicit_id:
        return explicit_id.strip()
    env_value = os.environ.get("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID")
    if env_value:
        return env_value.strip()
    if contract is not None:
        return contract.spreadsheet_id
    raise RuntimeError("Spreadsheet ID not provided.")


def _import_google_auth():
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2 import service_account

    return AuthorizedSession, service_account


def build_authorized_session(service_account_json: Path):
    AuthorizedSession, service_account = _import_google_auth()
    credentials = service_account.Credentials.from_service_account_file(
        str(service_account_json),
        scopes=list(GOOGLE_SHEETS_SCOPES),
    )
    return AuthorizedSession(credentials)


def _clean_key(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def _sheet_input_value(value: Any) -> Any:
    # The values API skips JSON null instead of clearing the destination cell.
    # Canonical blank values must therefore be explicit empty strings.
    return "" if value is None else value


def _column_letter(column_number: int) -> str:
    if column_number < 1:
        raise ValueError(f"Column number must be >= 1, got {column_number}")
    result = ""
    current = column_number
    while current:
        current, remainder = divmod(current - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _group_consecutive_indices(indices: list[int]) -> list[tuple[int, int]]:
    if not indices:
        return []
    ordered = sorted(set(indices))
    groups: list[tuple[int, int]] = []
    start = ordered[0]
    previous = ordered[0]
    for value in ordered[1:]:
        if value == previous + 1:
            previous = value
            continue
        groups.append((start, previous + 1))
        start = value
        previous = value
    groups.append((start, previous + 1))
    return groups


def _boolean_rule(
    *,
    condition_type: str,
    format_spec: dict[str, Any],
    value: str | None = None,
) -> dict[str, Any]:
    condition: dict[str, Any] = {"type": condition_type}
    if value is not None:
        condition["values"] = [{"userEnteredValue": value}]
    text_format: dict[str, Any] = {}
    if format_spec.get("bold"):
        text_format["bold"] = True
    if format_spec.get("text_rgb"):
        red, green, blue = format_spec["text_rgb"]
        text_format["foregroundColor"] = {"red": red, "green": green, "blue": blue}
    fmt: dict[str, Any] = {}
    if format_spec.get("background_rgb"):
        red, green, blue = format_spec["background_rgb"]
        fmt["backgroundColor"] = {"red": red, "green": green, "blue": blue}
    if text_format:
        fmt["textFormat"] = text_format
    return {
        "booleanRule": {
            "condition": condition,
            "format": fmt,
        }
    }


def build_tab_ui_requests(
    tab_contract: TabContract,
    *,
    sheet_id: int,
    row_count: int,
    column_count: int,
    existing_conditional_rule_count: int = 0,
    existing_protected_range_ids: list[int] | None = None,
) -> list[dict[str, Any]]:
    if not tab_contract.ui:
        return []

    ui = tab_contract.ui
    header_index = {header: idx for idx, header in enumerate(tab_contract.headers)}
    max_row_count = max(int(row_count or 0), int(ui.get("min_row_count") or 0), 2)
    max_column_count = max(int(column_count or 0), len(tab_contract.headers))
    requests: list[dict[str, Any]] = [
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": sheet_id,
                    "gridProperties": {
                        "frozenRowCount": int(ui.get("frozen_row_count") or 1),
                    },
                },
                "fields": "gridProperties.frozenRowCount",
            }
        },
        {
            "setBasicFilter": {
                "filter": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": max_row_count,
                        "startColumnIndex": 0,
                        "endColumnIndex": len(tab_contract.headers),
                    }
                }
            }
        },
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": 0,
                    "endIndex": max_column_count,
                },
                "properties": {"hiddenByUser": False},
                "fields": "hiddenByUser",
            }
        },
    ]

    hidden_columns = [header_index[name] for name in ui.get("hidden_columns") or [] if name in header_index]
    for start_index, end_index in _group_consecutive_indices(hidden_columns):
        requests.append(
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": start_index,
                        "endIndex": end_index,
                    },
                    "properties": {"hiddenByUser": True},
                    "fields": "hiddenByUser",
                }
            }
        )

    for rule_index in range(max(existing_conditional_rule_count, 0) - 1, -1, -1):
        requests.append(
            {
                "deleteConditionalFormatRule": {
                    "sheetId": sheet_id,
                    "index": rule_index,
                }
            }
        )

    for protected_range_id in existing_protected_range_ids or []:
        requests.append(
            {
                "deleteProtectedRange": {
                    "protectedRangeId": int(protected_range_id),
                }
            }
        )

    for position, rule_spec in enumerate(ui.get("conditional_formats") or []):
        column_name = str(rule_spec["column"])
        column_index = header_index[column_name]
        requests.append(
            {
                "addConditionalFormatRule": {
                    "index": position,
                    "rule": {
                        "ranges": [
                            {
                                "sheetId": sheet_id,
                                "startRowIndex": 1,
                                "endRowIndex": max_row_count,
                                "startColumnIndex": column_index,
                                "endColumnIndex": column_index + 1,
                            }
                        ],
                        **_boolean_rule(
                            condition_type=str(rule_spec["type"]),
                            format_spec=rule_spec,
                            value=str(rule_spec.get("value")) if rule_spec.get("value") is not None else None,
                        ),
                    },
                }
            }
        )

    clear_validation_columns = [
        header_index[str(column_name)]
        for column_name in ui.get("clear_data_validation_columns") or []
        if str(column_name) in header_index
    ]
    for column_index in clear_validation_columns:
        requests.append(
            {
                "setDataValidation": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 1,
                        "endRowIndex": max_row_count,
                        "startColumnIndex": column_index,
                        "endColumnIndex": column_index + 1,
                    },
                    "rule": None,
                }
            }
        )

    validation_spec = dict(ui.get("data_validation") or {})
    validation_column = validation_spec.get("column")
    if validation_column and validation_column in header_index:
        requests.append(
            {
                "setDataValidation": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 1,
                        "endRowIndex": max_row_count,
                        "startColumnIndex": header_index[str(validation_column)],
                        "endColumnIndex": header_index[str(validation_column)] + 1,
                    },
                    "rule": {
                        "condition": {
                            "type": "ONE_OF_LIST",
                            "values": [
                                {"userEnteredValue": str(value)}
                                for value in validation_spec.get("allowed_values") or []
                            ],
                        },
                        "strict": True,
                        "showCustomUi": True,
                    },
                }
            }
        )

    protection_spec = dict(ui.get("protected_sheet") or {})
    unprotected_columns = [
        header_index[str(column_name)]
        for column_name in protection_spec.get("unprotected_columns") or []
        if str(column_name) in header_index
    ]
    if protection_spec:
        requests.append(
            {
                "addProtectedRange": {
                    "protectedRange": {
                        "range": {"sheetId": sheet_id},
                        "warningOnly": bool(protection_spec.get("warning_only", False)),
                        "description": f"Managed protection for {tab_contract.name}",
                        "unprotectedRanges": [
                            {
                                "sheetId": sheet_id,
                                "startRowIndex": 1,
                                "endRowIndex": max_row_count,
                                "startColumnIndex": start_index,
                                "endColumnIndex": end_index,
                            }
                            for start_index, end_index in _group_consecutive_indices(unprotected_columns)
                        ],
                    }
                }
            }
        )

    return requests


def build_tab_reorder_requests(
    current_sheets: list[dict[str, Any]],
    desired_titles: list[str],
) -> list[dict[str, Any]]:
    title_to_props = {
        str((sheet.get("properties") or {}).get("title")): dict(sheet.get("properties") or {})
        for sheet in current_sheets
    }
    requests: list[dict[str, Any]] = []
    for target_index, title in enumerate(desired_titles):
        props = title_to_props.get(title)
        if not props:
            continue
        if int(props.get("index", -1)) == target_index:
            continue
        requests.append(
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": int(props["sheetId"]),
                        "index": target_index,
                    },
                    "fields": "index",
                }
            }
        )
    return requests


def rows_to_matrix(headers: list[str], rows: list[dict[str, Any]]) -> list[list[Any]]:
    matrix: list[list[Any]] = [headers]
    for row in rows:
        matrix.append([_sheet_input_value(row.get(header, "")) for header in headers])
    return matrix


def _resolve_header_mapping(
    expected_headers: list[str],
    observed_row: list[Any],
    *,
    allow_trailing_missing: bool = False,
) -> tuple[bool, list[int], list[int]]:
    observed = [str(cell or "").strip() for cell in observed_row]
    if observed[: len(expected_headers)] == expected_headers:
        return True, list(range(len(expected_headers))), []
    if (
        allow_trailing_missing
        and observed
        and len(observed) < len(expected_headers)
        and observed == expected_headers[: len(observed)]
    ):
        return True, list(range(len(expected_headers))), []

    nonblank_headers = [(idx, value) for idx, value in enumerate(observed) if value]
    if [value for _, value in nonblank_headers] == expected_headers:
        blank_columns = [idx + 1 for idx, value in enumerate(observed) if not value]
        return True, [idx for idx, _ in nonblank_headers], blank_columns

    return False, list(range(len(expected_headers))), []


def extract_rows_from_matrix(headers: list[str], matrix: list[list[Any]] | None) -> list[dict[str, Any]]:
    if not matrix:
        return []
    has_header, header_indices, _blank_columns = _resolve_header_mapping(
        headers,
        matrix[0],
        allow_trailing_missing=True,
    )
    data_rows = matrix[1:] if has_header else matrix
    rows: list[dict[str, Any]] = []
    for values in data_rows:
        if not any(str(cell or "").strip() for cell in values):
            continue
        row = {
            header: values[source_idx] if source_idx < len(values) else ""
            for header, source_idx in zip(headers, header_indices)
        }
        rows.append(row)
    return rows


def extract_rows_with_positions_from_matrix(
    headers: list[str],
    matrix: list[list[Any]] | None,
) -> list[dict[str, Any]]:
    if not matrix:
        return []
    has_header, header_indices, _blank_columns = _resolve_header_mapping(
        headers,
        matrix[0],
        allow_trailing_missing=True,
    )
    start_index = 1 if has_header else 0
    rows: list[dict[str, Any]] = []
    for sheet_row, values in enumerate(matrix[start_index:], start=start_index + 1):
        if not any(str(cell or "").strip() for cell in values):
            continue
        row = {
            header: values[source_idx] if source_idx < len(values) else ""
            for header, source_idx in zip(headers, header_indices)
        }
        rows.append({"sheet_row": sheet_row, "row": row})
    return rows


def detect_board_ownership_layout(
    header_rows: dict[str, list[Any]],
) -> dict[str, Any]:
    """Classify actual Board headers without trusting the repo contract version."""
    tab_reports: dict[str, dict[str, Any]] = {}
    total_required = 0
    total_present = 0
    trailing_order_ok = True
    for tab_name, required_columns in REQUIRED_SPLIT_COLUMNS.items():
        observed_header_list = [
            str(value or "").strip()
            for value in (header_rows.get(tab_name) or [])
            if str(value or "").strip()
        ]
        observed_headers = set(observed_header_list)
        present = [column for column in required_columns if column in observed_headers]
        missing = [column for column in required_columns if column not in observed_headers]
        tab_trailing_order_ok = bool(
            len(present) == len(required_columns)
            and observed_header_list[-len(required_columns) :]
            == list(required_columns)
        )
        if present and not tab_trailing_order_ok:
            trailing_order_ok = False
        total_required += len(required_columns)
        total_present += len(present)
        tab_reports[tab_name] = {
            "required_appended_columns": list(required_columns),
            "present_appended_columns": present,
            "missing_appended_columns": missing,
            "trailing_order_ok": tab_trailing_order_ok,
        }
    if total_present == 0:
        mode = OWNERSHIP_MODE_LEGACY_V3
    elif total_present == total_required and trailing_order_ok:
        mode = OWNERSHIP_MODE_SPLIT_V1
    else:
        mode = OWNERSHIP_MODE_PARTIAL
    return {
        "ok": mode != OWNERSHIP_MODE_PARTIAL,
        "ownership_mode": mode,
        "required_appended_column_count": total_required,
        "present_appended_column_count": total_present,
        "tabs": tab_reports,
        "error": (
            "PARTIAL_BOARD_OWNERSHIP_LAYOUT"
            if mode == OWNERSHIP_MODE_PARTIAL
            else ""
        ),
    }


def resolve_effective_board_state(
    *,
    salesraw_rows: list[dict[str, Any]],
    run_control_row: dict[str, Any] | None,
    target_date: str,
) -> dict[str, Any]:
    """Pure employee-first resolution for split Board size and READY state."""
    resolution_events: list[dict[str, Any]] = []
    effective_rows: list[dict[str, Any]] = []
    for raw_row in salesraw_rows:
        row = dict(raw_row)
        employee_size = str(row.get("MY_SIZE") or "").strip()
        auto_size = str(row.get("AUTO_SIZE_SUGGESTION") or "").strip()
        if employee_size:
            effective_size = employee_size
            size_source = "EMPLOYEE_MY_SIZE"
            if auto_size:
                resolution_events.append(
                    {
                        "code": "AUTO_SIZE_DISCARDED_EMPLOYEE_VALUE",
                        "_db_row_id": str(row.get("_db_row_id") or "").strip(),
                        "OrderID": str(row.get("OrderID") or "").strip(),
                    }
                )
        elif auto_size:
            effective_size = auto_size
            size_source = "AUTO_SIZE_SUGGESTION"
            resolution_events.append(
                {
                    "code": "AUTO_SIZE_SELECTED_EMPLOYEE_BLANK",
                    "_db_row_id": str(row.get("_db_row_id") or "").strip(),
                    "OrderID": str(row.get("OrderID") or "").strip(),
                }
            )
        else:
            effective_size = ""
            size_source = ""
        row["raw_my_size"] = employee_size
        row["raw_auto_size_suggestion"] = auto_size
        row["effective_size"] = effective_size
        row["effective_size_source"] = size_source
        # Existing readiness/writeback consumers intentionally receive a copy
        # whose MY_SIZE is the resolved effective value.
        row["MY_SIZE"] = effective_size
        effective_rows.append(row)

    raw_control = dict(run_control_row or {})
    employee_ready = str(raw_control.get("ready_for_closeout") or "").strip().upper()
    employee_ready_at = str(raw_control.get("ready_set_at") or "").strip()
    observed_at = str(raw_control.get("employee_ready_observed_at") or "").strip()
    auto_ready = str(raw_control.get("auto_ready_for_closeout") or "").strip().upper()
    auto_ready_at = str(raw_control.get("auto_ready_set_at") or "").strip()
    invalid_employee_value = ""
    ready_source = ""
    ready_set_at = ""
    if employee_ready == "HOLD":
        effective_ready = "HOLD"
        if auto_ready == "READY":
            resolution_events.append(
                {"code": "AUTO_READY_DISCARDED_EMPLOYEE_HOLD", "target_date": target_date}
            )
    elif employee_ready == "READY":
        effective_ready = "READY"
        ready_source = "EMPLOYEE"
        ready_set_at = employee_ready_at or observed_at
        if auto_ready == "READY":
            resolution_events.append(
                {"code": "AUTO_READY_DISCARDED_EMPLOYEE_READY", "target_date": target_date}
            )
        if not ready_set_at:
            resolution_events.append(
                {"code": "EMPLOYEE_READY_IDENTITY_PENDING_OBSERVATION", "target_date": target_date}
            )
    elif employee_ready:
        effective_ready = "INVALID"
        invalid_employee_value = employee_ready
        resolution_events.append(
            {
                "code": "INVALID_EMPLOYEE_READY_VALUE",
                "target_date": target_date,
                "value": employee_ready,
            }
        )
    elif auto_ready == "READY" and auto_ready_at:
        effective_ready = "READY"
        ready_source = "AUTO"
        ready_set_at = auto_ready_at
    else:
        effective_ready = "HOLD"

    effective_control = dict(raw_control)
    effective_control["raw_ready_for_closeout"] = str(
        raw_control.get("ready_for_closeout") or ""
    ).strip()
    effective_control["raw_ready_set_at"] = employee_ready_at
    effective_control["raw_employee_ready_observed_at"] = observed_at
    effective_control["raw_auto_ready_for_closeout"] = str(
        raw_control.get("auto_ready_for_closeout") or ""
    ).strip()
    effective_control["raw_auto_ready_set_at"] = auto_ready_at
    effective_control["ready_for_closeout"] = effective_ready
    effective_control["ready_source"] = ready_source
    effective_control["ready_set_at"] = ready_set_at
    if ready_source == "AUTO":
        effective_control["ready_set_by"] = str(
            raw_control.get("auto_ready_set_by") or ""
        ).strip()
    request_identity = {
        "target_date": str(target_date or "").strip(),
        "ready_source": ready_source,
        "ready_set_at": ready_set_at,
    }
    return {
        "raw_salesraw_rows": [dict(row) for row in salesraw_rows],
        "effective_salesraw_rows": effective_rows,
        "raw_run_control_row": raw_control,
        "effective_run_control_row": effective_control,
        "ready_for_closeout": effective_ready,
        "ready_source": ready_source,
        "ready_set_at": ready_set_at,
        "request_identity": request_identity,
        "request_identity_ok": bool(
            effective_ready == "READY" and ready_source and ready_set_at
        ),
        "invalid_employee_ready_value": invalid_employee_value,
        "resolution_events": resolution_events,
    }


def plan_sparse_cell_updates(
    *,
    tab_contract: TabContract,
    sheet_row: int,
    existing_row: dict[str, Any],
    desired_row: dict[str, Any],
    allowed_columns: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Plan changed-cell writes and reject any column outside the owner set."""
    allowed = set(allowed_columns or tab_contract.publisher_owned_column_set)
    unknown = allowed - set(tab_contract.headers)
    if unknown:
        raise ValueError(
            f"{tab_contract.name} sparse update has unknown columns: {sorted(unknown)}"
        )
    updates: list[dict[str, Any]] = []
    for column in tab_contract.headers:
        if column not in allowed:
            continue
        before = existing_row.get(column, "")
        after = desired_row.get(column, "")
        if before == after:
            continue
        column_number = tab_contract.headers.index(column) + 1
        updates.append(
            {
                "range": (
                    f"{tab_contract.name}!{_column_letter(column_number)}{int(sheet_row)}"
                ),
                "value": after,
                "field": column,
            }
        )
    return updates


def validate_ownership_contract(contract: OpsBoardContract) -> list[str]:
    errors: list[str] = []
    if contract.version != 4:
        errors.append(f"board contract version must be 4, got {contract.version}")
    if contract.board_ownership_mode != OWNERSHIP_MODE_SPLIT_V1:
        errors.append("board_ownership_mode must be split_v1")
    if contract.effective_resolution != "employee_first_at_closeout_read":
        errors.append("effective_resolution must be employee_first_at_closeout_read")
    for tab_name, appended in REQUIRED_SPLIT_COLUMNS.items():
        tab = contract.tabs.get(tab_name)
        if tab is None:
            errors.append(f"missing ownership tab: {tab_name}")
            continue
        if tuple(tab.headers[-len(appended) :]) != tuple(appended):
            errors.append(f"{tab_name} appended ownership columns are not exact trailing headers")
        employee = tab.ownership_column_set("employee_owned_columns")
        watcher = tab.ownership_column_set("watcher_owned_columns")
        automation = tab.ownership_column_set("automation_status_columns")
        preserved = tab.publisher_preserved_column_set
        publisher = tab.publisher_owned_column_set
        if employee & watcher or employee & automation or watcher & automation:
            errors.append(f"{tab_name} ownership sets overlap")
        if preserved != employee | watcher | automation:
            errors.append(f"{tab_name} publisher-preserved set does not match nonpublisher owners")
        if publisher & preserved or publisher | preserved != set(tab.headers):
            errors.append(f"{tab_name} publisher ownership does not partition headers")
    run_defaults = contract.tabs.get("Run_Control")
    if run_defaults and str(run_defaults.new_row_defaults.get("ready_for_closeout") or ""):
        errors.append("Run_Control v4 ready_for_closeout default must be blank")
    return errors


def merge_rows_preserving_editables(
    tab_contract: TabContract,
    fresh_rows: list[dict[str, Any]],
    existing_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    existing_by_key = {
        _clean_key(row.get(tab_contract.key_column)): row
        for row in existing_rows
        if _clean_key(row.get(tab_contract.key_column))
    }
    merged: list[dict[str, Any]] = []
    for fresh in fresh_rows:
        key = _clean_key(fresh.get(tab_contract.key_column))
        out = dict(fresh)
        existing = existing_by_key.get(key)
        if existing:
            for column in tab_contract.publisher_preserved_column_set:
                # Preserve explicit blanks too: the publisher does not own the
                # cell and may not synthesize a replacement value.
                out[column] = existing.get(column, "")
        merged.append(out)
    return merged


def validate_contract_layout(
    contract: OpsBoardContract,
    sheet_names: list[str],
    header_rows: dict[str, list[Any]],
) -> dict[str, Any]:
    required_tabs = list(contract.tabs)
    missing_tabs = [name for name in required_tabs if name not in sheet_names]
    extra_tabs = [name for name in sheet_names if name not in required_tabs]
    tab_reports: dict[str, dict[str, Any]] = {}
    ok = not missing_tabs
    for tab_name, tab_contract in contract.tabs.items():
        observed = [str(cell or "").strip() for cell in header_rows.get(tab_name, [])]
        expected = tab_contract.headers
        header_ok, _header_indices, blank_columns = _resolve_header_mapping(expected, observed)
        tab_reports[tab_name] = {
            "header_ok": header_ok,
            "expected_headers": expected,
            "observed_headers": observed,
            "ignored_blank_header_columns": blank_columns,
        }
        ok = ok and header_ok
    ownership_layout = detect_board_ownership_layout(header_rows)
    return {
        "ok": ok,
        "missing_tabs": missing_tabs,
        "extra_tabs": extra_tabs,
        "tabs": tab_reports,
        "ownership_layout": ownership_layout,
        "ownership_mode": ownership_layout["ownership_mode"],
    }


class GoogleOpsBoardClient:
    def __init__(self, spreadsheet_id: str, session) -> None:
        self.spreadsheet_id = spreadsheet_id
        self.session = session
        self._tab_value_extents: dict[str, tuple[int, int]] = {}
        self._tab_grid_extents: dict[str, tuple[int, int]] = {}
        self._sheet_id_by_title: dict[str, int] = {}

    @classmethod
    def from_service_account_file(cls, spreadsheet_id: str, service_account_json: Path) -> "GoogleOpsBoardClient":
        return cls(spreadsheet_id=spreadsheet_id, session=build_authorized_session(service_account_json))

    def _request(self, method: str, url: str, **kwargs):
        response = self.session.request(method, url, timeout=30, **kwargs)
        if response.status_code >= 400:
            detail = response.text[:1000]
            raise RuntimeError(f"Google Sheets API {method} failed: {response.status_code} {detail}")
        return response

    def get_metadata(self) -> dict[str, Any]:
        url = (
            f"https://sheets.googleapis.com/v4/spreadsheets/{self.spreadsheet_id}"
            "?fields=sheets(properties(sheetId,title,index,gridProperties(rowCount,columnCount)))"
        )
        metadata = self._request("GET", url).json()
        for sheet in metadata.get("sheets", []):
            properties = sheet.get("properties") or {}
            title = str(properties.get("title") or "")
            if not title:
                continue
            if properties.get("sheetId") is not None:
                self._sheet_id_by_title[title] = int(properties["sheetId"])
            grid = properties.get("gridProperties") or {}
            self._tab_grid_extents[title] = (
                int(grid.get("rowCount") or 0),
                int(grid.get("columnCount") or 0),
            )
        return metadata

    def get_ui_metadata(self) -> dict[str, Any]:
        url = (
            f"https://sheets.googleapis.com/v4/spreadsheets/{self.spreadsheet_id}"
            "?fields=sheets(properties(sheetId,title,gridProperties(rowCount,columnCount,frozenRowCount)),"
            "basicFilter,conditionalFormats,protectedRanges(protectedRangeId))"
        )
        return self._request("GET", url).json()

    def get_sheet_names(self) -> list[str]:
        meta = self.get_metadata()
        return [sheet["properties"]["title"] for sheet in meta.get("sheets", [])]

    def get_sheet_id_map(self) -> dict[str, int]:
        self.get_metadata()
        return dict(self._sheet_id_by_title)

    def batch_update(self, requests: list[dict[str, Any]]) -> dict[str, Any]:
        if not requests:
            return {}
        url = f"https://sheets.googleapis.com/v4/spreadsheets/{self.spreadsheet_id}:batchUpdate"
        return self._request("POST", url, json={"requests": requests}).json()

    def ensure_tabs(self, tab_names: list[str]) -> list[str]:
        existing = set(self.get_sheet_names())
        missing = [tab for tab in tab_names if tab not in existing]
        if not missing:
            return []
        self.batch_update([{"addSheet": {"properties": {"title": tab}}} for tab in missing])
        return missing

    def get_header_rows(self, tab_names: list[str]) -> dict[str, list[Any]]:
        if not tab_names:
            return {}
        range_params = "&".join(f"ranges={quote(tab + '!1:1')}" for tab in tab_names)
        url = (
            f"https://sheets.googleapis.com/v4/spreadsheets/{self.spreadsheet_id}/values:batchGet"
            f"?majorDimension=ROWS&{range_params}"
        )
        payload = self._request("GET", url).json()
        headers: dict[str, list[Any]] = {tab: [] for tab in tab_names}
        for value_range in payload.get("valueRanges", []):
            range_name = str(value_range.get("range", "")).split("!")[0].strip("'")
            values = value_range.get("values", [])
            headers[range_name] = values[0] if values else []
        return headers

    def get_tab_values(self, tab_name: str) -> list[list[Any]]:
        encoded_range = quote(f"{tab_name}!A:ZZ")
        url = f"https://sheets.googleapis.com/v4/spreadsheets/{self.spreadsheet_id}/values/{encoded_range}?majorDimension=ROWS"
        payload = self._request("GET", url).json()
        values = payload.get("values", [])
        self._tab_value_extents[tab_name] = (
            len(values),
            max((len(row) for row in values), default=0),
        )
        return values

    def clear_tab(self, tab_name: str) -> None:
        encoded_range = quote(f"{tab_name}!A:ZZ")
        url = f"https://sheets.googleapis.com/v4/spreadsheets/{self.spreadsheet_id}/values/{encoded_range}:clear"
        self._request("POST", url, json={})

    def write_tab_rows(self, tab_name: str, headers: list[str], rows: list[dict[str, Any]]) -> None:
        self.clear_tab(tab_name)
        encoded_range = quote(f"{tab_name}!A1")
        url = (
            f"https://sheets.googleapis.com/v4/spreadsheets/{self.spreadsheet_id}/values/{encoded_range}"
            "?valueInputOption=RAW"
        )
        body = {
            "range": f"{tab_name}!A1",
            "majorDimension": "ROWS",
            "values": rows_to_matrix(headers, rows),
        }
        self._request("PUT", url, json=body)

    def overwrite_tab_rows(self, tab_name: str, rows: list[list[Any]]) -> None:
        """Replace tab values atomically while retaining formatting and validation.

        UpdateCells clears userEnteredValue for every uncovered cell inside the
        explicit union range. This avoids values.update's null-skip behavior and
        does not depend on trailing empty rows/cells surviving a values read.
        """
        previous_extent = self._tab_value_extents.get(tab_name)
        if previous_extent is None:
            self.get_tab_values(tab_name)
            previous_extent = self._tab_value_extents[tab_name]

        new_row_count = len(rows)
        new_column_count = max((len(row) for row in rows), default=0)
        grid_extent = self._tab_grid_extents.get(tab_name, (0, 0))
        union_row_count = max(previous_extent[0], grid_extent[0], new_row_count, 1)
        union_column_count = max(previous_extent[1], grid_extent[1], new_column_count, 1)

        sheet_id = self._sheet_id_by_title.get(tab_name)
        if sheet_id is None:
            sheet_id = self.get_sheet_id_map().get(tab_name)
        if sheet_id is None:
            raise RuntimeError(f"Google Sheets metadata is missing tab: {tab_name}")

        def user_entered_value(value: Any) -> dict[str, Any]:
            if value is None or value == "":
                return {}
            if isinstance(value, bool):
                return {"userEnteredValue": {"boolValue": value}}
            if isinstance(value, (int, float)):
                return {"userEnteredValue": {"numberValue": value}}
            return {"userEnteredValue": {"stringValue": str(value)}}

        update_request = {
            "updateCells": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": union_row_count,
                    "startColumnIndex": 0,
                    "endColumnIndex": union_column_count,
                },
                "rows": [
                    {"values": [user_entered_value(value) for value in row]}
                    for row in rows
                ],
                "fields": "userEnteredValue",
            }
        }
        self.batch_update([update_request])
        self._tab_value_extents[tab_name] = (new_row_count, new_column_count)

    def append_tab_rows(self, tab_name: str, headers: list[str], rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        encoded_range = quote(f"{tab_name}!A1")
        url = (
            f"https://sheets.googleapis.com/v4/spreadsheets/{self.spreadsheet_id}/values/{encoded_range}:append"
            "?valueInputOption=RAW&insertDataOption=INSERT_ROWS"
        )
        body = {
            "range": f"{tab_name}!A1",
            "majorDimension": "ROWS",
            "values": [
                [_sheet_input_value(row.get(header, "")) for header in headers]
                for row in rows
            ],
        }
        self._request("POST", url, json=body)

    def update_tab_rows(self, tab_name: str, headers: list[str], updates: list[dict[str, Any]]) -> None:
        if not updates:
            return
        data = []
        end_col = max(len(headers), 1)
        range_tail = _column_letter(end_col)
        for update in updates:
            sheet_row = int(update["sheet_row"])
            row = update["row"]
            data.append(
                {
                    "range": f"{tab_name}!A{sheet_row}:{range_tail}{sheet_row}",
                    "majorDimension": "ROWS",
                    "values": [
                        [_sheet_input_value(row.get(header, "")) for header in headers]
                    ],
                }
            )
        url = (
            f"https://sheets.googleapis.com/v4/spreadsheets/{self.spreadsheet_id}/values:batchUpdate"
            "?valueInputOption=RAW"
        )
        self._request("POST", url, json={"data": data})

    def update_cells(self, updates: list[dict[str, Any]]) -> None:
        if not updates:
            return
        data = []
        for update in updates:
            data.append(
                {
                    "range": str(update["range"]),
                    "majorDimension": "ROWS",
                    "values": [[_sheet_input_value(update.get("value", ""))]],
                }
            )
        url = (
            f"https://sheets.googleapis.com/v4/spreadsheets/{self.spreadsheet_id}/values:batchUpdate"
            "?valueInputOption=RAW"
        )
        self._request("POST", url, json={"data": data})

    def delete_tab_rows(self, tab_name: str, sheet_rows: list[int]) -> None:
        """Delete existing data rows bottom-up without sending preserved cells."""
        rows = sorted({int(value) for value in sheet_rows if int(value) > 1}, reverse=True)
        if not rows:
            return
        sheet_id = self.get_sheet_id_map().get(tab_name)
        if sheet_id is None:
            raise RuntimeError(f"Google Sheets metadata is missing tab: {tab_name}")
        self.batch_update(
            [
                {
                    "deleteDimension": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "ROWS",
                            "startIndex": sheet_row - 1,
                            "endIndex": sheet_row,
                        }
                    }
                }
                for sheet_row in rows
            ]
        )

    def snapshot_tabs(self, tab_names: list[str]) -> dict[str, list[list[Any]]]:
        return {tab: self.get_tab_values(tab) for tab in tab_names}

    def apply_tab_ui(self, tab_contract: TabContract) -> None:
        if not tab_contract.ui:
            return
        meta = self.get_ui_metadata()
        sheet_meta = None
        for sheet in meta.get("sheets", []):
            props = sheet.get("properties") or {}
            if str(props.get("title")) == tab_contract.name:
                sheet_meta = sheet
                break
        if sheet_meta is None:
            raise RuntimeError(f"Cannot apply UI: missing sheet metadata for {tab_contract.name}")
        props = sheet_meta.get("properties") or {}
        requests = build_tab_ui_requests(
            tab_contract=tab_contract,
            sheet_id=int(props["sheetId"]),
            row_count=int((props.get("gridProperties") or {}).get("rowCount") or 0),
            column_count=int((props.get("gridProperties") or {}).get("columnCount") or 0),
            existing_conditional_rule_count=len(sheet_meta.get("conditionalFormats") or []),
            existing_protected_range_ids=[
                int(pr["protectedRangeId"])
                for pr in (sheet_meta.get("protectedRanges") or [])
                if pr.get("protectedRangeId") is not None
            ],
        )
        self.batch_update(requests)

    def apply_contract_ui(self, contract: OpsBoardContract) -> list[str]:
        applied: list[str] = []
        meta = self.get_metadata()
        reorder_requests = build_tab_reorder_requests(meta.get("sheets", []), list(contract.tabs))
        if reorder_requests:
            self.batch_update(reorder_requests)
        for tab_contract in contract.tabs.values():
            if not tab_contract.ui:
                continue
            self.apply_tab_ui(tab_contract)
            applied.append(tab_contract.name)
        return applied


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
