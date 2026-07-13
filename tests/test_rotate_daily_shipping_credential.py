from __future__ import annotations

import hashlib
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from scripts.rotate_daily_shipping_credential import (
    ROTATION_APPLY_ENV,
    CredentialRotationError,
    _verify_telegram_get_me,
    inspect_rotation_readiness,
    rotate_credential,
)


ALMATY_TZ = ZoneInfo("Asia/Almaty")
NOW = datetime(2026, 7, 14, 19, 30, tzinfo=ALMATY_TZ)
OLD_TOKEN = "123456789:" + "A" * 35
NEW_TOKEN = "987654321:" + "B" * 35


def _write_owner_file(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o600)
    return path


def _env_file(tmp_path: Path) -> Path:
    return _write_owner_file(
        tmp_path / "repo" / ".env",
        "# retained\n"
        f"TELEGRAM_BOT_TOKEN={OLD_TOKEN}\n"
        "TELEGRAM_CHAT_ID=123\n"
        "UNCHANGED=value\n",
    )


def _successful_closeout(tmp_path: Path, *, target_date: str = "2026-07-14") -> Path:
    run_id = f"successful-{target_date}-closeout"
    run_dir = (
        tmp_path
        / "repo"
        / "exports"
        / "google_ops_board"
        / "workflow_runs"
        / target_date
        / run_id
    )
    expected_orders = _write_owner_file(
        run_dir / "expected_closeout_orders.json",
        json.dumps(
            {
                "schema_version": 3,
                "target_date": target_date,
                "request_identity": {
                    "target_date": target_date,
                    "ready_set_at": f"{target_date}T17:00:00+05:00",
                },
                "expected_order_ids": [],
                "orders": [],
                "counts": {"orders": 0, "order_lines": 0, "overdue_orders": 0},
            }
        )
        + "\n",
    )
    expected_sha = hashlib.sha256(expected_orders.read_bytes()).hexdigest()
    marker = _write_owner_file(
        run_dir / "zero_order_completion.json",
        json.dumps(
            {
                "schema_version": 1,
                "completed": True,
                "mode": "apply",
                "run_id": run_id,
                "target_date": target_date,
                "request_identity": {
                    "target_date": target_date,
                    "ready_set_at": f"{target_date}T17:00:00+05:00",
                },
                "required_order_count": 0,
                "required_orders_path": str(expected_orders.resolve()),
                "required_orders_sha256": expected_sha,
            }
        )
        + "\n",
    )
    path = run_dir / "closeout_report.json"
    return _write_owner_file(
        path,
        json.dumps(
            {
                "ok": True,
                "mode": "apply",
                "target_date": target_date,
                "run_id": run_id,
                "zero_order_noop": True,
                "expected_closeout_order_count": 0,
                "expected_closeout_orders_path": str(expected_orders.resolve()),
                "zero_order_completion_path": str(marker.resolve()),
            }
        )
        + "\n",
    )


def _superficial_closeout(tmp_path: Path) -> Path:
    run_id = "superficial-closeout"
    path = (
        tmp_path
        / "repo"
        / "exports"
        / "google_ops_board"
        / "workflow_runs"
        / "2026-07-14"
        / run_id
        / "closeout_report.json"
    )
    return _write_owner_file(
        path,
        json.dumps(
            {
                "ok": True,
                "mode": "apply",
                "target_date": "2026-07-14",
                "run_id": run_id,
                "zero_order_noop": False,
                "expected_closeout_order_count": 1,
            }
        )
        + "\n",
    )


def _token_file(tmp_path: Path, token: str = NEW_TOKEN) -> Path:
    return _write_owner_file(tmp_path / "private" / "fresh-token.txt", token + "\n")


