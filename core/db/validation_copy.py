"""Temporary SQLite copies for read-only validators that need derived views."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3
import tempfile
from collections.abc import Iterator


@contextmanager
def validation_db_path(source_db: Path) -> Iterator[Path]:
    """Yield a writable temporary DB path copied from ``source_db``.

    Some validators need to rebuild SQLite views before querying. Running those
    view DDL statements against production changes the DB file even when no
    business data changes. This helper uses SQLite's backup API so validators can
    safely create/drop derived views on an isolated copy.
    """

    with tempfile.TemporaryDirectory(prefix="ab_validation_db_") as tmp_dir:
        copy_path = Path(tmp_dir) / "validation.db"
        src_uri = f"file:{source_db.expanduser().resolve()}?mode=ro"
        src = sqlite3.connect(src_uri, uri=True)
        dst = sqlite3.connect(str(copy_path))
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()

        yield copy_path


@contextmanager
def validation_db_copy(source_db: Path) -> Iterator[sqlite3.Connection]:
    """Yield a connection to a writable temporary copy of ``source_db``."""

    with validation_db_path(source_db) as copy_path:
        conn = sqlite3.connect(str(copy_path))
        try:
            yield conn
        finally:
            conn.close()
