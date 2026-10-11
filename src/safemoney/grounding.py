"""Grounding check: every dollar figure in a reply must come from a tool (or the user).

A figure counts as grounded when its absolute value in cents equals a number
that a tool returned in a dollar field (keys ending in ``usd``, plus the daily
forecast rows), a "$" figure inside tool text (policy check details), or a
figure the user typed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

_FIGURE = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{1,2}))?(?!\d)")


def figures(text: str) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for m in _FIGURE.finditer(text):
        whole = m.group(1).replace(",", "")
        frac = (m.group(2) or "0").ljust(2, "0")
        try:
            cents = int(Decimal(whole) * 100 + Decimal(frac))
        except InvalidOperation:
            continue
        out.append((m.group(0), cents))
    return out


def _numbers(value: Any) -> list[float]:
    if isinstance(value, bool):
        return []
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, list):
        return [n for v in value for n in _numbers(v)]
    if isinstance(value, dict):
        return [n for v in value.values() for n in _numbers(v)]
    return []


def known_cents(payloads: list[dict[str, Any]]) -> set[int]:
    known: set[int] = set()

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k.endswith("usd") or k == "daily":
                    known.update(abs(round(n * 100)) for n in _numbers(v))
                else:
                    walk(v)
        elif isinstance(obj, str):
            known.update(abs(c) for _, c in figures(obj))
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    for p in payloads:
        walk(p)
    return known


@dataclass(frozen=True)
class Grounding:
    grounded: bool
    figures: list[str]
    ungrounded: list[str]


def check(reply: str, payloads: list[dict[str, Any]], user_text: str = "") -> Grounding:
    known = known_cents(payloads) | {c for _, c in figures(user_text)}
    found = figures(reply)
    bad = [raw for raw, cents in found if cents not in known]
    return Grounding(not bad, [raw for raw, _ in found], bad)
