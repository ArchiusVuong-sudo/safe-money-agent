"""Trace recorder: every step of a run, stored and streamed."""

from __future__ import annotations

import asyncio
from typing import Any

from ..db import TraceDB
from ..models import Step, utcnow
from .channel import RunChannel


def step_dict(st: Step) -> dict[str, Any]:
    return {
        "seq": st.seq,
        "type": st.type,
        "name": st.name,
        "data": st.data,
        "ms": st.ms,
        "at": st.at.isoformat() + "Z",
    }


class TraceRecorder:
    def __init__(self, traces: TraceDB, run_id: str, channel: RunChannel | None = None) -> None:
        self.traces = traces
        self.run_id = run_id
        self.channel = channel
        self._seq = 0
        self._lock = asyncio.Lock()
        self.steps: list[dict[str, Any]] = []

    async def step(self, type_: str, name: str = "", data: dict[str, Any] | None = None, ms: int | None = None) -> dict[str, Any]:
        async with self._lock:
            self._seq += 1
            st = Step(run_id=self.run_id, seq=self._seq, type=type_, name=name, data=data or {}, ms=ms, at=utcnow())
            with self.traces.session() as s:
                s.add(st)
            out = step_dict(st)
            self.steps.append(out)
        await self.emit({"type": "step", "step": out})
        return out

    async def emit(self, event: dict[str, Any]) -> None:
        if self.channel is not None:
            await self.channel.publish(event)
