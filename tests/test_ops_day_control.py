import json
import subprocess
from pathlib import Path

import pytest

from scripts import ops_day_control as control


TARGET_DATE = "2026-07-18"


@pytest.fixture(autouse=True)
def _isolated_audit_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    audit_root = tmp_path / "audit"
    monkeypatch.setattr(control, "DEFAULT_AUDIT_ROOT", audit_root)
    return audit_root


def _write_send_batch(
    today_folder: Path,
    *,
    batch: str,
    target_date: str = TARGET_DATE,
    ledger_state: str = "api_started",
) -> Path:
    batch_root = today_folder / "MERGED" / "SEND" / batch
    batch_root.mkdir(parents=True, exist_ok=True)
    manifest_path = batch_root / "send_batch_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 4,
                "target_date": target_date,
                "entries": [{"pdf_key": "pdf-a"}],
            }
        ),
        encoding="utf-8",
    )
    (batch_root / "telegram_send_ledger.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "entries": {
                    "pdf-a": {
                        "state": ledger_state,
                        "history": [{"state": ledger_state, "at": "before"}],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return manifest_path


def test_mark_store_fulfilled_is_dry_run_by_default_and_is_audited(
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "workflow_runs"

    rc = control.main(
        [
            "--date",
            TARGET_DATE,
            "--run-root",
            str(run_root),
            "mark-store-fulfilled",
            "--store",
            "Universal",
            "--reason",
            "owner sent manually",
        ]
    )

    assert rc == 0
    assert not (run_root / TARGET_DATE / "closeout_checkpoint.json").exists()
    audit_rows = (control.DEFAULT_AUDIT_ROOT / f"{TARGET_DATE}.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    assert len(audit_rows) == 1
    assert json.loads(audit_rows[0])["command"] == "mark-store-fulfilled"


def test_apply_requires_env_gate_and_records_failed_attempt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv(control.APPLY_ENV_GATE, raising=False)
    run_root = tmp_path / "workflow_runs"

    rc = control.main(
        [
            "--date",
            TARGET_DATE,
            "--run-root",
            str(run_root),
            "--apply",
            "mark-store-fulfilled",
            "--store",
            "UNIVERSAL",
            "--reason",
            "owner sent manually",
        ]
    )

    assert rc == 1
    assert not (run_root / TARGET_DATE / "closeout_checkpoint.json").exists()
    audit = json.loads(
        (control.DEFAULT_AUDIT_ROOT / f"{TARGET_DATE}.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()[0]
    )
    assert audit["returncode"] == 1
    assert "ENABLE_OPS_DAY_CONTROL=1" in audit["result"]["error"]


def test_postpone_store_apply_writes_through_day_state_module(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(control.APPLY_ENV_GATE, "1")
    run_root = tmp_path / "workflow_runs"

    rc = control.main(
        [
            "--date",
            TARGET_DATE,
            "--run-root",
            str(run_root),
            "--apply",
            "postpone-store",
            "--store",
            "STORE-B",
            "--postponed-to",
            "2026-07-19",
            "--reason",
            "pickup moved",
            "--set-by",
            "operator-a",
        ]
    )

    assert rc == 0
    payload = json.loads(
        (run_root / TARGET_DATE / "closeout_checkpoint.json").read_text(
            encoding="utf-8"
        )
    )
    record = payload["store_day_states"]["stores"]["STOREB"]
    assert record["state"] == "POSTPONED"
    assert record["postponed_to"] == "2026-07-19"


def test_send_store_telegram_pins_newest_manifest_and_stamps_auto_sent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(control.APPLY_ENV_GATE, "1")
    today_folder = tmp_path / "Today"
    _write_send_batch(today_folder, batch="older")
    newest = _write_send_batch(today_folder, batch="newest")
    newest.touch()
    observed: dict[str, object] = {}

    def _fake_run(command, **kwargs):
        observed["command"] = command
        observed["kwargs"] = kwargs
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"ok": True, "sent": 1}),
            stderr="",
        )

    monkeypatch.setattr(control.subprocess, "run", _fake_run)
    run_root = tmp_path / "workflow_runs"
    rc = control.main(
        [
            "--date",
            TARGET_DATE,
            "--run-root",
            str(run_root),
            "--apply",
            "send-store-telegram",
            "--store",
            "Universal",
            "--today-folder",
            str(today_folder),
        ]
    )

    assert rc == 0
    command = list(observed["command"])
    assert command[command.index("--manifest-path") + 1] == str(newest)
    assert command[command.index("--store") + 1] == "UNIVERSAL"
    assert len(command[command.index("--manifest-sha256") + 1]) == 64
    payload = json.loads(
        (run_root / TARGET_DATE / "closeout_checkpoint.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["store_day_states"]["stores"]["UNIVERSAL"]["state"] == "AUTO_SENT"


def test_clear_stuck_send_entry_resets_non_confirmed_with_history_note(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(control.APPLY_ENV_GATE, "1")
    today_folder = tmp_path / "Today"
    manifest_path = _write_send_batch(today_folder, batch="batch")

    rc = control.main(
        [
            "--date",
            TARGET_DATE,
            "--apply",
            "clear-stuck-send-entry",
            "--entry",
            "pdf-a",
            "--today-folder",
            str(today_folder),
            "--reason",
            "confirmed no Telegram request left the process",
            "--set-by",
            "operator-a",
        ]
    )

    assert rc == 0
    ledger = json.loads(
        (manifest_path.parent / "telegram_send_ledger.json").read_text(
            encoding="utf-8"
        )
    )
    entry = ledger["entries"]["pdf-a"]
    assert entry["state"] == "pending"
    assert "operator-a" in entry["history"][-1]["note"]


def test_clear_stuck_send_entry_refuses_confirmed_entry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(control.APPLY_ENV_GATE, "1")
    today_folder = tmp_path / "Today"
    manifest_path = _write_send_batch(
        today_folder,
        batch="batch",
        ledger_state="confirmed",
    )
    before = (manifest_path.parent / "telegram_send_ledger.json").read_bytes()

    rc = control.main(
        [
            "--date",
            TARGET_DATE,
            "--apply",
            "clear-stuck-send-entry",
            "--entry",
            "pdf-a",
            "--today-folder",
            str(today_folder),
            "--reason",
            "operator requested reset",
        ]
    )

    assert rc == 1
    assert (manifest_path.parent / "telegram_send_ledger.json").read_bytes() == before
