"""Local-first configuration. External AI and emergency dispatch are disabled by default."""
from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "VIIL Sentinel"
    demo_mode: bool = True
    meta_provider: str = "mock"
    meta_model_id: str = "muse-spark-1.3"
    meta_model_api_key: SecretStr | None = None
    # Live provider may only be invoked by explicit local probe, never demo requests.
    meta_live_enabled: bool = False
    # Candidate intake is synthetic-only and disabled without a separate HMAC secret.
    edge_candidate_ingest_enabled: bool = False
    edge_candidate_source_id: str = "synthetic-clip-01"
    edge_candidate_hmac_secret: SecretStr | None = None
    edge_candidate_ledger_path: str | None = None
    # Separate read-only, loopback-only UI contract. Not production user RBAC.
    caregiver_inbox_enabled: bool = False
    caregiver_inbox_token: SecretStr | None = None
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def allowed_origins(self) -> list[str]:
        return [value.strip() for value in self.cors_origins.split(",") if value.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
