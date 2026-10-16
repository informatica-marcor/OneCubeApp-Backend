from __future__ import annotations
from dataclasses import dataclass
from dotenv import load_dotenv
import os

load_dotenv()

def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        raise RuntimeError(f"Env var {name} must be an int. Got: {raw!r}")


def _get_list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if not raw:
        return default
    return [x.strip() for x in raw.split(",") if x.strip()]


@dataclass(frozen=True)
class Settings:
    host: str = os.getenv("HOST", "http://localhost")
    port: int = _get_int("PORT", 8000)

    database_url: str = os.getenv("DATABASE_URL") or os.getenv("URL_DATABASE")
    cors_origins: list[str] = None

    code_ttl_minutes: int = _get_int("CODE_TTL_MINUTES", 10)
    code_length: int = _get_int("CODE_LENGTH", 6)
    max_attempts: int = _get_int("MAX_ATTEMPTS", 5)
    temporary_access_days: int = _get_int("TEMPORARY_ACCESS_DAYS", 1)
    

    uploads_root: str = os.getenv("UPLOADS_ROOT")
    root: str = os.getenv("ROOT") or "."
    
    resend_api_key: str | None = os.getenv("RESEND_API_KEY")
    email_address: str | None = os.getenv("EMAIL_ADDRESS")

    encryption_key: str = os.getenv("ENCRYPTION_KEY")

    secret_key: str = os.getenv("SECRET_KEY")
    algorithm: str = os.getenv("ALGORITHM") or "HS256"
    access_token_expire_minutes: int = _get_int("ACCESS_TOKEN_EXPIRE_MINUTES", 43200)

    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")

    max_visits_per_user: int = _get_int("MAX_VISITS_PER_USER", 5)
    timezone: str = os.getenv("TIMEZONE", "America/Santiago")

    def __post_init__(self):
        if not self.database_url:
            raise RuntimeError("Missing DATABASE_URL (or URL_DATABASE) in environment or .env")
        if not self.public_base_url:
            host = self.host.removeprefix("http://").removeprefix("https://")
            object.__setattr__(self, "public_base_url", f"http://{host}:{self.port}")
        if self.cors_origins is None:
            object.__setattr__(self, "cors_origins", _get_list("CORS_ORIGINS", ["http://localhost:3000", "http://localhost:5173"]))

settings = Settings()