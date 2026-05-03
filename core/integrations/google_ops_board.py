from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
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


@dataclass(frozen=True)
class TabContract:
    name: str
    headers: list[str]
    key_column: str
    editable_columns: list[str]
    ui: dict[str, Any]

    @property
    def editable_column_set(self) -> set[str]:
        return set(self.editable_columns)


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
    writeback: dict[str, dict[str, str]]
    same_day_cutoff_default: str = "16:00"
    same_day_cutoff_by_store: dict[str, str] = field(default_factory=dict)


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
        same_day_cutoff_default=str(data.get("same_day_cutoff_default") or "16:00"),
        same_day_cutoff_by_store={
            str(k): str(v) for k, v in (data.get("same_day_cutoff_by_store") or {}).items()
        },
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
        matrix.append([row.get(header, "") for header in headers])
    return matrix


def _resolve_header_mapping(
    expected_headers: list[str],
    observed_row: list[Any],
) -> tuple[bool, list[int], list[int]]:
    observed = [str(cell or "").strip() for cell in observed_row]
    if observed[: len(expected_headers)] == expected_headers:
        return True, list(range(len(expected_headers))), []

    nonblank_headers = [(idx, value) for idx, value in enumerate(observed) if value]
    if [value for _, value in nonblank_headers] == expected_headers:
        blank_columns = [idx + 1 for idx, value in enumerate(observed) if not value]
        return True, [idx for idx, _ in nonblank_headers], blank_columns

    return False, list(range(len(expected_headers))), []


def extract_rows_from_matrix(headers: list[str], matrix: list[list[Any]] | None) -> list[dict[str, Any]]:
    if not matrix:
        return []
    has_header, header_indices, _blank_columns = _resolve_header_mapping(headers, matrix[0])
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
    has_header, header_indices, _blank_columns = _resolve_header_mapping(headers, matrix[0])
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
            for column in tab_contract.editable_columns:
                existing_value = existing.get(column)
                if str(existing_value or "").strip():
                    out[column] = existing_value
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
    return {
        "ok": ok,
        "missing_tabs": missing_tabs,
        "extra_tabs": extra_tabs,
        "tabs": tab_reports,
    }


class GoogleOpsBoardClient:
    def __init__(self, spreadsheet_id: str, session) -> None:
        self.spreadsheet_id = spreadsheet_id
        self.session = session

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
        return self._request("GET", url).json()

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
        meta = self.get_metadata()
        return {
            str(sheet["properties"]["title"]): int(sheet["properties"]["sheetId"])
            for sheet in meta.get("sheets", [])
        }

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
        return payload.get("values", [])

    def clear_tab(self, tab_name: str) -> None:
        encoded_range = quote(f"{tab_name}!A:ZZ")
        url = f"https://sheets.googleapis.com/v4/spreadsheets/{self.spreadsheet_id}/values/{encoded_range}:clear"
        self._request("POST", url, json={})

    def write_tab_rows(self, tab_name: str, headers: list[str], rows: list[dict[str, Any]]) -> None:
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
            "values": [[row.get(header, "") for header in headers] for row in rows],
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
                    "values": [[row.get(header, "") for header in headers]],
                }
            )
        url = (
            f"https://sheets.googleapis.com/v4/spreadsheets/{self.spreadsheet_id}/values:batchUpdate"
            "?valueInputOption=RAW"
        )
        self._request("POST", url, json={"data": data})

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
