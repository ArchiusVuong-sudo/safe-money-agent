"""The permission gate: policy first, then a person, then the tool."""

from __future__ import annotations

import asyncio
import datetime as dt

from sqlalchemy import func, select

from safemoney.agent.approvals import AutoApprover, UIApprover
from safemoney.agent.gate import Gate, ToolHost, expire_stale
from safemoney.agent.trace import TraceRecorder
from safemoney.models import Approval, Entry
from safemoney.tools import ToolContext

from .conftest import make_gate

MOVE = "mcp__money__move_money"


def approvals(ctx: ToolContext) -> list[Approval]:
    with ctx.money.session() as s:
        return list(s.scalars(select(Approval)))


async def test_policy_failure_is_denied_and_never_shown(ctx: ToolContext, recorder: TraceRecorder, today: dt.date) -> None:
    approver = AutoApprover("approved")
    gate = Gate(ctx, approver, recorder)  # type: ignore[arg-type]
    d = await gate.check(MOVE, {"from_account": "chk", "to_account": "sav", "amount_usd": 1500, "date": today.isoformat()})
    assert not d.allow and d.outcome == "policy_denied"
    assert '"failed_checks"' in d.message and "max_safe_on_next_payday_usd" in d.message
    assert approver.asked == [] and approvals(ctx) == []
    step = recorder.steps[-1]
    assert step["type"] == "permission" and step["data"]["decision"] == "deny" and step["data"]["failed"] == ["floors"]


async def test_outside_payee_is_refused_even_when_asked(ctx: ToolContext, recorder: TraceRecorder, today: dt.date) -> None:
    gate = make_gate(ctx, recorder)
    d = await gate.check(MOVE, {"from_account": "sav", "to_account": "contact_riley", "amount_usd": 3800, "date": today.isoformat()})
    assert not d.allow and "own_accounts" in d.message
    assert approvals(ctx) == []


async def test_passing_request_waits_for_approval(ctx: ToolContext, recorder: TraceRecorder, today: dt.date) -> None:
    gate = make_gate(ctx, recorder, "approved")
    args = {"from_account": "sav", "to_account": "chk", "amount_usd": 400, "date": today.isoformat()}
    d = await gate.check(MOVE, args)
    assert d.allow and d.outcome == "approved"
    assert d.updated_input == {**args, "amount_usd": 400.0, "memo": ""}
    [a] = approvals(ctx)
    assert a.status == "approved" and a.run_id == ctx.run_id
    assert [s["type"] for s in recorder.steps] == ["permission", "approval"]
    assert recorder.channel is not None and any(e["type"] == "approval_request" for e in recorder.channel.events)


async def test_decline_denies(ctx: ToolContext, recorder: TraceRecorder, today: dt.date) -> None:
    gate = make_gate(ctx, recorder, "declined")
    d = await gate.check(MOVE, {"from_account": "sav", "to_account": "chk", "amount_usd": 400, "date": today.isoformat()})
    assert not d.allow and d.outcome == "declined" and "Do not ask again" in d.message
    assert approvals(ctx)[0].status == "declined"


async def test_no_answer_expires(ctx: ToolContext, recorder: TraceRecorder, today: dt.date) -> None:
    gate = Gate(ctx, UIApprover(), recorder, timeout_s=0.05)
    d = await gate.check(MOVE, {"from_account": "sav", "to_account": "chk", "amount_usd": 400, "date": today.isoformat()})
    assert d.outcome == "expired" and not d.allow
    assert approvals(ctx)[0].status == "expired"


async def test_ui_approver_resolves_the_waiting_card(ctx: ToolContext, recorder: TraceRecorder, today: dt.date) -> None:
    ui = UIApprover()
    gate = Gate(ctx, ui, recorder, timeout_s=5)
    task = asyncio.create_task(gate.check(MOVE, {"from_account": "sav", "to_account": "chk", "amount_usd": 400, "date": today.isoformat()}))
    while not approvals(ctx):
        await asyncio.sleep(0.01)
    approval_id = approvals(ctx)[0].id
    while not ui.is_waiting(approval_id):
        await asyncio.sleep(0.01)
    assert ui.resolve(approval_id, "approved") is True
    assert ui.resolve(approval_id, "approved") is False  # only once
    assert (await task).allow


async def test_invalid_and_unknown_tools(ctx: ToolContext, recorder: TraceRecorder) -> None:
    gate = make_gate(ctx, recorder)
    bad = await gate.check(MOVE, {"from_account": "sav"})
    assert bad.outcome == "invalid" and not bad.allow
    unknown = await gate.check("Bash", {"command": "ls"})
    assert unknown.outcome == "unknown_tool" and not unknown.allow
    assert gate.outcomes == ["invalid", "unknown_tool"]


async def test_read_tools_pass_through(ctx: ToolContext, recorder: TraceRecorder) -> None:
    gate = make_gate(ctx, recorder)
    d = await gate.check("mcp__money__forecast", {"days": 30})
    assert d.allow and gate.outcomes == []


async def test_host_records_ledger_write(ctx: ToolContext, recorder: TraceRecorder, today: dt.date) -> None:
    gate = make_gate(ctx, recorder)
    host = ToolHost(ctx, recorder)
    args = {"from_account": "sav", "to_account": "chk", "amount_usd": 400, "date": today.isoformat()}
    d = await gate.check(MOVE, args)
    out, is_error = await host.call(MOVE, d.updated_input or args)
    assert not is_error and out["status"] == "posted"
    types = [s["type"] for s in recorder.steps]
    assert types == ["permission", "approval", "tool_call", "tool_result", "ledger_write"]
    with ctx.money.session() as s:
        assert s.scalar(select(func.count()).select_from(Entry).where(Entry.source == "agent")) == 1


async def test_host_turns_tool_errors_into_results(ctx: ToolContext, recorder: TraceRecorder, today: dt.date) -> None:
    host = ToolHost(ctx, recorder)
    out, is_error = await host.call(MOVE, {"from_account": "sav", "to_account": "chk", "amount_usd": 400, "date": today.isoformat()})
    assert is_error and "no approved request" in out["error"]


def test_stale_pending_approvals_expire(ctx: ToolContext) -> None:
    with ctx.money.session() as s:
        s.add(Approval(id="old", run_id="r", tool="move_money", args={}, args_hash="h", preview={}, status="pending"))
    assert expire_stale(ctx.money) == 1
    assert approvals(ctx)[0].status == "expired"
