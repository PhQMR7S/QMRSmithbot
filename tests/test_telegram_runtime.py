from uuid import uuid4

from qmrsmithbot.telegram.provisioning import hash_webhook_secret, verify_webhook_secret
from qmrsmithbot.telegram.webhook_service import TelegramWebhookService


def test_webhook_secret_hash_is_constant_length_and_not_plaintext() -> None:
    secret = "A" * 32
    digest = hash_webhook_secret(secret)
    assert digest != secret
    assert len(digest) == 64
    assert verify_webhook_secret(secret, digest)
    assert not verify_webhook_secret("wrong", digest)


def test_webhook_url_is_project_scoped_and_https(monkeypatch) -> None:
    monkeypatch.setattr(
        "qmrsmithbot.telegram.webhook_service.settings.telegram_webhook_base_url",
        "https://runtime.example.test/",
    )
    project_id = uuid4()
    assert TelegramWebhookService._webhook_url(project_id) == (
        f"https://runtime.example.test/api/v1/telegram/webhook/{project_id}"
    )
