"""Local-first configuration. External AI and emergency dispatch are disabled by default."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "VIIL Sentinel"
    demo_mode: bool = True
    meta_provider: str = "mock"
    meta_model_id: str = "muse-spark-1.3"
    meta_model_api_key: str | None = None
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def allowed_origins(self) -> list[str]:
        return [value.strip() for value in self.cors_origins.split(",") if value.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
