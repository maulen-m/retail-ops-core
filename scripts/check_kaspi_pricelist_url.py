#!/usr/bin/env python3
"""Check that a Kaspi pricelist URL is reachable and valid XML."""

from __future__ import annotations

import argparse
from urllib.request import urlopen
from xml.etree import ElementTree as ET


def check_url(url: str, timeout: int = 10) -> None:
    with urlopen(url, timeout=timeout) as response:
        status = getattr(response, "status", 200)
        if status != 200:
            raise RuntimeError(f"URL returned status {status}")
        data = response.read()
    root = ET.fromstring(data)
    if not root.tag.endswith("kaspi_catalog"):
        raise RuntimeError("Root element is not kaspi_catalog")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Kaspi pricelist URL")
    parser.add_argument("--url", required=True, help="HTTPS URL to pricelist XML")
    parser.add_argument("--timeout", type=int, default=10, help="Request timeout (seconds)")
    args = parser.parse_args()

    check_url(args.url, timeout=args.timeout)
    print(f"OK: {args.url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
