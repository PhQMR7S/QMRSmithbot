from qmrsmithbot.runtime.access import AccessDecision, PlatformAccessGate


class FakeMembership:
    def __init__(self, members: set[tuple[int, str]]) -> None:
        self.members = members

    async def is_member(self, user_id: int, channel: str) -> bool:
        return (user_id, channel) in self.members


async def test_gate_reports_all_missing_channels() -> None:
    gate = PlatformAccessGate(FakeMembership({(7, "@qmr") }))
    decision = await gate.check(
        user_id=7,
        enabled=True,
        required_channels=("@qmr", "@qmrnews"),
    )
    assert decision == AccessDecision(False, ("@qmrnews",))


async def test_gate_bypass_does_not_query_membership() -> None:
    gate = PlatformAccessGate(FakeMembership(set()))
    decision = await gate.check(
        user_id=7,
        enabled=True,
        required_channels=("@qmr",),
        admin_bypass=True,
    )
    assert decision.allowed
