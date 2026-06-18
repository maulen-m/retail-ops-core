#!/usr/bin/env python3
"""Validate the active MVOS source contract registry.

The validator accepts the current registry's legacy field names while reporting
canonical-field gaps separately, so the gate can distinguish active conflicts
from migration work that belongs in later contract cleanup.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY = (
    PROJECT_ROOT
    / "docs"
    / "contracts"
    / "mvos_source_contracts"
    / "ACTIVE_MVOS_SOURCE_CONTRACT_REGISTRY.json"
)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _field(contract: dict[str, Any], canonical: str, *aliases: str) -> Any:
    if canonical in contract:
        return contract[canonical]
    for alias in aliases:
        if alias in contract:
            return contract[alias]
    return None


def _path_for_artifact(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _digest_path(path: Path) -> str:
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    rows: list[str] = []
    for child in sorted(p for p in path.rglob("*") if p.is_file()):
        rel = child.relative_to(path).as_posix()
        rows.append(f"{rel}\t{child.stat().st_size}\t{hashlib.sha256(child.read_bytes()).hexdigest()}")
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()


def validate_registry(registry_path: Path, *, strict: bool = False) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    computed_artifact_sha256: dict[str, dict[str, str]] = {}

    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "ok": False,
            "errors": [f"registry JSON load failed: {exc}"],
            "warnings": [],
            "contract_count": 0,
            "active_contract_count": 0,
            "computed_artifact_sha256": {},
        }

    if not isinstance(registry, dict):
        errors.append("registry root must be a JSON object")
        contracts: list[Any] = []
    else:
        if not registry.get("schema_version"):
            errors.append("registry missing schema_version")
        if not registry.get("registry_id"):
            errors.append("registry missing registry_id")
        contracts = _as_list(registry.get("contracts"))
        if not isinstance(registry.get("contracts"), list):
            errors.append("registry key contracts must be a list")

    seen_contract_ids: set[str] = set()
    active_domain_scope: dict[tuple[str, str], str] = {}
    active_count = 0

    for index, raw_contract in enumerate(contracts):
        if not isinstance(raw_contract, dict):
            errors.append(f"contracts[{index}] must be an object")
            continue

        contract_id = str(raw_contract.get("contract_id") or "").strip()
        domain = str(raw_contract.get("domain") or "").strip()
        proof_scope = str(_field(raw_contract, "proof_scope", "scope") or "").strip()
        scope_profile = str(raw_contract.get("scope_profile") or "").strip()
        source_paths = [str(p) for p in _as_list(_field(raw_contract, "source_artifact_paths", "evidence_paths"))]
        source_sha = _field(raw_contract, "source_artifact_sha256")
        production_authority = _field(raw_contract, "production_authority", "production_use_allowed")
        owner_publication_authority = _field(raw_contract, "owner_publication_authority")
        required_validators = _as_list(raw_contract.get("required_validators"))
        retained_blockers = _as_list(raw_contract.get("retained_blockers"))
        forbidden_claims = _as_list(_field(raw_contract, "forbidden_claims", "stoplines"))
        active = _as_bool(raw_contract.get("active", True))

        label = contract_id or f"contracts[{index}]"

        if not contract_id:
            errors.append(f"contracts[{index}] missing contract_id")
        elif contract_id in seen_contract_ids:
            errors.append(f"duplicate contract_id: {contract_id}")
        seen_contract_ids.add(contract_id)

        if not domain:
            errors.append(f"{label} missing domain")
        if not proof_scope:
            errors.append(f"{label} missing proof_scope/scope")
        if not raw_contract.get("accepted_by"):
            errors.append(f"{label} missing accepted_by")
        if not raw_contract.get("accepted_at"):
            errors.append(f"{label} missing accepted_at")
        if not required_validators:
            errors.append(f"{label} missing required_validators")
        if not forbidden_claims:
            errors.append(f"{label} missing forbidden_claims/stoplines")

        if not scope_profile:
            warnings.append(f"{label} missing canonical scope_profile field")
        if source_paths and source_sha is None:
            warnings.append(f"{label} missing canonical source_artifact_sha256 field; computed dynamically")
        if not retained_blockers:
            warnings.append(f"{label} has no retained_blockers list; using contract status/stoplines for blocker visibility")
        if owner_publication_authority is None:
            warnings.append(f"{label} missing owner_publication_authority; treated as false")

        if active:
            active_count += 1
            key = (domain, proof_scope)
            prior = active_domain_scope.get(key)
            if prior is not None:
                errors.append(
                    f"duplicate active domain/scope: {domain}/{proof_scope} ({prior}, {label})"
                )
            else:
                active_domain_scope[key] = label

        if "copied_temp" in proof_scope and _as_bool(production_authority):
            errors.append(f"{label} is copied-temp scoped but claims production authority")
        if "copied_temp" in proof_scope and _as_bool(owner_publication_authority):
            errors.append(f"{label} is copied-temp scoped but claims owner publication authority")
        if raw_contract.get("superseded_by") and active:
            errors.append(f"{label} is active but has superseded_by={raw_contract.get('superseded_by')}")

        computed: dict[str, str] = {}
        for raw_path in source_paths:
            path = _path_for_artifact(raw_path)
            if not path.exists():
                errors.append(f"{label} source artifact missing: {raw_path}")
                continue
            computed[raw_path] = _digest_path(path)
        if computed:
            computed_artifact_sha256[label] = computed

    return {
        "ok": not errors,
        "strict": strict,
        "registry": str(registry_path),
        "contract_count": len(contracts),
        "active_contract_count": active_count,
        "errors": errors,
        "warnings": warnings,
        "computed_artifact_sha256": computed_artifact_sha256,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the active MVOS source contract registry")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = validate_registry(args.registry, strict=args.strict)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    elif report["ok"]:
        print("MVOS_SOURCE_CONTRACT_REGISTRY PASS")
        print(f"contract_count={report['contract_count']}")
        print(f"active_contract_count={report['active_contract_count']}")
        print(f"warning_count={len(report['warnings'])}")
    else:
        print("MVOS_SOURCE_CONTRACT_REGISTRY FAIL")
        for err in report["errors"]:
            print(f"- {err}")
        if report["warnings"]:
            print("warnings:")
            for warning in report["warnings"]:
                print(f"- {warning}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

