from __future__ import annotations

from pathlib import Path

import pytest

from scripts.sync_google_ops_board import _require_apply_gate as require_publish_apply_gate
from scripts.sync_google_ops_board_sizes_to_db import _require_apply_gate as require_db_apply_gate
from scripts.run_google_ops_board_closeout import _require_apply_gate as require_closeout_apply_gate


def test_publish_apply_gate_requires_env_opt_in(monkeypatch):
    monkeypatch.delenv("ENABLE_GOOGLE_OPS_BOARD_WRITE", raising=False)

    with pytest.raises(RuntimeError, match="ENABLE_GOOGLE_OPS_BOARD_WRITE=1"):
        require_publish_apply_gate(True, "ENABLE_GOOGLE_OPS_BOARD_WRITE")


def test_db_apply_gate_requires_env_opt_in(monkeypatch):
    monkeypatch.delenv("ENABLE_GOOGLE_OPS_BOARD_DB_WRITE", raising=False)

    with pytest.raises(RuntimeError, match="ENABLE_GOOGLE_OPS_BOARD_DB_WRITE=1"):
        require_db_apply_gate(True, "ENABLE_GOOGLE_OPS_BOARD_DB_WRITE")


def test_closeout_apply_gate_requires_env_opt_in(monkeypatch):
    monkeypatch.delenv("ENABLE_GOOGLE_OPS_BOARD_CLOSEOUT", raising=False)

    with pytest.raises(RuntimeError, match="ENABLE_GOOGLE_OPS_BOARD_CLOSEOUT=1"):
        require_closeout_apply_gate(True, "ENABLE_GOOGLE_OPS_BOARD_CLOSEOUT")


def test_non_apply_mode_skips_gate(monkeypatch):
    monkeypatch.delenv("ENABLE_GOOGLE_OPS_BOARD_WRITE", raising=False)

    require_publish_apply_gate(False, "ENABLE_GOOGLE_OPS_BOARD_WRITE")
    require_db_apply_gate(False, "ENABLE_GOOGLE_OPS_BOARD_DB_WRITE")
    require_closeout_apply_gate(False, "ENABLE_GOOGLE_OPS_BOARD_CLOSEOUT")
