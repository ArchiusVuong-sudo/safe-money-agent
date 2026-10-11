from __future__ import annotations

import datetime as dt

import pytest
from pydantic import ValidationError

from safemoney import ledger, policy
from safemoney.db import MoneyDB
from safemoney.policy import CancelRequest, TransferRequest


def tr(today: dt.date, amount: float, frm: str = "sav", to: str = "chk", days: int = 0) -> TransferRequest:
    return TransferRequest(from_account=frm, to_account=to, amount_usd=amount, date=today + dt.timedelta(days=days))


def evaluate(money: MoneyDB, today: dt.date, req: TransferRequest) -> policy.PolicyResult:
    with money.session() as s:
        return policy.evaluate_transfer(s, today, req)


def failed(r: policy.PolicyResult) -> list[str]:
    return [c.id for c in r.failed]


def test_fix_amount_passes_every_check(money: MoneyDB, today: dt.date) -> None:
    r = evaluate(money, today, tr(today, 400))
    assert r.allowed and failed(r) == []
    assert r.preview["low_points"]["chk"]["before"]["usd"] == -304.29
    assert r.preview["low_points"]["chk"]["after"]["usd"] == 95.71


def test_too_small_a_fix_fails_the_floor(money: MoneyDB, today: dt.date) -> None:
    r = evaluate(money, today, tr(today, 300))
    assert failed(r) == ["floors"]
    assert r.hints["min_needed_today_usd"] == 354.29


def test_transfer_to_a_contact_is_refused(money: MoneyDB, today: dt.date) -> None:
    r = evaluate(money, today, tr(today, 200, frm="chk", to="contact_riley"))
    assert "own_accounts" in failed(r)
    assert "not one of your own accounts" in r.checks[0].detail


@pytest.mark.parametrize(("frm", "to"), [("chk", "chk"), ("chk", "nope"), ("nope", "sav")])
def test_bad_account_pairs_are_refused(money: MoneyDB, today: dt.date, frm: str, to: str) -> None:
    assert "own_accounts" in failed(evaluate(money, today, tr(today, 50, frm=frm, to=to)))


@pytest.mark.parametrize(("amount", "ok"), [(0.99, False), (1.0, None), (2000.0, True), (2000.01, False)])
def test_amount_bounds(money: MoneyDB, today: dt.date, amount: float, ok: bool | None) -> None:
    r = evaluate(money, today, tr(today, amount))
    assert ("amount_range" not in failed(r)) is (ok is not False)
    if ok:
        assert r.allowed


@pytest.mark.parametrize(("days", "ok"), [(-1, False), (0, True), (30, True), (31, False)])
def test_date_window(money: MoneyDB, today: dt.date, days: int, ok: bool) -> None:
    r = evaluate(money, today, tr(today, 50, frm="chk", to="sav", days=days))
    assert ("date_window" not in failed(r)) is ok


def test_over_ask_today_fails_floor_with_payday_hint(money: MoneyDB, today: dt.date) -> None:
    r = evaluate(money, today, tr(today, 1500, frm="chk", to="sav"))
    assert failed(r) == ["floors"]
    assert r.hints["max_safe_today_usd"] == 0.0
    assert r.hints["next_payday"] == (today + dt.timedelta(days=8)).isoformat()
    assert r.hints["max_safe_on_next_payday_usd"] == 1597.44


def test_over_ask_on_payday_passes(money: MoneyDB, today: dt.date) -> None:
    r = evaluate(money, today, tr(today, 1500, frm="chk", to="sav", days=8))
    assert r.allowed, r.failed


def test_savings_floor_is_enforced(money: MoneyDB, today: dt.date) -> None:
    with money.session() as s:
        ledger.post_transfer(
            s, idempotency_key="drain", from_account="sav", to_account="chk", amount_cents=200_000, effective_on=today, today=today
        )
    r = evaluate(money, today, tr(today, 1500))  # savings 1,800 -> 300, under the 500 floor
    assert failed(r) == ["floors"]
    assert "sav falls to" in r.checks[3].detail


def test_duplicate_transfer_is_refused(money: MoneyDB, today: dt.date) -> None:
    with money.session() as s:
        ledger.post_transfer(
            s, idempotency_key="x", from_account="sav", to_account="chk", amount_cents=40_000, effective_on=today, today=today
        )
    assert "not_duplicate" in failed(evaluate(money, today, tr(today, 400)))


def test_input_validation() -> None:
    with pytest.raises(ValidationError):
        TransferRequest(from_account="sav", to_account="chk", amount_usd=10.001, date=dt.date.today())
    with pytest.raises(ValidationError):
        TransferRequest.model_validate({"from_account": "sav", "to_account": "chk", "amount_usd": 10, "date": "2026-01-01", "extra": 1})
    with pytest.raises(ValidationError):
        TransferRequest(from_account="sav", to_account="chk", amount_usd=-5, date=dt.date.today())


def test_args_hash_is_canonical(today: dt.date) -> None:
    a = TransferRequest.model_validate({"from_account": "sav", "to_account": "chk", "amount_usd": 400, "date": today.isoformat()})
    b = TransferRequest.model_validate({"date": today.isoformat(), "amount_usd": 400.0, "to_account": "chk", "from_account": "sav"})
    assert policy.args_hash(a) == policy.args_hash(b)


@pytest.mark.parametrize(
    ("series", "fails"),
    [("flickwave-video", []), ("maple-court-apartments", ["is_subscription"]), ("nope", ["series_exists", "is_subscription", "is_active"])],
)
def test_cancel_policy(money: MoneyDB, today: dt.date, series: str, fails: list[str]) -> None:
    with money.session() as s:
        r = policy.evaluate_cancel(s, today, CancelRequest(series_id=series))
    assert [c.id for c in r.failed] == fails


def test_cancel_preview_and_already_cancelled(money: MoneyDB, today: dt.date) -> None:
    with money.session() as s:
        r = policy.evaluate_cancel(s, today, CancelRequest(series_id="flickwave-video"))
        assert r.preview["amount_usd"] == 15.49 and r.preview["previous_amount_usd"] == 11.99
        assert r.preview["saves_next_30_days_usd"] == 15.49
        ledger.cancel_series(s, "flickwave-video", "a1")
        again = policy.evaluate_cancel(s, today, CancelRequest(series_id="flickwave-video"))
    assert [c.id for c in again.failed] == ["is_active"]
