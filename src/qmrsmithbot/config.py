from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    app_name: str = "QMRSmithbot"
    log_level: str = "INFO"
    database_url: str = "postgresql+asyncpg://qmrsmith:qmrsmith@localhost:5432/qmrsmith"
    redis_url: str = "redis://localhost:6379/0"
    telegram_factory_bot_token: str = ""
    platform_required_channel: str = ""
    platform_required_channel_enabled: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
