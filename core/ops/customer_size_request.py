"""No-send planning helpers for Kaspi customer size requests.

This module intentionally has no customer-message send capability. It builds
redacted request plans and synthetic reply size decisions so the workflow can be
validated before any live Kaspi chat lane is approved.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable, Mapping

from core.calc.size_probability import calc_size_from_params
from core.integrations.kaspi_order_stage import StageCode
from core.utils.sku_normalize import normalize_size


DEFAULT_REQUEST_TEMPLATE = (
    "Добрый день, пожалуйста подскажите примерный Рост и Вес, "
    "подберем точный размер😊"
)

ACTIVE_INTERNAL_STATUSES = {"NEW", "ACCEPTED", "READY"}
TERMINAL_INTERNAL_STATUSES = {
    "SHIPPED",
    "ON_DELIVERY",
    "DELIVERED",
    "COMPLETED",
    "ISSUED",
    "CANCELLED",
    "RETURNING",
    "RETURNED",
}
TERMINAL_KASPI_STATUS_TOKENS = {
    "COMPLETED",
    "CANCELLED",
    "CANCELLING",
    "RETURNED",
    "RETURNING",
    "ARCHIVE",
}
REQUEST_CHANNEL = "KASPI_MERCHANT_CHAT_UI"
KASPI_MERCHANT_ORDERS_BASE_URL = "https://kaspi.kz/mc/#/orders-new"
LEDGER_STATUS_RANK = {
    "SIZE_CONFIRMED": 10,
    "CLASSIFICATION_READY": 20,
    "REPLY_OBSERVED": 30,
    "REPLY_OBSERVED_NO_SIZE_SIGNAL": 35,
    "REQUEST_SENT": 40,
    "UNKNOWN_SEND_OUTCOME": 42,
    "SEND_IN_PROGRESS": 43,
    "POLLING": 45,
    "SEND_PLANNED_NO_SEND": 50,
}


@dataclass(frozen=True)
class ReplyFacts:
    """PII-safe facts parsed from a customer reply."""

    reply_hash: str
    height_cm: int | None
    weight_kg: int | None
    explicit_size: str | None
    parse_confidence: str


@dataclass(frozen=True)
class SizeDecision:
    """Dry-run size decision derived from reply facts."""

    size: str | None
    source: str
    confidence: str
    height_cm: int | None = None
    weight_kg: int | None = None
    explicit_size: str | None = None


@dataclass(frozen=True)
class OrderCandidate:
    """Internal candidate row. Do not serialize raw_order_id."""

    db_row_id: int | None
    raw_order_id: str
    order_ref: str
    store_code: str | None
    sku_key: str | None
    sku_id: str | None
    product_type: str
    internal_status: str | None
    kaspi_status: str | None
    planned_shipment_date: str | None
    created_at: str | None
    reason_codes: tuple[str, ...]

    def ledger_key(self, template_hash_value: str) -> str:
        return private_hash(
            "kaspi_size_request_ledger",
            "|".join(
                [
                    self.store_code or "",
                    self.raw_order_id,
                    self.sku_id or "",
                    template_hash_value,
                ]
            ),
        )

    def to_redacted_dict(self) -> dict[str, Any]:
        return {
            "db_row_id": self.db_row_id,
            "order_ref": self.order_ref,
            "store_code": self.store_code,
            "sku_key": self.sku_key,
            "sku_id": self.sku_id,
            "product_type": self.product_type,
            "internal_status": self.internal_status,
            "kaspi_status": self.kaspi_status,
            "planned_shipment_date": self.planned_shipment_date,
            "created_at": self.created_at,
            "reason_codes": list(self.reason_codes),
        }


def private_hash(namespace: str, value: Any, length: int = 24) -> str:
    """Return a stable redacted reference for evidence files."""
    raw = f"{namespace}:{'' if value is None else value}".encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()[:length]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_request_template(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip())


def request_template_hash(text: str) -> str:
    normalized = normalize_request_template(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _parse_int(value: str) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _find_explicit_size(text: str, product_type: str = "CL") -> str | None:
    candidates = re.findall(
        r"(?<![A-ZА-Я0-9])(?:XS|S|M|L|XL|XXL|XXXL|XXXXL|2XL|3XL|4XL|5XL|"
        r"ХС|С|М|Л|ХЛ|ХХЛ|ХХХЛ|2ХЛ|3ХЛ|4ХЛ|5ХЛ)(?![A-ZА-Я0-9])",
        text.upper(),
        flags=re.IGNORECASE,
    )
    for token in candidates:
        normalized = normalize_size(token, product_type=product_type)
        if normalized:
            return normalized
    return None


def parse_size_reply(reply_text: str, product_type: str = "CL") -> ReplyFacts:
    """
    Extract height, weight, and explicit size from a reply without storing text.

    The returned object contains only a hash plus structured facts.
    """
    text = str(reply_text or "")
    compact = re.sub(r"\s+", " ", text.replace("\u00a0", " ")).strip()
    lower = compact.lower()

    height_cm = None
    weight_kg = None

    height_match = re.search(r"(?:рост|height|h)\D{0,12}(\d{2,3})", lower)
    if height_match:
        candidate = _parse_int(height_match.group(1))
        if candidate and 120 <= candidate <= 230:
            height_cm = candidate

    weight_match = re.search(r"(?:вес|weight|w)\D{0,12}(\d{2,3})", lower)
    if weight_match:
        candidate = _parse_int(weight_match.group(1))
        if candidate and 30 <= candidate <= 180:
            weight_kg = candidate

    if height_cm is None:
        cm_match = re.search(r"(\d{2,3})\s*(?:см|cm)\b", lower)
        if cm_match:
            candidate = _parse_int(cm_match.group(1))
            if candidate and 120 <= candidate <= 230:
                height_cm = candidate

    if weight_kg is None:
        kg_match = re.search(r"(\d{2,3})\s*(?:кг|kg)\b", lower)
        if kg_match:
            candidate = _parse_int(kg_match.group(1))
            if candidate and 30 <= candidate <= 180:
                weight_kg = candidate

    if height_cm is None or weight_kg is None:
        numbers = [_parse_int(value) for value in re.findall(r"\d{2,3}", lower)]
        plausible = [value for value in numbers if value is not None]
        if len(plausible) >= 2:
            first, second = plausible[0], plausible[1]
            if height_cm is None and 120 <= first <= 230:
                height_cm = first
            if weight_kg is None and 30 <= second <= 180:
                weight_kg = second

    explicit_size = _find_explicit_size(compact, product_type=product_type)
    if height_cm and weight_kg:
        confidence = "HIGH"
    elif explicit_size:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    return ReplyFacts(
        reply_hash=private_hash("kaspi_size_reply_text", compact),
        height_cm=height_cm,
        weight_kg=weight_kg,
        explicit_size=explicit_size,
        parse_confidence=confidence,
    )


def decide_size_from_reply(facts: ReplyFacts, product_type: str = "CL") -> SizeDecision:
    if facts.height_cm and facts.weight_kg:
        size = calc_size_from_params(facts.height_cm, facts.weight_kg, product_type=product_type)
        return SizeDecision(
            size=size,
            source="CUSTOMER_HEIGHT_WEIGHT",
            confidence="HIGH" if size else "LOW",
            height_cm=facts.height_cm,
            weight_kg=facts.weight_kg,
            explicit_size=facts.explicit_size,
        )
    if facts.explicit_size:
        return SizeDecision(
            size=facts.explicit_size,
            source="CUSTOMER_EXPLICIT_SIZE",
            confidence="MEDIUM",
            explicit_size=facts.explicit_size,
        )
    return SizeDecision(
        size=None,
        source="NO_SIZE_SIGNAL",
        confidence="LOW",
        height_cm=facts.height_cm,
        weight_kg=facts.weight_kg,
        explicit_size=facts.explicit_size,
    )


def _has_text(value: Any) -> bool:
    return str(value or "").strip() != ""


def _normalize_status(value: Any) -> str:
    return str(value or "").strip().upper()


def _coerce_date(value: Any) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text[: len(fmt)], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _product_type_from_row(row: Mapping[str, Any]) -> str:
    for key in ("product_type", "sku_key", "sku_id"):
        value = row.get(key)
        if value:
            prefix = str(value).split("_", 1)[0].upper()
            if prefix:
                return prefix
    return "CL"


def _row_matches_window(row: Mapping[str, Any], target_date: date, lookback_days: int) -> bool:
    start = target_date - timedelta(days=max(0, lookback_days))
    for key in ("planned_shipment_date", "created_at", "updated_at", "status_updated_at"):
        parsed = _coerce_date(row.get(key))
        if parsed and start <= parsed <= target_date:
            return True
    return False


def is_missing_size_candidate(
    row: Mapping[str, Any],
    *,
    target_date: date,
    lookback_days: int = 3,
    active_statuses: Iterable[str] = ACTIVE_INTERNAL_STATUSES,
) -> tuple[bool, tuple[str, ...]]:
    reasons: list[str] = []
    if _has_text(row.get("assigned_size")) or _has_text(row.get("my_size")):
        return False, ("size_already_present",)
    reasons.append("missing_size")

    internal_status = _normalize_status(row.get("internal_status"))
    kaspi_status = _normalize_status(row.get("kaspi_status"))
    if internal_status in TERMINAL_INTERNAL_STATUSES:
        return False, ("terminal_internal_status",)
    if kaspi_status in TERMINAL_KASPI_STATUS_TOKENS:
        return False, ("terminal_kaspi_status",)
    if internal_status and internal_status not in {s.upper() for s in active_statuses}:
        return False, ("non_active_internal_status",)
    reasons.append("active_not_terminal")

    if not _row_matches_window(row, target_date, lookback_days):
        return False, ("outside_target_window",)
    reasons.append("target_window")

    if _has_text(row.get("customer_height_cm")) and _has_text(row.get("customer_weight_kg")):
        return False, ("customer_params_already_present",)

    return True, tuple(reasons)


def _select_columns(conn: sqlite3.Connection) -> list[str]:
    available = {row["name"] for row in conn.execute("PRAGMA table_info(fact_orders_kaspi)").fetchall()}
    desired = [
        "id",
        "order_id",
        "store_code",
        "sku_key",
        "sku_id",
        "product_type",
        "my_size",
        "assigned_size",
        "customer_height_cm",
        "customer_weight_kg",
        "internal_status",
        "kaspi_status",
        "planned_shipment_date",
        "created_at",
        "updated_at",
        "status_updated_at",
    ]
    return [column for column in desired if column in available]


def load_missing_size_candidates(
    db_path: Path,
    *,
    target_date: date,
    lookback_days: int = 3,
    stores: Iterable[str] | None = None,
    limit: int | None = None,
) -> list[OrderCandidate]:
    """
    Load active missing-size candidates from SQLite using read-only mode.
    """
    db_path = Path(db_path)
    store_filter = {str(store).strip() for store in stores or [] if str(store).strip()}
    uri = f"file:{db_path}?mode=ro"
    candidates: list[OrderCandidate] = []

    with sqlite3.connect(uri, uri=True) as conn:
        conn.row_factory = sqlite3.Row
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='fact_orders_kaspi'"
        ).fetchone()
        if not table:
            return []
        columns = _select_columns(conn)
        if "order_id" not in columns:
            return []
        rows = conn.execute(
            f"SELECT {', '.join(columns)} FROM fact_orders_kaspi ORDER BY id DESC"
        ).fetchall()

    for raw in rows:
        row = dict(raw)
        store_code = row.get("store_code")
        if store_filter and str(store_code or "").strip() not in store_filter:
            continue
        matches, reasons = is_missing_size_candidate(
            row,
            target_date=target_date,
            lookback_days=lookback_days,
        )
        if not matches:
            continue
        order_id = str(row.get("order_id") or "").strip()
        if not order_id:
            continue
        candidates.append(
            OrderCandidate(
                db_row_id=row.get("id"),
                raw_order_id=order_id,
                order_ref=private_hash("kaspi_order_id", order_id),
                store_code=store_code,
                sku_key=row.get("sku_key"),
                sku_id=row.get("sku_id"),
                product_type=_product_type_from_row(row),
                internal_status=row.get("internal_status"),
                kaspi_status=row.get("kaspi_status"),
                planned_shipment_date=row.get("planned_shipment_date"),
                created_at=row.get("created_at"),
                reason_codes=reasons,
            )
        )
        if limit and len(candidates) >= limit:
            break
    return candidates


def build_request_ledger_plan(
    candidates: Iterable[OrderCandidate],
    *,
    template: str = DEFAULT_REQUEST_TEMPLATE,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    now = now or datetime.now()
    template_hash_value = request_template_hash(template)
    rows = []
    for candidate in candidates:
        rows.append(
            {
                "ledger_key": candidate.ledger_key(template_hash_value),
                "db_row_id": candidate.db_row_id,
                "order_ref": candidate.order_ref,
                "store_code": candidate.store_code,
                "sku_key": candidate.sku_key,
                "sku_id": candidate.sku_id,
                "channel": REQUEST_CHANNEL,
                "template_hash": template_hash_value,
                "status": "SEND_PLANNED_NO_SEND",
                "created_at": now.isoformat(timespec="seconds"),
                "send_allowed": False,
                "reason": "no_send_canary_planning_only",
            }
        )
    return rows


def suggest_merchant_status_filter(candidate: OrderCandidate | Mapping[str, Any]) -> str:
    """
    Return the likely Kaspi merchant order-list status filter for a candidate.

    This is a UI-navigation hint, not inventory/order truth. The merchant account
    must still match `store_code`; searching an STOREB order inside an ACMEWEAR
    merchant tab is expected to return no result.
    """
    if isinstance(candidate, OrderCandidate):
        internal_status = _normalize_status(candidate.internal_status)
        kaspi_status = _normalize_status(candidate.kaspi_status)
    else:
        internal_status = _normalize_status(candidate.get("internal_status"))
        kaspi_status = _normalize_status(candidate.get("kaspi_status"))

    if internal_status == "ACCEPTED" and kaspi_status == "KASPI_DELIVERY":
        return "KASPI_DELIVERY_CARGO_ASSEMBLY"
    if internal_status == "READY" or kaspi_status == "KASPI_DELIVERY":
        return "KASPI_DELIVERY_WAIT_FOR_COURIER"
    if internal_status == "NEW" or kaspi_status in {"APPROVED_BY_BANK", "NEW"}:
        return "NEW"
    if kaspi_status:
        return kaspi_status
    if internal_status:
        return internal_status
    return "UNKNOWN"


def build_live_ui_canary_targets(
    candidates: Iterable[OrderCandidate],
) -> list[dict[str, Any]]:
    """Build redacted one-row-per-candidate live UI canary target hints."""
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        status_filter = suggest_merchant_status_filter(candidate)
        rows.append(
            {
                "order_ref": candidate.order_ref,
                "db_row_id": candidate.db_row_id,
                "store_code": candidate.store_code,
                "sku_key": candidate.sku_key,
                "sku_id": candidate.sku_id,
                "internal_status": candidate.internal_status,
                "kaspi_status": candidate.kaspi_status,
                "suggested_merchant_status_filter": status_filter,
                "suggested_merchant_orders_url": (
                    f"{KASPI_MERCHANT_ORDERS_BASE_URL}?status={status_filter}"
                    if status_filter != "UNKNOWN"
                    else KASPI_MERCHANT_ORDERS_BASE_URL
                ),
                "raw_order_id_exported": False,
                "requires_matching_merchant_account": True,
                "allowed_probe_action": "search_order_and_observe_chat_button_no_send",
            }
        )
    return rows


def summarize_live_ui_targets_by_store(targets: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    for target in targets:
        key = (
            str(target.get("store_code") or ""),
            str(target.get("suggested_merchant_status_filter") or ""),
        )
        bucket = buckets.setdefault(
            key,
            {
                "store_code": key[0],
                "suggested_merchant_status_filter": key[1],
                "candidate_count": 0,
                "sample_order_ref": "",
                "suggested_merchant_orders_url": target.get("suggested_merchant_orders_url"),
            },
        )
        bucket["candidate_count"] += 1
        if not bucket["sample_order_ref"]:
            bucket["sample_order_ref"] = target.get("order_ref") or ""
    return sorted(
        buckets.values(),
        key=lambda row: (str(row["store_code"]), str(row["suggested_merchant_status_filter"])),
    )


def build_google_board_update_plan(
    reply_rows: Iterable[Mapping[str, Any]],
    *,
    product_type_default: str = "CL",
) -> list[dict[str, Any]]:
    """
    Convert synthetic reply rows into dry-run Google Board size updates.

    Input rows may contain `db_row_id`, `order_ref`, `reply_text`, and
    `product_type`. Raw reply text is never emitted.
    """
    plan: list[dict[str, Any]] = []
    for row in reply_rows:
        product_type = str(row.get("product_type") or product_type_default or "CL")
        facts = parse_size_reply(str(row.get("reply_text") or ""), product_type=product_type)
        decision = decide_size_from_reply(facts, product_type=product_type)
        plan.append(
            {
                "db_row_id": row.get("db_row_id"),
                "order_ref": row.get("order_ref") or private_hash("kaspi_order_id", row.get("order_id")),
                "product_type": product_type,
                "reply_hash": facts.reply_hash,
                "height_cm": facts.height_cm,
                "weight_kg": facts.weight_kg,
                "explicit_size": facts.explicit_size,
                "planned_my_size": decision.size,
                "planned_assigned_size": decision.size,
                "size_source": decision.source,
                "size_confidence": decision.confidence,
                "google_board_column": "MY_SIZE",
                "db_column": "assigned_size",
                "write_allowed": False,
            }
        )
    return plan


LEDGER_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS customer_size_request_ledger (
    ledger_key TEXT PRIMARY KEY,
    order_ref TEXT NOT NULL,
    db_row_id INTEGER,
    store_code TEXT,
    sku_key TEXT,
    sku_id TEXT,
    channel TEXT NOT NULL,
    template_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    request_planned_at TEXT,
    request_sent_at TEXT,
    last_observed_at TEXT,
    reply_hash TEXT,
    height_cm INTEGER,
    weight_kg INTEGER,
    explicit_size TEXT,
    planned_size TEXT,
    size_source TEXT,
    size_confidence TEXT,
    send_allowed INTEGER NOT NULL DEFAULT 0,
    raw_order_id_exported INTEGER NOT NULL DEFAULT 0,
    raw_reply_text_exported INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_customer_size_request_ledger_order_ref
    ON customer_size_request_ledger(order_ref);
CREATE INDEX IF NOT EXISTS idx_customer_size_request_ledger_status
    ON customer_size_request_ledger(status);
"""


