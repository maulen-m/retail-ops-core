#!/usr/bin/env python3
"""
Run the internal analytics API (no external deps).

Endpoints:
  GET /kpis/last30
  GET /timeseries/monthly
  GET /calendar/daily
  GET /compare/summary
  GET /filters/options

Query params:
  start_date=YYYY-MM-DD
  end_date=YYYY-MM-DD
  store=CODE1,CODE2
  sku=SKU1,SKU2
  include_returns=true|false
"""

import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import sys
from pathlib import Path
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.analytics.api import handle_request, json_response


class AnalyticsHandler(BaseHTTPRequestHandler):
    server_version = "AnalyticsAPI/0.1"

    def _set_headers(self, status: int, content_length: int) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(content_length))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_OPTIONS(self):
        self._set_headers(204, 0)

    def do_GET(self):
        parsed = urlparse(self.path)
        status, payload = handle_request(parsed.path, parsed.query)
        body = json_response(status, payload)
        self._set_headers(status, len(body))
        self.wfile.write(body)

    def log_message(self, format, *args):  # noqa: A003
        return  # quiet by default


def main() -> None:
    parser = argparse.ArgumentParser(description="Run analytics API")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", type=int, default=8008, help="Bind port")
    args = parser.parse_args()

    server = HTTPServer((args.host, args.port), AnalyticsHandler)
    print(f"Analytics API listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
