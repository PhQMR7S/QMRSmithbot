from uuid import UUID

from qmrsmithbot.request_context import resolve_request_id


def test_valid_request_id_is_normalized() -> None:
    value = "9D9B9B9E-2D9D-4F43-8D0D-3D8A4F6A2D17"
    assert resolve_request_id(value) == value.lower()
    UUID(resolve_request_id(value))


def test_invalid_request_id_is_replaced() -> None:
    generated = resolve_request_id("attacker-supplied-log-line")
    UUID(generated)
    assert generated != "attacker-supplied-log-line"
