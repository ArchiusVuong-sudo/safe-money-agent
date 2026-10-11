"""Engines and sessions for the money and trace databases."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from .models import MoneyBase, TraceBase


def _engine(path: Path) -> Engine:
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _pragmas(conn, _record):  # type: ignore[no-untyped-def]
        cur = conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()

    return engine


class Database:
    """One SQLite file with a session factory."""

    def __init__(self, path: Path, base: type[MoneyBase] | type[TraceBase]) -> None:
        self.path = path
        self.engine = _engine(path)
        base.metadata.create_all(self.engine)
        self._factory = sessionmaker(self.engine, expire_on_commit=False)

    @contextmanager
    def session(self) -> Iterator[Session]:
        with self._factory() as s:
            try:
                yield s
                s.commit()
            except Exception:
                s.rollback()
                raise

    def dispose(self) -> None:
        self.engine.dispose()


class MoneyDB(Database):
    def __init__(self, path: Path) -> None:
        super().__init__(path, MoneyBase)

    def copy_to(self, dest: Path) -> MoneyDB:
        """A full, independent copy (used to give each eval case its own data)."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        src = sqlite3.connect(self.path)
        dst = sqlite3.connect(dest)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        return MoneyDB(dest)


class TraceDB(Database):
    def __init__(self, path: Path) -> None:
        super().__init__(path, TraceBase)
