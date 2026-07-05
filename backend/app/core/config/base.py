from pathlib import Path

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseAppSettings(BaseSettings):
    @computed_field
    @property
    def PROJECT_ROOT(self) -> Path:
        return Path(__file__).resolve().parent.parent.parent.parent

    @computed_field
    @property
    def FIXTURE_JOBS_PATH(self) -> Path:
        return self.PROJECT_ROOT / "data" / "sample_jobs.json"

    @computed_field
    @property
    def SKILL_ALIASES_PATH(self) -> Path:
        return self.PROJECT_ROOT / "data" / "skill_aliases.json"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )