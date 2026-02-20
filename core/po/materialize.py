from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from core.db import get_db
from core.po.lifecycle import create_po, add_po_line


def _extract_note_value(notes: str | None, key: str) -> str | None:
    if not notes:
        return None
    for part in notes.split(";"):
        part = part.strip()
        if part.startswith(f"{key}="):
            return part.split("=", 1)[1].strip()
    return None


def _table_columns(conn, table_name: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _table_exists(conn, table_name: str) -> bool:
    return bool(_table_columns(conn, table_name))


def materialize_plan_po(
    dashboard_path: Path,
    plan_name: str,
    po_id: str,
    supplier: str,
    notes: str | None,
    user: str | None,
    db_path: Path,
    apply: bool = False,
) -> dict:
    dashboard_path = Path(dashboard_path)
    if not dashboard_path.exists():
        raise RuntimeError(f"Dashboard JSON not found: {dashboard_path}")

    try:
        payload = json.loads(dashboard_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Failed to parse dashboard JSON: {exc}") from exc

    pos = payload.get("pos", {})
    plan = pos.get(plan_name)
    if not isinstance(plan, dict):
        raise RuntimeError(f"Plan not found: {plan_name}")

    if apply:
        write_enabled = os.environ.get("PO_WRITE_ENABLED", "false").strip().lower() in {
            "1",
            "true",
            "yes",
        }
        if not write_enabled:
            raise RuntimeError("PO_WRITE_ENABLED=true required for --apply writes")

    plan_hash = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()[:12]
    plan_msg = plan.get("po_message_date") or ""
    notes_parts = [f"PLAN={plan_name}", f"PLAN_HASH={plan_hash}"]
    if plan_msg:
        notes_parts.append(f"PLAN_MSG_DATE={plan_msg}")
    if notes:
        notes_parts.append(notes)
    notes_str = "; ".join(notes_parts)

    with get_db(db_path) as conn:
        if not _table_exists(conn, "po_header"):
            raise RuntimeError("Missing po_header table; run schema migration before materialize-plan")

        existing = conn.execute(
            "SELECT notes FROM po_header WHERE po_id = ?",
            (po_id,),
        ).fetchone()
        if existing:
            existing_hash = _extract_note_value(existing["notes"], "PLAN_HASH")
            if not existing_hash:
                raise RuntimeError(f"Existing PO {po_id} missing PLAN_HASH; refusing to overwrite")
            if existing_hash != plan_hash:
                raise RuntimeError(
                    f"PLAN_HASH mismatch for {po_id}: existing={existing_hash} new={plan_hash}"
                )
            return {
                "status": "IDEMPOTENT",
                "po_id": po_id,
                "plan_name": plan_name,
                "plan_hash": plan_hash,
            }

    if not apply:
        return {
            "status": "DRY_RUN",
            "po_id": po_id,
            "plan_name": plan_name,
            "plan_hash": plan_hash,
        }

    size_lines = plan.get("size_level", [])
    if not size_lines:
        raise RuntimeError("Plan has no size_level data; cannot materialize.")

    sku_cost_map = {}
    sku_weight_map = {}
    for sku in plan.get("sku_level", []):
        sku_key = sku.get("sku_key")
        if not sku_key:
            continue
        sku_cost_map[sku_key] = float(sku.get("base_cost_cny") or 0)
        sku_weight_map[sku_key] = float(sku.get("weight_per_unit_kg") or 0)

    create_po(
        supplier_code=supplier,
        po_id=po_id,
        order_date=None,
        notes=notes_str,
        created_by=user or "cli",
        db_path=db_path,
    )

    units_total = 0
    total_cost_cny = 0.0
    weight_nom_kg = 0.0

    for line in size_lines:
        order_qty = int(line.get("order_qty") or 0)
        if order_qty <= 0:
            continue
        sku_key = line.get("sku_key") or ""
        size = line.get("size") or ""
        sku_id = line.get("sku_id") or (f"{sku_key}_{size}" if sku_key and size else sku_key)
        unit_cost_cny = sku_cost_map.get(sku_key, 0.0)
        add_po_line(
            po_id=po_id,
            sku_id=sku_id,
            order_qty=order_qty,
            unit_cost_cny=unit_cost_cny,
            sku_key=sku_key or None,
            my_size=size or None,
            db_path=db_path,
        )
        units_total += order_qty
        total_cost_cny += unit_cost_cny * order_qty
        if line.get("weight_kg") is not None:
            weight_nom_kg += float(line.get("weight_kg") or 0)
        else:
            weight_nom_kg += sku_weight_map.get(sku_key, 0.0) * order_qty

    with get_db(db_path) as conn:
        columns = _table_columns(conn, "po_header")
        updates = []
        values = []
        if "units_total" in columns:
            updates.append("units_total = ?")
            values.append(units_total)
        if "total_cost_cny" in columns:
            updates.append("total_cost_cny = ?")
            values.append(round(total_cost_cny, 2))
        if "weight_nom_kg" in columns:
            updates.append("weight_nom_kg = ?")
            values.append(round(weight_nom_kg, 2))
        if updates:
            values.append(po_id)
            conn.execute(
                f"UPDATE po_header SET {', '.join(updates)} WHERE po_id = ?",
                values,
            )

    return {
        "status": "CREATED",
        "po_id": po_id,
        "plan_name": plan_name,
        "plan_hash": plan_hash,
        "units_total": units_total,
        "weight_nom_kg": round(weight_nom_kg, 2),
        "total_cost_cny": round(total_cost_cny, 2),
    }
