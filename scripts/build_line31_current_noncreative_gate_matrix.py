#!/usr/bin/env python3
"""Build the current LINE31 non-creative readiness matrix from read-only validators."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import shlex
import subprocess
import sys
from typing import Any, Iterable
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALMATY_TZ = ZoneInfo("Asia/Almaty")
DEFAULT_OUTPUT_ROOT = (
    PROJECT_ROOT / "exports" / "validation" / "line31_current_noncreative_gate_refresh_current"
)


@dataclass(frozen=True)
class ValidatorSpec:
    gate: str
    command: tuple[str, ...]
    retained_blocker: str
    evidence_summary_ok: str
    evidence_summary_fail: str
    blocking_for_green_except_creative: bool = True
    scope: str = "line31_launch_blocking"


DEFAULT_VALIDATORS = (
    ValidatorSpec(
        gate="strict_repo_gate",
        command=(sys.executable, "scripts/validate_params.py", "--strict"),
        retained_blocker="strict_repo_gate",
        evidence_summary_ok="validate_params.py --strict passed.",
        evidence_summary_fail="validate_params.py --strict failed.",
        blocking_for_green_except_creative=False,
        scope="repo_wide_advisory",
    ),
    ValidatorSpec(
        gate="on_delivery_freeze",
        command=(sys.executable, "scripts/validate_on_delivery_freeze.py", "--until", "2026-05-31"),
        retained_blocker="compact_child_on_delivery_cost",
        evidence_summary_ok="on-delivery freeze validation passed.",
        evidence_summary_fail="on-delivery freeze validation failed.",
    ),
    ValidatorSpec(
        gate="cogs_integrity",
        command=(sys.executable, "scripts/validate_cogs_integrity.py", "--as-of", "2026-05-31"),
        retained_blocker="compact_child_cogs_integrity",
        evidence_summary_ok="COGS integrity validation passed.",
        evidence_summary_fail="COGS integrity validation failed.",
    ),
    ValidatorSpec(
        gate="profit_publication_integrity",
        command=(
            sys.executable,
            "scripts/validate_profit_publication_integrity.py",
            "--as-of",
            "2026-05-31",
        ),
        retained_blocker="profit_publication_integrity",
        evidence_summary_ok="profit publication integrity validation passed.",
        evidence_summary_fail="profit publication integrity validation failed.",
    ),
    ValidatorSpec(
        gate="po_dashboard_stock_freshness",
        command=(sys.executable, "scripts/validate_po_dashboard_invariants.py"),
        retained_blocker="generic_po_dashboard_stock_freshness_validator",
        evidence_summary_ok="generic PO dashboard invariants passed.",
        evidence_summary_fail="generic PO dashboard invariants failed.",
    ),
)


def _safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in value)


def _write_json(path: Path, data: Any) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _run_validator(spec: ValidatorSpec, *, cwd: Path, output_dir: Path) -> dict[str, Any]:
    completed = subprocess.run(
        spec.command,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    name = _safe_name(spec.gate)
    stdout_path = output_dir / f"{name}.stdout"
    stderr_path = output_dir / f"{name}.stderr"
    stdout_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")
    ok = completed.returncode == 0
    return {
        "gate": spec.gate,
        "status": "GREEN"
        if ok
        else ("YELLOW_ADVISORY" if not spec.blocking_for_green_except_creative else "YELLOW"),
        "scope": spec.scope,
        "blocking_for_green_except_creative": spec.blocking_for_green_except_creative,
        "command": shlex.join(spec.command),
        "exit_code": completed.returncode,
        "retained_blocker": "" if ok else spec.retained_blocker,
        "evidence_summary": spec.evidence_summary_ok if ok else spec.evidence_summary_fail,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
    }


def _summary_markdown(matrix: dict[str, Any]) -> str:
    lines = [
        "# LINE31 Current Non-Creative Gate Matrix",
        "",
        f"Generated: {matrix['generated_at']}",
        "",
        f"Overall gate: `{matrix['overall_gate']}`",
        f"Can use GREEN_EXCEPT_CREATIVE: `{str(matrix['can_use_green_except_creative']).lower()}`",
        "",
        "## Validator Status",
        "",
        "| gate | status | scope | blocking | command | retained blocker |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in matrix["final_status"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{row['gate']}`",
                    f"`{row['status']}`",
                    f"`{row.get('scope', '')}`",
                    f"`{str(row.get('blocking_for_green_except_creative', True)).lower()}`",
                    f"`{row['command']}`",
                    row["retained_blocker"] or "",
                ]
            )
            + " |"
        )
    if matrix.get("advisory_repo_blockers"):
        lines.extend(
            [
                "",
                "## Advisory Repo-Wide Blockers",
                "",
                "These are recorded for the broader Autonomous_business health queue, but they do not block LINE31 `GREEN_EXCEPT_CREATIVE` when all LINE31 launch-blocking gates pass.",
                "",
            ]
        )
        lines.extend(f"- `{item}`" for item in matrix["advisory_repo_blockers"])
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "This matrix is generated from read-only validators only. It does not perform DB, workbook, scheduler, source-pointer, Web_automation, Kaspi/API/WebUI/Meta, campaign, price, stock, cash, PO, supplier, or publication writes.",
            "",
        ]
    )
    return "\n".join(lines)


def build_matrix(
    *,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    run_id: str | None = None,
    validators: Iterable[ValidatorSpec] = DEFAULT_VALIDATORS,
    cwd: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    run_id = run_id or datetime.now(ALMATY_TZ).strftime("%Y%m%d_%H%M%S")
    generated_at = datetime.now(ALMATY_TZ).isoformat(timespec="seconds")
    evidence_dir = output_root / "validator_outputs" / run_id
    evidence_dir.mkdir(parents=True, exist_ok=True)

    rows = [_run_validator(spec, cwd=cwd, output_dir=evidence_dir) for spec in validators]
    retained = [
        row["retained_blocker"]
        for row in rows
        if row["retained_blocker"] and row["blocking_for_green_except_creative"]
    ]
    advisory = [
        row["retained_blocker"]
        for row in rows
        if row["retained_blocker"] and not row["blocking_for_green_except_creative"]
    ]
    can_use_green = not retained
    matrix = {
        "generated_at": generated_at,
        "round": "current_noncreative_gate_refresh",
        "overall_gate": "GREEN" if can_use_green else "YELLOW",
        "can_use_green_except_creative": can_use_green,
        "gate_reason": (
            "All LINE31 launch-blocking non-creative validators passed."
            if can_use_green and advisory
            else (
                "All current non-creative validators passed."
                if can_use_green
                else "One or more LINE31 launch-blocking non-creative validators failed."
            )
        ),
        "evidence_root": str(output_root),
        "validator_output_dir": str(evidence_dir),
        "final_status": rows,
        "retained_noncreative_blockers": retained,
        "advisory_repo_blockers": advisory,
        "cleared_noncreative_gates": [row["gate"] for row in rows if row["status"] == "GREEN"],
        "no_external_writes_performed_by_matrix_refresh": True,
    }
    _write_json(output_root / "CURRENT_NONCREATIVE_GATE_MATRIX.json", matrix)
    (output_root / "CURRENT_NONCREATIVE_GATE_MATRIX.md").write_text(
        _summary_markdown(matrix),
        encoding="utf-8",
    )
    commands = ["gate\tscope\tblocking_for_green_except_creative\tcommand\texit_code\tstdout_path\tstderr_path"]
    for row in rows:
        commands.append(
            "\t".join(
                [
                    row["gate"],
                    row["scope"],
                    str(row["blocking_for_green_except_creative"]).lower(),
                    row["command"],
                    str(row["exit_code"]),
                    row["stdout_path"],
                    row["stderr_path"],
                ]
            )
        )
    (output_root / "COMMANDS_RUN.tsv").write_text("\n".join(commands) + "\n", encoding="utf-8")
    return matrix


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    matrix = build_matrix(output_root=args.output_root, run_id=args.run_id)
    if args.json:
        print(json.dumps(matrix, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"LINE31 current non-creative gate: {matrix['overall_gate']}")
        print(args.output_root / "CURRENT_NONCREATIVE_GATE_MATRIX.json")
    return 0 if matrix["can_use_green_except_creative"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
