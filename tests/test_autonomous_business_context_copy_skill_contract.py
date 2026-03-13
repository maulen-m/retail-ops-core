from pathlib import Path


SKILL_ROOT = Path("Oracle_listings/skills/autonomous-business-context-copy")


def test_skill_files_exist() -> None:
    assert (SKILL_ROOT / "SKILL.md").exists()
    assert (SKILL_ROOT / "agents" / "openai.yaml").exists()
    assert (SKILL_ROOT / "scripts" / "build_context_copy.py").exists()


def test_skill_requires_flat_updated_folder_and_finder_open() -> None:
    content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert "Updated/" in content
    assert "flat" in content.lower()
    assert "opens the finished folder in Finder automatically" in content
    assert "original basenames" in content


def test_skill_requires_fresh_top17_context_folder() -> None:
    content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert "context_top17_md_" in content
    assert "top 17" in content.lower()
    assert "Do not carry forward older `context_top20_md_*`" in content
    assert "Do not create inner subfolders inside `context_top17_md_<timestamp>/`" in content


def test_skill_points_to_external_oracle_root_only() -> None:
    content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert "~/Docs/Oracle/Autonomous_business/" in content
    assert "external" in content.lower()
