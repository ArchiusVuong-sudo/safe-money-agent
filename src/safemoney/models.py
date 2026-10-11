"""Data model.

Two databases:
- the money database (one per household copy): accounts, a double-entry
  journal (entries and their postings), recurring-series status and approvals;
- the trace database (one per app): agent runs, their steps and eval results.

Money is stored as integer cents. Idempotency keys are unique, so the schema
moves to Postgres without changes in meaning.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


class MoneyBase(DeclarativeBase):
    pass


class TraceBase(DeclarativeBase):
    pass


# ---------------------------------------------------------------- money DB


class Account(MoneyBase):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20))  # checking | savings | external
    owner: Mapped[str] = mapped_column(String(20))  # self | contact | world
    floor_cents: Mapped[int] = mapped_column(Integer, default=0)


class Entry(MoneyBase):
    """One journal entry. Its postings always sum to zero."""

    __tablename__ = "entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    idempotency_key: Mapped[str] = mapped_column(String(80), unique=True)
    effective_on: Mapped[dt.date] = mapped_column(Date, index=True)
    kind: Mapped[str] = mapped_column(String(20))  # income | bill | subscription | spend | p2p | transfer
    counterparty: Mapped[str] = mapped_column(String(120))
    memo: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(40))
    series_key: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(20), default="feed")  # feed | agent
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    postings: Mapped[list[Posting]] = relationship(back_populates="entry", cascade="all, delete-orphan")


class Posting(MoneyBase):
    __tablename__ = "postings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("entries.id"), index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    amount_cents: Mapped[int] = mapped_column(Integer)

    entry: Mapped[Entry] = relationship(back_populates="postings")


class SeriesStatus(MoneyBase):
    """Overrides for detected recurring series (a cancelled subscription)."""

    __tablename__ = "series_status"

    series_key: Mapped[str] = mapped_column(String(80), primary_key=True)
    status: Mapped[str] = mapped_column(String(20))  # cancelled
    changed_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    approval_id: Mapped[str | None] = mapped_column(String(40), nullable=True, unique=True)


class Approval(MoneyBase):
    """A person's decision on one exact write request."""

    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(40), index=True)
    tool: Mapped[str] = mapped_column(String(40))  # move_money | cancel_subscription
    args: Mapped[dict[str, Any]] = mapped_column(JSON)
    args_hash: Mapped[str] = mapped_column(String(64), index=True)
    preview: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | approved | declined | expired
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    decided_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    used_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)


# ---------------------------------------------------------------- trace DB


class Run(TraceBase):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    kind: Mapped[str] = mapped_column(String(10))  # chat | eval
    prompt: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(10))  # live | replay
    model: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(20), default="running")  # running | done | error
    started_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    ended_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    num_turns: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cache_creation_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cache_read_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(nullable=True)
    final_text: Mapped[str] = mapped_column(Text, default="")
    grounded: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    ungrounded: Mapped[list[str]] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    case_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    eval_run_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    script: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    steps: Mapped[list[Step]] = relationship(back_populates="run", order_by="Step.seq", cascade="all, delete-orphan")


class Step(TraceBase):
    __tablename__ = "steps"
    __table_args__ = (UniqueConstraint("run_id", "seq"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(30))
    name: Mapped[str] = mapped_column(String(80), default="")
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    run: Mapped[Run] = relationship(back_populates="steps")


class EvalRun(TraceBase):
    __tablename__ = "eval_runs"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    provider: Mapped[str] = mapped_column(String(10))
    model: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(20), default="running")
    started_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    ended_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)


class EvalResult(TraceBase):
    __tablename__ = "eval_results"
    __table_args__ = (UniqueConstraint("eval_run_id", "case_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    eval_run_id: Mapped[str] = mapped_column(ForeignKey("eval_runs.id"), index=True)
    case_id: Mapped[str] = mapped_column(String(40))
    run_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued | running | passed | failed | error
    checks: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
