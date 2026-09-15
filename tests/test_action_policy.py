import pytest

from qmrsmithbot.workflows.action_policy import (
    ActionPolicyError,
    resolve_and_validate_host,
    validate_http_url,
    validate_redirect,
)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/secret",
        "http://localhost/secret",
        "http://169.254.169.254/latest/meta-data",
        "http://10.0.0.5/internal",
        "http://192.168.1.10/internal",
        "http://[::1]/secret",
        "ftp://example.com/file",
        "file:///etc/passwd",
        "http://user:pass@example.com/",
    ],
)
def test_http_url_rejects_unsafe_targets(url: str) -> None:
    with pytest.raises(ActionPolicyError):
        validate_http_url(url)


def test_http_url_accepts_public_https_target() -> None:
    assert validate_http_url("https://example.com/api") == "https://example.com/api"


def test_http_url_rejects_fragments_and_invalid_ports() -> None:
    with pytest.raises(ActionPolicyError, match="fragments"):
        validate_http_url("https://example.com/api#secret")
    with pytest.raises(ActionPolicyError, match="invalid port"):
        validate_http_url("https://example.com:bad/api")


def test_redirect_uses_the_same_url_policy() -> None:
    with pytest.raises(ActionPolicyError):
        validate_redirect("http://127.0.0.1/admin")


def test_resolved_addresses_are_rejected_when_private(monkeypatch: pytest.MonkeyPatch) -> None:
    from qmrsmithbot.workflows import action_policy

    monkeypatch.setattr(
        action_policy.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (2, 1, 6, "", ("10.0.0.7", 0)),
            (2, 1, 6, "", ("93.184.216.34", 0)),
        ],
    )

    with pytest.raises(ActionPolicyError, match="disallowed address"):
        resolve_and_validate_host("attacker.example")


def test_resolved_public_addresses_are_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    from qmrsmithbot.workflows import action_policy

    monkeypatch.setattr(
        action_policy.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("93.184.216.34", 0))],
    )

    resolved = resolve_and_validate_host("example.com")
    assert resolved[0].address == "93.184.216.34"
