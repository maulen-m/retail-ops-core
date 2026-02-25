#!/usr/bin/env python3
"""Build deterministic domain scorecards for PO, inventory, cashflow, and truth drift."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import shlex
import subprocess
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "daily"
Runner = Callable[[str, Path], tuple[int, str]]


def _run_shell(cmd: str, cwd: Path) -> tuple[int, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        shell=True,
        text=True,
        capture_output=True,
    )
    output = ((proc.stdout or "") + (proc.stderr or "")).strip()
    return int(proc.returncode), output


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_md(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        f"# {payload['domain']} scorecard",
        "",
        f"- generated_at: `{payload['generated_at']}`",
        f"- as_of: `{payload['as_of']}`",
        f"- status: `{payload['status']}`",
        f"- command: `{payload['command']}`",
        f"- rc: `{payload['rc']}`",
        "",
        "## Summary",
        "",
        f"- {payload['summary']}",
    ]
    if payload.get("details"):
        lines.extend(["", "## Details", ""])
        for line in payload["details"]:
            lines.append(f"- {line}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _build_scorecard(
    *,
    domain: str,
    as_of: str,
    cmd: str,
    rc: int,
    output: str,
    details: list[str] | None = None,
) -> dict[str, Any]:
    summary = output.splitlines()[-1] if output else ""
    return {
        "domain": domain,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "as_of": as_of,
        "command": cmd,
        "rc": int(rc),
        "status": "GREEN" if rc == 0 else "RED",
        "summary": summary or ("PASS" if rc == 0 else "FAIL"),
        "details": details or [],
        "raw_output": output,
    }


def build_domain_scorecards(
    *,
    project_root: Path,
    as_of: str,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    strict: bool = False,
    runner: Runner | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    out_dir = Path(output_root).resolve() / as_of
    out_dir.mkdir(parents=True, exist_ok=True)
    run = runner or _run_shell

    quoted_root = shlex.quote(str(root))
    quoted_as_of = shlex.quote(as_of)

    report: dict[str, Any] = {
        "as_of": as_of,
        "output_dir": str(out_dir),
        "scorecards": {},
        "ok": True,
        "exit_code": 0,
    }

    specs = [
        ("po", f"python3 scripts/validate_po_money_gate.py --project-root {quoted_root} --json"),
        ("inventory", "python3 scripts/validate_inventory_cost_drift.py"),
        ("cashflow", "python3 scripts/validate_cashflow_invariants.py"),
        (
            "portfolio",
            (
                "python3 scripts/build_portfolio_completeness_report.py "
                f"--strict --as-of {quoted_as_of} "
                f"--db {shlex.quote(str(root / 'db' / 'app.db'))} "
                f"--output-root {shlex.quote(str(out_dir.parent))}"
            ),
        ),
    ]
    for domain, cmd in specs:
        rc, output = run(cmd, root)
        details: list[str] = []
        if domain == "po":
            try:
                parsed = json.loads(output)
                required_failed = parsed.get("required_failed") or []
                if required_failed:
                    details.append(f"required_failed={','.join(required_failed)}")
                details.append(f"checks={len(parsed.get('checks') or [])}")
            except Exception:
                details.append("po_json_parse=failed")
        payload = _build_scorecard(domain=domain, as_of=as_of, cmd=cmd, rc=rc, output=output, details=details)
        _write_json(out_dir / f"{domain}_scorecard.json", payload)
        _write_md(out_dir / f"{domain}_scorecard.md", payload)
        report["scorecards"][domain] = payload
        if rc != 0:
            report["ok"] = False

    drift_build_cmd = f"python3 scripts/build_ops_drift_pack.py --as-of {quoted_as_of}"
    drift_validate_cmd = (
        f"python3 scripts/validate_drift_pack_slo.py --strict --as-of {quoted_as_of} "
        f"--output-root {shlex.quote(str(root / 'exports' / 'validation'))}"
    )
    build_rc, build_output = run(drift_build_cmd, root)
    validate_rc, validate_output = run(drift_validate_cmd, root)
    drift_rc = 0 if (build_rc == 0 and validate_rc == 0) else 1
    drift_payload = _build_scorecard(
        domain="truth_drift",
        as_of=as_of,
        cmd=f"{drift_build_cmd} && {drift_validate_cmd}",
        rc=drift_rc,
        output=(validate_output if validate_output else build_output),
        details=[
            f"build_rc={build_rc}",
            f"validate_rc={validate_rc}",
        ],
    )
    _write_json(out_dir / "truth_drift_report.json", drift_payload)
    _write_md(out_dir / "truth_drift_report.md", drift_payload)
    report["scorecards"]["truth_drift"] = drift_payload
    if drift_rc != 0:
        report["ok"] = False

    report["exit_code"] = 0 if report["ok"] else (1 if strict else 0)
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build daily domain scorecards (PO/inventory/cashflow/truth)")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--as-of", default=date.today().isoformat())
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    report = build_domain_scorecards(
        project_root=args.project_root,
        as_of=args.as_of,
        output_root=args.output_root,
        strict=bool(args.strict),
    )
    print(f"output_dir={report['output_dir']}")
    print(f"status={'PASS' if report['ok'] else 'FAIL'}")
    for domain, payload in report["scorecards"].items():
        print(f"{domain}={payload['status']}")
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
