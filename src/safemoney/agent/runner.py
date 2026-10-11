"""One agent run: trace it, drive the provider, check grounding, store the result."""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

from .. import grounding
from ..db import MoneyDB, TraceDB
from ..models import Run, utcnow
from ..tools import ToolContext
from .approvals import Approver
from .channel import Bus
from .gate import Gate, ToolHost
from .prompt import system_prompt, user_prompt
from .providers import AgentRequest, Provider, normalize
from .trace import TraceRecorder


@dataclass
class RunSpec:
    message: str
    history: list[tuple[str, str]]
    kind: str = "chat"  # chat | eval
    case_id: str | None = None
    eval_run_id: str | None = None
    run_id: str | None = None


def new_run_id() -> str:
    return "run_" + uuid.uuid4().hex[:10]


def create_run(traces: TraceDB, spec: RunSpec, provider: Provider) -> str:
    run_id = spec.run_id or new_run_id()
    with traces.session() as s:
        s.add(
            Run(
                id=run_id,
                kind=spec.kind,
                prompt=spec.message,
                provider=provider.name,
                model=provider.model,
                status="running",
                case_id=spec.case_id,
                eval_run_id=spec.eval_run_id,
            )
        )
    return run_id


async def execute_run(
    run_id: str,
    spec: RunSpec,
    *,
    money: MoneyDB,
    traces: TraceDB,
    bus: Bus | None,
    provider: Provider,
    approver: Approver,
    today: dt.date,
    approval_timeout_s: float = 300,
) -> Run:
    channel = bus.get(run_id) or bus.open(run_id) if bus else None
    recorder = TraceRecorder(traces, run_id, channel)
    ctx = ToolContext(money=money, today=today, run_id=run_id)
    gate = Gate(ctx, approver, recorder, approval_timeout_s)
    host = ToolHost(ctx, recorder)
    await recorder.emit({"type": "run_started", "run_id": run_id, "provider": provider.name, "model": provider.model})
    await recorder.step("user", "", {"message": spec.message})

    req = AgentRequest(
        message=spec.message,
        prompt=user_prompt(spec.message, spec.history),
        system_prompt=system_prompt(today),
        fixture_key=f"case:{spec.case_id}" if spec.case_id else normalize(spec.message),
    )
    try:
        result = await provider.run(req, host, gate, recorder)
        error = result.error
    except Exception as exc:  # keep the run row honest even on a crash
        from .providers import ProviderResult

        result, error = ProviderResult(), f"{type(exc).__name__}: {exc}"

    check = grounding.check(result.final_text, [*host.payloads, *gate.seen], spec.message)
    status = "error" if error else "done"
    if error:
        await recorder.step("error", "", {"error": error[:2000]})
    await recorder.step(
        "result",
        "",
        {
            **result.usage,
            "cost_usd": result.cost_usd,
            "duration_ms": result.duration_ms,
            "num_turns": result.num_turns,
            "grounded": check.grounded,
            "figures": check.figures,
            "ungrounded": check.ungrounded,
            "note": result.note,
            "provider": provider.name,
        },
    )
    with traces.session() as s:
        run = s.get(Run, run_id)
        assert run is not None
        run.status = status
        run.ended_at = utcnow()
        run.duration_ms = result.duration_ms
        run.num_turns = result.num_turns
        run.input_tokens = result.usage.get("input_tokens")
        run.output_tokens = result.usage.get("output_tokens")
        run.cache_creation_tokens = result.usage.get("cache_creation_tokens")
        run.cache_read_tokens = result.usage.get("cache_read_tokens")
        run.cost_usd = result.cost_usd
        run.final_text = result.final_text
        run.grounded = check.grounded
        run.ungrounded = check.ungrounded
        run.error = error
        run.script = {**result.script, "prompt": spec.message, "recorded_on": today.isoformat(), "usage": result.usage,
                      "cost_usd": result.cost_usd, "duration_ms": result.duration_ms, "num_turns": result.num_turns}
    await recorder.emit({"type": "run_finished", "run_id": run_id, "status": status, "final_text": result.final_text})
    if channel is not None:
        await channel.close()
    with traces.session() as s:
        final = s.get(Run, run_id)
        assert final is not None
        return final
