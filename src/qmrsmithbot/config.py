from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse

from cryptography.fernet import Fernet
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    app_name: str = "QMRSmithbot"
    log_level: str = "INFO"
    database_url: str = "postgresql+asyncpg://qmrsmith:qmrsmith@localhost:5432/qmrsmith"
    redis_url: str = "redis://localhost:6379/0"
    telegram_factory_bot_token: SecretStr = SecretStr("")
    telegram_factory_admin_ids: tuple[int, ...] = ()
    telegram_factory_enabled: bool = False
    telegram_runtime_consumer_verified: bool = False
    telegram_factory_webhook_secret: SecretStr = SecretStr("")
    telegram_credential_encryption_key: SecretStr = SecretStr("")
    telegram_webhook_base_url: str = ""
    telegram_worker_poll_seconds: float = Field(default=1.0, ge=0.1, le=30.0)
    telegram_worker_batch_size: int = Field(default=10, ge=1, le=100)
    telegram_worker_lease_seconds: int = Field(default=120, ge=10, le=3600)
    telegram_worker_handler_timeout_seconds: int = Field(default=90, ge=5, le=1800)
    telegram_worker_max_attempts: int = Field(default=8, ge=1, le=100)
    telegram_worker_shutdown_grace_seconds: int = Field(default=30, ge=1, le=300)
    platform_required_channel: str = ""
    platform_required_channel_enabled: bool = False
    auth_dev_bootstrap_enabled: bool = True
    auth_oidc_enabled: bool = False
    auth_oidc_issuer: str = ""
    auth_oidc_client_id: str = ""
    auth_oidc_client_secret: SecretStr = SecretStr("")
    auth_oidc_redirect_uri: str = ""
    auth_state_encryption_key: SecretStr = SecretStr("")
    session_absolute_ttl_minutes: int = Field(default=480, ge=5, le=10080)
    session_idle_ttl_minutes: int = Field(default=30, ge=5, le=1440)
    rate_limit_enabled: bool = False
    rate_limit_backend: Literal['redis', 'postgresql'] = 'redis'
    rate_limit_requests: int = Field(default=10, ge=1, le=10000)
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    @model_validator(mode="after")
    def validate_environment(self) -> "Settings":
        if self.telegram_factory_enabled:
            import re
            secret = self.telegram_factory_webhook_secret.get_secret_value()
            if not self.telegram_factory_bot_token.get_secret_value():
                raise ValueError("Factory token is required when the factory is enabled")
            if not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", secret):
                raise ValueError("Factory webhook secret must contain 32 to 256 URL-safe characters")
            if not re.fullmatch(r"[0-9]{5,16}:[A-Za-z0-9_-]{30,100}",
                                self.telegram_factory_bot_token.get_secret_value()):
                raise ValueError("Factory bot token has an invalid format")
        if any(user_id <= 0 for user_id in self.telegram_factory_admin_ids):
            raise ValueError("TELEGRAM_FACTORY_ADMIN_IDS must contain positive user IDs")
        environment = self.app_env.strip().lower()
        if environment not in {"development", "test", "staging", "production"}:
            raise ValueError("app_env must be development, test, staging, or production")
        if self.session_idle_ttl_minutes >= self.session_absolute_ttl_minutes:
            raise ValueError("session idle TTL must be shorter than absolute TTL")
        if self.telegram_worker_lease_seconds <= self.telegram_worker_poll_seconds:
            raise ValueError("Telegram worker lease must exceed poll interval")
        if self.telegram_worker_lease_seconds <= self.telegram_worker_handler_timeout_seconds:
            raise ValueError("Telegram worker lease must exceed handler timeout")
        if environment == "production":
            if not self.telegram_factory_bot_token.get_secret_value():
                raise ValueError("TELEGRAM_FACTORY_BOT_TOKEN is required in production")
            if not self.telegram_credential_encryption_key.get_secret_value().strip():
                raise ValueError("TELEGRAM_CREDENTIAL_ENCRYPTION_KEY is required in production")
            if not self.telegram_webhook_base_url.strip():
                raise ValueError("TELEGRAM_WEBHOOK_BASE_URL is required in production")
            if self.database_url == (
                "postgresql+asyncpg://qmrsmith:qmrsmith@localhost:5432/qmrsmith"
            ):
                raise ValueError("DATABASE_URL must be explicitly configured in production")
            if self.auth_dev_bootstrap_enabled:
                raise ValueError("AUTH_DEV_BOOTSTRAP_ENABLED must be false in production")
            if not self.rate_limit_enabled:
                raise ValueError("RATE_LIMIT_ENABLED must be true in production")
            if not self.auth_oidc_enabled:
                raise ValueError("AUTH_OIDC_ENABLED must be true in production")
        if self.telegram_credential_encryption_key.get_secret_value().strip():
            try:
                Fernet(
                    self.telegram_credential_encryption_key.get_secret_value().encode("ascii")
                )
            except (ValueError, TypeError) as exc:
                raise ValueError(
                    "TELEGRAM_CREDENTIAL_ENCRYPTION_KEY must be a valid Fernet key"
                ) from exc
        if self.telegram_webhook_base_url.strip():
            webhook_base = urlparse(self.telegram_webhook_base_url)
            if webhook_base.scheme != "https" or not webhook_base.netloc:
                raise ValueError("TELEGRAM_WEBHOOK_BASE_URL must be an HTTPS URL")
        if self.auth_oidc_enabled:
            required = {
                "AUTH_OIDC_ISSUER": self.auth_oidc_issuer,
                "AUTH_OIDC_CLIENT_ID": self.auth_oidc_client_id,
                "AUTH_OIDC_CLIENT_SECRET": self.auth_oidc_client_secret.get_secret_value(),
                "AUTH_OIDC_REDIRECT_URI": self.auth_oidc_redirect_uri,
                "AUTH_STATE_ENCRYPTION_KEY": self.auth_state_encryption_key.get_secret_value(),
            }
            missing = [name for name, value in required.items() if not value.strip()]
            if missing:
                raise ValueError(f"OIDC configuration is incomplete: {', '.join(missing)}")
            issuer = urlparse(self.auth_oidc_issuer)
            redirect = urlparse(self.auth_oidc_redirect_uri)
            if issuer.scheme != "https" or not issuer.netloc:
                raise ValueError("AUTH_OIDC_ISSUER must be an HTTPS URL")
            if redirect.scheme != "https" or not redirect.netloc:
                raise ValueError("AUTH_OIDC_REDIRECT_URI must be an HTTPS URL")
            try:
                Fernet(self.auth_state_encryption_key.get_secret_value().encode("ascii"))
            except (ValueError, TypeError) as exc:
                raise ValueError("AUTH_STATE_ENCRYPTION_KEY must be a valid Fernet key") from exc
        if self.platform_required_channel_enabled and not self.platform_required_channel.strip():
            raise ValueError(
                "PLATFORM_REQUIRED_CHANNEL is required when platform access protection is enabled"
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
