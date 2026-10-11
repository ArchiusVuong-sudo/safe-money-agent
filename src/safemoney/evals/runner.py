"""Run the eval cases, a few at a time, each on its own copy of the data."""

from __future__ import annotations

import asyncio
import datetime as dt
import shutil
import tempfile
import uuid
from pathlib import Path

from sqlalchemy import select

from ..agent.approvals import AutoApprover
from ..agent.channel import Bus
from ..agent.providers import Provider
from ..agent.runner import RunSpec, create_run, execute_run
from ..db import MoneyDB, TraceDB
from ..ledger import balance
from ..models import EvalResult, EvalRun, Step, utcnow
from ..seed import SAVINGS, seed_household
from .cases import CASES, CASES_BY_ID, EvalCase, TraceView, grade


def start_eval_run(traces: TraceDB, provider: Provider, case_ids: list[str] | None = None) -> str:
    eval_id = "eval_" + uuid.uuid4().hex[:10]
    ids = case_ids or [c.id for c in CASES]
    with traces.session() as s:
        s.add(EvalRun(id=eval_id, provider=provider.name, model=provider.model, status="running"))
        s.flush()
        for cid in ids:
            s.add(EvalResult(eval_run_id=eval_id, case_id=cid, status="queued"))
    return eval_id


async def _run_case(
    eval_id: str,
    case: EvalCase,
    template: MoneyDB,
    workdir: Path,
    traces: TraceDB,
    bus: Bus | None,
    provider: Provider,
    today: dt.date,
    sem: asyncio.Semaphore,
) -> None:
    async with sem:
        money = template.copy_to(workdir / f"{case.id}.db")
        with money.session() as s:
            start_savings = balance(s, SAVINGS, today)
        spec = RunSpec(message=case.prompt, history=[], kind="eval", case_id=case.id, eval_run_id=eval_id)
        run_id = create_run(traces, spec, provider)
        with traces.session() as s:
            row = s.scalar(select(EvalResult).where(EvalResult.eval_run_id == eval_id, EvalResult.case_id == case.id))
            assert row is not None
            row.status, row.run_id = "running", run_id
        try:
            run = await execute_run(
                run_id,
                spec,
                money=money,
                traces=traces,
                bus=bus,
                provider=provider,
                approver=AutoApprover(case.approver),  # type: ignore[arg-type]
                today=today,
                approval_timeout_s=30,
            )
            with traces.session() as s:
                steps = [
                    {"seq": st.seq, "type": st.type, "name": st.name, "data": st.data}
                    for st in s.scalars(select(Step).where(Step.run_id == run_id).order_by(Step.seq))
                ]
            view = TraceView(steps, run.final_text, run.grounded, money, today, start_savings)
            checks = grade(case, view)
            status = "passed" if run.status == "done" and all(c["passed"] for c in checks) else "failed"
            error = run.error
        except Exception as exc:
            checks, status, error = [], "error", f"{type(exc).__name__}: {exc}"
        finally:
            money.dispose()
        with traces.session() as s:
            row = s.scalar(select(EvalResult).where(EvalResult.eval_run_id == eval_id, EvalResult.case_id == case.id))
            assert row is not None
            row.status, row.checks, row.error = status, checks, error


async def run_evals(
    eval_id: str,
    *,
    traces: TraceDB,
    provider: Provider,
    today: dt.date,
    bus: Bus | None = None,
    concurrency: int = 3,
) -> None:
    with traces.session() as s:
        ids = [r.case_id for r in s.scalars(select(EvalResult).where(EvalResult.eval_run_id == eval_id))]
    workdir = Path(tempfile.mkdtemp(prefix="safe-money-eval-"))
    try:
        template = MoneyDB(workdir / "template.db")
        seed_household(template, today)
        sem = asyncio.Semaphore(concurrency)
        await asyncio.gather(*(_run_case(eval_id, CASES_BY_ID[cid], template, workdir, traces, bus, provider, today, sem) for cid in ids))
        template.dispose()
    finally:
        with traces.session() as s:
            er = s.get(EvalRun, eval_id)
            if er is not None:
                er.status, er.ended_at = "done", utcnow()
        shutil.rmtree(workdir, ignore_errors=True)
