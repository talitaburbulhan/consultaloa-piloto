from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "LOA — Pesquisa com evidências"
    database_url: str = "sqlite:///./storage/loa.db"
    feedback_database_url: str = ""
    source_dir: Path = Path("../dados")
    storage_dir: Path = Path("./storage")
    cors_origins: str = "http://localhost:3000"
    auth_required: bool = False
    editor_emails: str = ""
    reviewer_emails: str = ""
    pilot_education_only: bool = True
    cloudflare_access_team_domain: str = ""
    cloudflare_access_audience: str = ""
    environment: str = "development"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def allowed_origins(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def allowed_editors(self) -> set[str]:
        return {item.strip().casefold() for item in self.editor_emails.split(",") if item.strip()}

    @property
    def allowed_reviewers(self) -> set[str]:
        return {item.strip().casefold() for item in self.reviewer_emails.split(",") if item.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