def init_customer_size_request_ledger(conn: sqlite3.Connection) -> None:
    conn.executescript(LEDGER_SCHEMA_SQL)


def _connect_ledger_db(ledger_path: Path) -> sqlite3.Connection:
    ledger_path = Path(ledger_path)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(ledger_path)
    conn.row_factory = sqlite3.Row
    init_customer_size_request_ledger(conn)
    return conn


def _ledger_status_rank(status: Any) -> int:
    return LEDGER_STATUS_RANK.get(str(status or "").strip().upper(), 999)


def _deduplicate_customer_size_request_ledger(conn: sqlite3.Connection) -> int:
    """
    Keep one row per redacted order/template identity.

    Earlier no-send probes may have had sparse SKU identity. A later order-sync
    refresh can enrich `sku_id`, which changes the historical ledger_key but not
    the customer/order we must avoid double-prompting. Channel is metadata only:
    UI, browser-gateway, and future API transports must not create separate send
    identities for the same order/template.
    """
    rows = conn.execute(
        """
        SELECT * FROM customer_size_request_ledger
        ORDER BY order_ref, template_hash, updated_at DESC, ledger_key
        """
    ).fetchall()
    groups: dict[tuple[str, str], list[sqlite3.Row]] = {}
    for row in rows:
        groups.setdefault(
            (str(row["order_ref"]), str(row["template_hash"])),
            [],
        ).append(row)

    deleted = 0
    merge_fields = [
        "db_row_id",
        "store_code",
        "sku_key",
        "sku_id",
        "request_sent_at",
        "last_observed_at",
        "reply_hash",
        "height_cm",
        "weight_kg",
        "explicit_size",
        "planned_size",
        "size_source",
        "size_confidence",
    ]
    for grouped_rows in groups.values():
        if len(grouped_rows) <= 1:
            continue
        keeper = sorted(
            grouped_rows,
            key=lambda row: (
                _ledger_status_rank(row["status"]),
                -int(row["db_row_id"] or 0),
                str(row["updated_at"] or ""),
            ),
        )[0]
        keep_key = keeper["ledger_key"]
        updates: dict[str, Any] = {}
        for field in merge_fields:
            if keeper[field] not in (None, ""):
                continue
            for candidate in grouped_rows:
                if candidate["ledger_key"] == keep_key:
                    continue
                if candidate[field] not in (None, ""):
                    updates[field] = candidate[field]
                    break
        if updates:
            assignments = ", ".join(f"{field} = ?" for field in updates)
            conn.execute(
                f"UPDATE customer_size_request_ledger SET {assignments} WHERE ledger_key = ?",
                [*updates.values(), keep_key],
            )
        duplicate_keys = [row["ledger_key"] for row in grouped_rows if row["ledger_key"] != keep_key]
        conn.executemany(
            "DELETE FROM customer_size_request_ledger WHERE ledger_key = ?",
            [(key,) for key in duplicate_keys],
        )
        deleted += len(duplicate_keys)
    return deleted


