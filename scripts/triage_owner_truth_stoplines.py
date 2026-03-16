#!/usr/bin/env python3
"""Aggregate owner-truth stoplines into a single deterministic summary artifact."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.webui_archive_truth_utils import DEFAULT_LEDGER_ROOT, resolve_latest_dir
from scripts.webui_chronology_contract_utils import load_webui_chronology_gates


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _entry(name: str, path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    if payload is None:
        return {
            "check": name,
            "path": str(path),
            "status": "MISSING",
            "ok": False,
            "error_code": "MISSING_ARTIFACT",
            "message": f"artifact missing or unreadable: {path}",
        }
    status = str(payload.get("status") or "").upper()
    ok = bool(payload.get("ok", status == "PASS")) and status in {"PASS", "GREEN"}
    return {
        "check": name,
        "path": str(path),
        "status": status,
        "ok": ok,
        "error_code": payload.get("error_code") or (None if ok else "CHECK_FAILED"),
        "message": payload.get("message") or "",
    }


def _entry_any(name: str, paths: list[Path]) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    for path in paths:
        row = _entry(name, path)
        if row["ok"]:
            return row
        failures.append(row)
    return failures[0] if failures else {
        "check": name,
        "path": "",
        "status": "MISSING",
        "ok": False,
        "error_code": "MISSING_ARTIFACT",
        "message": "no candidate paths provided",
    }


def _publication_validation_dir(root: Path, as_of: str) -> Path | None:
    publication_path = root / "exports" / "north_star_owner_review" / as_of / "publication_readiness.json"
    payload = _load_json(publication_path)
    if not isinstance(payload, dict):
        return None
    gates = payload.get("gates") or {}
    if not isinstance(gates, dict):
        return None
    candidates: list[Path] = []
    for gate in gates.values():
        if not isinstance(gate, dict):
            continue
        raw_path = gate.get("path")
        if not raw_path:
            continue
        candidate = Path(str(raw_path))
        if not candidate.is_absolute():
            candidate = root / candidate
        parent = candidate.parent.resolve()
        if parent.exists():
            candidates.append(parent)
    if not candidates:
        return None
    counts: dict[Path, int] = {}
    for candidate in candidates:
        counts[candidate] = counts.get(candidate, 0) + 1
    return sorted(counts.items(), key=lambda item: (item[1], str(item[0])))[-1][0]


def _resolve_validation_dir(
    root: Path,
    *,
    truth_source: str,
    as_of: str,
    explicit: Path | None,
) -> Path:
    if explicit is not None:
        return explicit.resolve()
    if truth_source == "webui_archive":
        default = root / "exports" / "validation" / "webui_archive_single_truth" / as_of
    else:
        default = root / "exports" / "validation" / "crm_north_star_restate" / as_of
    if default.exists():
        return default
    publication_fallback = _publication_validation_dir(root, as_of)
    if publication_fallback is not None:
        return publication_fallback
    return default


def _latest_child(root: Path) -> Path | None:
    if not root.exists():
        return None
    dirs = sorted(path for path in root.iterdir() if path.is_dir())
    return dirs[-1] if dirs else None


def _resolve_optional_root(explicit: Path | None, default_root: Path) -> Path | None:
    if explicit is not None:
        candidate = explicit.expanduser()
        if candidate.exists():
            return candidate.resolve()
        alt = default_root / candidate
        if alt.exists():
            return alt.resolve()
        return candidate.resolve()
    try:
        return resolve_latest_dir(default_root)
    except Exception:
        return None


def _resolve_download_root(root: Path, download_run_id: str | None) -> Path | None:
    download_root = root / "exports" / "webui_archive_download_runs"
    if download_run_id:
        candidate = Path(download_run_id).expanduser()
        if candidate.exists():
            return candidate.resolve()
        return (download_root / download_run_id).resolve()
    return _latest_child(download_root)


def triage_owner_truth_stoplines(
    *,
    as_of: date,
    project_root: Path,
    truth_source: str,
    validation_dir: Path | None,
    pack_root: Path | None,
    ledger_root: Path | None,
    download_run_id: str | None,
    output_path: Path | None,
    strict: bool,
) -> dict[str, Any]:
    root = project_root.resolve()
    as_of_str = as_of.isoformat()
    validation_root = _resolve_validation_dir(
        root,
        truth_source=truth_source,
        as_of=as_of_str,
        explicit=validation_dir,
    )
    resolved_pack_root = _resolve_optional_root(pack_root, root / "exports" / "webui_archive_packs")
    resolved_ledger_root = _resolve_optional_root(ledger_root, DEFAULT_LEDGER_ROOT)
    resolved_download_root = _resolve_download_root(root, download_run_id)

    checks = [
        _entry(
            "reference_freshness",
            root / "exports" / "validation" / "identity_stabilization" / as_of_str / "validate_reference_freshness.json",
        ),
        _entry(
            "external_snapshot_parity",
            root / "exports" / "validation" / "identity_stabilization" / as_of_str / "validate_external_snapshot_parity.json",
        ),
        _entry(
            "recent_identity_coverage",
            root / "exports" / "validation" / "identity_stabilization" / as_of_str / "validate_recent_identity_coverage.json",
        ),
        _entry(
            "order_entries_freshness",
            root / "exports" / "validation" / "identity_stabilization" / as_of_str / "validate_order_entries_freshness.json",
        ),
        _entry(
            "ads_readiness",
            root / "exports" / "validation" / "ads_sidecar_readiness" / as_of_str / "ads_sidecar_readiness_report.json",
        ),
        _entry(
            "opex_readiness",
            root / "exports" / "validation" / "opex_readiness" / as_of_str / "opex_readiness_report.json",
        ),
        _entry(
            "returns_economics",
            root / "exports" / "validation" / "returns_economics" / as_of_str / "returns_economics_report.json",
        ),
        _entry(
            "cash_reconciliation",
            root / "exports" / "validation" / "cash_reconciliation" / as_of_str / "cash_reconciliation_report.json",
        ),
        _entry(
            "owner_pnl",
            root / "exports" / "owner_pnl" / as_of_str / "OWNER_PNL.json",
        ),
        _entry(
            "north_star_publication_readiness",
            root / "exports" / "north_star_owner_review" / as_of_str / "publication_readiness.json",
        ),
    ]

    if truth_source == "webui_archive":
        chronology_gates, _chronology_ok, _chronology_meta = load_webui_chronology_gates(validation_root)
        chronology_checks = [
            {
                "check": check_name,
                "path": gate["path"],
                "status": gate["status"],
                "ok": gate["ok"],
                "error_code": gate.get("payload", {}).get("error_code") or (None if gate["ok"] else "CHECK_FAILED"),
                "message": gate.get("payload", {}).get("message") or gate.get("reason") or "",
            }
            for check_name, gate in chronology_gates.items()
        ]
        checks.extend(
            [
                _entry(
                    "webui_pack_integrity",
                    (
                        resolved_pack_root / "integrity_report.json"
                        if resolved_pack_root is not None
                        else root / "exports" / "webui_archive_packs" / "__missing__" / "integrity_report.json"
                    ),
                ),
                _entry(
                    "webui_ledger_continuity",
                    (
                        resolved_ledger_root / "continuity_report.json"
                        if resolved_ledger_root is not None
                        else root / "exports" / "order_status_ledger" / "__missing__" / "continuity_report.json"
                    ),
                ),
                _entry(
                    "webui_download_validation",
                    (
                        resolved_download_root / "download_validation.json"
                        if resolved_download_root is not None
                        else root / "exports" / "webui_archive_download_runs" / "__missing__" / "download_validation.json"
                    ),
                ),
                *chronology_checks,
                _entry("webui_vs_current_db", validation_root / "webui_vs_db_report.json"),
                _entry("webui_ads_offer_coverage", validation_root / "ads_offer_universe_report.json"),
                _entry("webui_ads_spend_reality", validation_root / "ads_spend_reality_report.json"),
                _entry("webui_cogs_completeness", validation_root / "cogs_completeness_report.json"),
                _entry("webui_cogs_realism", validation_root / "cogs_realism_report.json"),
                _entry("order_status_audit", validation_root / "order_status_audit_report.json"),
            ]
        )
    else:
        checks.extend(
            [
                _entry_any(
                    "north_star_sales_truth_band",
                    [
                        validation_root / "sales_truth_vs_crm_report.json",
                        validation_root / "sales_against_workbook_report.json",
                    ],
                ),
                _entry("north_star_ads_offer_coverage", validation_root / "ads_offer_universe_report.json"),
                _entry("north_star_ads_spend_reality", validation_root / "ads_spend_reality_report.json"),
                _entry("north_star_cogs_completeness", validation_root / "cogs_completeness_report.json"),
                _entry("north_star_cogs_realism", validation_root / "cogs_realism_report.json"),
            ]
        )

    stoplines = [
        {
            "check": row["check"],
            "error_code": row["error_code"],
            "message": row["message"],
            "path": row["path"],
        }
        for row in checks
        if not row["ok"]
    ]

    summary = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "as_of": as_of_str,
        "truth_source": truth_source,
        "validation_dir": str(validation_root),
        "status": "PASS" if not stoplines else "FAIL",
        "ok": len(stoplines) == 0,
        "error_code": stoplines[0]["error_code"] if stoplines else None,
        "stopline_count": len(stoplines),
        "checks": checks,
        "stoplines": stoplines,
    }

    final_json = output_path or (root / "exports" / "daily" / as_of_str / "owner_truth_summary.json")
    final_md = final_json.with_suffix(".md")
    final_json.parent.mkdir(parents=True, exist_ok=True)
    final_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    md_lines = [
        "# Owner Truth Stopline Triage",
        "",
        f"- as_of: `{as_of_str}`",
        f"- truth_source: `{truth_source}`",
        f"- status: `{summary['status']}`",
        f"- stopline_count: `{summary['stopline_count']}`",
        "",
        "| check | status | error_code | path |",
        "|---|---|---|---|",
    ]
    for row in checks:
        md_lines.append(
            f"| `{row['check']}` | `{row['status']}` | `{row['error_code'] or ''}` | `{row['path']}` |"
        )
    if stoplines:
        md_lines.extend(["", "## Stoplines", ""])
        for row in stoplines:
            md_lines.append(f"- `{row['check']}` `{row['error_code']}`: {row['message']} ({row['path']})")
    final_md.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    summary["json_path"] = str(final_json)
    summary["md_path"] = str(final_md)
    if strict and stoplines:
        raise RuntimeError("owner truth stoplines present")
    return summary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Aggregate owner truth stoplines")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--truth-source", choices=["db", "webui_archive"], default="db")
    parser.add_argument("--validation-dir", type=Path, default=None)
    parser.add_argument("--pack-root", type=Path, default=None)
    parser.add_argument("--ledger-root", type=Path, default=None)
    parser.add_argument("--download-run-id", default=None)
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        summary = triage_owner_truth_stoplines(
            as_of=date.fromisoformat(str(args.as_of)),
            project_root=args.project_root,
            truth_source=str(args.truth_source),
            validation_dir=args.validation_dir,
            pack_root=args.pack_root,
            ledger_root=args.ledger_root,
            download_run_id=args.download_run_id,
            output_path=args.output_path,
            strict=bool(args.strict),
        )
    except Exception as exc:
        print("status=FAIL")
        print("error_code=OWNER_TRUTH_STOPLINE")
        print(f"message={exc}")
        return 1

    print(f"owner_truth_summary_json={summary['json_path']}")
    print(f"owner_truth_summary_md={summary['md_path']}")
    print(f"status={summary['status']}")
    if summary.get("error_code"):
        print(f"error_code={summary['error_code']}")
    return 0 if summary["ok"] or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
