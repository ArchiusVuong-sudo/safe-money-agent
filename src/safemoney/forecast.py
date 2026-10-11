"""30-day balance forecast, computed in code.

Start from today's balances, then add, day by day:
- every active recurring series (paychecks, bills, subscriptions, auto-save),
- every scheduled transfer already in the ledger,
- the average daily discretionary spend of the last 60 days (checking only,
  one-off purchases over $400 left out),
- optional hypothetical transfers (used by simulate and the policy).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .ledger import balance, own_accounts
from .models import Entry, Posting
from .recurring import RecurringSeries, detect
from .seed import CHECKING

HORIZON_DAYS = 30
SPEND_WINDOW_DAYS = 60
ONE_OFF_CENTS = 40_000  # single purchases above $400 are one-offs, not daily spend


@dataclass(frozen=True)
class Hypothetical:
    from_account: str
    to_account: str
    amount_cents: int
    on: dt.date
    label: str = "Proposed transfer"


@dataclass(frozen=True)
class Event:
    label: str
    account: str
    amount_cents: int
    kind: str  # recurring | scheduled | proposed


@dataclass
class Day:
    date: dt.date
    offset: int
    balances: dict[str, int]
    events: list[Event] = field(default_factory=list)


@dataclass(frozen=True)
class LowPoint:
    account: str
    cents: int
    date: dt.date
    first_below_floor: dt.date | None


@dataclass
class Forecast:
    today: dt.date
    days: list[Day]
    floors: dict[str, int]
    avg_daily_spend_cents: int
    series: list[RecurringSeries]
    next_payday: dt.date | None
    next_pay_cents: int | None

    def low(self, account: str, since: dt.date | None = None) -> LowPoint:
        days = [d for d in self.days if since is None or d.date >= since]
        lowest = min(days, key=lambda d: (d.balances[account], d.date))
        floor = self.floors.get(account, 0)
        below = next((d.date for d in days if d.balances[account] < floor), None)
        return LowPoint(account, lowest.balances[account], lowest.date, below)

    def balance_on(self, account: str, on: dt.date) -> int:
        return next(d.balances[account] for d in self.days if d.date == on)


def avg_daily_spend(s: Session, today: dt.date) -> int:
    since = today - dt.timedelta(days=SPEND_WINDOW_DAYS)
    total = s.scalar(
        select(func.coalesce(func.sum(Posting.amount_cents), 0))
        .join(Entry, Entry.id == Posting.entry_id)
        .where(
            Posting.account_id == CHECKING,
            Entry.kind == "spend",
            Entry.effective_on > since,
            Entry.effective_on <= today,
            Posting.amount_cents > -ONE_OFF_CENTS,
        )
    )
    return round(-int(total or 0) / SPEND_WINDOW_DAYS)


def build(
    s: Session,
    today: dt.date,
    *,
    hypotheticals: list[Hypothetical] | None = None,
    horizon: int = HORIZON_DAYS,
) -> Forecast:
    accounts = own_accounts(s)
    ids = [a.id for a in accounts]
    floors = {a.id: a.floor_cents for a in accounts}
    running = {a: balance(s, a, today) for a in ids}
    spend = avg_daily_spend(s, today)
    series = detect(s, today)
    end = today + dt.timedelta(days=horizon)

    by_day: dict[dt.date, list[Event]] = {}

    def add(day: dt.date, ev: Event) -> None:
        by_day.setdefault(day, []).append(ev)

    for ser in series:
        if ser.status != "active":
            continue
        day = ser.next_date
        while day <= end:
            add(day, Event(ser.counterparty, CHECKING, ser.amount_cents, "recurring"))
            if ser.counter_account:
                add(day, Event(ser.counterparty, ser.counter_account, -ser.amount_cents, "recurring"))
            day += dt.timedelta(days=ser.cadence_days)

    scheduled = s.execute(
        select(Entry, Posting)
        .join(Posting, Posting.entry_id == Entry.id)
        .where(Entry.effective_on > today, Entry.effective_on <= end, Posting.account_id.in_(ids))
    ).all()
    for entry, posting in scheduled:
        add(entry.effective_on, Event(entry.counterparty, posting.account_id, posting.amount_cents, "scheduled"))

    for h in hypotheticals or []:
        if h.on < today or h.on > end:
            continue
        if h.from_account in running:
            add(h.on, Event(h.label, h.from_account, -h.amount_cents, "proposed"))
        if h.to_account in running:
            add(h.on, Event(h.label, h.to_account, h.amount_cents, "proposed"))

    days: list[Day] = []
    for offset in range(horizon + 1):
        day = today + dt.timedelta(days=offset)
        events = by_day.get(day, [])
        if offset > 0 and CHECKING in running:
            running[CHECKING] -= spend
        for ev in events:
            running[ev.account] += ev.amount_cents
        days.append(Day(day, offset, dict(running), list(events)))

    pay = next((x for x in series if x.kind == "income" and x.status == "active"), None)
    return Forecast(
        today=today,
        days=days,
        floors=floors,
        avg_daily_spend_cents=spend,
        series=series,
        next_payday=pay.next_date if pay else None,
        next_pay_cents=pay.amount_cents if pay else None,
    )
