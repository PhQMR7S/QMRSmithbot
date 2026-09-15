from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    app_name: str = "QMRSmithbot"
    log_level: str = "INFO"
    database_url: str
    redis_url: str
    telegram_factory_bot_token: str
    platform_required_channel: str
    platform_required_channel_enabled: bool = True

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
