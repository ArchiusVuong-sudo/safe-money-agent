from __future__ import annotations

import datetime as dt

from safemoney import forecast as fc
from safemoney import ledger
from safemoney.db import MoneyDB
from safemoney.recurring import detect
from safemoney.seed import series_key


def by_id(money: MoneyDB, today: dt.date) -> dict[str, object]:
    with money.session() as s:
        return {r.id: r for r in detect(s, today)}


def test_detects_paycheck_bills_subscriptions_and_autosave(money: MoneyDB, today: dt.date) -> None:
    found = by_id(money, today)
    assert set(found) == {
        series_key("Brightfield Supply Co payroll"),
        series_key("Maple Court Apartments"),
        series_key("Cedar Valley Power"),
        series_key("Harborline Auto Insurance"),
        series_key("Kestrel Mobile"),
        series_key("Bluepeak Card autopay"),
        series_key("Ridgeway Student Loans"),
        series_key("Flickwave Video"),
        series_key("Pinecast Music"),
        series_key("Cloudnest Storage"),
        series_key("Fitloop Training"),
        series_key("Auto-save to Rainy Day Savings"),
    }
    pay = found[series_key("Brightfield Supply Co payroll")]
    assert pay.kind == "income" and pay.cadence == "biweekly" and pay.amount_cents == 265_000  # type: ignore[attr-defined]
    assert found[series_key("Auto-save to Rainy Day Savings")].kind == "transfer"  # type: ignore[attr-defined]
    assert found[series_key("Auto-save to Rainy Day Savings")].counter_account == "sav"  # type: ignore[attr-defined]
    subs = [k for k, v in found.items() if v.kind == "subscription"]  # type: ignore[attr-defined]
    assert set(subs) == {series_key(n) for n in ("Cloudnest Storage", "Fitloop Training", "Flickwave Video", "Pinecast Music")}


def test_flags_only_the_price_rise(money: MoneyDB, today: dt.date) -> None:
    found = by_id(money, today)
    changed = [k for k, v in found.items() if v.price_changed]  # type: ignore[attr-defined]
    assert changed == [series_key("Flickwave Video")]
    fw = found[series_key("Flickwave Video")]
    assert fw.previous_amount_cents == -1_199 and fw.last_amount_cents == -1_549  # type: ignore[attr-defined]
    assert fw.amount_cents == -1_549  # type: ignore[attr-defined]


def test_variable_bills_use_the_average(money: MoneyDB, today: dt.date) -> None:
    power = by_id(money, today)[series_key("Cedar Valley Power")]
    assert power.variable and not power.price_changed  # type: ignore[attr-defined]
    assert power.amount_cents == -round((9_640 + 8_815 + 9_170) / 3)  # type: ignore[attr-defined]


def test_everyday_merchants_are_not_recurring(money: MoneyDB, today: dt.date) -> None:
    found = by_id(money, today)
    assert not {
        series_key(n) for n in ("Green Basket Market", "Corner Bean Cafe", "City Transit", "Noodle Lane Kitchen", "Riley Park")
    } & set(found)


def test_cancelled_series_leaves_the_forecast(money: MoneyDB, today: dt.date) -> None:
    with money.session() as s:
        ledger.cancel_series(s, series_key("Flickwave Video"), "a1")
        f = fc.build(s, today)
    fw = next(r for r in f.series if r.id == series_key("Flickwave Video"))
    assert fw.status == "cancelled"
    assert not [e for d in f.days for e in d.events if e.label == "Flickwave Video"]
