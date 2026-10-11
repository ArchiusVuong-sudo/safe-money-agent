"""Opt-in live check against Claude through the Agent SDK: LIVE=1 uv run pytest -m live"""

from __future__ import annotations

import datetime as dt
import os

import pytest
from sqlalchemy import select

from safemoney import ledger
from safemoney.agent.approvals import AutoApprover
from safemoney.agent.providers import LiveProvider
from safemoney.agent.runner import RunSpec, create_run, execute_run
from safemoney.db import MoneyDB, TraceDB
from safemoney.models import Step
from safemoney.tools import READ_TOOLS, WRITE_TOOLS

pytestmark = [pytest.mark.live, pytest.mark.skipif(os.environ.get("LIVE") != "1", reason="set LIVE=1 to call Claude")]


async def test_live_fix_goes_through_the_gate(money: MoneyDB, traces: TraceDB, today: dt.date) -> None:
    provider = LiveProvider(os.environ.get("AGENT_MODEL", "claude-sonnet-5-5"), 12)
    spec = RunSpec(message="Checking is forecast to drop below $0 before payday. Fix this.", history=[])
    run_id = create_run(traces, spec, provider)
    run = await execute_run(
        run_id, spec, money=money, traces=traces, bus=None, provider=provider, approver=AutoApprover("approved"), today=today
    )
    assert run.status == "done", run.error
    with traces.session() as s:
        steps = list(s.scalars(select(Step).where(Step.run_id == run_id).order_by(Step.seq)))
    init = next(st for st in steps if st.type == "init")
    assert sorted(init.data["tools"]) == sorted(READ_TOOLS + WRITE_TOOLS)  # only the app's own tools
    asks = [st for st in steps if st.type == "permission" and st.name == "move_money"]
    assert asks, "move_money must reach can_use_tool"
    with money.session() as s:
        assert len(ledger.agent_transfers(s)) == 1
    assert (run.input_tokens or 0) + (run.cache_read_tokens or 0) > 0
