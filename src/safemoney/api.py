"""FastAPI app: REST for the screens, SSE for the live trace, static files for the UI.

Run it with one worker: approvals wait on in-memory futures and the trace
stream lives in memory, all on one event loop.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from . import forecast as fc
from . import ledger
from .agent.approvals import UIApprover
from .agent.channel import Bus
from .agent.gate import approval_dict, expire_stale
from .agent.providers import LiveProvider, Provider, ReplayProvider, live_login_available, normalize
from .agent.runner import RunSpec, create_run, execute_run
from .agent.trace import step_dict
from .config import Settings, load_settings
from .db import MoneyDB, TraceDB
from .evals.cases import CASES
from .evals.runner import run_evals, start_eval_run
from .models import Approval, Entry, EvalResult, EvalRun, Posting, Run, Step, utcnow
from .money import day_label, usd
from .seed import CHECKING, HOUSEHOLD_NAME, SAVINGS, seed_household

log = logging.getLogger("safemoney")

SUGGESTIONS = [
    "Checking is forecast to drop below $0 before payday. Fix this.",
    "Move $1,500 to savings today.",
    "Which subscription went up in price? Cancel it.",
    "What is the $40.00 payment to Riley Park about?",
]


@dataclass
class AppState:
    settings: Settings
    today: dt.date
    money: MoneyDB
    traces: TraceDB
    provider: Provider
    mode_reason: str
    bus: Bus = field(default_factory=Bus)
    approver: UIApprover = field(default_factory=UIApprover)
    tasks: set[asyncio.Task[Any]] = field(default_factory=set)
    chat_since: dt.datetime = field(default_factory=utcnow)
    eval_task: asyncio.Task[Any] | None = None

    def spawn(self, coro: Any) -> asyncio.Task[Any]:
        task = asyncio.create_task(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task


def pick_provider(settings: Settings, today: dt.date) -> tuple[Provider, str]:
    if settings.force_replay:
        return ReplayProvider(settings.fixtures_dir, today, settings.replay_delay_ms), "DEMO_REPLAY=1"
    if live_login_available():
        return LiveProvider(settings.agent_model, settings.max_turns), "Claude login found"
    reason = "no Claude login or API key found"
    if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        # Every CLAUDE_CODE_* variable is kept out of the agent's environment on purpose.
        reason += " (CLAUDE_CODE_OAUTH_TOKEN is not passed to the agent; log in to Claude Code or set ANTHROPIC_API_KEY)"
    return ReplayProvider(settings.fixtures_dir, today, settings.replay_delay_ms), reason


def fresh_money(settings: Settings, today: dt.date) -> MoneyDB:
    path = settings.data_dir / "money.db"
    for suffix in ("", "-wal", "-shm"):
        p = path.with_name(path.name + suffix)
        if p.exists():
            p.unlink()
    db = MoneyDB(path)
    seed_household(db, today)
    return db


def build_state(settings: Settings | None = None, today: dt.date | None = None) -> AppState:
    settings = settings or load_settings()
    today = today or dt.date.today()
    traces = TraceDB(settings.data_dir / "traces.db")
    with traces.session() as s:
        for r in s.scalars(select(Run).where(Run.status == "running")):
            r.status, r.error = "error", "server restarted during the run"
        for e in s.scalars(select(EvalRun).where(EvalRun.status == "running")):
            e.status = "done"
        for res in s.scalars(select(EvalResult).where(EvalResult.status.in_(["queued", "running"]))):
            res.status, res.error = "error", "server restarted during the run"
    money = fresh_money(settings, today)
    expire_stale(money)
    provider, reason = pick_provider(settings, today)
    return AppState(settings, today, money, traces, provider, reason)


# ---------------------------------------------------------------- payloads


def home_payload(st: AppState) -> dict[str, Any]:
    with st.money.session() as s:
        f = fc.build(s, st.today)
        accounts = [
            {"id": a.id, "name": a.name, "type": a.kind, "balance": usd(ledger.balance(s, a.id, st.today)), "floor": usd(a.floor_cents)}
            for a in ledger.own_accounts(s)
        ]
        scheduled = [
            {
                "entry_id": e.id,
                "date": e.effective_on.isoformat(),
                "label": e.counterparty,
                "amount": usd(max(p.amount_cents for p in e.postings)),
                "from": next(p.account_id for p in e.postings if p.amount_cents < 0),
                "to": next(p.account_id for p in e.postings if p.amount_cents > 0),
            }
            for e in ledger.agent_transfers(s)
            if e.effective_on > st.today
        ]
    low = f.low(CHECKING)
    payday = f.next_payday
    below_zero = next((d for d in f.days if d.balances[CHECKING] < 0), None)
    alert = None
    if below_zero is not None:
        alert = {
            "kind": "overdraft",
            "low": usd(low.cents),
            "low_date": low.date.isoformat(),
            "low_day": day_label(low.date),
            "first_below_zero": below_zero.date.isoformat(),
            "first_below_zero_day": day_label(below_zero.date),
            "before_payday": payday is not None and below_zero.date < payday,
        }
    elif low.cents < f.floors[CHECKING]:
        alert = {"kind": "tight", "low": usd(low.cents), "low_date": low.date.isoformat(), "low_day": day_label(low.date)}
    return {
        "today": st.today.isoformat(),
        "household": HOUSEHOLD_NAME,
        "accounts": accounts,
        "floors": {k: usd(v) for k, v in f.floors.items()},
        "next_payday": payday.isoformat() if payday else None,
        "next_payday_day": day_label(payday) if payday else None,
        "next_pay": usd(f.next_pay_cents) if f.next_pay_cents else None,
        "avg_daily_spend": usd(f.avg_daily_spend_cents),
        "low": {"amount": usd(low.cents), "date": low.date.isoformat(), "day": day_label(low.date)},
        "alert": alert,
        "forecast": [
            {
                "date": d.date.isoformat(),
                "day": day_label(d.date),
                "checking": usd(d.balances[CHECKING]),
                "savings": usd(d.balances[SAVINGS]),
                "events": [{"label": e.label, "account": e.account, "amount": usd(e.amount_cents), "kind": e.kind} for e in d.events],
            }
            for d in f.days
        ],
        "recurring": [
            {
                "id": r.id,
                "name": r.counterparty,
                "kind": r.kind,
                "cadence": r.cadence,
                "amount": usd(abs(r.amount_cents)),
                "previous": usd(abs(r.previous_amount_cents)) if r.previous_amount_cents is not None else None,
                "price_changed": r.price_changed,
                "next_date": r.next_date.isoformat(),
                "status": r.status,
            }
            for r in f.series
        ],
        "scheduled": scheduled,
    }


def transactions_payload(st: AppState, limit: int) -> list[dict[str, Any]]:
    with st.money.session() as s:
        rows = s.execute(
            select(Entry, Posting)
            .join(Posting, Posting.entry_id == Entry.id)
            .where(Posting.account_id.in_([CHECKING, SAVINGS]), Entry.category != "opening")
            .order_by(Entry.effective_on.desc(), Entry.id.desc())
            .limit(limit)
        ).all()
        return [
            {
                "id": e.id,
                "posting_id": p.id,
                "date": e.effective_on.isoformat(),
                "day": day_label(e.effective_on),
                "account": p.account_id,
                "amount": usd(p.amount_cents),
                "merchant": e.counterparty,
                "memo": e.memo,
                "category": e.category,
                "kind": e.kind,
                "source": e.source,
                "status": "scheduled" if e.effective_on > st.today else "posted",
            }
            for e, p in rows
        ]


def run_summary(r: Run, steps: int | None = None) -> dict[str, Any]:
    return {
        "id": r.id,
        "kind": r.kind,
        "prompt": r.prompt,
        "provider": r.provider,
        "model": r.model,
        "status": r.status,
        "started_at": r.started_at.isoformat() + "Z",
        "duration_ms": r.duration_ms,
        "num_turns": r.num_turns,
        "input_tokens": r.input_tokens,
        "output_tokens": r.output_tokens,
        "cache_creation_tokens": r.cache_creation_tokens,
        "cache_read_tokens": r.cache_read_tokens,
        "cost_usd": r.cost_usd,
        "final_text": r.final_text,
        "grounded": r.grounded,
        "ungrounded": r.ungrounded,
        "error": r.error,
        "case_id": r.case_id,
        "eval_run_id": r.eval_run_id,
        "steps": steps,
    }


def eval_payload(st: AppState, eval_id: str) -> dict[str, Any]:
    with st.traces.session() as s:
        er = s.get(EvalRun, eval_id)
        if er is None:
            raise HTTPException(404, "no such eval run")
        results = {r.case_id: r for r in s.scalars(select(EvalResult).where(EvalResult.eval_run_id == eval_id))}
        runs = {r.id: r for r in s.scalars(select(Run).where(Run.eval_run_id == eval_id))}
        cases: list[dict[str, Any]] = []
        for c in CASES:
            r = results.get(c.id)
            if r is None:
                continue
            run = runs.get(r.run_id or "")
            cases.append(
                {
                    "id": c.id,
                    "title": c.title,
                    "prompt": c.prompt,
                    "approver": c.approver,
                    "status": r.status,
                    "checks": r.checks or [{"id": k.id, "label": k.label, "passed": None, "detail": ""} for k in c.checks],
                    "error": r.error,
                    "run": run_summary(run) if run else None,
                }
            )
        done = [c for c in cases if c["status"] in {"passed", "failed", "error"}]
        checks = [k for c in done for k in c["checks"]]
        return {
            "id": er.id,
            "provider": er.provider,
            "model": er.model,
            "status": er.status,
            "started_at": er.started_at.isoformat() + "Z",
            "ended_at": er.ended_at.isoformat() + "Z" if er.ended_at else None,
            "cases": cases,
            "summary": {
                "cases": len(cases),
                "finished": len(done),
                "passed": sum(1 for c in done if c["status"] == "passed"),
                "checks": len(checks),
                "checks_passed": sum(1 for k in checks if k["passed"]),
            },
        }


# ---------------------------------------------------------------- app


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=500)


class DecisionIn(BaseModel):
    decision: Literal["approve", "decline"]


def create_app(state: AppState | None = None) -> FastAPI:
    holder: dict[str, AppState] = {}

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        holder["st"] = state or build_state()
        log.info("mode=%s (%s) model=%s", holder["st"].provider.name, holder["st"].mode_reason, holder["st"].provider.model)
        yield
        for t in list(holder["st"].tasks):
            t.cancel()

    app = FastAPI(title="Safe Money Agent", lifespan=lifespan)

    def st() -> AppState:
        return holder["st"]

    @app.get("/api/state")
    def get_state() -> dict[str, Any]:
        s = st()
        return {
            "mode": s.provider.name,
            "mode_reason": s.mode_reason,
            "model": s.provider.model,
            "today": s.today.isoformat(),
            "household": HOUSEHOLD_NAME,
            "synthetic": True,
            "suggestions": [p for p in SUGGESTIONS if not isinstance(s.provider, ReplayProvider) or s.provider.has(normalize(p))],
        }

    @app.get("/api/home")
    def get_home() -> dict[str, Any]:
        return home_payload(st())

    @app.get("/api/transactions")
    def get_transactions(limit: int = 60) -> list[dict[str, Any]]:
        return transactions_payload(st(), max(1, min(limit, 200)))

    def _chat_running(s: AppState) -> bool:
        with s.traces.session() as db:
            return bool(db.scalar(select(func.count()).select_from(Run).where(Run.kind == "chat", Run.status == "running")))

    @app.post("/api/chat")
    async def post_chat(body: ChatIn) -> dict[str, Any]:
        s = st()
        if _chat_running(s):
            raise HTTPException(409, "The assistant is still working on the last message.")
        with s.traces.session() as db:
            prior = list(
                db.scalars(
                    select(Run).where(Run.kind == "chat", Run.status == "done", Run.started_at >= s.chat_since).order_by(Run.started_at)
                )
            )
        history = [(r.prompt, r.final_text) for r in prior][-3:]
        spec = RunSpec(message=body.message.strip(), history=history)
        run_id = create_run(s.traces, spec, s.provider)
        s.bus.open(run_id)
        s.spawn(
            execute_run(
                run_id,
                spec,
                money=s.money,
                traces=s.traces,
                bus=s.bus,
                provider=s.provider,
                approver=s.approver,
                today=s.today,
                approval_timeout_s=s.settings.approval_timeout_s,
            )
        )
        return {"run_id": run_id}

    @app.get("/api/chat")
    def get_chat() -> list[dict[str, Any]]:
        s = st()
        with s.traces.session() as db:
            runs = list(db.scalars(select(Run).where(Run.kind == "chat", Run.started_at >= s.chat_since).order_by(Run.started_at)))
            out = []
            for r in runs:
                cards = [
                    step_dict(x)
                    for x in db.scalars(
                        select(Step).where(Step.run_id == r.id, Step.type.in_(["permission", "approval"])).order_by(Step.seq)
                    )
                ]
                out.append({**run_summary(r), "gate_steps": cards})
        with s.money.session() as db:
            approvals = {a.id: approval_dict(a) for a in db.scalars(select(Approval))}
        for item in out:
            item["approvals"] = [
                approvals[x["data"]["approval_id"]]
                for x in item["gate_steps"]
                if x["type"] == "permission" and x["data"].get("approval_id") in approvals
            ]
        return out

    @app.get("/api/runs")
    def list_runs(kind: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        with st().traces.session() as db:
            q = select(Run).order_by(Run.started_at.desc()).limit(max(1, min(limit, 500)))
            if kind:
                q = q.where(Run.kind == kind)
            runs = list(db.scalars(q))
            counts = dict(
                db.execute(select(Step.run_id, func.count()).where(Step.run_id.in_([r.id for r in runs])).group_by(Step.run_id)).all()
            )
            return [run_summary(r, counts.get(r.id, 0)) for r in runs]

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        with st().traces.session() as db:
            r = db.get(Run, run_id)
            if r is None:
                raise HTTPException(404, "no such run")
            steps = [step_dict(x) for x in db.scalars(select(Step).where(Step.run_id == run_id).order_by(Step.seq))]
            return {**run_summary(r, len(steps)), "trace": steps}

    @app.get("/api/runs/{run_id}/events")
    async def run_events(run_id: str) -> StreamingResponse:
        s = st()
        channel = s.bus.get(run_id)

        async def stream() -> AsyncIterator[str]:
            if channel is None:
                # Finished in an earlier process: send the stored trace once.
                data = get_run(run_id)
                for step in data["trace"]:
                    yield f"data: {json.dumps({'type': 'step', 'step': step})}\n\n"
                yield f"data: {json.dumps({'type': 'run_finished', 'run_id': run_id, 'status': data['status'], 'final_text': data['final_text']})}\n\n"
                return
            async for ev in channel.subscribe():
                if ev is None:
                    yield ": ping\n\n"
                else:
                    yield f"data: {json.dumps(ev)}\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/api/approvals/pending")
    def pending_approvals() -> list[dict[str, Any]]:
        s = st()
        with s.money.session() as db:
            rows = list(db.scalars(select(Approval).where(Approval.status == "pending").order_by(Approval.created_at)))
            return [{**approval_dict(a), "waiting": s.approver.is_waiting(a.id)} for a in rows]

    # Endpoints that touch the event loop (futures, tasks) are async so they
    # run on the loop thread, not in the threadpool.
    @app.post("/api/approvals/{approval_id}")
    async def decide(approval_id: str, body: DecisionIn) -> dict[str, Any]:
        s = st()
        with s.money.session() as db:
            a = db.get(Approval, approval_id)
            if a is None:
                raise HTTPException(404, "no such approval")
            if a.status != "pending":
                raise HTTPException(409, f"already {a.status}")
        ok = s.approver.resolve(approval_id, "approved" if body.decision == "approve" else "declined")
        if not ok:
            raise HTTPException(409, "this request is no longer waiting")
        return {"ok": True}

    @app.post("/api/reset")
    async def reset() -> dict[str, Any]:
        s = st()
        if _chat_running(s):
            raise HTTPException(409, "Wait for the current answer before resetting.")
        s.money.dispose()
        s.money = fresh_money(s.settings, s.today)
        s.chat_since = utcnow()
        return {"ok": True}

    @app.post("/api/evals/run")
    async def eval_start() -> dict[str, Any]:
        s = st()
        if s.eval_task is not None and not s.eval_task.done():
            raise HTTPException(409, "An eval run is already going.")
        eval_id = start_eval_run(s.traces, s.provider)
        s.eval_task = s.spawn(
            run_evals(eval_id, traces=s.traces, provider=s.provider, today=s.today, bus=s.bus, concurrency=s.settings.eval_concurrency)
        )
        return {"eval_id": eval_id}

    @app.get("/api/evals/latest")
    def eval_latest() -> dict[str, Any] | None:
        s = st()
        with s.traces.session() as db:
            er = db.scalar(select(EvalRun).order_by(EvalRun.started_at.desc()).limit(1))
            eid = er.id if er else None
        return eval_payload(s, eid) if eid else None

    @app.get("/api/evals/{eval_id}")
    def eval_get(eval_id: str) -> dict[str, Any]:
        return eval_payload(st(), eval_id)

    @app.get("/api/evals")
    def eval_list() -> list[dict[str, Any]]:
        s = st()
        with s.traces.session() as db:
            ids = [e.id for e in db.scalars(select(EvalRun).order_by(EvalRun.started_at.desc()).limit(20))]
        return [{k: v for k, v in eval_payload(s, i).items() if k != "cases"} for i in ids]

    dist = (state.settings if state else load_settings()).web_dist
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            target = dist / path
            if path and target.is_file() and dist in target.resolve().parents:
                return FileResponse(target)
            return FileResponse(dist / "index.html")

    return app
