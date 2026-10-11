"""In-memory event channels, one per run, for the live trace stream (SSE).

Subscribers read by index, so a late subscriber still gets every event from
the start. Single process only: run uvicorn with one worker.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any


class RunChannel:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.closed = False
        self._cond = asyncio.Condition()

    async def publish(self, event: dict[str, Any]) -> None:
        async with self._cond:
            self.events.append(event)
            self._cond.notify_all()

    async def close(self) -> None:
        async with self._cond:
            self.closed = True
            self._cond.notify_all()

    async def subscribe(self, heartbeat_s: float = 15.0) -> AsyncIterator[dict[str, Any] | None]:
        """Yields events; yields None as a heartbeat when idle."""
        i = 0
        while True:
            async with self._cond:
                if i >= len(self.events) and not self.closed:
                    try:
                        await asyncio.wait_for(self._cond.wait(), timeout=heartbeat_s)
                    except TimeoutError:
                        pass
                batch = self.events[i:]
                done = self.closed and i + len(batch) >= len(self.events)
            if not batch and not done:
                yield None
            for ev in batch:
                yield ev
            i += len(batch)
            if done:
                return


class Bus:
    def __init__(self) -> None:
        self._channels: dict[str, RunChannel] = {}

    def open(self, run_id: str) -> RunChannel:
        ch = RunChannel()
        self._channels[run_id] = ch
        return ch

    def get(self, run_id: str) -> RunChannel | None:
        return self._channels.get(run_id)
