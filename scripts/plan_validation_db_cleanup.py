#!/usr/bin/env python3
"""Build non-destructive cleanup manifests for validation DB artifacts."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIELDS = ["path", "size_bytes", "size_mib", "class", "evidence_hint"]
PRODUCTION_OR_APPLY_MARKERS = (
    "db_order_entry_owner_apply",
    "owner_apply",
    "pre_apply",
    "prod_apply",
    "production_apply",
)
ELIGIBLE_CLASSES = {"CANDIDATE_COPIED_DB_BACKUP", "CANDIDATE_COPIED_TEMP_DB"}
EVIDENCE_NAMES = ("VALIDATOR_EXIT_MATRIX.tsv",)
EVIDENCE_SUBSTRINGS = ("sha", "closeout")


class CleanupManifestError(RuntimeError):
    pass


def _repo_relative(repo: Path, path: Path) -> str:
    return path.resolve().relative_to(repo.resolve()).as_posix()


def classify_db_path(repo: Path, path: Path) -> str:
    rel = _repo_relative(repo, path)
    if any(marker in rel for marker in PRODUCTION_OR_APPLY_MARKERS):
        return "EXCLUDE_PRODUCTION_OR_APPLY_BACKUP"
    if "/backups/" in rel or "/backup/" in rel:
        return "CANDIDATE_COPIED_DB_BACKUP"
    lowered = rel.lower()
    if "copied" in lowered or "copy" in lowered or "temp" in lowered:
        return "CANDIDATE_COPIED_TEMP_DB"
    return "REVIEW_MANUALLY"


def _has_evidence_file(paths: Iterable[Path]) -> bool:
    for path in paths:
        if not path.is_file():
            continue
        name = path.name
        lowered = name.lower()
        if name in EVIDENCE_NAMES:
            return True
        if any(token in lowered for token in EVIDENCE_SUBSTRINGS):
            return True
    return False


def evidence_hint(path: Path) -> str:
    same_dir = path.parent
    if _has_evidence_file(same_dir.iterdir()):
        return "same_dir_evidence"
    parent = same_dir.parent
    nearby_files = (candidate for candidate in parent.rglob("*") if candidate.is_file())
    if _has_evidence_file(nearby_files):
        return "nearby_evidence"
    return "no_nearby_sha_or_matrix_seen"


def collect_rows(repo: Path, validation_root: Path) -> list[dict[str, str]]:
    root = validation_root.resolve()
    try:
        root.relative_to(repo.resolve())
    except ValueError as exc:
        raise CleanupManifestError(f"validation root escapes repo: {root}") from exc
    if not root.exists():
        raise CleanupManifestError(f"validation root missing: {root}")
    rows: list[dict[str, str]] = []
    for path in sorted(root.rglob("*.db")):
        stat = path.stat()
        rows.append(
            {
                "path": _repo_relative(repo, path),
                "size_bytes": str(stat.st_size),
                "size_mib": f"{stat.st_size / 1048576:.1f}",
                "class": classify_db_path(repo, path),
                "evidence_hint": evidence_hint(path),
            }
        )
    rows.sort(key=lambda row: (row["class"], -int(row["size_bytes"]), row["path"]))
    return rows


def select_first_batch(rows: list[dict[str, str]], limit: int) -> list[dict[str, str]]:
    eligible = [
        row
        for row in rows
        if row["class"] in ELIGIBLE_CLASSES
        and row["evidence_hint"] != "no_nearby_sha_or_matrix_seen"
    ]
    eligible.sort(key=lambda row: (-int(row["size_bytes"]), row["path"]))
    return eligible[:limit]


def write_tsv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def summarize(rows: list[dict[str, str]], batch_rows: list[dict[str, str]]) -> dict[str, object]:
    class_summary: dict[str, dict[str, float | int]] = {}
    for row in rows:
        bucket = class_summary.setdefault(row["class"], {"rows": 0, "size_mib": 0.0})
        bucket["rows"] = int(bucket["rows"]) + 1
        bucket["size_mib"] = float(bucket["size_mib"]) + float(row["size_mib"])
    return {
        "row_count": len(rows),
        "first_batch_count": len(batch_rows),
        "first_batch_bytes": sum(int(row["size_bytes"]) for row in batch_rows),
        "first_batch_mib": round(sum(int(row["size_bytes"]) for row in batch_rows) / 1048576, 1),
        "class_summary": class_summary,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Plan non-destructive cleanup candidates for exports/validation DB artifacts"
    )
    parser.add_argument("--repo", default=str(PROJECT_ROOT))
    parser.add_argument("--validation-root", default="exports/validation")
    parser.add_argument("--manifest-out", default=None)
    parser.add_argument("--first-batch-out", default=None)
    parser.add_argument("--batch-count", type=int, default=16)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    repo = Path(args.repo).resolve()
    validation_root = Path(args.validation_root)
    if not validation_root.is_absolute():
        validation_root = repo / validation_root
    rows = collect_rows(repo, validation_root)
    batch_rows = select_first_batch(rows, args.batch_count)
    if args.manifest_out:
        manifest_out = Path(args.manifest_out)
        if not manifest_out.is_absolute():
            manifest_out = repo / manifest_out
        write_tsv(manifest_out, rows)
    if args.first_batch_out:
        first_batch_out = Path(args.first_batch_out)
        if not first_batch_out.is_absolute():
            first_batch_out = repo / first_batch_out
        write_tsv(first_batch_out, batch_rows)
    summary = summarize(rows, batch_rows)
    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        print("VALIDATION_DB_CLEANUP_PLAN")
        print(f"row_count={summary['row_count']}")
        print(f"first_batch_count={summary['first_batch_count']}")
        print(f"first_batch_mib={summary['first_batch_mib']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
