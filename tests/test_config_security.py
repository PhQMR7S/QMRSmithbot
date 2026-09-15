import pytest
from pydantic import SecretStr

from qmrsmithbot.config import Settings

OIDC_TEST_VALUES = {
    "auth_oidc_enabled": True,
    "auth_oidc_issuer": "https://id.example.com",
    "auth_oidc_client_id": "qmrsmithbot-test",
    "auth_oidc_client_secret": SecretStr("oidc-secret"),
    "auth_oidc_redirect_uri": "https://app.example.com/api/v1/auth/oidc/callback",
    "auth_state_encryption_key": SecretStr(
        "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
    ),
}
TELEGRAM_TEST_VALUES = {
    "telegram_credential_encryption_key": SecretStr(
        "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB="
    ),
    "telegram_webhook_base_url": "https://app.example.com",
}


def test_production_requires_rate_limiting() -> None:
    with pytest.raises(ValueError, match="RATE_LIMIT_ENABLED"):
        Settings(
            app_env="production",
            telegram_factory_bot_token=SecretStr("telegram-secret"),
            database_url="postgresql+asyncpg://app:secret@db/qmrsmith",
            auth_dev_bootstrap_enabled=False,
            rate_limit_enabled=False,
            **TELEGRAM_TEST_VALUES,
        )


def test_production_accepts_explicit_security_controls() -> None:
    settings = Settings(
        app_env="production",
        telegram_factory_bot_token=SecretStr("telegram-secret"),
        database_url="postgresql+asyncpg://app:secret@db/qmrsmith",
        auth_dev_bootstrap_enabled=False,
        rate_limit_enabled=True,
        **OIDC_TEST_VALUES,
        **TELEGRAM_TEST_VALUES,
    )
    assert settings.rate_limit_requests == 10
    assert settings.rate_limit_window_seconds == 60
    assert settings.telegram_webhook_base_url == "https://app.example.com"