def test_readiness_is_metadata_only_and_does_not_require_token_input(tmp_path: Path) -> None:
    env_path = _env_file(tmp_path)
    report = inspect_rotation_readiness(
        env_path=env_path,
        key="TELEGRAM_BOT_TOKEN",
        project_root=tmp_path / "repo",
    )

    assert report["gate"] == "READY_AFTER_CLOSEOUT"
    assert report["key_present"] is True
    assert report["credential_values_read"] is False
    assert report["credential_values_exposed"] is False
    assert OLD_TOKEN not in json.dumps(report)


def test_readiness_refuses_symlink_and_loose_permissions(tmp_path: Path) -> None:
    target = _env_file(tmp_path)
    symlink = tmp_path / "repo" / "linked.env"
    symlink.symlink_to(target)
    with pytest.raises(CredentialRotationError, match="symlink"):
        inspect_rotation_readiness(
            env_path=symlink,
            key="TELEGRAM_BOT_TOKEN",
            project_root=tmp_path / "repo",
        )

    target.chmod(0o644)
    with pytest.raises(CredentialRotationError, match="0600"):
        inspect_rotation_readiness(
            env_path=target,
            key="TELEGRAM_BOT_TOKEN",
            project_root=tmp_path / "repo",
        )


def test_rotation_requires_explicit_apply_gate(tmp_path: Path) -> None:
    with pytest.raises(CredentialRotationError, match=ROTATION_APPLY_ENV):
        rotate_credential(
            env_path=_env_file(tmp_path),
            key="TELEGRAM_BOT_TOKEN",
            token_file=_token_file(tmp_path),
            closeout_report_path=_successful_closeout(tmp_path),
            receipt_root=tmp_path / "receipts",
            project_root=tmp_path / "repo",
            apply=True,
            environment={},
            now=NOW,
            verifier=lambda _token: {"ok": True},
        )


def test_dry_run_does_not_read_missing_token_or_write_receipts(tmp_path: Path) -> None:
    env_path = _env_file(tmp_path)
    before = env_path.read_bytes()
    receipt_root = tmp_path / "receipts"

    report = rotate_credential(
        env_path=env_path,
        key="TELEGRAM_BOT_TOKEN",
        token_file=tmp_path / "does-not-exist",
        closeout_report_path=tmp_path / "also-missing",
        receipt_root=receipt_root,
        project_root=tmp_path / "repo",
        apply=False,
        environment={},
        now=NOW,
        verifier=lambda _token: pytest.fail("dry-run must not verify a token"),
    )

    assert report["gate"] == "DRY_RUN"
    assert report["credential_values_read"] is False
    assert env_path.read_bytes() == before
    assert not receipt_root.exists()


@pytest.mark.parametrize(
    ("report_patch", "match"),
    [
        ({"ok": False}, "successful apply"),
        ({"mode": "dry_run"}, "successful apply"),
        ({"target_date": "2026-07-13"}, "target date"),
    ],
)
def test_rotation_requires_same_day_successful_apply_closeout(
    tmp_path: Path, report_patch: dict[str, object], match: str
) -> None:
    closeout_path = _successful_closeout(tmp_path)
    closeout = json.loads(closeout_path.read_text(encoding="utf-8"))
    closeout.update(report_patch)
    closeout_path.write_text(json.dumps(closeout), encoding="utf-8")

    with pytest.raises(CredentialRotationError, match=match):
        rotate_credential(
            env_path=_env_file(tmp_path),
            key="TELEGRAM_BOT_TOKEN",
            token_file=_token_file(tmp_path),
            closeout_report_path=closeout_path,
            receipt_root=tmp_path / "receipts",
            project_root=tmp_path / "repo",
            apply=True,
            environment={ROTATION_APPLY_ENV: "1"},
            now=NOW,
            verifier=lambda _token: {"ok": True},
        )


def test_rotation_rejects_superficial_ok_without_ledger_confirmed_evidence(
    tmp_path: Path,
) -> None:
    with pytest.raises(CredentialRotationError, match="ledger-confirmed"):
        rotate_credential(
            env_path=_env_file(tmp_path),
            key="TELEGRAM_BOT_TOKEN",
            token_file=_token_file(tmp_path),
            closeout_report_path=_superficial_closeout(tmp_path),
            receipt_root=tmp_path / "receipts",
            project_root=tmp_path / "repo",
            apply=True,
            environment={ROTATION_APPLY_ENV: "1"},
            now=NOW,
            verifier=lambda _token: {"ok": True},
        )


