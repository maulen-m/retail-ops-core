from pathlib import Path


def test_gmail_api_client_module_exists():
    assert Path("core/integrations/gmail_api_client.py").exists()


def test_gmail_pubsub_listener_wrapper_loads_env():
    script = Path("scripts/gmail_pubsub_listener.sh").read_text(encoding="utf-8")
    assert "scripts/load_dotenv.sh" in script
    assert "load_dotenv \"$ROOT/.env\"" in script
    assert "GOOGLE_APPLICATION_CREDENTIALS" in script


def test_gmail_watch_refresh_wrapper_loads_env():
    script = Path("scripts/gmail_watch_refresh.sh").read_text(encoding="utf-8")
    assert "scripts/load_dotenv.sh" in script
    assert "load_dotenv \"$ROOT/.env\"" in script
