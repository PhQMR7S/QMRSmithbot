import pytest
from pydantic import SecretStr

from qmrsmithbot.config import Settings


def test_production_requires_rate_limiting() -> None:
    with pytest.raises(ValueError, match="RATE_LIMIT_ENABLED"):
        Settings(
            app_env="production",
            telegram_factory_bot_token=SecretStr("telegram-secret"),
            database_url="postgresql+asyncpg://app:secret@db/qmrsmith",
            auth_dev_bootstrap_enabled=False,
            rate_limit_enabled=False,
        )


def test_production_accepts_explicit_security_controls() -> None:
    settings = Settings(
        app_env="production",
        telegram_factory_bot_token=SecretStr("telegram-secret"),
        database_url="postgresql+asyncpg://app:secret@db/qmrsmith",
        auth_dev_bootstrap_enabled=False,
        rate_limit_enabled=True,
    )
    assert settings.rate_limit_requests == 10
    assert settings.rate_limit_window_seconds == 60
