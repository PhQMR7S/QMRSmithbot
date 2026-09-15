from dataclasses import dataclass
from typing import Protocol


class TelegramMembershipChecker(Protocol):
    async def is_member(self, user_id: int, channel: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class AccessDecision:
    allowed: bool
    missing_channels: tuple[str, ...] = ()


class PlatformAccessGate:
    """Platform-owned access policy executed before tenant workflow logic."""

    def __init__(self, checker: TelegramMembershipChecker) -> None:
        self._checker = checker

    async def check(
        self,
        *,
        user_id: int,
        enabled: bool,
        required_channels: tuple[str, ...],
        admin_bypass: bool = False,
    ) -> AccessDecision:
        if not enabled or admin_bypass or not required_channels:
            return AccessDecision(True)

        missing = []
        for channel in required_channels:
            if not await self._checker.is_member(user_id, channel):
                missing.append(channel)

        return AccessDecision(not missing, tuple(missing))
