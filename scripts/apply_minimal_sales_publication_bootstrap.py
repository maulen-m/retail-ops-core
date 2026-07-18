#!/usr/bin/env python3
"""Canonical CLI for the copy-only minimal sales publication bootstrap."""

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.apply_minimal_sales_source_identity_schema import main


if __name__ == "__main__":
    raise SystemExit(main())
