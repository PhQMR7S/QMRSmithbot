from qmrsmithbot.telegram.provisioning import hash_webhook_secret, verify_webhook_secret


def test_webhook_secret_hash_is_deterministic_and_one_way_format() -> None:
    secret = "test-webhook-secret"
    digest = hash_webhook_secret(secret)
    assert len(digest) == 64
    assert digest != secret
    assert hash_webhook_secret(secret) == digest


def test_webhook_secret_verification_uses_exact_secret() -> None:
    stored_hash = hash_webhook_secret("correct-secret")
    assert verify_webhook_secret("correct-secret", stored_hash)
    assert not verify_webhook_secret("wrong-secret", stored_hash)
