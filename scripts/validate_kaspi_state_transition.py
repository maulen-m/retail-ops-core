#!/usr/bin/env python3
"""Validate Kaspi write-like API event state transitions (no HTTP-only success)."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "exceptions"
REQUIRED_EVENT_FIELDS = {"order_code", "action", "http_success", "confirmed", "pre_state", "post_state"}


def _render_md(payload: dict[str, Any]) -> str:
    lines = [
        "# Kaspi State Transition Validation",
        "",
        f"- generated_at: `{payload['generated_at']}`",
        f"- as_of: `{payload['as_of']}`",
        f"- status: `{payload['status']}`",
        f"- events_checked: `{payload['events_checked']}`",
        f"- http_only_success_count: `{payload['http_only_success_count']}`",
    ]
    if payload["errors"]:
        lines.extend(["", "## Errors"])
        for err in payload["errors"]:
            lines.append(f"- {err}")
    if payload["exceptions"]:
        lines.extend(["", "## Exceptions"])
        for row in payload["exceptions"]:
            lines.append(f"- `{row['order_code']}` `{row['action']}` reason={row['reason']}")
    return "\n".join(lines) + "\n"


def validate_kaspi_state_transition(
    *,
    input_path: Path,
    as_of: str | None,
    output_root: Path,
    strict: bool,
) -> dict[str, Any]:
    src = Path(input_path)
    if not src.exists():
        raise RuntimeError(f"missing input events file: {src}")

    payload = json.loads(src.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("input payload must be JSON object")

    resolved_as_of = as_of or str(payload.get("as_of") or date.today().isoformat())
    events = payload.get("events")
    if not isinstance(events, list):
        raise RuntimeError("input payload must contain events list")

    errors: list[str] = []
    exceptions: list[dict[str, Any]] = []
    http_only_success_count = 0

    for idx, row in enumerate(events):
        if not isinstance(row, dict):
            errors.append(f"events[{idx}] must be object")
            continue
        missing = sorted(field for field in REQUIRED_EVENT_FIELDS if field not in row)
        if missing:
            errors.append(f"events[{idx}] missing fields: {','.join(missing)}")
            continue

        order_code = str(row.get("order_code") or "")
        action = str(row.get("action") or "")
        http_success = bool(row.get("http_success"))
        confirmed = bool(row.get("confirmed"))
        pre_state = str(row.get("pre_state") or "")
        post_state = str(row.get("post_state") or "")

        if http_success and not confirmed:
            http_only_success_count += 1
            msg = f"events[{idx}] HTTP success without confirmed state transition (order={order_code}, action={action})"
            errors.append(msg)
            exceptions.append(
                {
                    "order_code": order_code,
                    "action": action,
                    "reason": "http_success_without_transition_confirmation",
                    "pre_state": pre_state,
                    "post_state": post_state,
                }
            )
            continue

        if confirmed and not http_success:
            errors.append(
                f"events[{idx}] invalid confirmed=true with http_success=false (order={order_code}, action={action})"
            )
            exceptions.append(
                {
                    "order_code": order_code,
                    "action": action,
                    "reason": "confirmed_without_http_success",
                    "pre_state": pre_state,
                    "post_state": post_state,
                }
            )
            continue

        if confirmed and (not post_state or post_state == pre_state):
            errors.append(
                f"events[{idx}] confirmed transition requires changed post_state (order={order_code}, action={action})"
            )
            exceptions.append(
                {
                    "order_code": order_code,
                    "action": action,
                    "reason": "confirmed_without_state_change",
                    "pre_state": pre_state,
                    "post_state": post_state,
                }
            )

    ok = len(errors) == 0
    result = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "as_of": resolved_as_of,
        "status": "PASS" if ok else "FAIL",
        "ok": ok,
        "events_checked": len(events),
        "http_only_success_count": http_only_success_count,
        "errors": errors,
        "exceptions": exceptions,
        "input_path": str(src),
    }

    out_dir = Path(output_root).resolve() / resolved_as_of
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "api_state_transition_exceptions.json"
    md_path = out_dir / "api_state_transition_exceptions.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_render_md(result), encoding="utf-8")

    result["json_path"] = str(json_path)
    result["md_path"] = str(md_path)

    if strict and not ok:
        raise RuntimeError("kaspi state transition validation failed: " + "; ".join(errors))
    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate Kaspi API state transition events")
    parser.add_argument("--input", type=Path, required=True, help="Path to transition events JSON")
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    report = validate_kaspi_state_transition(
        input_path=args.input,
        as_of=args.as_of,
        output_root=args.output_root,
        strict=bool(args.strict),
    )
    print(f"api_state_transition_json={report['json_path']}")
    print(f"api_state_transition_md={report['md_path']}")
    print(f"http_only_success_count={report['http_only_success_count']}")
    print(f"status={report['status']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
