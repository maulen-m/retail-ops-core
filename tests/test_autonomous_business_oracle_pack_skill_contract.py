from pathlib import Path


SKILL_ROOT = Path("Oracle_listings/skills/autonomous-business-oracle-pack")


def test_skill_files_exist() -> None:
    assert (SKILL_ROOT / "SKILL.md").exists()
    assert (SKILL_ROOT / "agents" / "openai.yaml").exists()
    assert (SKILL_ROOT / "scripts" / "build_oracle_pack.py").exists()


def test_zipper_skill_points_to_dedicated_oracle_pack_skill() -> None:
    content = Path("Oracle_listings/skills/autonomous_business_zipper/SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "autonomous-business-oracle-pack" in content


def test_oracle_pack_skill_requires_finder_open_and_no_opt_out() -> None:
    content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert "opens the final folder in Finder automatically" in content
    assert "--no-open-finder" not in content


def test_oracle_pack_skill_is_external_dir_only() -> None:
    content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert "~/Docs/Oracle/Autonomous_business/" in content
    assert "Output root is always" in content
    assert "--output-root" not in content
