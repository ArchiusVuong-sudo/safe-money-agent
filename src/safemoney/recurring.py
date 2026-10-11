"""Detect recurring series (paychecks, bills, subscriptions) from the feed.

A counterparty is recurring when it has 3 or more charges on checking at a
steady weekly, biweekly or monthly interval. The detector also flags a price
change: the same amount every time, then a different last amount.
"""

from __future__ import annotations

import datetime as dt
import statistics
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from .ledger import cancelled_series, own_accounts
from .models import Entry, Posting
from .seed import CHECKING, series_key

CADENCES = {"weekly": 7, "biweekly": 14, "monthly": 30}
_TOLERANCE = {"weekly": 1, "biweekly": 1, "monthly": 3}


@dataclass(frozen=True)
class RecurringSeries:
    id: str
    counterparty: str
    category: str
    kind: str  # income | bill | subscription | transfer
    cadence: str
    cadence_days: int
    amount_cents: int  # signed, on checking; what the forecast uses
    last_amount_cents: int
    previous_amount_cents: int | None
    price_changed: bool
    variable: bool
    occurrences: int
    last_date: dt.date
    next_date: dt.date
    counter_account: str | None  # set for transfers between own accounts
    status: str  # active | cancelled


def _cadence(intervals: list[int]) -> str | None:
    med = statistics.median(intervals)
    for name, days in CADENCES.items():
        if abs(med - days) <= _TOLERANCE[name] and all(abs(i - days) <= _TOLERANCE[name] for i in intervals):
            return name
    return None


def detect(s: Session, today: dt.date) -> list[RecurringSeries]:
    rows = s.execute(
        select(Entry, Posting.amount_cents)
        .join(Posting, Posting.entry_id == Entry.id)
        .where(Posting.account_id == CHECKING, Entry.source == "feed", Entry.effective_on <= today)
        .where(Entry.category != "opening")
        .order_by(Entry.effective_on, Entry.id)
    ).all()
    groups: dict[str, list[tuple[Entry, int]]] = defaultdict(list)
    for entry, cents in rows:
        groups[entry.counterparty].append((entry, cents))

    cancelled = cancelled_series(s)
    own_ids = {a.id for a in own_accounts(s)}
    found: list[RecurringSeries] = []
    for counterparty, items in groups.items():
        if len(items) < 3:
            continue
        dates = [e.effective_on for e, _ in items]
        intervals = [(b - a).days for a, b in zip(dates, dates[1:], strict=False)]
        cadence = _cadence(intervals)
        if cadence is None:
            continue
        amounts = [c for _, c in items]
        first_amounts = amounts[:-1]
        price_changed = len(set(first_amounts)) == 1 and amounts[-1] != first_amounts[0]
        spread = (max(amounts) - min(amounts)) / max(1, abs(statistics.mean(amounts)))
        variable = not price_changed and spread > 0.02
        forecast_amount = round(statistics.mean(amounts[-3:])) if variable else amounts[-1]
        last_entry = items[-1][0]
        counter = [p.account_id for p in last_entry.postings if p.account_id != CHECKING]
        own_counter = counter[0] if counter and counter[0] in own_ids else None
        kind = (
            "income"
            if amounts[-1] > 0
            else "transfer"
            if own_counter
            else "subscription"
            if last_entry.category == "subscription"
            else "bill"
        )
        step = CADENCES[cadence]
        next_date = dates[-1] + dt.timedelta(days=step)
        while next_date <= today:
            next_date += dt.timedelta(days=step)
        key = series_key(counterparty)
        found.append(
            RecurringSeries(
                id=key,
                counterparty=counterparty,
                category=last_entry.category,
                kind=kind,
                cadence=cadence,
                cadence_days=step,
                amount_cents=forecast_amount,
                last_amount_cents=amounts[-1],
                previous_amount_cents=amounts[-2],
                price_changed=price_changed,
                variable=variable,
                occurrences=len(items),
                last_date=dates[-1],
                next_date=next_date,
                counter_account=own_counter,
                status="cancelled" if key in cancelled else "active",
            )
        )
    found.sort(key=lambda r: (r.next_date, r.id))
    return found
