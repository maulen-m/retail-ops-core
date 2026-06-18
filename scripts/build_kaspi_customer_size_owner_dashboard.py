#!/usr/bin/env python3
"""Build owner-facing dashboard artifacts for the Kaspi customer-size workflow."""
from __future__ import annotations

import argparse
import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _latest_workflow_dir() -> Path:
    matches = [
        path
        for path in (REPO_ROOT / "exports" / "validation").glob(
            "kaspi_customer_size_workflow_readiness_*"
        )
        if (path / "manifest.json").exists()
    ]
    if not matches:
        raise FileNotFoundError("No kaspi_customer_size_workflow_readiness_* packet found")
    return max(matches, key=lambda path: (path / "manifest.json").stat().st_mtime)


def _default_output_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return REPO_ROOT / "exports" / "validation" / f"kaspi_customer_size_owner_dashboard_{stamp}"


def _load_approval_phrase(blockers: list[dict[str, Any]]) -> tuple[str, str]:
    for blocker in blockers:
        phrase_path = str(blocker.get("approval_phrase_file") or "").strip()
        if not phrase_path:
            continue
        path = Path(phrase_path)
        if not path.exists():
            continue
        return phrase_path, path.read_text(encoding="utf-8").strip()
    return "", ""


def _load_live_send_approval_phrase(approval_dir: Path | None) -> tuple[str, str]:
    if not approval_dir:
        return "", ""
    phrase_path = approval_dir / "REQUIRED_EXACT_LIVE_SEND_CANARY_APPROVAL_PHRASE.txt"
    if not phrase_path.exists():
        return "", ""
    return str(phrase_path), phrase_path.read_text(encoding="utf-8").strip()


def _status_badge(gate: str) -> str:
    normalized = str(gate or "").upper()
    if normalized.startswith("GREEN"):
        return "READY"
    if normalized.startswith("YELLOW") or normalized.startswith("BLOCKED"):
        return "WAIT"
    if normalized.startswith("RED"):
        return "STOP"
    return "INFO"


def _build_markdown(
    *,
    workflow_dir: Path,
    manifest: dict[str, Any],
    stages: list[dict[str, Any]],
    blockers: list[dict[str, Any]],
    approval_phrase_path: str,
    approval_phrase: str,
) -> str:
    summary = manifest.get("ledger_summary") or {}
    lines = [
        "# Kaspi Customer Size Workflow Owner Dashboard",
        "",
        f"Gate: {manifest.get('gate')}",
        "",
        f"- Source packet: {workflow_dir}",
        f"- Ledger rows: {summary.get('ledger_rows', 0)}",
        f"- Pending live-send canary rows: {summary.get('pending_live_send_canary_count', 0)}",
        f"- Board-ready size rows: {summary.get('google_board_size_fill_ready_count', 0)}",
        f"- Retained blockers: {manifest.get('blockers_count', len(blockers))}",
        "",
        "## Current Stopline",
        "",
    ]
    if blockers:
        lines.extend(f"- {row.get('stage')}: {row.get('blocker')}" for row in blockers)
    else:
        lines.append("- No retained blockers in the source packet.")
    lines.extend(
        [
            "",
            "## Stages",
            "",
            "| Seq | Status | Stage | Gate | Count | Next Action |",
            "| --- | --- | --- | --- | ---: | --- |",
        ]
    )
    for row in stages:
        lines.append(
            "| {sequence} | {badge} | {stage} | {gate} | {count} | {next_action} |".format(
                sequence=row.get("sequence", ""),
                badge=_status_badge(str(row.get("gate") or "")),
                stage=row.get("stage", ""),
                gate=row.get("gate", ""),
                count=row.get("current_count", 0),
                next_action=row.get("next_action", ""),
            )
        )
    lines.extend(
        [
            "",
            "## Exact Next Approval",
            "",
        ]
    )
    if approval_phrase:
        lines.extend(
            [
                f"- Source: {approval_phrase_path}",
                "",
                "```text",
                approval_phrase,
                "```",
            ]
        )
    else:
        lines.append("- No approval phrase file was available in retained blockers.")
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "- Customer send allowed now: false",
            "- Kaspi chat write allowed now: false",
            "- Google Board write allowed now: false",
            "- Production DB write allowed now: false",
            "- Telegram/WhatsApp send allowed now: false",
            "- Raw order IDs exported: false",
            "- Raw reply text exported: false",
            "",
        ]
    )
    return "\n".join(lines)


