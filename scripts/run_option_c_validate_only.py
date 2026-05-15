#!/usr/bin/env python3
"""Run the Option C validate-only contract on a copied/read-only DB target."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from typing import Any, Sequence


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PRODUCTION_DB = PROJECT_ROOT / "db" / "app.db"
PROOF_WINDOW_LOCK_ENV = "AB_PROOF_WINDOW_LOCK_PATH"
PROOF_WINDOW_LOCK_DEFAULT_RELATIVE = Path("config") / "proof_window.lock"
PROOF_WINDOW_BLOCK_EXIT_CODE = 75
PROOF_WINDOW_BLOCK_TOKEN = "STRICT_DAILY_PREFLIGHT_BLOCKED_BY_PROOF_WINDOW_LOCK"
UNSUPPORTED_VALIDATOR_TARGET_CODE = "BLOCKED_UNSUPPORTED_VALIDATOR_DB_TARGET"
UNCONTAINED_VALIDATOR_OUTPUT_CODE = "BLOCKED_UNCONTAINED_VALIDATOR_OUTPUT"


@dataclass(frozen=True)
class ValidateOnlyConfig:
    as_of: str
    evidence_dir: Path
    mode: str = "existing-copy"
    source_db_path: Path | None = None
    copied_db_path: Path | None = None
    execute_validators: bool = True
    project_root: Path = PROJECT_ROOT
    surface: str = "cash-risk-daily"


@dataclass(frozen=True)
class ValidatorCommand:
    name: str
    command: list[str]
    supports_explicit_db_target: bool = True
    db_target_flags: tuple[str, ...] = ("--db",)
    requires_output_containment: bool = False
    output_target_flags: tuple[str, ...] = ("--output-root", "--output-dir")


@dataclass(frozen=True)
class ValidatorTargetCheck:
    ok: bool
    code: str
    message: str


@dataclass(frozen=True)
class ValidatorRunResult:
    name: str
    command: list[str]
    exit_code: int
    status: str
    stdout: str
    stderr: str


@dataclass
class ValidateOnlyResult:
    exit_code: int
    message: str
    written_files: list[Path] = field(default_factory=list)
    banner_path: Path | None = None
    owner_draft_path: Path | None = None
    copied_db_path: Path | None = None


def _resolve_proof_window_lock_path(project_root: Path | None = None) -> Path:
    raw = os.environ.get(PROOF_WINDOW_LOCK_ENV, "").strip()
    if raw:
        return Path(raw).expanduser()
    root = project_root if project_root is not None else PROJECT_ROOT
    return root / PROOF_WINDOW_LOCK_DEFAULT_RELATIVE


def _proof_window_lock_block_message(lock_path: Path, *, stat_error: str | None = None) -> str:
    msg = f"{PROOF_WINDOW_BLOCK_TOKEN} path={lock_path}"
    if stat_error:
        msg += f" stat_error={stat_error}"
    return msg


def _proof_window_lock_block_status(project_root: Path | None = None) -> tuple[int, str] | None:
    lock_path = _resolve_proof_window_lock_path(project_root)
    try:
        lock_path.stat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        return PROOF_WINDOW_BLOCK_EXIT_CODE, _proof_window_lock_block_message(
            lock_path,
            stat_error=str(exc),
        )
    return PROOF_WINDOW_BLOCK_EXIT_CODE, _proof_window_lock_block_message(lock_path)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_child(root: Path, *parts: str) -> Path:
    root_resolved = root.resolve()
    path = (root / Path(*parts)).resolve()
    try:
        path.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError(f"Refusing to write outside evidence dir: {path}") from exc
    return path


def _write_json(evidence_dir: Path, relative: Sequence[str], payload: dict[str, Any] | list[Any]) -> Path:
    path = _safe_child(evidence_dir, *relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _write_text(evidence_dir: Path, relative: Sequence[str], text: str) -> Path:
    path = _safe_child(evidence_dir, *relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _copy_source_db(source_db_path: Path, target_db_path: Path) -> None:
    target_db_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_db_path, target_db_path)


def _integrity_check_readonly(db_path: Path) -> str:
    uri = f"file:{db_path.resolve()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        row = conn.execute("PRAGMA integrity_check").fetchone()
        return str(row[0]) if row else "missing_integrity_result"
    finally:
        conn.close()


def build_validator_commands(
    *,
    copied_db_path: Path,
    as_of: str,
    evidence_dir: Path | None = None,
) -> list[ValidatorCommand]:
    db = str(copied_db_path)
    py = sys.executable
    validator_output_root = (
        (evidence_dir / "04_validator_outputs")
        if evidence_dir is not None
        else (copied_db_path.parent / "04_validator_outputs")
    ).resolve()
    return [
        ValidatorCommand(
            name="policy_source_freshness",
            command=[
                py,
                "scripts/validate_policy_source_freshness.py",
                "--strict",
                "--json",
                "--db",
                db,
            ],
        ),
        ValidatorCommand(
            name="ads_sidecar_readiness",
            command=[
                py,
                "scripts/validate_ads_sidecar_readiness.py",
                "--as-of",
                as_of,
                "--strict",
                "--db",
                db,
                "--output-root",
                str(validator_output_root / "ads_sidecar_readiness"),
            ],
            requires_output_containment=True,
        ),
        ValidatorCommand(
            name="ads_offer_universe_coverage",
            command=[
                py,
                "scripts/validate_ads_offer_universe_coverage.py",
                "--as-of",
                as_of,
                "--strict",
                "--db-path",
                db,
                "--output-dir",
                str(validator_output_root / "ads_offer_universe"),
            ],
            db_target_flags=("--db-path",),
            requires_output_containment=True,
        ),
        ValidatorCommand(
            name="operational_stock_integration",
            command=[
                py,
                "scripts/validate_operational_stock_integration_gates.py",
                "--json",
                "--db",
                db,
            ],
        ),
        ValidatorCommand(
            name="order_cashflow_coverage",
            command=[
                py,
                "scripts/validate_order_cashflow_coverage.py",
                "--as-of",
                as_of,
                "--strict",
                "--json",
                "--db",
                db,
            ],
        ),
        ValidatorCommand(
            name="cashflow_actual_model_separation",
            command=[
                py,
                "scripts/validate_cashflow_actual_model_separation.py",
                "--anchor-date",
                as_of,
                "--strict",
                "--json",
                "--db",
                db,
            ],
        ),
        ValidatorCommand(
            name="cashflow_invariants",
            command=[
                py,
                "scripts/validate_cashflow_invariants.py",
                "--db",
                db,
            ],
        ),
    ]


def validator_has_explicit_db_target(command: ValidatorCommand, copied_db_path: Path) -> bool:
    if not command.supports_explicit_db_target:
        return False
    parts = [str(part) for part in command.command]
    expected = str(copied_db_path)
    for idx, part in enumerate(parts[:-1]):
        if part in command.db_target_flags and parts[idx + 1] == expected:
            return True
    return False


def _is_relative_to(child: Path, parent: Path) -> bool:
    try:
        child.expanduser().resolve().relative_to(parent.expanduser().resolve())
        return True
    except ValueError:
        return False


def validator_output_paths_inside_evidence(command: ValidatorCommand, evidence_dir: Path) -> bool:
    if not command.requires_output_containment:
        return True

    parts = [str(part) for part in command.command]
    output_flags = set(command.output_target_flags)
    output_paths: list[Path] = []
    for idx, part in enumerate(parts[:-1]):
        if part in output_flags:
            output_paths.append(Path(parts[idx + 1]))

    if not output_paths:
        return False
    return all(_is_relative_to(path, evidence_dir) for path in output_paths)


def validate_validator_commands(
    commands: Sequence[ValidatorCommand],
    *,
    copied_db_path: Path,
    evidence_dir: Path | None = None,
) -> ValidatorTargetCheck:
    unsupported = [
        command.name
        for command in commands
        if not validator_has_explicit_db_target(command, copied_db_path)
    ]
    if unsupported:
        return ValidatorTargetCheck(
            ok=False,
            code=UNSUPPORTED_VALIDATOR_TARGET_CODE,
            message=f"{UNSUPPORTED_VALIDATOR_TARGET_CODE}: {', '.join(unsupported)}",
        )
    if evidence_dir is None:
        uncontained = [command.name for command in commands if command.requires_output_containment]
    else:
        uncontained = [
            command.name
            for command in commands
            if not validator_output_paths_inside_evidence(command, evidence_dir)
        ]
    if uncontained:
        return ValidatorTargetCheck(
            ok=False,
            code=UNCONTAINED_VALIDATOR_OUTPUT_CODE,
            message=f"{UNCONTAINED_VALIDATOR_OUTPUT_CODE}: {', '.join(uncontained)}",
        )
    return ValidatorTargetCheck(ok=True, code="OK", message="validator targets explicit")


def _run_validator_command(command: ValidatorCommand, *, project_root: Path) -> ValidatorRunResult:
    completed = subprocess.run(
        command.command,
        cwd=str(project_root),
        text=True,
        capture_output=True,
        check=False,
    )
    status = "PASS" if int(completed.returncode) == 0 else "FAIL"
    return ValidatorRunResult(
        name=command.name,
        command=command.command,
        exit_code=int(completed.returncode),
        status=status,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _collect_warning_cohorts(db_path: Path) -> list[dict[str, Any]]:
    cohorts: list[dict[str, Any]] = []
    tables = [
        ("product_identity_quarantine", "fact_order_entry_product_identity_quarantine"),
        ("header_only_source_gap", "fact_order_entry_header_only_source_gap_quarantine"),
    ]
    uri = f"file:{db_path.resolve()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        for cohort, table in tables:
            if not _table_exists(conn, table):
                cohorts.append(
                    {
                        "cohort": cohort,
                        "table": table,
                        "status": "MISSING",
                        "row_count": None,
                        "active_count": None,
                    }
                )
                continue
            row_count = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            active_count: int | None = None
            columns = _column_names(conn, table)
            if "active" in columns:
                active_count = int(
                    conn.execute(f"SELECT COUNT(*) FROM {table} WHERE active = 1").fetchone()[0]
                )
            cohorts.append(
                {
                    "cohort": cohort,
                    "table": table,
                    "status": "VISIBLE",
                    "row_count": row_count,
                    "active_count": active_count,
                }
            )
    finally:
        conn.close()
    return cohorts


def _banner_status(validator_runs: Sequence[ValidatorRunResult], *, execute_validators: bool) -> str:
    if not execute_validators:
        return "WARNING"
    if any(run.exit_code != 0 for run in validator_runs):
        return "BLOCKED"
    return "GREEN"


def _write_evidence_index(evidence_dir: Path, written_files: Sequence[Path]) -> Path:
    lines = ["file\tpurpose\n"]
    for path in written_files:
        rel = path.relative_to(evidence_dir)
        lines.append(f"{rel}\tOption C validate-only runner artifact\n")
    return _write_text(evidence_dir, ("EVIDENCE_FILE_INDEX.tsv",), "".join(lines))


def _cash_risk_daily_draft(*, banner: dict[str, Any], banner_path: Path) -> str:
    return "\n".join(
        [
            "# Cash Risk Daily",
            "",
            "Draft only. Validate-only evidence, not production decision authority.",
            "",
            f"- Trust banner: `{banner_path}`",
            f"- Banner status: `{banner['banner_status']}`",
            f"- As of: `{banner['as_of_date']}`",
            f"- DB mode: `{banner['db_mode']}`",
            "",
            "Blocked decisions:",
            "",
            *[f"- `{decision}`" for decision in banner["blocked_decisions"]],
            "",
            "Allowed decisions:",
            "",
            *[f"- `{decision}`" for decision in banner["allowed_decisions"]],
            "",
        ]
    )


def run_validate_only(config: ValidateOnlyConfig) -> ValidateOnlyResult:
    mode = config.mode.strip()
    if mode not in {"existing-copy", "copy-production"}:
        return ValidateOnlyResult(
            exit_code=2,
            message=f"OPTION_C_VALIDATE_ONLY_BLOCKED unsupported_mode={mode}",
        )

    if mode == "copy-production":
        proof_block = _proof_window_lock_block_status(config.project_root)
        if proof_block is not None:
            code, message = proof_block
            return ValidateOnlyResult(exit_code=code, message=message)

    evidence_dir = config.evidence_dir.resolve()
    written_files: list[Path] = []
    evidence_dir.mkdir(parents=True, exist_ok=True)

    if mode == "existing-copy":
        if config.copied_db_path is None:
            return ValidateOnlyResult(
                exit_code=2,
                message="OPTION_C_VALIDATE_ONLY_BLOCKED copied_db_path_required",
                written_files=written_files,
            )
        copied_db_path = config.copied_db_path.resolve()
        proof_window_lock_state = "not_checked_already_copied_db"
        production_db_touched = False
    else:
        source_db = (config.source_db_path or DEFAULT_PRODUCTION_DB).resolve()
        copied_db_path = _safe_child(evidence_dir, "03_db_copy", "app_option_c_validate_only.db")
        _copy_source_db(source_db, copied_db_path)
        written_files.append(copied_db_path)
        proof_window_lock_state = "absent"
        production_db_touched = True

    if not copied_db_path.exists():
        return ValidateOnlyResult(
            exit_code=2,
            message=f"OPTION_C_VALIDATE_ONLY_BLOCKED copied_db_missing path={copied_db_path}",
            written_files=written_files,
            copied_db_path=copied_db_path,
        )

    integrity = _integrity_check_readonly(copied_db_path)
    copied_db_sha = _sha256_file(copied_db_path)
    envelope = {
        "mode": "validate_only",
        "db_mode": mode,
        "as_of_date": config.as_of,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "evidence_dir": str(evidence_dir),
        "copied_db_path": str(copied_db_path),
        "copied_db_sha256": copied_db_sha,
        "copied_db_integrity": integrity,
        "proof_window_lock_state": proof_window_lock_state,
        "production_db_touched": production_db_touched,
        "surface": config.surface,
    }
    written_files.append(_write_json(evidence_dir, ("00_run_envelope.json",), envelope))

    commands = build_validator_commands(
        copied_db_path=copied_db_path,
        as_of=config.as_of,
        evidence_dir=evidence_dir,
    )
    target_check = validate_validator_commands(
        commands,
        copied_db_path=copied_db_path,
        evidence_dir=evidence_dir,
    )
    validator_runs: list[ValidatorRunResult] = []
    if target_check.ok and config.execute_validators:
        validator_runs = [
            _run_validator_command(command, project_root=config.project_root)
            for command in commands
        ]

    validator_payload = {
        "target_check": target_check.__dict__,
        "execute_validators": bool(config.execute_validators),
        "commands": [command.__dict__ for command in commands],
        "runs": [run.__dict__ for run in validator_runs],
    }
    written_files.append(
        _write_json(evidence_dir, ("04_validator_outputs", "validator_matrix.json"), validator_payload)
    )

    warning_cohorts = _collect_warning_cohorts(copied_db_path)
    written_files.append(
        _write_json(evidence_dir, ("05_exception_queues", "warning_cohorts.json"), warning_cohorts)
    )

    status = _banner_status(validator_runs, execute_validators=config.execute_validators)
    if integrity != "ok":
        status = "BLOCKED"
    if not target_check.ok:
        status = "BLOCKED"

    banner = {
        "surface": "Cash Risk Daily",
        "mode": "validate_only",
        "banner_status": status,
        "generated_at": envelope["generated_at"],
        "as_of_date": config.as_of,
        "db_mode": mode,
        "copied_db_path": str(copied_db_path),
        "copied_db_sha256": copied_db_sha,
        "copied_db_integrity": integrity,
        "proof_window_lock_state": proof_window_lock_state,
        "source_freshness_status": status,
        "validator_status": status if target_check.ok else target_check.code,
        "warning_cohorts": warning_cohorts,
        "blocked_decisions": [
            "cash_movement",
            "supplier_payment",
            "po_commitment",
            "ad_spend",
            "external_send",
            "workbook_write",
            "scheduler_enablement",
            "production_db_write",
            "price_or_stock_change",
        ],
        "allowed_decisions": [
            "review_draft",
            "review_exceptions",
            "request_source_refresh",
            "request_later_implementation_review",
        ],
        "last_statement_date": None,
        "evidence_path": str(evidence_dir),
    }
    banner_path = _write_json(
        evidence_dir,
        ("07_trust_banners", "cash_risk_daily_trust_banner.json"),
        banner,
    )
    written_files.append(banner_path)
    owner_draft_path = _write_text(
        evidence_dir,
        ("06_owner_drafts", "cash_risk_daily.md"),
        _cash_risk_daily_draft(banner=banner, banner_path=banner_path),
    )
    written_files.append(owner_draft_path)
    written_files.append(_write_evidence_index(evidence_dir, written_files))

    if status == "GREEN":
        exit_code = 0
    else:
        exit_code = 2
    message = f"OPTION_C_VALIDATE_ONLY_{status} evidence={evidence_dir}"
    return ValidateOnlyResult(
        exit_code=exit_code,
        message=message,
        written_files=written_files,
        banner_path=banner_path,
        owner_draft_path=owner_draft_path,
        copied_db_path=copied_db_path,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Option C validate-only on a copied/read-only DB")
    parser.add_argument("--as-of", default=date.today().isoformat())
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument(
        "--mode",
        choices=["existing-copy", "copy-production"],
        default="existing-copy",
        help="existing-copy never opens production DB; copy-production checks proof-window lock before copy",
    )
    parser.add_argument("--copied-db", type=Path, default=None)
    parser.add_argument("--source-db", type=Path, default=DEFAULT_PRODUCTION_DB)
    parser.add_argument("--no-execute-validators", action="store_true")
    args = parser.parse_args(argv)

    result = run_validate_only(
        ValidateOnlyConfig(
            as_of=str(args.as_of),
            evidence_dir=args.evidence_dir,
            mode=str(args.mode),
            source_db_path=args.source_db,
            copied_db_path=args.copied_db,
            execute_validators=not bool(args.no_execute_validators),
        )
    )
    print(
        json.dumps(
            {
                "exit_code": result.exit_code,
                "message": result.message,
                "banner_path": str(result.banner_path) if result.banner_path else None,
                "owner_draft_path": str(result.owner_draft_path) if result.owner_draft_path else None,
                "copied_db_path": str(result.copied_db_path) if result.copied_db_path else None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return int(result.exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
