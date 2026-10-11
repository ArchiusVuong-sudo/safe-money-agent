"""Fixed money rules, checked in code before anyone is asked to approve.

A transfer passes only when every check passes:
- both accounts are the user's own, and they differ;
- the amount is $1.00 to $2,000.00;
- the date is today or within the next 30 days;
- from the transfer date on, checking stays at or above $50 and savings at
  or above $500 on every forecast day;
- the same transfer is not already pending, approved or posted.

A cancellation passes when the series is a detected, active subscription and
no other cancellation of it is waiting.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import forecast as fc
from .ledger import agent_transfers, get_account
from .models import Approval
from .money import day_label, fmt, to_cents, usd

MIN_TRANSFER_CENTS = 100
MAX_TRANSFER_CENTS = 200_000
WINDOW_DAYS = 30


class TransferRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_account: str = Field(min_length=1, max_length=40)
    to_account: str = Field(min_length=1, max_length=40)
    amount_usd: float = Field(gt=0, le=1_000_000)
    date: dt.date
    memo: str = Field(default="", max_length=140)

    @field_validator("amount_usd")
    @classmethod
    def _two_decimals(cls, v: float) -> float:
        if abs(round(v, 2) - v) > 1e-9:
            raise ValueError("amount_usd must have at most 2 decimals")
        return round(v, 2)

    @property
    def amount_cents(self) -> int:
        return to_cents(self.amount_usd)


class CancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    series_id: str = Field(min_length=1, max_length=80)
    reason: str = Field(default="", max_length=200)


def args_hash(args: BaseModel) -> str:
    canonical = json.dumps(args.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True)
class Check:
    id: str
    label: str
    passed: bool
    detail: str


@dataclass
class PolicyResult:
    allowed: bool
    checks: list[Check]
    hints: dict[str, Any] = field(default_factory=dict)
    preview: dict[str, Any] = field(default_factory=dict)

    @property
    def failed(self) -> list[Check]:
        return [c for c in self.checks if not c.passed]

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "checks": [asdict(c) for c in self.checks],
            "failed": [c.id for c in self.failed],
            "hints": self.hints,
            "preview": self.preview,
        }


def _low(f: fc.Forecast, account: str, since: dt.date) -> dict[str, Any]:
    lp = f.low(account, since)
    return {"usd": usd(lp.cents), "date": lp.date.isoformat(), "day": day_label(lp.date)}


@dataclass(frozen=True)
class SafeRange:
    min_cents: int
    max_cents: int

    @property
    def exists(self) -> bool:
        return self.max_cents >= max(self.min_cents, MIN_TRANSFER_CENTS)


def safe_range(base: fc.Forecast, from_account: str, to_account: str, on: dt.date) -> SafeRange:
    """Smallest amount that lifts the destination to its floor, largest the source can spare."""
    src = base.low(from_account, on)
    dst = base.low(to_account, on)
    headroom = src.cents - base.floors[from_account]
    need = max(0, base.floors[to_account] - dst.cents)
    return SafeRange(min_cents=need, max_cents=min(headroom, MAX_TRANSFER_CENTS))


def _transfer_hints(today: dt.date, base: fc.Forecast, req: TransferRequest) -> dict[str, Any]:
    hints: dict[str, Any] = {
        "own_accounts": sorted(base.floors),
        "floors_usd": {k: usd(v) for k, v in base.floors.items()},
        "allowed_amount_usd": [usd(MIN_TRANSFER_CENTS), usd(MAX_TRANSFER_CENTS)],
        "latest_date": (today + dt.timedelta(days=WINDOW_DAYS)).isoformat(),
    }
    if req.from_account in base.floors and req.to_account in base.floors and req.from_account != req.to_account:
        today_range = safe_range(base, req.from_account, req.to_account, today)
        hints["max_safe_today_usd"] = usd(max(0, today_range.max_cents)) if today_range.exists else 0.0
        if today_range.min_cents > 0:
            hints["min_needed_today_usd"] = usd(today_range.min_cents)
        if base.next_payday is not None:
            pay_range = safe_range(base, req.from_account, req.to_account, base.next_payday)
            hints["next_payday"] = base.next_payday.isoformat()
            hints["next_payday_day"] = day_label(base.next_payday)
            hints["max_safe_on_next_payday_usd"] = usd(max(0, pay_range.max_cents)) if pay_range.exists else 0.0
    return hints


def evaluate_transfer(s: Session, today: dt.date, req: TransferRequest, *, approval_id: str | None = None) -> PolicyResult:
    cents = req.amount_cents
    src, dst = get_account(s, req.from_account), get_account(s, req.to_account)
    checks: list[Check] = []

    own = src is not None and dst is not None and src.owner == "self" and dst.owner == "self" and src.id != dst.id
    if own:
        detail = f"{src.name} to {dst.name}"  # type: ignore[union-attr]
    elif dst is not None and dst.owner != "self":
        detail = f"{dst.name} is not one of your own accounts"
    elif src is not None and dst is not None and src.id == dst.id:
        detail = "from and to are the same account"
    else:
        detail = "unknown account id"
    checks.append(Check("own_accounts", "Both accounts are yours", own, detail))

    in_range = MIN_TRANSFER_CENTS <= cents <= MAX_TRANSFER_CENTS
    checks.append(Check("amount_range", "Amount is $1 to $2,000", in_range, f"{fmt(cents)} requested"))

    last_day = today + dt.timedelta(days=WINDOW_DAYS)
    in_window = today <= req.date <= last_day
    checks.append(
        Check(
            "date_window",
            "Date is within 30 days",
            in_window,
            f"{req.date.isoformat()} (allowed {today.isoformat()} to {last_day.isoformat()})",
        )
    )

    base = fc.build(s, today)
    preview: dict[str, Any] = {
        "kind": "transfer",
        "amount_usd": usd(cents),
        "date": req.date.isoformat(),
        "day": day_label(req.date),
        "when": "today" if req.date == today else "scheduled",
        "from": {"id": req.from_account, "name": src.name if src else req.from_account},
        "to": {"id": req.to_account, "name": dst.name if dst else req.to_account},
        "memo": req.memo,
    }
    if own and in_window:
        after = fc.build(s, today, hypotheticals=[fc.Hypothetical(req.from_account, req.to_account, cents, req.date)])
        problems = []
        for acct in sorted(base.floors):
            lp = after.low(acct, req.date)
            if lp.cents < after.floors[acct]:
                problems.append(f"{acct} falls to {fmt(lp.cents)} on {day_label(lp.date)}, under the {fmt(after.floors[acct])} floor")
        floors_ok = not problems
        detail = (
            "; ".join(problems) if problems else "checking stays at or above $50 and savings at or above $500 from the transfer date on"
        )
        # Low points from the transfer date on: that is the part a transfer can change.
        preview["low_points"] = {
            acct: {"before": _low(base, acct, req.date), "after": _low(after, acct, req.date)} for acct in sorted(base.floors)
        }
        preview["low_since"] = req.date.isoformat()
    else:
        floors_ok = False
        detail = "not checked: accounts or date are invalid"
    checks.append(Check("floors", "Balances stay above floors", floors_ok, detail))

    h = args_hash(req)
    dup_entry = any(
        e.effective_on == req.date
        and sorted((p.account_id, p.amount_cents) for p in e.postings) == sorted([(req.from_account, -cents), (req.to_account, cents)])
        for e in agent_transfers(s)
    )
    dup_approval = s.scalar(
        select(Approval.id).where(
            Approval.args_hash == h,
            Approval.status.in_(["pending", "approved"]),
            Approval.used_at.is_(None),
            Approval.id != (approval_id or ""),
        )
    )
    not_dup = not dup_entry and dup_approval is None
    checks.append(
        Check(
            "not_duplicate",
            "Not a duplicate",
            not_dup,
            "no matching transfer" if not_dup else "the same transfer is already posted or waiting",
        )
    )

    allowed = all(c.passed for c in checks)
    hints = {} if allowed else _transfer_hints(today, base, req)
    return PolicyResult(allowed, checks, hints, preview)


def evaluate_cancel(s: Session, today: dt.date, req: CancelRequest, *, approval_id: str | None = None) -> PolicyResult:
    base = fc.build(s, today)
    series = next((x for x in base.series if x.id == req.series_id), None)
    checks = [
        Check("series_exists", "Recurring series found", series is not None, req.series_id),
        Check(
            "is_subscription",
            "It is a subscription",
            series is not None and series.kind == "subscription",
            series.kind if series else "unknown",
        ),
        Check(
            "is_active",
            "Still active",
            series is not None and series.status == "active",
            series.status if series else "unknown",
        ),
    ]
    h = args_hash(req)
    waiting = s.scalar(
        select(Approval.id).where(
            Approval.args_hash == h,
            Approval.status.in_(["pending", "approved"]),
            Approval.used_at.is_(None),
            Approval.id != (approval_id or ""),
        )
    )
    checks.append(
        Check("not_duplicate", "Not a duplicate", waiting is None, "no other request waiting" if waiting is None else "already waiting")
    )
    allowed = all(c.passed for c in checks)
    preview: dict[str, Any] = {"kind": "cancel", "series_id": req.series_id, "reason": req.reason}
    if series is not None:
        horizon_end = today + dt.timedelta(days=fc.HORIZON_DAYS)
        charges = 0
        day = series.next_date
        while day <= horizon_end:
            charges += 1
            day += dt.timedelta(days=series.cadence_days)
        preview.update(
            {
                "name": series.counterparty,
                "amount_usd": usd(-series.last_amount_cents),
                "previous_amount_usd": usd(-series.previous_amount_cents) if series.previous_amount_cents is not None else None,
                "next_charge": series.next_date.isoformat(),
                "saves_next_30_days_usd": usd(-series.amount_cents * charges),
            }
        )
    hints = {} if allowed else {"subscriptions": [x.id for x in base.series if x.kind == "subscription" and x.status == "active"]}
    return PolicyResult(allowed, checks, hints, preview)
