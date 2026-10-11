"""Record replay fixtures from real live runs.

    uv run python scripts/record_fixtures.py            # chat flow + all 8 eval cases
    uv run python scripts/record_fixtures.py --only chat
    uv run python scripts/record_fixtures.py --only evals

Needs a Claude login (or ANTHROPIC_API_KEY). Every fixture is the model side of
one live run: its text, its tool calls with arguments, the gate decisions it
saw and its token usage. Replay mode plays the model side back and runs the
app's real tools, policy, approvals and ledger.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

from sqlalchemy import select

from safemoney.agent.approvals import AutoApprover
from safemoney.agent.providers import LiveProvider, normalize
from safemoney.agent.runner import RunSpec, create_run, execute_run
from safemoney.config import load_settings
from safemoney.db import MoneyDB, TraceDB
from safemoney.evals.cases import CASES, FIX_PROMPT
from safemoney.evals.runner import run_evals, start_eval_run
from safemoney.models import EvalResult, Run
from safemoney.seed import seed_household

CHAT_FLOW = [
    (FIX_PROMPT, "approved"),
    ("Move $1,500 to savings today.", "approved"),
    ("Which subscription went up in price? Cancel it.", "approved"),
    ("What is the $40.00 payment to Riley Park about?", "approved"),
]


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48]


def fixture(key: str, variant: str, run: Run) -> dict[str, Any]:
    sc = run.script or {}
    return {
        "key": key,
        "prompt": run.prompt,
        "variant": variant,
        "recorded_on": sc.get("recorded_on"),
        "model": sc.get("model", run.model),
        "init_tools": sc.get("init_tools", []),
        "turns": sc.get("turns", []),
        "decisions": sc.get("decisions", []),
        "usage": sc.get("usage", {}),
        "cost_usd": sc.get("cost_usd"),
        "duration_ms": sc.get("duration_ms"),
        "num_turns": sc.get("num_turns"),
        "final_text": run.final_text,
        "grounded": run.grounded,
    }


def write(out_dir: Path, name: str, data: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{name}.json").write_text(json.dumps(data, indent=2) + "\n")
    print(f"  wrote {name}.json  decisions={data['decisions']}  grounded={data['grounded']}")


async def record_chat(provider: LiveProvider, work: Path, out_dir: Path, today: dt.date) -> None:
    traces = TraceDB(work / "chat-traces.db")
    money = MoneyDB(work / "chat-money.db")
    seed_household(money, today)
    history: list[tuple[str, str]] = []
    for message, decision in CHAT_FLOW:
        print(f"chat: {message}")
        spec = RunSpec(message=message, history=list(history))
        run_id = create_run(traces, spec, provider)
        run = await execute_run(
            run_id,
            spec,
            money=money,
            traces=traces,
            bus=None,
            provider=provider,
            approver=AutoApprover(decision),
            today=today,  # type: ignore[arg-type]
        )
        if run.error:
            sys.exit(f"live run failed: {run.error}")
        write(
            out_dir,
            f"chat-{slug(message)}-{'approve' if decision == 'approved' else 'decline'}",
            fixture(normalize(message), "approve", run),
        )
        history.append((message, run.final_text))

    # The same first message, declined, on fresh data: replay follows this branch on Decline.
    print(f"chat (declined): {FIX_PROMPT}")
    money2 = MoneyDB(work / "chat-money-2.db")
    seed_household(money2, today)
    spec = RunSpec(message=FIX_PROMPT, history=[])
    run_id = create_run(traces, spec, provider)
    run = await execute_run(
        run_id,
        spec,
        money=money2,
        traces=traces,
        bus=None,
        provider=provider,
        approver=AutoApprover("declined"),
        today=today,
    )
    write(out_dir, f"chat-{slug(FIX_PROMPT)}-decline", fixture(normalize(FIX_PROMPT), "decline", run))


async def record_evals(provider: LiveProvider, work: Path, out_dir: Path, today: dt.date) -> None:
    traces = TraceDB(work / "eval-traces.db")
    eval_id = start_eval_run(traces, provider)
    print(f"evals: {len(CASES)} cases, 3 at a time")
    await run_evals(eval_id, traces=traces, provider=provider, today=today, concurrency=3)
    with traces.session() as s:
        results = list(s.scalars(select(EvalResult).where(EvalResult.eval_run_id == eval_id)))
        for r in results:
            run = s.get(Run, r.run_id) if r.run_id else None
            passed = sum(1 for c in r.checks if c["passed"])
            print(f"  {r.case_id:<14} {r.status:<7} {passed}/{len(r.checks)}")
            if run is not None and not run.error:
                write(out_dir, f"case-{r.case_id}", fixture(f"case:{r.case_id}", "default", run))


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["chat", "evals"], default=None)
    args = ap.parse_args()
    settings = load_settings()
    provider = LiveProvider(settings.agent_model, settings.max_turns)
    today = dt.date.today()
    with tempfile.TemporaryDirectory(prefix="safe-money-record-") as tmp:
        work = Path(tmp)
        if args.only in (None, "chat"):
            await record_chat(provider, work, settings.fixtures_dir, today)
        if args.only in (None, "evals"):
            await record_evals(provider, work, settings.fixtures_dir, today)


if __name__ == "__main__":
    asyncio.run(main())