def test_rotation_rejects_token_file_inside_repo_or_with_loose_mode(tmp_path: Path) -> None:
    env_path = _env_file(tmp_path)
    inside = _write_owner_file(tmp_path / "repo" / "fresh-token.txt", NEW_TOKEN)
    with pytest.raises(CredentialRotationError, match="outside the repo"):
        rotate_credential(
            env_path=env_path,
            key="TELEGRAM_BOT_TOKEN",
            token_file=inside,
            closeout_report_path=_successful_closeout(tmp_path),
            receipt_root=tmp_path / "receipts",
            project_root=tmp_path / "repo",
            apply=True,
            environment={ROTATION_APPLY_ENV: "1"},
            now=NOW,
            verifier=lambda _token: {"ok": True},
        )

    outside = _token_file(tmp_path)
    outside.chmod(0o644)
    with pytest.raises(CredentialRotationError, match="0600"):
        rotate_credential(
            env_path=env_path,
            key="TELEGRAM_BOT_TOKEN",
            token_file=outside,
            closeout_report_path=_successful_closeout(tmp_path),
            receipt_root=tmp_path / "receipts",
            project_root=tmp_path / "repo",
            apply=True,
            environment={ROTATION_APPLY_ENV: "1"},
            now=NOW,
            verifier=lambda _token: {"ok": True},
        )


def test_rotation_rejects_invalid_or_duplicate_target_without_writing(tmp_path: Path) -> None:
    env_path = _env_file(tmp_path)
    before = env_path.read_bytes()
    invalid = _token_file(tmp_path, token="not-a-telegram-token")
    with pytest.raises(CredentialRotationError, match="token format"):
        rotate_credential(
            env_path=env_path,
            key="TELEGRAM_BOT_TOKEN",
            token_file=invalid,
            closeout_report_path=_successful_closeout(tmp_path),
            receipt_root=tmp_path / "receipts",
            project_root=tmp_path / "repo",
            apply=True,
            environment={ROTATION_APPLY_ENV: "1"},
            now=NOW,
            verifier=lambda _token: {"ok": True},
        )
    assert env_path.read_bytes() == before

    env_path.write_text(
        f"TELEGRAM_BOT_TOKEN={OLD_TOKEN}\nTELEGRAM_BOT_TOKEN={OLD_TOKEN}\n",
        encoding="utf-8",
    )
    with pytest.raises(CredentialRotationError, match="duplicate"):
        rotate_credential(
            env_path=env_path,
            key="TELEGRAM_BOT_TOKEN",
            token_file=_token_file(tmp_path),
            closeout_report_path=_successful_closeout(tmp_path),
            receipt_root=tmp_path / "receipts",
            project_root=tmp_path / "repo",
            apply=True,
            environment={ROTATION_APPLY_ENV: "1"},
            now=NOW,
            verifier=lambda _token: {"ok": True},
        )


def test_failed_read_only_verification_does_not_write_or_expose_token(tmp_path: Path) -> None:
    env_path = _env_file(tmp_path)
    before = env_path.read_bytes()

    with pytest.raises(CredentialRotationError, match="verification failed") as exc_info:
        rotate_credential(
            env_path=env_path,
            key="TELEGRAM_BOT_TOKEN",
            token_file=_token_file(tmp_path),
            closeout_report_path=_successful_closeout(tmp_path),
            receipt_root=tmp_path / "receipts",
            project_root=tmp_path / "repo",
            apply=True,
            environment={ROTATION_APPLY_ENV: "1"},
            now=NOW,
            verifier=lambda _token: {"ok": False, "error": "telegram_get_me_rejected"},
        )

    assert NEW_TOKEN not in str(exc_info.value)
    assert env_path.read_bytes() == before
    assert not (tmp_path / "receipts").exists()


