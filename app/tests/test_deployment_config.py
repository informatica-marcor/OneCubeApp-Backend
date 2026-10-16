import runpy
from pathlib import Path

import dotenv
import pytest


@pytest.fixture
def load_settings(monkeypatch):
    # Aislar las pruebas de credenciales y rutas del .env local.
    monkeypatch.setattr(dotenv, "load_dotenv", lambda: None)
    for name in ("DATABASE_URL", "URL_DATABASE", "ROOT", "HOST", "PORT", "PUBLIC_BASE_URL", "CORS_ORIGINS"):
        monkeypatch.delenv(name, raising=False)

    def load(**variables):
        for name, value in variables.items():
            monkeypatch.setenv(name, value)
        config = Path(__file__).resolve().parents[1] / "core" / "config.py"
        return runpy.run_path(str(config))["settings"]

    return load


def test_database_url_has_priority(load_settings):
    settings = load_settings(DATABASE_URL="postgresql://new/db", URL_DATABASE="postgresql://legacy/db")
    assert settings.database_url == "postgresql://new/db"


def test_legacy_database_url_supported(load_settings):
    assert load_settings(URL_DATABASE="postgresql://legacy/db").database_url == "postgresql://legacy/db"


def test_blank_database_url_falls_back_to_legacy(load_settings):
    assert load_settings(DATABASE_URL="", URL_DATABASE="postgresql://legacy/db").database_url == "postgresql://legacy/db"


def test_missing_database_url_is_actionable(load_settings):
    with pytest.raises(RuntimeError, match="Missing DATABASE_URL"):
        load_settings()


def test_https_public_url_and_cors(load_settings):
    settings = load_settings(
        DATABASE_URL="postgresql://test/db",
        PUBLIC_BASE_URL="https://api.example.com/",
        CORS_ORIGINS="https://app.example.com, http://localhost:5173",
    )
    assert settings.public_base_url == "https://api.example.com"
    assert settings.cors_origins == ["https://app.example.com", "http://localhost:5173"]


def test_local_defaults(load_settings):
    settings = load_settings(DATABASE_URL="postgresql://test/db")
    assert settings.root == "."
    assert settings.public_base_url == "http://localhost:8000"
    assert "http://localhost:5173" in settings.cors_origins


def test_legacy_host_and_port(load_settings):
    settings = load_settings(DATABASE_URL="postgresql://test/db", HOST="127.0.0.1", PORT="9000")
    assert settings.public_base_url == "http://127.0.0.1:9000"