def upsert_request_ledger_plan(
    ledger_path: Path,
    ledger_rows: Iterable[Mapping[str, Any]],
    *,
    now: datetime | None = None,
) -> dict[str, int]:
    """Persist redacted request-plan rows into a local control-plane ledger."""
    now = now or datetime.now()
    stats = {"input_rows": 0, "inserted": 0, "updated": 0, "deduplicated": 0}
    with _connect_ledger_db(ledger_path) as conn:
        for row in ledger_rows:
            stats["input_rows"] += 1
            ledger_key = str(row["ledger_key"])
            existing = conn.execute(
                "SELECT ledger_key FROM customer_size_request_ledger WHERE ledger_key = ?",
                (ledger_key,),
            ).fetchone()
            if not existing:
                existing = conn.execute(
                    """
                    SELECT ledger_key
                    FROM customer_size_request_ledger
                    WHERE order_ref = ?
                      AND template_hash = ?
                    ORDER BY
                        CASE status
                            WHEN 'SIZE_CONFIRMED' THEN 10
                            WHEN 'CLASSIFICATION_READY' THEN 20
                            WHEN 'REPLY_OBSERVED' THEN 30
                            WHEN 'REPLY_OBSERVED_NO_SIZE_SIGNAL' THEN 35
                            WHEN 'REQUEST_SENT' THEN 40
                            WHEN 'UNKNOWN_SEND_OUTCOME' THEN 42
                            WHEN 'SEND_IN_PROGRESS' THEN 43
                            WHEN 'POLLING' THEN 45
                            WHEN 'SEND_PLANNED_NO_SEND' THEN 50
                            ELSE 999
                        END,
                        updated_at DESC,
                        ledger_key
                    LIMIT 1
                    """,
                    (
                        row.get("order_ref"),
                        row.get("template_hash"),
                    ),
                ).fetchone()
            effective_ledger_key = str(existing["ledger_key"]) if existing else ledger_key
            payload = {
                "ledger_key": effective_ledger_key,
                "order_ref": row.get("order_ref"),
                "db_row_id": row.get("db_row_id"),
                "store_code": row.get("store_code"),
                "sku_key": row.get("sku_key"),
                "sku_id": row.get("sku_id"),
                "channel": row.get("channel") or REQUEST_CHANNEL,
                "template_hash": row.get("template_hash"),
                "status": row.get("status") or "SEND_PLANNED_NO_SEND",
                "request_planned_at": row.get("created_at") or now.isoformat(timespec="seconds"),
                "updated_at": now.isoformat(timespec="seconds"),
            }
            conn.execute(
                """
                INSERT INTO customer_size_request_ledger (
                    ledger_key, order_ref, db_row_id, store_code, sku_key, sku_id,
                    channel, template_hash, status, request_planned_at,
                    send_allowed, raw_order_id_exported, raw_reply_text_exported, updated_at
                ) VALUES (
                    :ledger_key, :order_ref, :db_row_id, :store_code, :sku_key, :sku_id,
                    :channel, :template_hash, :status, :request_planned_at,
                    0, 0, 0, :updated_at
                )
                ON CONFLICT(ledger_key) DO UPDATE SET
                    db_row_id = excluded.db_row_id,
                    store_code = excluded.store_code,
                    sku_key = excluded.sku_key,
                    sku_id = excluded.sku_id,
                    status = CASE
                        WHEN customer_size_request_ledger.status IN (
                            'REQUEST_SENT', 'POLLING', 'REPLY_OBSERVED',
                            'CLASSIFICATION_READY', 'SIZE_CONFIRMED',
                            'UNKNOWN_SEND_OUTCOME', 'SEND_IN_PROGRESS'
                        )
                        THEN customer_size_request_ledger.status
                        ELSE excluded.status
                    END,
                    updated_at = excluded.updated_at
                """,
                payload,
            )
            if existing:
                stats["updated"] += 1
            else:
                stats["inserted"] += 1
        stats["deduplicated"] = _deduplicate_customer_size_request_ledger(conn)
        conn.commit()
    return stats


