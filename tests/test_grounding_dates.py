from __future__ import annotations

import datetime as dt

from safemoney import grounding
from safemoney.agent.dates import shift_obj, shift_text
from safemoney.agent.providers import normalize

REC = dt.date(2026, 10, 11)


def test_figures_are_parsed_to_cents() -> None:
    got = grounding.figures("Moved $400.00, low -$304.29, rent $1,450 and $3.5 fee; not 400 or $")
    assert got == [("$400.00", 40_000), ("$304.29", 30_429), ("$1,450", 145_000), ("$3.5", 350)]


def test_grounded_when_every_figure_came_from_a_tool() -> None:
    payloads = [{"balance_usd": 1672.69, "daily": [["2026-10-11", -304.29, 3800.0]], "checks": [{"detail": "falls to -$1,404.29"}]}]
    ok = grounding.check("Checking $1,672.69 dips to -$304.29, or -$1,404.29.", payloads)
    assert ok.grounded and ok.ungrounded == []


def test_flags_a_figure_no_tool_returned() -> None:
    bad = grounding.check("You could move $45.71 or about $300.", [{"max_safe_today_usd": 45.71}])
    assert not bad.grounded and bad.ungrounded == ["$300"]


def test_user_figures_count_and_ids_do_not() -> None:
    assert grounding.check("Moving $1,500.00 is not safe.", [], user_text="Move $1,500 to savings").grounded
    assert not grounding.check("That is $5.00.", [{"entry_id": 5}]).grounded


def test_shift_iso_and_human_dates() -> None:
    text = "On Sun, Oct 18 (2026-10-18) checking dips; payday is Monday, October 19th and Oct 31 then Nov 1."
    out = shift_text(text, 3, REC)
    assert out == "On Wed, Oct 21 (2026-10-21) checking dips; payday is Thursday, October 22nd and Nov 3 then Nov 4."


def test_shift_across_year_end() -> None:
    assert shift_text("Wed, Dec 30 and 2026-12-30", 3, dt.date(2026, 12, 20)) == "Sat, Jan 2 and 2027-01-02"


def test_shift_zero_and_nested() -> None:
    assert shift_text("Oct 18", 0, REC) == "Oct 18"
    assert shift_obj({"a": ["2026-10-11", 5], "b": "x"}, 1, REC) == {"a": ["2026-10-12", 5], "b": "x"}


def test_normalize_prompt_keys() -> None:
    assert normalize("Move $1,500 to  savings today.") == normalize("move $1500 to savings today")
