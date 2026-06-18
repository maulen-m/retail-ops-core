from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TELEGRAM_TIMEOUT_SECONDS = 60


def _redact_token(text: str, token: str) -> str:
    if not token:
        return text
    return text.replace(token, "<redacted-token>").replace(f"bot{token}", "bot<redacted-token>")


def _retry_after_seconds(payload: dict[str, Any]) -> int | None:
    parameters = payload.get("parameters") if isinstance(payload, dict) else {}
    if isinstance(parameters, dict) and parameters.get("retry_after") is not None:
        try:
            return max(0, int(parameters["retry_after"]))
        except (TypeError, ValueError):
            return None
    description = str(payload.get("description") or "")
    match = re.search(r"retry after\s+(\d+)", description, flags=re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def _dotenv_values(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def get_waybill_telegram_config(
    *,
    token: str | None = None,
    chat_id: str | None = None,
) -> dict[str, str]:
    dotenv = _dotenv_values(PROJECT_ROOT / ".env")
    resolved_token = str(
        token
        or os.environ.get("TELEGRAM_BOT_TOKEN_WAYBILL")
        or dotenv.get("TELEGRAM_BOT_TOKEN_WAYBILL")
        or os.environ.get("TELEGRAM_BOT_TOKEN")
        or dotenv.get("TELEGRAM_BOT_TOKEN")
        or ""
    ).strip()
    resolved_chat_id = str(
        chat_id or os.environ.get("TELEGRAM_WAYBILL_CHAT_ID") or dotenv.get("TELEGRAM_WAYBILL_CHAT_ID") or ""
    ).strip()
    if not resolved_token:
        raise ValueError("TELEGRAM_BOT_TOKEN_WAYBILL or TELEGRAM_BOT_TOKEN environment variable not set")
    if not resolved_chat_id:
        raise ValueError("TELEGRAM_WAYBILL_CHAT_ID environment variable not set")
    return {"token": resolved_token, "chat_id": resolved_chat_id}


def send_message(
    *,
    token: str,
    chat_id: str,
    text: str,
    parse_mode: str = "HTML",
    timeout_seconds: int = 15,
    reply_markup: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    try:
        response = requests.post(url, json=payload, timeout=timeout_seconds)
        try:
            data = response.json()
        except ValueError:
            data = {"ok": False, "description": response.text}
        if response.ok and data.get("ok"):
            result = data.get("result") or {}
            return {
                "success": True,
                "message_id": str(result.get("message_id") or ""),
                "chat_id": str((result.get("chat") or {}).get("id") or chat_id),
                "date": result.get("date"),
            }
        return {
            "success": False,
            "error": str(data.get("description") or response.text or response.status_code),
            "status_code": response.status_code,
            "retry_after": _retry_after_seconds(data),
            "ambiguous": False,
        }
    except requests.Timeout as exc:
        return {"success": False, "error": _redact_token(str(exc), token), "ambiguous": True}
    except requests.RequestException as exc:
        return {"success": False, "error": _redact_token(str(exc), token), "ambiguous": True}


def send_document(
    *,
    token: str,
    chat_id: str,
    document_path: Path,
    caption: str = "",
    timeout_seconds: int = DEFAULT_TELEGRAM_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    path = Path(document_path)
    url = f"https://api.telegram.org/bot{token}/sendDocument"
    data = {"chat_id": chat_id}
    if caption:
        data["caption"] = caption
        data["parse_mode"] = "HTML"
    try:
        with path.open("rb") as handle:
            response = requests.post(
                url,
                data=data,
                files={"document": (path.name, handle, "application/pdf")},
                timeout=timeout_seconds,
            )
        try:
            payload = response.json()
        except ValueError:
            payload = {"ok": False, "description": response.text}
        if response.ok and payload.get("ok"):
            result = payload.get("result") or {}
            document = result.get("document") or {}
            return {
                "success": True,
                "message_id": str(result.get("message_id") or ""),
                "chat_id": str((result.get("chat") or {}).get("id") or chat_id),
                "date": result.get("date"),
                "file_id": str(document.get("file_id") or ""),
                "file_unique_id": str(document.get("file_unique_id") or ""),
                "file_name": str(document.get("file_name") or path.name),
                "file_size": document.get("file_size"),
            }
        return {
            "success": False,
            "error": str(payload.get("description") or response.text or response.status_code),
            "status_code": response.status_code,
            "retry_after": _retry_after_seconds(payload),
            "ambiguous": False,
        }
    except requests.Timeout as exc:
        return {"success": False, "error": _redact_token(str(exc), token), "ambiguous": True}
    except requests.RequestException as exc:
        return {"success": False, "error": _redact_token(str(exc), token), "ambiguous": True}