def test_transport_failure_suppresses_token_bearing_exception_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def rejected_get(url: str, **_kwargs: object) -> None:
        raise RuntimeError(f"request rejected for {url}")

    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(get=rejected_get))
    try:
        _verify_telegram_get_me(NEW_TOKEN)
    except CredentialRotationError as exc:
        rendered = "".join(traceback.format_exception(exc))
    else:
        pytest.fail("transport failure must reject the fresh token")

    assert NEW_TOKEN not in rendered
    assert "api.telegram.org" not in rendered


def test_successful_rotation_is_atomic_backed_up_and_secret_free_in_receipt(
    tmp_path: Path,
) -> None:
    env_path = _env_file(tmp_path)
    report = rotate_credential(
        env_path=env_path,
        key="TELEGRAM_BOT_TOKEN",
        token_file=_token_file(tmp_path),
        closeout_report_path=_successful_closeout(tmp_path),
        receipt_root=tmp_path / "receipts",
        project_root=tmp_path / "repo",
        apply=True,
        environment={ROTATION_APPLY_ENV: "1"},
        now=NOW,
        verifier=lambda _token: {"ok": True, "bot_id_present": True},
    )

    persisted = env_path.read_text(encoding="utf-8")
    serialized = json.dumps(report)
    backup = Path(report["backup_path"])
    receipt = Path(report["receipt_path"])
    assert f"TELEGRAM_BOT_TOKEN={NEW_TOKEN}" in persisted
    assert "UNCHANGED=value" in persisted
    assert OLD_TOKEN not in persisted
    assert OLD_TOKEN in backup.read_text(encoding="utf-8")
    assert backup.stat().st_mode & 0o777 == 0o600
    assert receipt.stat().st_mode & 0o777 == 0o600
    assert env_path.stat().st_mode & 0o777 == 0o600
    assert report["gate"] == "GREEN"
    assert report["credential_values_read"] is True
    assert report["credential_values_exposed"] is False
    assert report["closeout_completion_kind"] == "zero_order_noop"
    assert report["closeout_pending_count"] == 0
    assert OLD_TOKEN not in serialized
    assert NEW_TOKEN not in serialized


def test_live_root_is_explicit_when_code_and_runtime_roots_differ(tmp_path: Path) -> None:
    code_root = tmp_path / "release"
    live_root = tmp_path / "repo"
    code_root.mkdir()
    with pytest.raises(CredentialRotationError, match="live project root"):
        rotate_credential(
            env_path=_env_file(tmp_path),
            key="TELEGRAM_BOT_TOKEN",
            token_file=_token_file(tmp_path),
            closeout_report_path=_successful_closeout(tmp_path),
            receipt_root=tmp_path / "receipts",
            project_root=code_root,
            apply=True,
            environment={ROTATION_APPLY_ENV: "1"},
            now=NOW,
            verifier=lambda _token: {"ok": True},
        )

    report = rotate_credential(
        env_path=live_root / ".env",
        key="TELEGRAM_BOT_TOKEN",
        token_file=_token_file(tmp_path),
        closeout_report_path=_successful_closeout(tmp_path),
        receipt_root=tmp_path / "receipts-explicit",
        project_root=code_root,
        live_project_root=live_root,
        apply=True,
        environment={ROTATION_APPLY_ENV: "1"},
        now=NOW,
        verifier=lambda _token: {"ok": True},
    )
    assert report["gate"] == "GREEN"


def test_only_allowlisted_telegram_keys_can_rotate(tmp_path: Path) -> None:
    with pytest.raises(CredentialRotationError, match="not allowlisted"):
        inspect_rotation_readiness(
            env_path=_env_file(tmp_path),
            key="KASPI_TOKEN_ACMEWEAR",
            project_root=tmp_path / "repo",
        )
