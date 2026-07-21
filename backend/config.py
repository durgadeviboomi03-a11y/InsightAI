"""
backend/config.py

Centralized application settings, loaded from environment variables (.env file).

Uses Pydantic Settings so every value is validated and type-checked at startup —
if a required setting is missing or malformed, the app fails fast with a clear
error instead of crashing later mid-request.
"""

from functools import lru_cache
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application-wide settings.

    Values are loaded from a `.env` file in the project root, falling back
    to the defaults defined below if not set. Never hardcode real secrets
    here — defaults exist only for local development convenience.
    """

    # ---------- General ----------
    APP_NAME: str = "InsightAI"
    APP_ENV: str = "development"  # development | staging | production
    DEBUG: bool = True

    # ---------- Database ----------
    DATABASE_URL: str = "mysql+pymysql://insightai_user:insightai_pass@localhost:3306/insightai"

    # ---------- Authentication / JWT ----------
    SECRET_KEY: str = "changeme-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ---------- CORS ----------
    # Comma-separated list in .env, e.g.: CORS_ORIGINS=http://localhost:5500,http://127.0.0.1:5500
    CORS_ORIGINS: List[str] = ["http://localhost:5500", "http://127.0.0.1:5500"]

    # ---------- File Upload ----------
    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_SIZE_MB: int = 50
    ALLOWED_UPLOAD_EXTENSIONS: List[str] = [".csv", ".xlsx", ".xls"]

    # ---------- Reports ----------
    REPORTS_DIR: str = "reports"
    CHARTS_DIR: str = "charts"

    # ---------- ML Models ----------
    MODELS_DIR: str = "models"

    # ---------- Generative AI ----------
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-1.5-flash"

    # ---------- Logging ----------
    LOG_LEVEL: str = "INFO"
    LOG_DIR: str = "logs"

    @field_validator("CORS_ORIGINS", "ALLOWED_UPLOAD_EXTENSIONS", mode="before")
    @classmethod
    def split_comma_separated(cls, value: str | List[str]) -> List[str]:
        """
        Allows CORS_ORIGINS and ALLOWED_UPLOAD_EXTENSIONS to be set in .env
        as a plain comma-separated string (e.g. "a,b,c") while still being
        usable as a proper Python list throughout the app.
        """
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """
    Returns a cached Settings instance.

    Using lru_cache means the .env file is only read once per process
    lifetime, and the same Settings object is reused everywhere it's
    requested — avoiding repeated disk reads and ensuring consistency.
    """
    return Settings()