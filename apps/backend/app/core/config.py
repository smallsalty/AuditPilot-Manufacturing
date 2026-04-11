from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    database_url: str = Field(
        default="postgresql+psycopg://auditpilot:auditpilot@localhost:5432/auditpilot",
        alias="DATABASE_URL",
    )
    llm_provider: str = Field(default="minimax", alias="LLM_PROVIDER")
    llm_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("LLM_API_KEY", "GLM_API_KEY"),
    )
    llm_base_url: str = Field(
        default="https://api.minimax.io/v1",
        validation_alias=AliasChoices("LLM_BASE_URL", "GLM_BASE_URL"),
    )
    llm_model: str = Field(
        default="",
        validation_alias=AliasChoices("LLM_MODEL", "GLM_MODEL"),
    )
    akshare_enable: bool = Field(default=True, alias="AKSHARE_ENABLE")
    cninfo_enable: bool = Field(default=True, alias="CNINFO_ENABLE")
    cninfo_query_url: str = Field(
        default="https://www.cninfo.com.cn/new/hisAnnouncement/query",
        alias="CNINFO_QUERY_URL",
    )
    cninfo_static_base_url: str = Field(default="https://static.cninfo.com.cn", alias="CNINFO_STATIC_BASE_URL")
    sync_lookback_days: int = Field(default=7, alias="SYNC_LOOKBACK_DAYS")
    embedding_model_name: str = Field(default="hashing-zh-demo", alias="EMBEDDING_MODEL_NAME")
    backend_cors_origins_raw: str = Field(default="http://localhost:3000", alias="BACKEND_CORS_ORIGINS")

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[4] / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def repo_root(self) -> Path:
        return Path(__file__).resolve().parents[4]

    @property
    def data_root(self) -> Path:
        return self.repo_root / "data"

    @property
    def uploads_dir(self) -> Path:
        return self.repo_root / "apps" / "backend" / "uploads"

    @property
    def backend_cors_origins(self) -> list[str]:
        return [item.strip() for item in self.backend_cors_origins_raw.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
