from pathlib import Path


def test_gitignore_includes_ops_reliability_generated_paths() -> None:
    content = Path(".gitignore").read_text(encoding="utf-8")
    expected = [
        "Oracle_listings/generated/",
        "db/backups/",
        "db/backups",
        "db/backups.pre_migration_*/",
        "logs",
        "logs.pre_migration_*/",
        "backups",
        "backups.pre_migration_*/",
        "config/anchors/SALES_KSP_CRM_LATEST.xlsx",
        "config/business_insides/BUSINESS_INSIDES_*.md",
        "config/business_insides/snapshots/BUSINESS_INSIDES_*.md",
    ]
    for entry in expected:
        assert entry in content


def test_gitignore_does_not_ignore_transfer_ledger_docs() -> None:
    content = Path(".gitignore").read_text(encoding="utf-8")
    assert "docs/transfer_ledger/" not in content
    assert "transfer_ledger" not in [line.strip() for line in content.splitlines()]
