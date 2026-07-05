from .base import BaseAppSettings
from pydantic import SecretStr, computed_field
from functools import lru_cache

class Settings(BaseAppSettings):
    POSTGRES_USER: str
    POSTGRES_PASSWORD: SecretStr
    POSTGRES_DB: str
    POSTGRES_HOST: str
    POSTGRES_PORT: int
    CORS_ALLOWED_ORIGINS: list[str]
    LITELLM_BASE_URL:str
    LITELLM_API_KEY: SecretStr
    LLM_MODEL :str = "azure/FW-Kimi-K2.6"

    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Career Coach"
    ENVIRONMENT: str = "development"

    # Observability — read from the environment by the Langfuse SDK.
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"

    @computed_field
    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+psycopg://"
            f"{self.POSTGRES_USER}:"
            f"{self.POSTGRES_PASSWORD.get_secret_value()}@"
            f"{self.POSTGRES_HOST}:"
            f"{self.POSTGRES_PORT}/"
            f"{self.POSTGRES_DB}"
        )
        
    # Search Automation
    MATCH_SCORE_NOTIFICATION_THRESHOLD: int = 70
    TOP_N_JOBS_PER_USER: int = 3
    

@lru_cache
def get_settings() -> Settings:
    return Settings()