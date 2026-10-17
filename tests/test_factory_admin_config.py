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
