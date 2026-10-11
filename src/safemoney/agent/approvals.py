"""Who answers an approval card: a person in the UI, or a fixed eval policy."""

from __future__ import annotations

import asyncio
from typing import Literal, Protocol

Decision = Literal["approved", "declined", "expired"]


class Approver(Protocol):
    async def decide(self, approval_id: str, timeout_s: float) -> Decision: ...


class UIApprover:
    """Waits for the person to hold Approve or tap Decline in the app."""

    def __init__(self) -> None:
        self._pending: dict[str, asyncio.Future[Decision]] = {}

    async def decide(self, approval_id: str, timeout_s: float) -> Decision:
        fut: asyncio.Future[Decision] = asyncio.get_running_loop().create_future()
        self._pending[approval_id] = fut
        try:
            return await asyncio.wait_for(fut, timeout=timeout_s)
        except TimeoutError:
            return "expired"
        finally:
            self._pending.pop(approval_id, None)

    def resolve(self, approval_id: str, decision: Decision) -> bool:
        fut = self._pending.get(approval_id)
        if fut is None or fut.done():
            return False
        fut.set_result(decision)
        return True

    def is_waiting(self, approval_id: str) -> bool:
        return approval_id in self._pending


class AutoApprover:
    """Answers every card the same way (eval cases and recording scripts)."""

    def __init__(self, decision: Decision) -> None:
        self.decision = decision
        self.asked: list[str] = []

    async def decide(self, approval_id: str, timeout_s: float) -> Decision:
        self.asked.append(approval_id)
        await asyncio.sleep(0)
        return self.decision
