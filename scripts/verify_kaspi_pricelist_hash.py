#!/usr/bin/env python3
"""Verify remote Kaspi pricelist content matches local hash."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from urllib.request import urlopen


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_hash(url: str, local_path: Path, timeout: int = 10) -> None:
    local_bytes = local_path.read_bytes()
    local_hash = _sha256(local_bytes)

    with urlopen(url, timeout=timeout) as response:
        status = getattr(response, "status", 200)
        if status != 200:
            raise RuntimeError(f"URL returned status {status}")
        remote_bytes = response.read()
    remote_hash = _sha256(remote_bytes)

    if remote_hash != local_hash:
        raise RuntimeError(
            f"Hash mismatch: remote={remote_hash} local={local_hash}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Kaspi pricelist hash")
    parser.add_argument("--url", required=True, help="HTTPS URL to pricelist XML")
    parser.add_argument("--local", required=True, type=Path, help="Local XML file")
    parser.add_argument("--timeout", type=int, default=10, help="Request timeout (seconds)")
    args = parser.parse_args()

    verify_hash(args.url, args.local, timeout=args.timeout)
    print(f"OK: {args.url} matches {args.local}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
