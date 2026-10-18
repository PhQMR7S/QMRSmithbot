import pytest
from pydantic import ValidationError

from qmrsmithbot.config import Settings


def test_factory_admin_ids_from_environment(monkeypatch):
    monkeypatch.setenv("TELEGRAM_FACTORY_ADMIN_IDS", "[123456, 987654]")
    assert Settings(_env_file=None).telegram_factory_admin_ids == (123456, 987654)


@pytest.mark.parametrize("ids", [(0,), (-1,)])
def test_invalid_admin_ids(ids):
    with pytest.raises(ValidationError, match="positive user IDs"):
        Settings(_env_file=None, telegram_factory_admin_ids=ids)


def test_token_remains_masked():
    config = Settings(_env_file=None, telegram_factory_bot_token="private-test-value")
    assert "private-test-value" not in repr(config)
    assert "private-test-value" not in config.model_dump_json()



def test_enabling_factory_requires_secret():
    with pytest.raises(ValidationError, match="Factory webhook secret"):
        Settings(_env_file=None, telegram_factory_enabled=True,
                 telegram_factory_bot_token='test', telegram_factory_webhook_secret='short')


def test_factory_secret_is_masked():
    config = Settings(_env_file=None, telegram_factory_webhook_secret='private-test-secret')
    assert 'private-test-secret' not in config.model_dump_json()



def test_enabled_factory_requires_valid_token_format():
    with pytest.raises(ValidationError, match="invalid format"):
        Settings(_env_file=None, telegram_factory_enabled=True,
                 telegram_factory_bot_token='invalid', telegram_factory_webhook_secret='a' * 48)
