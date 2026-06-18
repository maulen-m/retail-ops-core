#!/usr/bin/env python3
"""Validate manifest-driven write-side env + --apply gating contracts."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = PROJECT_ROOT / "config" / "write_side_gating_manifest.yaml"


def load_manifest(manifest_path: Path) -> list[dict[str, str]]:
    raw: Any = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    rows = raw.get("scripts")
    if not isinstance(rows, list):
        raise RuntimeError("manifest format invalid: key 'scripts' must be a list")
    normalized: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise RuntimeError("manifest format invalid: each item must be a mapping")
        path = str(row.get("path", "")).strip()
        env_gate = str(row.get("env_gate", "")).strip()
        apply_flag = str(row.get("apply_flag", "")).strip()
        if not path or not env_gate or not apply_flag:
            raise RuntimeError("manifest format invalid: each row needs path/env_gate/apply_flag")
        normalized.append({"path": path, "env_gate": env_gate, "apply_flag": apply_flag})
    return normalized


def validate_manifest(
    *,
    manifest_path: Path,
    project_root: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    errors: list[str] = []
    checked: list[str] = []
    seen: set[str] = set()

    entries = load_manifest(manifest_path)
    for entry in entries:
        rel_path = entry["path"]
        env_gate = entry["env_gate"]
        apply_flag = entry["apply_flag"]
        if rel_path in seen:
            errors.append(f"duplicate manifest path: {rel_path}")
            continue
        seen.add(rel_path)

        file_path = (project_root / rel_path).resolve()
        if not file_path.exists():
            errors.append(f"missing script from manifest: {rel_path}")
            continue
        text = file_path.read_text(encoding="utf-8")
        if apply_flag not in text:
            errors.append(f"{rel_path} missing apply flag token: {apply_flag}")
        if env_gate not in text:
            errors.append(f"{rel_path} missing env gate token: {env_gate}")
        checked.append(rel_path)

    return {
        "ok": not errors,
        "checked_count": len(checked),
        "checked": checked,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate write-side env + apply gate manifest")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--strict", action="store_true", help="Accepted for MVOS gate compatibility")
    args = parser.parse_args()

    if not args.manifest.exists():
        print(f"ERROR: manifest missing: {args.manifest}")
        return 1

    try:
        report = validate_manifest(
            manifest_path=args.manifest,
            project_root=args.project_root,
        )
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1

    if not report["ok"]:
        print("WRITE_SIDE_GATING FAIL")
        for err in report["errors"]:
            print(f"- {err}")
        return 1

    print("WRITE_SIDE_GATING PASS")
    print(f"checked_count={report['checked_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
