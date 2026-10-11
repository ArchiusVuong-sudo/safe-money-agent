"""The seed always yields one overdraft dip before payday, whatever the start date."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from safemoney import forecast as fc
from safemoney import ledger
from safemoney.db import MoneyDB
from safemoney.seed import CHECKING, SAVINGS, seed_household

START = dt.date(2026, 9, 1)


@pytest.mark.parametrize("offset", range(60))
def test_dip_window_and_size_for_60_start_dates(tmp_path: Path, offset: int) -> None:
    today = START + dt.timedelta(days=offset)
    db = MoneyDB(tmp_path / "m.db")
    seed_household(db, today)
    with db.session() as s:
        f = fc.build(s, today)
        assert ledger.balance(s, CHECKING, today) == 167_269
        assert ledger.balance(s, SAVINGS, today) == 380_000
    db.dispose()

    below_zero = [d.offset for d in f.days if d.balances[CHECKING] < 0]
    low = f.low(CHECKING)
    assert below_zero[0] == 5  # first day below $0
    assert (low.date - today).days == 7  # low point one day before payday
    assert low.cents == -30_429
    assert f.next_payday == today + dt.timedelta(days=8)
    assert below_zero == [5, 6, 7]  # the whole dip sits before payday
    assert all(d.balances[CHECKING] >= 5_000 for d in f.days if d.offset >= 8)  # healthy after payday
    assert f.low(SAVINGS).cents >= 50_000
    assert f.avg_daily_spend_cents == 3_670


def test_one_off_purchases_stay_out_of_daily_spend(money: MoneyDB, today: dt.date) -> None:
    with money.session() as s:
        assert fc.avg_daily_spend(s, today) == 3_670  # a $1,860.45 repair 40 days ago is not daily spend


def test_scheduled_transfer_shows_in_forecast(money: MoneyDB, today: dt.date) -> None:
    payday = today + dt.timedelta(days=8)
    with money.session() as s:
        before = fc.build(s, today).balance_on(CHECKING, payday)
        ledger.post_transfer(
            s, idempotency_key="t1", from_account=CHECKING, to_account=SAVINGS, amount_cents=150_000, effective_on=payday, today=today
        )
        after = fc.build(s, today)
        assert ledger.balance(s, CHECKING, today) == 167_269  # not moved yet
    assert after.balance_on(CHECKING, payday) == before - 150_000
    assert any(e.kind == "scheduled" for d in after.days for e in d.events)


def test_hypothetical_transfer_changes_only_the_forecast(money: MoneyDB, today: dt.date) -> None:
    with money.session() as s:
        f = fc.build(s, today, hypotheticals=[fc.Hypothetical("sav", "chk", 40_000, today)])
        assert ledger.balance(s, CHECKING, today) == 167_269
    assert f.low(CHECKING).cents == -30_429 + 40_000
