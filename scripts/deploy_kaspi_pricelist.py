#!/usr/bin/env python3
"""Deploy Kaspi pricelist XML to S3/CloudFront with safety gates."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.integrations.kaspi_pricelist.generator import generate_pricelist


ENV_FLAG = "ENABLE_KASPI_PRICELIST_PUBLISH"
CATALOG_FILENAME = "kaspi_catalog.xml"
BACKUP_SUFFIX = "_last_good"


@dataclass(frozen=True)
class DeployResult:
    store_code: str
    local_xml_path: Path
    remote_path: str | None
    backup_path: str | None


class LocalUploader:
    def __init__(self, root: Path):
        self.root = root

    def target_paths(self, store_code: str) -> tuple[str, str]:
        dest = self.root / store_code / CATALOG_FILENAME
        backup = dest.with_name(f"{dest.stem}{BACKUP_SUFFIX}{dest.suffix}")
        return str(dest), str(backup)

    def exists(self, path: str) -> bool:
        return Path(path).exists()

    def backup(self, dest: str, backup: str) -> bool:
        if not self.exists(dest):
            return False
        Path(backup).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dest, backup)
        return True

    def upload(self, src: Path, dest: str) -> None:
        dest_path = Path(dest)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest_path)

    def restore(self, backup: str, dest: str) -> None:
        if not self.exists(backup):
            raise RuntimeError(f"Backup not found: {backup}")
        self.upload(Path(backup), dest)


class S3Uploader:
    def __init__(self, bucket: str, prefix: str | None):
        if not bucket:
            raise ValueError("bucket is required for S3 upload")
        if shutil.which("aws") is None:
            raise RuntimeError("aws CLI not found; install AWS CLI to deploy to S3")
        self.bucket = bucket
        self.prefix = (prefix or "").strip("/")

    def _key(self, store_code: str, filename: str) -> str:
        parts = [p for p in [self.prefix, store_code, filename] if p]
        return "/".join(parts)

    def target_paths(self, store_code: str) -> tuple[str, str]:
        key = self._key(store_code, CATALOG_FILENAME)
        dest = f"s3://{self.bucket}/{key}"
        backup_key = self._key(
            store_code, f"{Path(CATALOG_FILENAME).stem}{BACKUP_SUFFIX}{Path(CATALOG_FILENAME).suffix}"
        )
        backup = f"s3://{self.bucket}/{backup_key}"
        return dest, backup

    def exists(self, path: str) -> bool:
        result = subprocess.run(
            ["aws", "s3", "ls", path],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0 and bool(result.stdout.strip())

    def backup(self, dest: str, backup: str) -> bool:
        if not self.exists(dest):
            return False
        subprocess.run(["aws", "s3", "cp", dest, backup], check=True)
        return True

    def upload(self, src: Path, dest: str) -> None:
        subprocess.run(
            ["aws", "s3", "cp", str(src), dest, "--content-type", "application/xml"],
            check=True,
        )

    def restore(self, backup: str, dest: str) -> None:
        if not self.exists(backup):
            raise RuntimeError(f"Backup not found: {backup}")
        subprocess.run(["aws", "s3", "cp", backup, dest], check=True)


def deploy_pricelist(
    store_codes: Iterable[str],
    db_path: Path,
    config_path: Path,
    output_dir: Path,
    allowlist_path: Path | None,
    publish: bool,
    uploader: LocalUploader | S3Uploader,
) -> list[DeployResult]:
    if publish and allowlist_path is None:
        raise RuntimeError("allowlist_path is required when publishing")
    results: list[DeployResult] = []
    for store_code in store_codes:
        effective_allowlist = allowlist_path if allowlist_path else None
        result = generate_pricelist(
            db_path=db_path,
            store_code=store_code,
            config_path=config_path,
            output_dir=output_dir,
            dry_run=not publish,
            publish_path=None,
            allowlist_path=effective_allowlist,
        )

        remote_path = None
        backup_path = None
        if publish:
            remote_path, backup_path = uploader.target_paths(store_code)
            uploader.backup(remote_path, backup_path)
            uploader.upload(result.catalog_path, remote_path)

        results.append(
            DeployResult(
                store_code=store_code,
                local_xml_path=result.catalog_path,
                remote_path=remote_path,
                backup_path=backup_path,
            )
        )
    return results


def rollback_pricelist(store_codes: Iterable[str], uploader: LocalUploader | S3Uploader) -> None:
    for store_code in store_codes:
        dest, backup = uploader.target_paths(store_code)
        uploader.restore(backup, dest)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deploy Kaspi pricelist XML to S3")
    parser.add_argument(
        "--store",
        action="append",
        required=True,
        help="Store code (repeat for multiple stores)",
    )
    parser.add_argument("--db", default="db/app.db", help="Path to sqlite DB")
    parser.add_argument(
        "--config",
        default="config/kaspi_pricelist.yaml",
        help="Pricelist config YAML",
    )
    parser.add_argument(
        "--output-dir",
        default="exports/kaspi_pricelist",
        help="Output directory for generated XML",
    )
    parser.add_argument("--allowlist", default=None, help="Path to SKU allowlist")
    parser.add_argument("--publish", action="store_true", help="Upload to S3")
    parser.add_argument("--rollback", action="store_true", help="Republish last-known-good backup")
    parser.add_argument("--bucket", default=None, help="S3 bucket for hosting")
    parser.add_argument(
        "--prefix",
        default="",
        help="S3 key prefix (optional). Example: kaspi/pricelist",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    store_codes = args.store
    allowlist_path = Path(args.allowlist) if args.allowlist else None

    if args.rollback and not args.publish:
        raise RuntimeError("--rollback requires --publish")

    if args.publish or args.rollback:
        if os.environ.get(ENV_FLAG) != "1":
            raise RuntimeError(f"{ENV_FLAG}=1 is required to publish")
        if allowlist_path is None:
            raise RuntimeError("--allowlist is required when publishing")
        if not args.bucket:
            raise RuntimeError("--bucket is required when publishing")

    uploader = S3Uploader(bucket=args.bucket, prefix=args.prefix) if args.publish else None

    if args.rollback:
        if uploader is None:
            raise RuntimeError("Uploader not initialized for rollback")
        rollback_pricelist(store_codes=store_codes, uploader=uploader)
        for store_code in store_codes:
            dest, _ = uploader.target_paths(store_code)
            print(f"Rollback published for {store_code}: {dest}")
        return 0

    results = deploy_pricelist(
        store_codes=store_codes,
        db_path=Path(args.db),
        config_path=Path(args.config),
        output_dir=Path(args.output_dir),
        allowlist_path=allowlist_path,
        publish=args.publish,
        uploader=uploader or LocalUploader(Path(args.output_dir)),
    )

    for result in results:
        print(f"{result.store_code}: {result.local_xml_path}")
        if result.remote_path:
            print(f"Uploaded to: {result.remote_path}")
            if result.backup_path:
                print(f"Backup stored at: {result.backup_path}")
    if not args.publish:
        print("Dry-run only (no upload)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
