from pathlib import Path


def test_assemble_store_shell_skips_non_shell_env_keys() -> None:
    text = Path("excel_ui/assemble_per_store/_assemble_store.sh").read_text(encoding="utf-8")
    assert "SHELL_KEY_RE = re.compile" in text
    assert "if not SHELL_KEY_RE.match(key):" in text
