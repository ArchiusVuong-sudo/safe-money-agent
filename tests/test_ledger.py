from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import func, select

from safemoney import ledger
from safemoney.db import MoneyDB
from safemoney.models import Entry, Posting, SeriesStatus


def counts(money: MoneyDB) -> tuple[int, int]:
    with money.session() as s:
        return s.scalar(select(func.count()).select_from(Entry)) or 0, s.scalar(select(func.count()).select_from(Posting)) or 0


def test_every_seed_entry_balances(money: MoneyDB) -> None:
    with money.session() as s:
        sums = s.execute(select(Posting.entry_id, func.sum(Posting.amount_cents)).group_by(Posting.entry_id)).all()
    assert sums and all(total == 0 for _, total in sums)


def test_transfer_posts_two_legs_once_per_key(money: MoneyDB, today: dt.date) -> None:
    before = counts(money)
    with money.session() as s:
        first = ledger.post_transfer(
            s, idempotency_key="k1", from_account="sav", to_account="chk", amount_cents=40_000, effective_on=today, today=today
        )
    with money.session() as s:
        again = ledger.post_transfer(
            s, idempotency_key="k1", from_account="sav", to_account="chk", amount_cents=40_000, effective_on=today, today=today
        )
    assert first.created and not again.created and first.entry_id == again.entry_id
    assert sorted(first.legs) == [("chk", 40_000), ("sav", -40_000)]
    assert counts(money) == (before[0] + 1, before[1] + 2)
    with money.session() as s:
        assert ledger.balance(s, "chk", today) == 167_269 + 40_000


def test_future_transfer_is_scheduled(money: MoneyDB, today: dt.date) -> None:
    with money.session() as s:
        t = ledger.post_transfer(
            s,
            idempotency_key="k2",
            from_account="chk",
            to_account="sav",
            amount_cents=10_000,
            effective_on=today + dt.timedelta(days=3),
            today=today,
        )
        assert t.status == "scheduled"
        assert ledger.balance(s, "chk", today) == 167_269


@pytest.mark.parametrize(("frm", "to", "cents"), [("chk", "chk", 100), ("chk", "sav", 0), ("chk", "nope", 100)])
def test_bad_transfers_raise(money: MoneyDB, today: dt.date, frm: str, to: str, cents: int) -> None:
    with money.session() as s, pytest.raises(ledger.LedgerError):
        ledger.post_transfer(s, idempotency_key="bad", from_account=frm, to_account=to, amount_cents=cents, effective_on=today, today=today)


def test_cancel_series_is_idempotent(money: MoneyDB) -> None:
    with money.session() as s:
        assert ledger.cancel_series(s, "flickwave-video", "a1") is True
    with money.session() as s:
        assert ledger.cancel_series(s, "flickwave-video", "a1") is False
        assert s.scalar(select(func.count()).select_from(SeriesStatus)) == 1