def _ledger_rows_by_order_ref(conn: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT * FROM customer_size_request_ledger
        ORDER BY request_planned_at DESC, ledger_key
        """
    ).fetchall()
    result: dict[str, sqlite3.Row] = {}
    for row in rows:
        result.setdefault(str(row["order_ref"]), row)
    return result


def record_synthetic_reply_observations(
    ledger_path: Path,
    reply_rows: Iterable[Mapping[str, Any]],
    *,
    product_type_default: str = "CL",
    now: datetime | None = None,
) -> dict[str, int]:
    """
    Record synthetic reply facts in the local ledger.

    This does not store raw reply text and does not write Google Board or app DB.
    """
    now = now or datetime.now()
    stats = {"input_rows": 0, "matched": 0, "unmatched": 0, "classification_ready": 0}
    with _connect_ledger_db(ledger_path) as conn:
        by_order_ref = _ledger_rows_by_order_ref(conn)
        for row in reply_rows:
            stats["input_rows"] += 1
            order_ref = str(row.get("order_ref") or private_hash("kaspi_order_id", row.get("order_id")))
            ledger_row = by_order_ref.get(order_ref)
            if not ledger_row:
                stats["unmatched"] += 1
                continue
            product_type = str(row.get("product_type") or product_type_default or "CL")
            facts = parse_size_reply(str(row.get("reply_text") or ""), product_type=product_type)
            decision = decide_size_from_reply(facts, product_type=product_type)
            status = "CLASSIFICATION_READY" if decision.size else "REPLY_OBSERVED_NO_SIZE_SIGNAL"
            if decision.size:
                stats["classification_ready"] += 1
            conn.execute(
                """
                UPDATE customer_size_request_ledger
                SET status = ?,
                    last_observed_at = ?,
                    reply_hash = ?,
                    height_cm = ?,
                    weight_kg = ?,
                    explicit_size = ?,
                    planned_size = ?,
                    size_source = ?,
                    size_confidence = ?,
                    raw_reply_text_exported = 0,
                    updated_at = ?
                WHERE ledger_key = ?
                """,
                (
                    status,
                    now.isoformat(timespec="seconds"),
                    facts.reply_hash,
                    facts.height_cm,
                    facts.weight_kg,
                    facts.explicit_size,
                    decision.size,
                    decision.source,
                    decision.confidence,
                    now.isoformat(timespec="seconds"),
                    ledger_row["ledger_key"],
                ),
            )
            stats["matched"] += 1
        conn.commit()
    return stats


def record_customer_reply_observations(
    ledger_path: Path,
    reply_rows: Iterable[Mapping[str, Any]],
    *,
    product_type_default: str = "CL",
    now: datetime | None = None,
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    """
    Record live/customer reply facts in the local ledger.

    Raw reply text is accepted only as transient input for parsing. It is not
    emitted in returned observations and is not stored in the ledger.
    """
    now = now or datetime.now()
    stats = {"input_rows": 0, "matched": 0, "unmatched": 0, "classification_ready": 0}
    observations: list[dict[str, Any]] = []
    with _connect_ledger_db(ledger_path) as conn:
        by_order_ref = _ledger_rows_by_order_ref(conn)
        rows = conn.execute(
            "SELECT * FROM customer_size_request_ledger ORDER BY updated_at DESC, ledger_key"
        ).fetchall()
        by_db_row_id: dict[int, sqlite3.Row] = {}
        for ledger_row in rows:
            if ledger_row["db_row_id"] is not None:
                by_db_row_id.setdefault(int(ledger_row["db_row_id"]), ledger_row)

        for row in reply_rows:
            stats["input_rows"] += 1
            ledger_row: sqlite3.Row | None = None
            match_method = "unmatched"
            order_ref_value = str(row.get("order_ref") or "").strip()
            if order_ref_value:
                ledger_row = by_order_ref.get(order_ref_value)
                match_method = "order_ref"
            if ledger_row is None and row.get("db_row_id") not in (None, ""):
                try:
                    ledger_row = by_db_row_id.get(int(row.get("db_row_id")))
                    match_method = "db_row_id"
                except (TypeError, ValueError):
                    ledger_row = None

            if not ledger_row:
                stats["unmatched"] += 1
                observations.append(
                    {
                        "order_ref": order_ref_value or "",
                        "db_row_id": row.get("db_row_id"),
                        "matched": False,
                        "match_method": "unmatched",
                        "raw_reply_text_exported": False,
                    }
                )
                continue

            product_type = str(row.get("product_type") or product_type_default or "CL")
            facts = parse_size_reply(str(row.get("reply_text") or ""), product_type=product_type)
            decision = decide_size_from_reply(facts, product_type=product_type)
            status = "CLASSIFICATION_READY" if decision.size else "REPLY_OBSERVED_NO_SIZE_SIGNAL"
            if decision.size:
                stats["classification_ready"] += 1
            conn.execute(
                """
                UPDATE customer_size_request_ledger
                SET status = ?,
                    last_observed_at = ?,
                    reply_hash = ?,
                    height_cm = ?,
                    weight_kg = ?,
                    explicit_size = ?,
                    planned_size = ?,
                    size_source = ?,
                    size_confidence = ?,
                    raw_reply_text_exported = 0,
                    updated_at = ?
                WHERE ledger_key = ?
                """,
                (
                    status,
                    now.isoformat(timespec="seconds"),
                    facts.reply_hash,
                    facts.height_cm,
                    facts.weight_kg,
                    facts.explicit_size,
                    decision.size,
                    decision.source,
                    decision.confidence,
                    now.isoformat(timespec="seconds"),
                    ledger_row["ledger_key"],
                ),
            )
            stats["matched"] += 1
            observations.append(
                {
                    "ledger_key": ledger_row["ledger_key"],
                    "order_ref": ledger_row["order_ref"],
                    "db_row_id": ledger_row["db_row_id"],
                    "store_code": ledger_row["store_code"],
                    "sku_key": ledger_row["sku_key"],
                    "sku_id": ledger_row["sku_id"],
                    "matched": True,
                    "match_method": match_method,
                    "reply_hash": facts.reply_hash,
                    "height_cm": facts.height_cm,
                    "weight_kg": facts.weight_kg,
                    "explicit_size": facts.explicit_size,
                    "planned_size": decision.size,
                    "size_source": decision.source,
                    "size_confidence": decision.confidence,
                    "status_after_observation": status,
                    "raw_order_id_exported": False,
                    "raw_reply_text_exported": False,
                }
            )
        conn.commit()
    return stats, observations


def record_live_send_canary_acceptance(
    ledger_path: Path,
    validation: Mapping[str, Any],
    *,
    now: datetime | None = None,
    reply_poll_windows_minutes: tuple[int, ...] = (10, 30, 60, 120),
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    """
    Stamp the local ledger after the one-order live-send canary is accepted.

    This is a local bookkeeping bridge only. It does not send messages, poll
    Kaspi, write Google Board, mutate the app DB, or install a scheduler.
    """
    now = now or datetime.now()
    stats = {
        "input_validations": 1,
        "matched": 0,
        "unmatched": 0,
        "updated_to_request_sent": 0,
        "already_after_send_or_reply": 0,
        "blocked_not_green": 0,
    }
    schedule: list[dict[str, Any]] = []
    if validation.get("gate") != "GREEN_LIVE_SEND_CANARY_RESULT_ACCEPTED_ONE_ORDER":
        stats["blocked_not_green"] = 1
        return stats, schedule

    order_ref = str(validation.get("selected_order_ref") or "").strip()
    if not order_ref:
        stats["unmatched"] = 1
        return stats, schedule

    with _connect_ledger_db(ledger_path) as conn:
        by_order_ref = _ledger_rows_by_order_ref(conn)
        ledger_row = by_order_ref.get(order_ref)
        if ledger_row is None:
            stats["unmatched"] = 1
            return stats, schedule

        stats["matched"] = 1
        prior_status = str(ledger_row["status"] or "").strip().upper()
        if prior_status in {
            "CLASSIFICATION_READY",
            "REPLY_OBSERVED",
            "REPLY_OBSERVED_NO_SIZE_SIGNAL",
            "SIZE_CONFIRMED",
        }:
            stats["already_after_send_or_reply"] = 1
        else:
            conn.execute(
                """
                UPDATE customer_size_request_ledger
                SET status = 'REQUEST_SENT',
                    request_sent_at = COALESCE(request_sent_at, ?),
                    send_allowed = 0,
                    raw_order_id_exported = 0,
                    raw_reply_text_exported = 0,
                    updated_at = ?
                WHERE ledger_key = ?
                """,
                (
                    now.isoformat(timespec="seconds"),
                    now.isoformat(timespec="seconds"),
                    ledger_row["ledger_key"],
                ),
            )
            conn.commit()
            stats["updated_to_request_sent"] = 1

        for minutes in reply_poll_windows_minutes:
            poll_at = now + timedelta(minutes=int(minutes))
            schedule.append(
                {
                    "order_ref": ledger_row["order_ref"],
                    "db_row_id": ledger_row["db_row_id"],
                    "store_code": ledger_row["store_code"],
                    "sku_key": ledger_row["sku_key"],
                    "sku_id": ledger_row["sku_id"],
                    "poll_after_minutes": int(minutes),
                    "poll_not_before_at": poll_at.isoformat(timespec="seconds"),
                    "suggested_action": "POLL_FOR_CUSTOMER_REPLY",
                    "customer_send_allowed": False,
                    "kaspi_chat_write_allowed": False,
                    "google_board_write_allowed": False,
                    "db_write_allowed": False,
                    "raw_order_id_exported": False,
                    "raw_reply_text_exported": False,
                }
            )
    return stats, schedule


def export_customer_size_ledger_snapshot(ledger_path: Path) -> list[dict[str, Any]]:
    with _connect_ledger_db(ledger_path) as conn:
        rows = conn.execute(
            """
            SELECT
                ledger_key, order_ref, db_row_id, store_code, sku_key, sku_id,
                channel, template_hash, status, request_planned_at, request_sent_at,
                last_observed_at, reply_hash, height_cm, weight_kg, explicit_size,
                planned_size, size_source, size_confidence, send_allowed,
                raw_order_id_exported, raw_reply_text_exported, updated_at
            FROM customer_size_request_ledger
            ORDER BY updated_at DESC, ledger_key
            """
        ).fetchall()
    return [dict(row) for row in rows]


def build_update_plan_from_ledger_snapshot(
    ledger_snapshot_rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    plan = []
    for row in ledger_snapshot_rows:
        planned_size = row.get("planned_size")
        if not planned_size:
            continue
        plan.append(
            {
                "ledger_key": row.get("ledger_key"),
                "db_row_id": row.get("db_row_id"),
                "order_ref": row.get("order_ref"),
                "store_code": row.get("store_code"),
                "planned_my_size": planned_size,
                "planned_assigned_size": planned_size,
                "height_cm": row.get("height_cm"),
                "weight_kg": row.get("weight_kg"),
                "explicit_size": row.get("explicit_size"),
                "size_source": row.get("size_source"),
                "size_confidence": row.get("size_confidence"),
                "google_board_column": "MY_SIZE",
                "db_column": "assigned_size",
                "write_allowed": False,
            }
        )
    return plan


def build_customer_size_next_actions(
    ledger_snapshot_rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Build a redacted operational queue from the local size-request ledger."""
    actions: list[dict[str, Any]] = []
    for row in ledger_snapshot_rows:
        status = str(row.get("status") or "").strip().upper()
        planned_size = row.get("planned_size")
        if status == "CLASSIFICATION_READY" and planned_size:
            action = "GOOGLE_BOARD_SIZE_FILL_READY_DRY_RUN"
            priority = 10
        elif status == "REPLY_OBSERVED_NO_SIZE_SIGNAL":
            action = "MANUAL_REVIEW_REPLY_NO_SIZE_SIGNAL"
            priority = 30
        elif status in {"REQUEST_SENT", "POLLING"}:
            action = "POLL_FOR_CUSTOMER_REPLY"
            priority = 40
        elif status == "SEND_PLANNED_NO_SEND":
            action = "LIVE_UI_SEND_CANARY_PENDING_APPROVAL"
            priority = 50
        else:
            action = "OBSERVE_ONLY"
            priority = 90
        actions.append(
            {
                "ledger_key": row.get("ledger_key"),
                "order_ref": row.get("order_ref"),
                "db_row_id": row.get("db_row_id"),
                "store_code": row.get("store_code"),
                "sku_key": row.get("sku_key"),
                "sku_id": row.get("sku_id"),
                "status": status,
                "planned_my_size": planned_size,
                "size_source": row.get("size_source"),
                "size_confidence": row.get("size_confidence"),
                "suggested_action": action,
                "priority": priority,
                "customer_send_allowed": False,
                "kaspi_chat_write_allowed": False,
                "google_board_write_allowed": False,
                "db_write_allowed": False,
                "raw_order_id_exported": False,
                "raw_reply_text_exported": False,
            }
        )
    return sorted(
        actions,
        key=lambda row: (
            int(row.get("priority") or 999),
            str(row.get("store_code") or ""),
            str(row.get("order_ref") or ""),
        ),
    )


def summarize_customer_size_ledger(
    ledger_snapshot_rows: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return counts that can drive a no-send scheduler/preflight dashboard."""
    rows = list(ledger_snapshot_rows)
    by_status: dict[str, int] = {}
    by_store: dict[str, int] = {}
    for row in rows:
        status = str(row.get("status") or "UNKNOWN").strip().upper() or "UNKNOWN"
        store = str(row.get("store_code") or "UNKNOWN").strip().upper() or "UNKNOWN"
        by_status[status] = by_status.get(status, 0) + 1
        by_store[store] = by_store.get(store, 0) + 1
    actions = build_customer_size_next_actions(rows)
    by_action: dict[str, int] = {}
    for action in actions:
        key = str(action["suggested_action"])
        by_action[key] = by_action.get(key, 0) + 1
    return {
        "ledger_rows": len(rows),
        "by_status": dict(sorted(by_status.items())),
        "by_store": dict(sorted(by_store.items())),
        "by_action": dict(sorted(by_action.items())),
        "pending_live_send_canary_count": by_action.get(
            "LIVE_UI_SEND_CANARY_PENDING_APPROVAL", 0
        ),
        "reply_poll_pending_count": by_action.get("POLL_FOR_CUSTOMER_REPLY", 0),
        "google_board_size_fill_ready_count": by_action.get(
            "GOOGLE_BOARD_SIZE_FILL_READY_DRY_RUN", 0
        ),
        "manual_review_required_count": by_action.get(
            "MANUAL_REVIEW_REPLY_NO_SIZE_SIGNAL", 0
        ),
    }


class _ChatTriggerParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.triggers: list[dict[str, str]] = []
        self._capture = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        classes = set(attr_map.get("class", "").split())
        if tag.lower() == "button" and {"init-chat-button", "chat-section"}.issubset(classes):
            self.triggers.append(attr_map)
        if tag.lower() in {"button", "textarea", "input"}:
            marker = " ".join(str(value) for value in attr_map.values()).lower()
            if "sendmessage" in marker or "отправ" in marker:
                self._capture = True


def inspect_chat_trigger_html(html: str) -> dict[str, Any]:
    parser = _ChatTriggerParser()
    parser.feed(html or "")
    order_chat_triggers = [
        trigger
        for trigger in parser.triggers
        if trigger.get("type") == "CLIENT_SELLER_BY_ORDER"
    ]
    return {
        "order_chat_trigger_count": len(order_chat_triggers),
        "all_chat_trigger_count": len(parser.triggers),
        "selector": "button.init-chat-button.chat-section[type='CLIENT_SELLER_BY_ORDER']",
        "send_surface_marker_observed": parser._capture,
        "probe_mode": "html_fixture_no_click_no_send",
        "gate": "GREEN_CHAT_TRIGGER_SELECTOR_FOUND_NO_SEND"
        if order_chat_triggers
        else "YELLOW_CHAT_TRIGGER_SELECTOR_NOT_FOUND",
    }


def active_stage_codes_for_size_request() -> list[str]:
    return [
        StageCode.SIGN_REQUIRED.value,
        StageCode.NEW_APPROVED.value,
        StageCode.PREORDER_IN_TRANSIT.value,
        StageCode.ACCEPTED_PENDING_ASSEMBLY.value,
        StageCode.ASSEMBLED_PENDING_HANDOVER.value,
    ]


def dataclass_to_dict(value: Any) -> dict[str, Any]:
    return asdict(value)
