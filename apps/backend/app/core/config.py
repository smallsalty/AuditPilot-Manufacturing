import os
from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _candidate_roots() -> list[Path]:
    cwd = Path.cwd().resolve()
    current_file = Path(__file__).resolve()
    candidates = [cwd, *cwd.parents, current_file.parent, *current_file.parents]

    seen: set[Path] = set()
    ordered: list[Path] = []
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            ordered.append(candidate)
    return ordered


def _looks_like_repo_root(path: Path) -> bool:
    return (
        (path / ".git").exists()
        or (path / "apps" / "backend" / "pyproject.toml").exists()
        or (path / "apps" / "frontend").exists()
    )


def discover_repo_root() -> Path:
    env_root = os.getenv("AUDITPILOT_REPO_ROOT")
    if env_root:
        candidate = Path(env_root).expanduser().resolve()
        if candidate.exists():
            return candidate

    for candidate in _candidate_roots():
        if _looks_like_repo_root(candidate):
            return candidate

    return Path.cwd().resolve()


REPO_ROOT = discover_repo_root()
ENV_FILE = next(
    (candidate for candidate in [Path.cwd().resolve() / ".env", REPO_ROOT / ".env"] if candidate.exists()),
    REPO_ROOT / ".env",
)


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
        validation_alias=AliasChoices("ANTHROPIC_API_KEY", "LLM_API_KEY", "GLM_API_KEY"),
    )
    llm_base_url: str = Field(
        default="https://api.minimaxi.com/anthropic",
        validation_alias=AliasChoices("ANTHROPIC_BASE_URL", "LLM_BASE_URL", "GLM_BASE_URL"),
    )
    llm_model: str = Field(
        default="MiniMax-M2.7",
        validation_alias=AliasChoices("ANTHROPIC_MODEL", "LLM_MODEL", "GLM_MODEL"),
    )
    akshare_enable: bool = Field(default=True, alias="AKSHARE_ENABLE")
    cninfo_enable: bool = Field(default=True, alias="CNINFO_ENABLE")
    cninfo_query_url: str = Field(
        default="https://www.cninfo.com.cn/new/hisAnnouncement/query",
        alias="CNINFO_QUERY_URL",
    )
    cninfo_static_base_url: str = Field(default="https://static.cninfo.com.cn", alias="CNINFO_STATIC_BASE_URL")
    sync_lookback_days: int = Field(default=7, alias="SYNC_LOOKBACK_DAYS")
    sync_initial_lookback_days: int = Field(default=365, alias="SYNC_INITIAL_LOOKBACK_DAYS")
    embedding_model_name: str = Field(default="hashing-zh-demo", alias="EMBEDDING_MODEL_NAME")
    backend_cors_origins_raw: str = Field(default="http://localhost:3000", alias="BACKEND_CORS_ORIGINS")

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def repo_root(self) -> Path:
        return REPO_ROOT

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
