from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from pathlib import Path

import pytest

from safemoney.agent.approvals import AutoApprover
from safemoney.agent.channel import Bus
from safemoney.agent.gate import Gate, ToolHost
from safemoney.agent.trace import TraceRecorder
from safemoney.db import MoneyDB, TraceDB
from safemoney.models import Run
from safemoney.seed import seed_household
from safemoney.tools import ToolContext

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "fixtures"


@pytest.fixture
def today() -> dt.date:
    return dt.date.today()


@pytest.fixture
def money(tmp_path: Path, today: dt.date) -> Iterator[MoneyDB]:
    db = MoneyDB(tmp_path / "money.db")
    seed_household(db, today)
    yield db
    db.dispose()


@pytest.fixture
def traces(tmp_path: Path) -> Iterator[TraceDB]:
    db = TraceDB(tmp_path / "traces.db")
    yield db
    db.dispose()


@pytest.fixture
def ctx(money: MoneyDB, today: dt.date) -> ToolContext:
    return ToolContext(money=money, today=today, run_id="run_test")


@pytest.fixture
def recorder(traces: TraceDB) -> TraceRecorder:
    with traces.session() as s:
        s.add(Run(id="run_test", kind="chat", prompt="test", provider="replay", model="test"))
    return TraceRecorder(traces, "run_test", Bus().open("run_test"))


def make_gate(ctx: ToolContext, recorder: TraceRecorder, decision: str = "approved", timeout_s: float = 5) -> Gate:
    return Gate(ctx, AutoApprover(decision), recorder, timeout_s)  # type: ignore[arg-type]


@pytest.fixture
def host(ctx: ToolContext, recorder: TraceRecorder) -> ToolHost:
    return ToolHost(ctx, recorder)
