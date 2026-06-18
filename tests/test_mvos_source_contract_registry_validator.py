from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path("scripts/validate_mvos_source_contract_registry.py")
REGISTRY = Path("docs/contracts/mvos_source_contracts/ACTIVE_MVOS_SOURCE_CONTRACT_REGISTRY.json")


def test_mvos_source_contract_registry_validator_exists() -> None:
    assert SCRIPT.exists(), "missing scripts/validate_mvos_source_contract_registry.py"
    assert REGISTRY.exists(), "missing active MVOS source contract registry"


def test_mvos_source_contract_registry_passes_current_registry() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--strict"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "MVOS_SOURCE_CONTRACT_REGISTRY PASS" in completed.stdout


def test_mvos_source_contract_registry_rejects_duplicate_active_domain_scope(tmp_path: Path) -> None:
    registry = {
        "schema_version": "mvos_source_contract_registry.v1",
        "registry_id": "test",
        "contracts": [
            {
                "contract_id": "A",
                "domain": "ads_source_truth",
                "scope": "copied_temp_mvos_proof",
                "active": True,
                "accepted_by": "test",
                "accepted_at": "2026-05-18",
                "production_use_allowed": False,
                "owner_publication_authority": False,
                "proof_use_allowed": True,
                "evidence_paths": [],
                "required_validators": ["validator"],
                "stoplines": ["do_not_write"],
            },
            {
                "contract_id": "B",
                "domain": "ads_source_truth",
                "scope": "copied_temp_mvos_proof",
                "active": True,
                "accepted_by": "test",
                "accepted_at": "2026-05-18",
                "production_use_allowed": False,
                "owner_publication_authority": False,
                "proof_use_allowed": True,
                "evidence_paths": [],
                "required_validators": ["validator"],
                "stoplines": ["do_not_write"],
            },
        ],
    }
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps(registry), encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--registry", str(registry_path), "--strict"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert "duplicate active domain/scope" in (completed.stdout + completed.stderr)

