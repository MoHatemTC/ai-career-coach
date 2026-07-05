from typing import ClassVar

from .base import BaseAppSettings
from pydantic import SecretStr, computed_field
from functools import lru_cache

class TestSettings(BaseAppSettings):
    # Not a pytest test class — stop pytest from collecting it by name.
    __test__: ClassVar[bool] = False

    TEST_POSTGRES_USER: str
    TEST_POSTGRES_PASSWORD: SecretStr
    TEST_POSTGRES_DB: str
    TEST_POSTGRES_HOST: str
    TEST_POSTGRES_PORT: int

    # LiteLLM proxy config for `integration`-marked tests only. Optional so the
    # default `make test` (unit) run never requires live-proxy credentials —
    # integration tests skip themselves when TEST_LITELLM_API_KEY is unset.
    TEST_LITELLM_BASE_URL: str = ""
    TEST_LITELLM_API_KEY: SecretStr = SecretStr("")
    TEST_LLM_MODEL: str = "azure/FW-Kimi-K2.6"

    @computed_field
    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+psycopg://"
            f"{self.TEST_POSTGRES_USER}:"
            f"{self.TEST_POSTGRES_PASSWORD.get_secret_value()}@"
            f"{self.TEST_POSTGRES_HOST}:"
            f"{self.TEST_POSTGRES_PORT}/"
            f"{self.TEST_POSTGRES_DB}"
        )




@lru_cache
def get_test_settings() -> TestSettings:
    return TestSettings()
           