from __future__ import annotations

import datetime as dt

from safemoney import forecast as fc
from safemoney import ledger
from safemoney.db import MoneyDB
from safemoney.recurring import detect


def by_id(money: MoneyDB, today: dt.date) -> dict[str, object]:
    with money.session() as s:
        return {r.id: r for r in detect(s, today)}


def test_detects_paycheck_bills_subscriptions_and_autosave(money: MoneyDB, today: dt.date) -> None:
    found = by_id(money, today)
    assert set(found) == {
        "brightfield-supply-co-payroll",
        "maple-court-apartments",
        "cedar-valley-power",
        "harborline-auto-insurance",
        "kestrel-mobile",
        "bluepeak-card-autopay",
        "ridgeway-student-loans",
        "flickwave-video",
        "pinecast-music",
        "cloudnest-storage",
        "fitloop-training",
        "auto-save-to-rainy-day-savings",
    }
    pay = found["brightfield-supply-co-payroll"]
    assert pay.kind == "income" and pay.cadence == "biweekly" and pay.amount_cents == 265_000  # type: ignore[attr-defined]
    assert found["auto-save-to-rainy-day-savings"].kind == "transfer"  # type: ignore[attr-defined]
    assert found["auto-save-to-rainy-day-savings"].counter_account == "sav"  # type: ignore[attr-defined]
    subs = [k for k, v in found.items() if v.kind == "subscription"]  # type: ignore[attr-defined]
    assert sorted(subs) == ["cloudnest-storage", "fitloop-training", "flickwave-video", "pinecast-music"]


def test_flags_only_the_price_rise(money: MoneyDB, today: dt.date) -> None:
    found = by_id(money, today)
    changed = [k for k, v in found.items() if v.price_changed]  # type: ignore[attr-defined]
    assert changed == ["flickwave-video"]
    fw = found["flickwave-video"]
    assert fw.previous_amount_cents == -1_199 and fw.last_amount_cents == -1_549  # type: ignore[attr-defined]
    assert fw.amount_cents == -1_549  # type: ignore[attr-defined]


def test_variable_bills_use_the_average(money: MoneyDB, today: dt.date) -> None:
    power = by_id(money, today)["cedar-valley-power"]
    assert power.variable and not power.price_changed  # type: ignore[attr-defined]
    assert power.amount_cents == -round((9_640 + 8_815 + 9_170) / 3)  # type: ignore[attr-defined]


def test_everyday_merchants_are_not_recurring(money: MoneyDB, today: dt.date) -> None:
    found = by_id(money, today)
    assert not {"green-basket-market", "corner-bean-cafe", "city-transit", "noodle-lane-kitchen", "riley-park"} & set(found)


def test_cancelled_series_leaves_the_forecast(money: MoneyDB, today: dt.date) -> None:
    with money.session() as s:
        ledger.cancel_series(s, "flickwave-video", "a1")
        f = fc.build(s, today)
    fw = next(r for r in f.series if r.id == "flickwave-video")
    assert fw.status == "cancelled"
    assert not [e for d in f.days for e in d.events if e.label == "Flickwave Video"]
