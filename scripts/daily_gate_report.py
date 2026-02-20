#!/usr/bin/env python3
"""
Generate a daily green/red gate report from .claude/PROGRESS.md.

Output: reports/daily_gate_report_YYYY-MM-DD.md (default)
"""

import argparse
import re
from datetime import date
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROGRESS = PROJECT_ROOT / ".claude" / "PROGRESS.md"
DEFAULT_REPORTS_DIR = PROJECT_ROOT / "reports"


def parse_progress(progress_text: str) -> dict:
    last_oracle_pack = None
    last_green_commit = None
    gate_date = None
    gate_lines: list[str] = []

    lines = progress_text.splitlines()
    gate_header = re.compile(r"^## Gates run \\((\\d{4}-\\d{2}-\\d{2})\\)")

    for idx, line in enumerate(lines):
        if line.startswith("- Last oracle pack:"):
            last_oracle_pack = line.split(":", 1)[1].strip()
        if line.startswith("- Last known green commit:"):
            last_green_commit = line.split(":", 1)[1].strip()

        header_match = gate_header.match(line.strip())
        if header_match:
            gate_date = header_match.group(1)
            for next_line in lines[idx + 1:]:
                if next_line.startswith("## "):
                    break
                if "→" in next_line:
                    gate_lines.append(next_line.strip())
            break

    return {
        "last_oracle_pack": last_oracle_pack,
        "last_green_commit": last_green_commit,
        "gate_date": gate_date,
        "gate_lines": gate_lines,
    }


def summarize_status(gate_lines: list[str]) -> str:
    if not gate_lines:
        return "RED"
    return "GREEN" if all("PASS" in line for line in gate_lines) else "RED"


def build_report(summary: dict, report_date: str) -> str:
    status = summarize_status(summary.get("gate_lines", []))
    gate_date = summary.get("gate_date") or "UNKNOWN"
    last_oracle_pack = summary.get("last_oracle_pack") or "UNKNOWN"
    last_green_commit = summary.get("last_green_commit") or "UNKNOWN"

    lines = [
        f"# Daily Gate Report — {report_date}",
        "",
        f"Status: {status}",
        f"Gates date: {gate_date}",
        f"Last green commit: {last_green_commit}",
        f"Last oracle pack: {last_oracle_pack}",
        "",
        "Gates summary:",
    ]

    gate_lines = summary.get("gate_lines", [])
    if gate_lines:
        lines.extend([f"- {line}" for line in gate_lines])
    else:
        lines.append("- No gate entries found in PROGRESS.md")

    lines.append("")
    lines.append("Source: .claude/PROGRESS.md")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate daily gate report from PROGRESS.md")
    parser.add_argument("--progress", type=str, default=str(DEFAULT_PROGRESS), help="Path to PROGRESS.md")
    parser.add_argument("--output", type=str, help="Output path for report")
    parser.add_argument("--date", type=str, help="Report date (YYYY-MM-DD)")
    args = parser.parse_args()

    progress_path = Path(args.progress)
    if not progress_path.exists():
        print(f"ERROR: PROGRESS.md not found at {progress_path}")
        return 1

    report_date = args.date or date.today().isoformat()
    output_path = Path(args.output) if args.output else (
        DEFAULT_REPORTS_DIR / f"daily_gate_report_{report_date}.md"
    )

    summary = parse_progress(progress_path.read_text(encoding="utf-8"))
    report = build_report(summary, report_date)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")

    print(f"Wrote daily gate report: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
