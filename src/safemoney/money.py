"""Small helpers for integer-cent money."""

from __future__ import annotations

import datetime as dt
from decimal import ROUND_HALF_UP, Decimal


def usd(cents: int) -> float:
    """Cents to a two-decimal dollar float, for tool output."""
    return float(Decimal(cents) / 100)


def to_cents(amount_usd: float | int | str | Decimal) -> int:
    value = Decimal(str(amount_usd)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int(value * 100)


def fmt(cents: int) -> str:
    """$1,234.56 or -$12.00."""
    sign = "-" if cents < 0 else ""
    return f"{sign}${abs(cents) / 100:,.2f}"


def day_label(d: dt.date) -> str:
    """Sun, Oct 18"""
    return f"{d.strftime('%a')}, {d.strftime('%b')} {d.day}"
