#!/usr/bin/env python3
"""Probe the live LINE31 landing page customer-visible label without external writes."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any
from zoneinfo import ZoneInfo


ALMATY_TZ = ZoneInfo("Asia/Almaty")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation"
DEFAULT_URL = "https://acmewear.pro/line31"
REQUIRED_LABEL = "AcmeWear 3в1"
FORBIDDEN_LABELS = ["ACMEWEAR LINE31", "AcmeWear LINE31"]
REQUIRED_ROUTES = ["/go/starry-black", "/go/ivory-white-starry-black"]


class ProbeError(RuntimeError):
    """Raised when the probe cannot read the target page."""


def _run_id() -> str:
    return datetime.now(ALMATY_TZ).strftime("%Y%m%d_%H%M%S")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _check(rows: list[dict[str, str]], name: str, ok: bool, detail: str) -> None:
    rows.append(
        {
            "check": name,
            "status": "PASS" if ok else "FAIL",
            "detail": detail,
        }
    )


def validate_html(html: str, *, status_code: int, effective_url: str, url: str) -> dict[str, Any]:
    rows: list[dict[str, str]] = []
    _check(rows, "http_status_200", status_code == 200, str(status_code))
    _check(rows, "effective_url_line31", effective_url.startswith(url), effective_url)
    _check(rows, "required_customer_label_present", REQUIRED_LABEL in html, REQUIRED_LABEL)
    for label in FORBIDDEN_LABELS:
        _check(rows, f"forbidden_label_absent_{label.replace(' ', '_')}", label not in html, label)
    for route in REQUIRED_ROUTES:
        _check(rows, f"required_route_present_{route.strip('/').replace('/', '_')}", route in html, route)
    _check(rows, "raw_kaspi_product_href_absent", "kaspi.kz/shop/p/" not in html, "kaspi.kz/shop/p/")
    _check(rows, "title_uses_required_label", f"<title>{REQUIRED_LABEL}" in html, REQUIRED_LABEL)
    failures = [row for row in rows if row["status"] == "FAIL"]
    return {
        "gate": "GREEN_LINE31_LIVE_CUSTOMER_LABEL_VERIFIED_NO_WRITE"
        if not failures
        else "YELLOW_LINE31_LIVE_CUSTOMER_LABEL_REVIEW_REQUIRED_NO_WRITE",
        "checks": rows,
        "checks_total": len(rows),
        "checks_failed": len(failures),
        "failed_checks": failures,
        "summary": {
            "url": url,
            "effective_url": effective_url,
            "http_status": status_code,
            "required_customer_label": REQUIRED_LABEL,
            "forbidden_labels": FORBIDDEN_LABELS,
            "required_routes": REQUIRED_ROUTES,
            "contains_required_customer_label": REQUIRED_LABEL in html,
            "contains_forbidden_customer_label": any(label in html for label in FORBIDDEN_LABELS),
            "contains_raw_kaspi_product_href": "kaspi.kz/shop/p/" in html,
        },
    }


def _fetch_live_html(*, url: str, output_path: Path, timeout_seconds: int) -> tuple[str, int, str]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [
            "curl",
            "-LsS",
            "--max-time",
            str(timeout_seconds),
            "-o",
            str(output_path),
            "-w",
            "%{http_code}\t%{url_effective}",
            url,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise ProbeError(f"curl failed with code {completed.returncode}: {completed.stderr.strip()}")
    parts = completed.stdout.strip().split("\t", 1)
    if len(parts) != 2:
        raise ProbeError(f"unexpected curl write-out: {completed.stdout!r}")
    status_code = int(parts[0])
    effective_url = parts[1]
    return output_path.read_text(encoding="utf-8", errors="replace"), status_code, effective_url


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["check", "status", "detail"])
        writer.writeheader()
        writer.writerows(rows)


def _write_closeout(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# LINE31 Live Customer Label Probe",
        "",
        f"Gate: {payload['gate']}",
        "",
        "## Boundary",
        "",
        "- Read-only HTTP GET of the public LINE31 landing page.",
        "- No website deploy, Meta write, Kaspi/WebUI/API write, DB/workbook write, or owner publication.",
        "",
        "## Result",
        "",
        f"- URL: `{payload['summary']['url']}`",
        f"- Effective URL: `{payload['summary']['effective_url']}`",
        f"- HTTP status: `{payload['summary']['http_status']}`",
        f"- Required label present: `{payload['summary']['contains_required_customer_label']}`",
        f"- Forbidden LINE31 label present: `{payload['summary']['contains_forbidden_customer_label']}`",
        f"- Raw Kaspi product href present: `{payload['summary']['contains_raw_kaspi_product_href']}`",
        f"- Checks total: `{payload['checks_total']}`",
        f"- Checks failed: `{payload['checks_failed']}`",
        f"- Landing HTML SHA-256: `{payload.get('landing_html_sha256', '')}`",
        f"- Checks CSV: `{payload['checks_csv']}`",
        "",
    ]
    if payload["failed_checks"]:
        lines.extend(["## Failed Checks", ""])
        lines.extend(f"- `{row['check']}`: {row['detail']}" for row in payload["failed_checks"])
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def build_probe(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = args.output_root.expanduser().resolve() / f"line31_live_customer_label_probe_{args.run_id or _run_id()}"
    output_dir.mkdir(parents=True, exist_ok=True)
    html_path = output_dir / "landing.html"
    if args.html_file:
        html_path.write_text(args.html_file.expanduser().read_text(encoding="utf-8"), encoding="utf-8")
        html = html_path.read_text(encoding="utf-8")
        status_code = args.html_status_code
        effective_url = args.url
    else:
        html, status_code, effective_url = _fetch_live_html(
            url=args.url,
            output_path=html_path,
            timeout_seconds=args.timeout_seconds,
        )
    validation = validate_html(html, status_code=status_code, effective_url=effective_url, url=args.url)
    checks_path = output_dir / "checks.csv"
    manifest_path = output_dir / "manifest.json"
    closeout_path = output_dir / "closeout.md"
    _write_csv(checks_path, validation["checks"])
    payload = {
        **{key: value for key, value in validation.items() if key != "checks"},
        "generated_at": datetime.now(ALMATY_TZ).isoformat(timespec="seconds"),
        "landing_html_path": str(html_path),
        "landing_html_sha256": _sha256(html_path),
        "checks_csv": str(checks_path),
        "closeout_path": str(closeout_path),
        "output_dir": str(output_dir),
        "external_write_attempted": False,
        "website_write_attempted": False,
        "meta_write_attempted": False,
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_closeout(closeout_path, payload)
    return {**payload, "manifest_path": str(manifest_path)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--timeout-seconds", type=int, default=20)
    parser.add_argument("--html-file", type=Path)
    parser.add_argument("--html-status-code", type=int, default=200)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        payload = build_probe(args)
    except (OSError, ProbeError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"{payload['gate']} evidence={payload['output_dir']}")
    return 0 if not payload["checks_failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
