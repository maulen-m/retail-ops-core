import subprocess
from pathlib import Path


def test_load_dotenv_preserves_spaces_and_prevents_command_execution(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "GMAIL_APP_PASSWORD=abcd efgh ijkl mnop",
                "GMAIL_USER=tester@example.com",
                "MALICIOUS=$(echo should_not_execute)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    script = """
set -euo pipefail
source scripts/load_dotenv.sh
load_dotenv "$1"
printf "%s\\n" "$GMAIL_APP_PASSWORD" "$GMAIL_USER" "$MALICIOUS"
"""
    result = subprocess.run(
        ["bash", "-lc", script, "--", str(env_file)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    lines = result.stdout.strip().splitlines()
    assert lines[0] == "abcd efgh ijkl mnop"
    assert lines[1] == "tester@example.com"
    assert lines[2] == "$(echo should_not_execute)"


def test_load_dotenv_missing_file_is_noop(tmp_path):
    missing = tmp_path / "missing.env"
    script = """
set -euo pipefail
source scripts/load_dotenv.sh
load_dotenv "$1"
echo "ok"
"""
    result = subprocess.run(
        ["bash", "-lc", script, "--", str(missing)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
