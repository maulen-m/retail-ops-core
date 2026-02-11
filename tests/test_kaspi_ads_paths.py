from __future__ import annotations

from pathlib import Path

import pytest

from scripts.kaspi_ads_paths import (
    assert_ads_db_path_safe,
    copy_ads_db_once,
    resolve_ads_db_path,
)


def test_resolve_ads_db_path_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    default_db = tmp_path / "default.db"
    env_db = tmp_path / "env.db"
    cli_db = tmp_path / "cli.db"

    env = {"KASPI_MARKETING_DB_PATH": str(env_db)}

    resolved = resolve_ads_db_path(
        ads_db_arg=cli_db,
        env=env,
        default_path=default_db,
    )
    assert resolved == cli_db.resolve()

    resolved = resolve_ads_db_path(
        ads_db_arg=None,
        env=env,
        default_path=default_db,
    )
    assert resolved == env_db.resolve()

    env = {}
    resolved = resolve_ads_db_path(
        ads_db_arg=None,
        env=env,
        default_path=default_db,
    )
    assert resolved == default_db.resolve()


def test_assert_ads_db_path_safe_rejects_prod_path(tmp_path: Path) -> None:
    prod = tmp_path / "prod.db"

    with pytest.raises(RuntimeError, match="Refusing to use production ads DB path"):
        assert_ads_db_path_safe(
            ads_db_path=prod,
            prod_ads_db_path=prod,
            env={},
        )


def test_assert_ads_db_path_safe_allows_prod_path_with_flag(tmp_path: Path) -> None:
    prod = tmp_path / "prod.db"

    # Must not raise.
    assert_ads_db_path_safe(
        ads_db_path=prod,
        prod_ads_db_path=prod,
        env={"ALLOW_PROD_ADS_DB": "1"},
    )


def test_copy_ads_db_once(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    source.write_bytes(b"abc")

    dest = tmp_path / "dest" / "ads.db"
    first = copy_ads_db_once(source_db=source, dest_db=dest)
    assert first["copied"] is True
    assert dest.read_bytes() == b"abc"

    source.write_bytes(b"changed")
    second = copy_ads_db_once(source_db=source, dest_db=dest)
    assert second["copied"] is False
    # Copy-once guarantee: existing destination is preserved.
    assert dest.read_bytes() == b"abc"
