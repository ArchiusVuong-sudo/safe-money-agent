"""The double-entry ledger: balances, transfers and series status."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Account, Entry, Posting, SeriesStatus


class LedgerError(Exception):
    pass


def own_accounts(s: Session) -> list[Account]:
    return list(s.scalars(select(Account).where(Account.owner == "self").order_by(Account.id)))


def get_account(s: Session, account_id: str) -> Account | None:
    return s.get(Account, account_id)


def balance(s: Session, account_id: str, as_of: dt.date) -> int:
    total = s.scalar(
        select(func.coalesce(func.sum(Posting.amount_cents), 0))
        .join(Entry, Entry.id == Posting.entry_id)
        .where(Posting.account_id == account_id, Entry.effective_on <= as_of)
    )
    return int(total or 0)


@dataclass(frozen=True)
class PostedTransfer:
    entry_id: int
    idempotency_key: str
    effective_on: dt.date
    status: str  # posted | scheduled
    legs: list[tuple[str, int]]
    created: bool  # False when the key already existed


def post_transfer(
    s: Session,
    *,
    idempotency_key: str,
    from_account: str,
    to_account: str,
    amount_cents: int,
    effective_on: dt.date,
    today: dt.date,
    memo: str = "",
) -> PostedTransfer:
    """Post a transfer as two legs that sum to zero, exactly once per key."""
    if amount_cents <= 0:
        raise LedgerError("amount must be positive")
    if from_account == to_account:
        raise LedgerError("from and to must differ")
    existing = s.scalar(select(Entry).where(Entry.idempotency_key == idempotency_key))
    if existing is not None:
        return _as_posted(existing, today, created=False)
    src, dst = s.get(Account, from_account), s.get(Account, to_account)
    if src is None or dst is None:
        raise LedgerError("unknown account")
    entry = Entry(
        idempotency_key=idempotency_key,
        effective_on=effective_on,
        kind="transfer",
        counterparty=f"Transfer to {dst.name}",
        memo=memo,
        category="transfer",
        source="agent",
    )
    entry.postings = [
        Posting(account_id=from_account, amount_cents=-amount_cents),
        Posting(account_id=to_account, amount_cents=amount_cents),
    ]
    s.add(entry)
    s.flush()
    return _as_posted(entry, today, created=True)


def _as_posted(entry: Entry, today: dt.date, *, created: bool) -> PostedTransfer:
    return PostedTransfer(
        entry_id=entry.id,
        idempotency_key=entry.idempotency_key,
        effective_on=entry.effective_on,
        status="scheduled" if entry.effective_on > today else "posted",
        legs=[(p.account_id, p.amount_cents) for p in entry.postings],
        created=created,
    )


def agent_transfers(s: Session) -> list[Entry]:
    return list(s.scalars(select(Entry).where(Entry.source == "agent").order_by(Entry.id)))


def cancelled_series(s: Session) -> set[str]:
    return set(s.scalars(select(SeriesStatus.series_key).where(SeriesStatus.status == "cancelled")))


def cancel_series(s: Session, series_key: str, approval_id: str) -> bool:
    """Mark a series cancelled. Returns False if it already was (no new row)."""
    current = s.get(SeriesStatus, series_key)
    if current is not None and current.status == "cancelled":
        return False
    if current is None:
        s.add(SeriesStatus(series_key=series_key, status="cancelled", approval_id=approval_id))
    else:
        current.status = "cancelled"
        current.approval_id = approval_id
    s.flush()
    return True
