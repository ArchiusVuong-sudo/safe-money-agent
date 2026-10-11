"""The permission gate and the tool host.

The gate is what the SDK calls through ``can_use_tool`` for every write tool
(write tools are never in ``allowed_tools``). Order:
1. validate the input;
2. run the policy in code; a failing request is denied with the failed checks
   and hints, and the person never sees it;
3. a passing request becomes an approval card and waits for the person;
4. only an approved request is allowed through to the tool.

The tool host runs the tools and records each call in the trace. The gate and
host know nothing about the SDK, so the replay provider drives them the same
way the SDK does.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select

from .. import policy
from ..models import Approval, utcnow
from ..policy import CancelRequest, TransferRequest
from ..tools import READ_TOOLS, TOOLS_BY_NAME, WRITE_TOOLS, ToolContext, ToolError, parse, short_name
from .approvals import Approver
from .trace import TraceRecorder


@dataclass(frozen=True)
class GateDecision:
    allow: bool
    outcome: str  # read | approved | policy_denied | declined | expired | invalid | unknown_tool
    message: str = ""
    updated_input: dict[str, Any] | None = None


def approval_dict(a: Approval) -> dict[str, Any]:
    return {
        "id": a.id,
        "run_id": a.run_id,
        "tool": a.tool,
        "args": a.args,
        "preview": a.preview,
        "status": a.status,
        "created_at": a.created_at.isoformat() + "Z",
    }


@dataclass
class Gate:
    ctx: ToolContext
    approver: Approver
    recorder: TraceRecorder
    timeout_s: float = 300
    outcomes: list[str] = field(default_factory=list)
    seen: list[dict[str, Any]] = field(default_factory=list)  # refusals the model read (for grounding)

    async def check(self, tool_name: str, tool_input: dict[str, Any]) -> GateDecision:
        decision = await self._check(tool_name, tool_input)
        if tool_name in WRITE_TOOLS or tool_name not in READ_TOOLS:
            self.outcomes.append(decision.outcome)
        return decision

    async def _check(self, tool_name: str, tool_input: dict[str, Any]) -> GateDecision:
        name = short_name(tool_name)
        if tool_name in READ_TOOLS:
            return GateDecision(True, "read", updated_input=tool_input)
        if tool_name not in WRITE_TOOLS:
            await self.recorder.step("permission", name, {"decision": "deny", "reason": "not one of the app's tools", "input": tool_input})
            return GateDecision(False, "unknown_tool", "This tool is not available.")

        model = TransferRequest if name == "move_money" else CancelRequest
        started = time.perf_counter()
        try:
            req = parse(model, tool_input)
        except ToolError as exc:
            await self.recorder.step("permission", name, {"decision": "deny", "reason": str(exc), "input": tool_input})
            return GateDecision(False, "invalid", str(exc))

        with self.ctx.money.session() as s:
            if isinstance(req, TransferRequest):
                result = policy.evaluate_transfer(s, self.ctx.today, req)
            else:
                result = policy.evaluate_cancel(s, self.ctx.today, req)
        ms = round((time.perf_counter() - started) * 1000)
        verdict = result.to_dict()

        if not result.allowed:
            await self.recorder.step(
                "permission", name, {"decision": "deny", "by": "policy", "input": req.model_dump(mode="json"), **verdict}, ms
            )
            refusal = {
                "refused_by": "policy",
                "failed_checks": [{"check": c.id, "detail": c.detail} for c in result.failed],
                "hints": result.hints,
                "next_step": "Nothing moved and the user was not asked. Replan with a request that passes, or explain why you cannot.",
            }
            self.seen.append(refusal)
            message = json.dumps(refusal)
            return GateDecision(False, "policy_denied", message)

        approval_id = uuid.uuid4().hex[:12]
        args = req.model_dump(mode="json")
        preview = {**result.preview, "checks": verdict["checks"]}
        with self.ctx.money.session() as s:
            approval = Approval(
                id=approval_id,
                run_id=self.ctx.run_id,
                tool=name,
                args=args,
                args_hash=policy.args_hash(req),
                preview=preview,
                status="pending",
            )
            s.add(approval)
            s.flush()
            card = approval_dict(approval)
        await self.recorder.step("permission", name, {"decision": "ask_user", "by": "policy", "input": args, "approval_id": approval_id, **verdict}, ms)
        await self.recorder.emit({"type": "approval_request", "approval": card})

        waited = time.perf_counter()
        answer = await self.approver.decide(approval_id, self.timeout_s)
        wait_ms = round((time.perf_counter() - waited) * 1000)
        with self.ctx.money.session() as s:
            row = s.get(Approval, approval_id)
            assert row is not None
            row.status = answer
            row.decided_at = utcnow()
        await self.recorder.step("approval", name, {"approval_id": approval_id, "decision": answer}, wait_ms)
        await self.recorder.emit({"type": "approval_resolved", "approval_id": approval_id, "decision": answer})

        if answer == "approved":
            return GateDecision(True, "approved", updated_input=args)
        if answer == "declined":
            return GateDecision(False, "declined", "The user declined this request. Nothing moved. Do not ask again in this turn; tell the user plainly.")
        return GateDecision(False, "expired", "No answer from the user within 5 minutes, so the request lapsed. Nothing moved.")


def expire_stale(ctx_money: Any) -> int:
    """Mark pending approvals from an earlier process as expired (their waiter is gone)."""
    with ctx_money.session() as s:
        rows = list(s.scalars(select(Approval).where(Approval.status == "pending")))
        for r in rows:
            r.status = "expired"
            r.decided_at = utcnow()
        return len(rows)


@dataclass
class ToolHost:
    """Runs the app's tools and records each call."""

    ctx: ToolContext
    recorder: TraceRecorder
    payloads: list[dict[str, Any]] = field(default_factory=list)

    async def call(self, tool_name: str, args: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        name = short_name(tool_name)
        spec = TOOLS_BY_NAME.get(name)
        await self.recorder.step("tool_call", name, {"input": args})
        started = time.perf_counter()
        is_error = False
        if spec is None:
            payload: dict[str, Any] = {"error": f"unknown tool {tool_name}"}
            is_error = True
        else:
            try:
                payload = await spec.handler(self.ctx, args)
            except ToolError as exc:
                payload, is_error = {"error": str(exc)}, True
            except Exception as exc:  # a bug in a tool must not crash the run
                payload, is_error = {"error": f"internal error: {type(exc).__name__}"}, True
        ms = round((time.perf_counter() - started) * 1000)
        await self.recorder.step("tool_result", name, {"output": payload, "is_error": is_error}, ms)
        if not is_error:
            self.payloads.append(payload)
            if name == "move_money":
                await self.recorder.step(
                    "ledger_write",
                    name,
                    {k: payload[k] for k in ("entry_id", "idempotency_key", "status", "date", "legs", "already_posted")},
                )
                await self.recorder.emit({"type": "money_changed"})
            elif name == "cancel_subscription":
                await self.recorder.step("ledger_write", name, {k: payload[k] for k in ("series_id", "status", "already_cancelled", "simulated")})
                await self.recorder.emit({"type": "money_changed"})
        return payload, is_error
