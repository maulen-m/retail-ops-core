from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from scripts.probe_line31_live_customer_label import validate_html


def test_validate_html_green_for_current_customer_label() -> None:
    html = """
    <html>
      <head><title>AcmeWear 3в1 — Заказать на Kaspi</title></head>
      <body>
        <h1>AcmeWear 3в1</h1>
        <a href="/go/starry-black">Заказать</a>
        <a href="/go/ivory-white-starry-black">Выбрать цвет</a>
      </body>
    </html>
    """

    payload = validate_html(
        html,
        status_code=200,
        effective_url="https://acmewear.pro/line31",
        url="https://acmewear.pro/line31",
    )

    assert payload["gate"] == "GREEN_LINE31_LIVE_CUSTOMER_LABEL_VERIFIED_NO_WRITE"
    assert payload["checks_failed"] == 0
    assert payload["summary"]["contains_required_customer_label"] is True
    assert payload["summary"]["contains_forbidden_customer_label"] is False


def test_validate_html_yellow_for_stale_line31_label() -> None:
    html = """
    <html>
      <head><title>ACMEWEAR LINE31 — Заказать на Kaspi</title></head>
      <body>
        <h1>ACMEWEAR LINE31</h1>
        <a href="/go/starry-black">Заказать</a>
        <a href="/go/ivory-white-starry-black">Выбрать цвет</a>
      </body>
    </html>
    """

    payload = validate_html(
        html,
        status_code=200,
        effective_url="https://acmewear.pro/line31",
        url="https://acmewear.pro/line31",
    )

    assert payload["gate"] == "YELLOW_LINE31_LIVE_CUSTOMER_LABEL_REVIEW_REQUIRED_NO_WRITE"
    assert payload["checks_failed"] > 0
    failed_names = {row["check"] for row in payload["failed_checks"]}
    assert "required_customer_label_present" in failed_names
    assert "forbidden_label_absent_ACMEWEAR_LINE31" in failed_names


def test_probe_cli_with_html_file_writes_evidence(tmp_path: Path) -> None:
    html_path = tmp_path / "line31.html"
    html_path.write_text(
        """
        <html>
          <head><title>AcmeWear 3в1 — Заказать на Kaspi</title></head>
          <body>
            <h1>AcmeWear 3в1</h1>
            <a href="/go/starry-black">Заказать</a>
            <a href="/go/ivory-white-starry-black">Выбрать цвет</a>
          </body>
        </html>
        """,
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/probe_line31_live_customer_label.py",
            "--html-file",
            str(html_path),
            "--output-root",
            str(tmp_path),
            "--run-id",
            "unit",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["gate"] == "GREEN_LINE31_LIVE_CUSTOMER_LABEL_VERIFIED_NO_WRITE"
    assert Path(payload["manifest_path"]).is_file()
    assert Path(payload["checks_csv"]).is_file()
    assert payload["external_write_attempted"] is False
