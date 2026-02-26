#!/usr/bin/env python3
"""Build deterministic exception triage output from exceptions.json + playbook mapping."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
from pathlib import Path
import re
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PLAYBOOK = PROJECT_ROOT / "docs" / "ops" / "EXCEPTION_PLAYBOOK.md"
DEFAULT_ALLOWLIST = PROJECT_ROOT / "config" / "exceptions_allowlist.json"


@dataclass(frozen=True)
class PlaybookRow:
    code: str
    severity: str
    owner: str
    recommended_action: str


def _strip_ticks(value: str) -> str:
    return value.strip().strip("`").strip()


def _parse_playbook(path: Path) -> dict[str, PlaybookRow]:
    if not path.exists():
        raise RuntimeError(f"playbook file missing: {path}")
    lines = path.read_text(encoding="utf-8").splitlines()
    table_rows: list[list[str]] = []
    for line in lines:
        line = line.strip()
        if not line.startswith("|"):
            continue
        parts = [part.strip() for part in line.split("|")[1:-1]]
        if not parts:
            continue
        table_rows.append(parts)

    header_idx = None
    for idx, row in enumerate(table_rows):
        lowered = [cell.lower() for cell in row]
        if "exception_code" in lowered and "owner" in lowered:
            header_idx = idx
            break
    if header_idx is None:
        raise RuntimeError(f"playbook table header not found in: {path}")

    header = [cell.lower() for cell in table_rows[header_idx]]
    required = ["exception_code", "severity", "owner", "recommended_action"]
    for column in required:
        if column not in header:
            raise RuntimeError(f"playbook missing required column `{column}`")
    index = {name: header.index(name) for name in required}

    mapping: dict[str, PlaybookRow] = {}
    for row in table_rows[header_idx + 1 :]:
        if all(re.fullmatch(r"-+", cell.replace(" ", "")) for cell in row):
            continue
        if len(row) < len(header):
            continue
        code = _strip_ticks(row[index["exception_code"]])
        if not code:
            continue
        severity = _strip_ticks(row[index["severity"]]).lower()
        owner = _strip_ticks(row[index["owner"]])
        action = _strip_ticks(row[index["recommended_action"]])
        mapping[code] = PlaybookRow(
            code=code,
            severity=severity,
            owner=owner,
            recommended_action=action,
        )

    if not mapping:
        raise RuntimeError(f"playbook mapping is empty: {path}")
    return mapping


def _load_allowlist(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"allowlist payload must be object: {path}")
    rows = payload.get("codes", {})
    if not isinstance(rows, dict):
        raise RuntimeError(f"allowlist `codes` must be object: {path}")
    normalized: dict[str, dict[str, str]] = {}
    for code, details in rows.items():
        if not isinstance(details, dict):
            raise RuntimeError(f"allowlist row for `{code}` must be object")
        reason = str(details.get("reason", "")).strip()
        expires_on = str(details.get("expires_on", "")).strip()
        if not reason:
            raise RuntimeError(f"allowlist row for `{code}` missing `reason`")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", expires_on):
            raise RuntimeError(f"allowlist row for `{code}` has invalid `expires_on`")
        date.fromisoformat(expires_on)
        normalized[str(code)] = {"reason": reason, "expires_on": expires_on}
    return normalized


def _load_exceptions(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise RuntimeError(f"exceptions file missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"exceptions payload must be object: {path}")
    rows = payload.get("exceptions", [])
    if not isinstance(rows, list):
        raise RuntimeError(f"`exceptions` must be array in: {path}")
    return payload


def _render_md(payload: dict[str, Any]) -> str:
    lines = [
        "# Exceptions Triage",
        "",
        f"- generated_at: `{payload['generated_at']}`",
        f"- as_of: `{payload['as_of']}`",
        f"- exceptions_path: `{payload['exceptions_path']}`",
        f"- status: `{payload['status']}`",
        "",
        "## Summary",
        "",
        f"- total_exceptions: `{payload['total_exceptions']}`",
        f"- critical_total: `{payload['critical_total']}`",
        f"- critical_unallowlisted: `{len(payload['critical_unallowlisted'])}`",
        f"- unknown_codes: `{len(payload['unknown_codes'])}`",
        f"- expired_allowlist: `{len(payload['expired_allowlist'])}`",
        "",
        "## Code Counts",
        "",
        "| exception_code | count | max_severity | owner | allowlisted |",
        "|---|---:|---|---|---:|",
    ]
    for row in payload["codes"]:
        lines.append(
            f"| `{row['exception_code']}` | {row['count']} | `{row['max_severity']}` | "
            f"`{row['owner']}` | {str(bool(row['allowlisted'])).lower()} |"
        )

    if payload["unknown_codes"]:
        lines.extend(["", "## Unknown Codes", ""])
        for code in payload["unknown_codes"]:
            lines.append(f"- `{code}`")

    if payload["critical_unallowlisted"]:
        lines.extend(["", "## Critical Unallowlisted", ""])
        for code in payload["critical_unallowlisted"]:
            lines.append(f"- `{code}`")

    if payload["expired_allowlist"]:
        lines.extend(["", "## Expired Allowlist", ""])
        for code in payload["expired_allowlist"]:
            lines.append(f"- `{code}`")

    lines.extend(["", "## Notes", ""])
    if payload["notes"]:
        for note in payload["notes"]:
            lines.append(f"- {note}")
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def triage_exceptions(
    *,
    exceptions_path: Path,
    playbook_path: Path,
    allowlist_path: Path,
    output_json: Path,
    output_md: Path,
    strict: bool,
) -> dict[str, Any]:
    payload = _load_exceptions(exceptions_path)
    playbook = _parse_playbook(playbook_path)
    allowlist = _load_allowlist(allowlist_path)
    as_of = str(payload.get("as_of") or "")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", as_of):
        raise RuntimeError(f"exceptions payload has invalid as_of: {as_of!r}")
    today = date.fromisoformat(as_of)

    unknown_allowlist = sorted(code for code in allowlist if code not in playbook)
    if unknown_allowlist:
        raise RuntimeError(
            "allowlist has codes missing from playbook: " + ", ".join(unknown_allowlist)
        )

    active_allowlist: set[str] = set()
    expired_allowlist: list[str] = []
    for code, row in allowlist.items():
        expiry = date.fromisoformat(row["expires_on"])
        if today <= expiry:
            active_allowlist.add(code)
        else:
            expired_allowlist.append(code)

    counts: dict[str, dict[str, Any]] = {}
    unknown_codes: set[str] = set()
    critical_codes: set[str] = set()
    severity_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    rank_to_label = {v: k for k, v in severity_rank.items()}

    for row in payload.get("exceptions", []):
        if not isinstance(row, dict):
            continue
        code = str(row.get("step") or "").strip()
        severity = str(row.get("severity") or "high").lower()
        if code not in playbook:
            unknown_codes.add(code or "<missing>")
            owner = "UNKNOWN"
        else:
            owner = playbook[code].owner
        if severity == "critical":
            critical_codes.add(code)
        bucket = counts.setdefault(
            code,
            {"count": 0, "max_rank": 0, "owner": owner},
        )
        bucket["count"] = int(bucket["count"]) + 1
        bucket["max_rank"] = max(int(bucket["max_rank"]), severity_rank.get(severity, 1))

    critical_unallowlisted = sorted(
        code for code in critical_codes if code not in active_allowlist
    )
    unknown_codes_sorted = sorted(code for code in unknown_codes if code != "<missing>")
    notes: list[str] = []
    if critical_unallowlisted:
        notes.append("Critical exceptions require fix or explicit temporary allowlist.")
    if unknown_codes_sorted:
        notes.append("Unknown exception codes require playbook update.")
    if expired_allowlist:
        notes.append("Expired allowlist rows require renewal or closure.")

    code_rows = []
    for code in sorted(counts):
        row = counts[code]
        code_rows.append(
            {
                "exception_code": code,
                "count": int(row["count"]),
                "max_severity": rank_to_label.get(int(row["max_rank"]), "low"),
                "owner": row["owner"],
                "allowlisted": code in active_allowlist,
            }
        )

    ok = not critical_unallowlisted and not unknown_codes_sorted and not expired_allowlist
    report = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "as_of": as_of,
        "exceptions_path": str(exceptions_path.resolve()),
        "playbook_path": str(playbook_path.resolve()),
        "allowlist_path": str(allowlist_path.resolve()),
        "status": "PASS" if ok else "FAIL",
        "ok": bool(ok),
        "total_exceptions": len(payload.get("exceptions", [])),
        "critical_total": sum(1 for row in payload.get("exceptions", []) if str((row or {}).get("severity", "")).lower() == "critical"),
        "unknown_codes": unknown_codes_sorted,
        "critical_unallowlisted": critical_unallowlisted,
        "expired_allowlist": sorted(expired_allowlist),
        "codes": code_rows,
        "notes": notes,
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_md.write_text(_render_md(report), encoding="utf-8")

    if strict and not ok:
        raise RuntimeError(
            "exceptions triage strict failure: "
            f"unknown_codes={len(unknown_codes_sorted)} "
            f"critical_unallowlisted={len(critical_unallowlisted)} "
            f"expired_allowlist={len(expired_allowlist)}"
        )
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Triage daily autopilot exceptions against playbook/allowlist")
    parser.add_argument("--exceptions", type=Path, required=True)
    parser.add_argument("--playbook", type=Path, default=DEFAULT_PLAYBOOK)
    parser.add_argument("--allowlist", type=Path, default=DEFAULT_ALLOWLIST)
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument("--output-md", type=Path, default=None)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    exceptions_path = args.exceptions.resolve()
    output_json = args.output_json or (exceptions_path.parent / "exceptions_triage.json")
    output_md = args.output_md or (exceptions_path.parent / "exceptions_triage.md")
    report = triage_exceptions(
        exceptions_path=exceptions_path,
        playbook_path=args.playbook.resolve(),
        allowlist_path=args.allowlist.resolve(),
        output_json=Path(output_json),
        output_md=Path(output_md),
        strict=bool(args.strict),
    )
    print(f"exceptions_triage_json={output_json}")
    print(f"exceptions_triage_md={output_md}")
    print(f"status={report['status']}")
    return 0 if report["ok"] or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
