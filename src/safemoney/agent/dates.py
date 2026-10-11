"""Shift dates in recorded replay text, so a run recorded on one day replays on another.

The seed is relative to today, so balances on day N match; only calendar dates
in the recorded model text and tool arguments need moving.
"""

from __future__ import annotations

import calendar
import datetime as dt
import re
from typing import Any

_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_MONTHS_LONG = list(calendar.month_name)[1:]
_MONTHS_SHORT = list(calendar.month_abbr)[1:]
_MONTH_ALT = "|".join(_MONTHS_LONG + [m for m in _MONTHS_SHORT if m != "May"] + ["Sept"])
_WEEKDAY_ALT = "Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|Mon|Tue|Wed|Thu|Fri|Sat|Sun"
# "Friday, October 17", "Fri Oct 17", "Oct 17", "October 17th"
_HUMAN = re.compile(
    rf"\b(?:(?P<wd>{_WEEKDAY_ALT}),?\s+)?(?P<mon>{_MONTH_ALT})\.?\s+(?P<day>\d{{1,2}})(?P<suf>st|nd|rd|th)?\b"
)
_WEEKDAYS_LONG = list(calendar.day_name)
_WEEKDAYS_SHORT = list(calendar.day_abbr)


def _month_index(name: str) -> int:
    name = name.rstrip(".")
    if name == "Sept":
        return 9
    if name in _MONTHS_LONG:
        return _MONTHS_LONG.index(name) + 1
    return _MONTHS_SHORT.index(name) + 1


def _suffix(day: int) -> str:
    if 11 <= day % 100 <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")


def shift_text(text: str, delta_days: int, recorded_on: dt.date) -> str:
    if delta_days == 0 or not text:
        return text
    delta = dt.timedelta(days=delta_days)

    def iso(m: re.Match[str]) -> str:
        try:
            d = dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return m.group(0)
        return (d + delta).isoformat()

    def human(m: re.Match[str]) -> str:
        month = _month_index(m.group("mon"))
        day = int(m.group("day"))
        year = recorded_on.year
        try:
            d = dt.date(year, month, day)
        except ValueError:
            return m.group(0)
        if (d - recorded_on).days < -180:  # a date early next year
            d = dt.date(year + 1, month, day)
        new = d + delta
        long_month = m.group("mon").rstrip(".") in _MONTHS_LONG
        mon = calendar.month_name[new.month] if long_month else calendar.month_abbr[new.month]
        out = f"{mon} {new.day}"
        if m.group("suf"):
            out += _suffix(new.day)
        if m.group("wd"):
            wd = m.group("wd")
            names = _WEEKDAYS_LONG if wd in _WEEKDAYS_LONG else _WEEKDAYS_SHORT
            sep = m.group(0)[len(wd) : m.group(0).index(m.group("mon"))]
            out = f"{names[new.weekday()]}{sep}{out}"
        return out

    text = _ISO.sub(iso, text)
    return _HUMAN.sub(human, text)


def shift_obj(obj: Any, delta_days: int, recorded_on: dt.date) -> Any:
    if isinstance(obj, str):
        return shift_text(obj, delta_days, recorded_on)
    if isinstance(obj, list):
        return [shift_obj(x, delta_days, recorded_on) for x in obj]
    if isinstance(obj, dict):
        return {k: shift_obj(v, delta_days, recorded_on) for k, v in obj.items()}
    return obj