def _build_html(markdown_text: str, manifest: dict[str, Any], stages: list[dict[str, Any]]) -> str:
    gate = html.escape(str(manifest.get("gate") or ""))
    rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(str(row.get('sequence', '')))}</td>"
        f"<td><span class='badge {html.escape(_status_badge(str(row.get('gate') or '')).lower())}'>{html.escape(_status_badge(str(row.get('gate') or '')))}</span></td>"
        f"<td>{html.escape(str(row.get('stage') or ''))}</td>"
        f"<td>{html.escape(str(row.get('gate') or ''))}</td>"
        f"<td>{html.escape(str(row.get('current_count', 0)))}</td>"
        f"<td>{html.escape(str(row.get('next_action') or ''))}</td>"
        "</tr>"
        for row in stages
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Kaspi Customer Size Workflow Owner Dashboard</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #17202a;
      --muted: #667085;
      --paper: #fbfaf7;
      --panel: #ffffff;
      --line: #e5ded2;
      --green: #16794c;
      --yellow: #9a6700;
      --red: #b42318;
      --blue: #175cd3;
    }}
    body {{
      margin: 0;
      padding: 32px;
      background: radial-gradient(circle at top left, #f4ead7, transparent 34rem), var(--paper);
      color: var(--ink);
      font-family: ui-serif, Georgia, Cambria, "Times New Roman", serif;
    }}
    main {{
      max-width: 1180px;
      margin: 0 auto;
    }}
    h1 {{
      font-size: clamp(32px, 4vw, 56px);
      line-height: 0.96;
      margin: 0 0 16px;
      letter-spacing: -0.04em;
    }}
    .gate {{
      display: inline-block;
      padding: 10px 14px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: var(--panel);
      color: var(--blue);
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 13px;
    }}
    .panel {{
      background: color-mix(in srgb, var(--panel) 92%, transparent);
      border: 1px solid var(--line);
      border-radius: 22px;
      padding: 22px;
      margin-top: 20px;
      box-shadow: 0 18px 60px rgba(74, 57, 33, 0.08);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
      font-size: 14px;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 11px 10px;
      text-align: left;
      vertical-align: top;
    }}
    th {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .badge {{
      display: inline-block;
      min-width: 48px;
      text-align: center;
      border-radius: 999px;
      padding: 4px 8px;
      font-weight: 700;
      font-size: 12px;
    }}
    .badge.ready {{ color: var(--green); background: #e9f8ef; }}
    .badge.wait {{ color: var(--yellow); background: #fff3cf; }}
    .badge.stop {{ color: var(--red); background: #ffe9e6; }}
    .badge.info {{ color: var(--blue); background: #eaf1ff; }}
    pre {{
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      background: #111827;
      color: #f8fafc;
      border-radius: 18px;
      padding: 18px;
      font-size: 13px;
      line-height: 1.5;
    }}
    @media (max-width: 760px) {{
      body {{ padding: 18px; }}
      table {{ display: block; overflow-x: auto; }}
    }}
  </style>
</head>
<body>
<main>
  <h1>Kaspi Customer Size Workflow</h1>
  <div class="gate">{gate}</div>
  <section class="panel">
    <h2>Stage Map</h2>
    <table>
      <thead>
        <tr><th>Seq</th><th>Status</th><th>Stage</th><th>Gate</th><th>Count</th><th>Next Action</th></tr>
      </thead>
      <tbody>
        {rows}
      </tbody>
    </table>
  </section>
  <section class="panel">
    <h2>Markdown Source</h2>
    <pre>{html.escape(markdown_text)}</pre>
  </section>
</main>
</body>
</html>
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow-dir", type=Path, help="Directory with manifest/workflow_stages/blockers.")
    parser.add_argument(
        "--live-send-approval-dir",
        type=Path,
        help="Optional directory containing REQUIRED_EXACT_LIVE_SEND_CANARY_APPROVAL_PHRASE.txt.",
    )
    parser.add_argument("--output-dir", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    workflow_dir = (args.workflow_dir or _latest_workflow_dir()).resolve()
    output_dir = args.output_dir or (
        workflow_dir / "owner_dashboard"
    )
    manifest = _read_json(workflow_dir / "manifest.json")
    stages = _read_json(workflow_dir / "workflow_stages.json")
    blockers = _read_json(workflow_dir / "retained_blockers.json")
    approval_phrase_path, approval_phrase = _load_approval_phrase(blockers)
    live_send_phrase_path, live_send_phrase = _load_live_send_approval_phrase(
        args.live_send_approval_dir.resolve() if args.live_send_approval_dir else None
    )
    if live_send_phrase:
        approval_phrase_path = live_send_phrase_path
        approval_phrase = live_send_phrase
    markdown_text = _build_markdown(
        workflow_dir=workflow_dir,
        manifest=manifest,
        stages=stages,
        blockers=blockers,
        approval_phrase_path=approval_phrase_path,
        approval_phrase=approval_phrase,
    )
    html_text = _build_html(markdown_text, manifest, stages)
    _write_text(output_dir / "owner_dashboard.md", markdown_text)
    _write_text(output_dir / "owner_dashboard.html", html_text)
    dashboard_manifest = {
        "gate": "GREEN_OWNER_DASHBOARD_BUILT_FROM_REDACTED_WORKFLOW_PACKET",
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "workflow_dir": str(workflow_dir),
        "markdown_path": str(output_dir / "owner_dashboard.md"),
        "html_path": str(output_dir / "owner_dashboard.html"),
        "approval_phrase_included": bool(approval_phrase),
        "approval_phrase_source": approval_phrase_path,
        "customer_send_allowed": False,
        "kaspi_chat_write_allowed": False,
        "google_board_write_allowed": False,
        "db_write_allowed": False,
        "raw_order_id_exported": False,
        "raw_reply_text_exported": False,
    }
    _write_text(
        output_dir / "manifest.json",
        json.dumps(dashboard_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    print(json.dumps(dashboard_manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
