"""Application configuration for the Feature Phone Digital Forensics System."""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    app_name: str = "Feature Phone Digital Forensics System"
    app_version: str = "0.1.0"
    api_v1_prefix: str = "/api/v1"
    offline_mode: bool = True

    database_url: str = f"sqlite:///{(BASE_DIR / 'forensics.db').as_posix()}"
    evidence_dir: Path = BASE_DIR / "evidence"

    secret_key: str = "offline-forensics-lab-dev-secret-change-in-production"
    access_token_expire_minutes: int = 480

    default_admin_username: str = "admin"
    default_admin_password: str = "ForensicsLab!2026"
    default_admin_full_name: str = "Lab Administrator"

    model_config = SettingsConfigDict(env_prefix="FPF_", extra="ignore")


settings = Settings()

