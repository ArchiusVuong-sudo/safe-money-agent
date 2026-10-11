"""Runtime settings, read once from the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else default


@dataclass(frozen=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 4102
    data_dir: Path = REPO_ROOT / "data"
    fixtures_dir: Path = REPO_ROOT / "fixtures"
    web_dist: Path = REPO_ROOT / "web" / "dist"
    force_replay: bool = False
    agent_model: str = "claude-sonnet-5-5"
    max_turns: int = 12
    approval_timeout_s: int = 300
    replay_delay_ms: int = 450
    eval_concurrency: int = 3


def load_settings() -> Settings:
    return Settings(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=_int("PORT", 4102),
        data_dir=Path(os.environ.get("DATA_DIR", str(REPO_ROOT / "data"))),
        fixtures_dir=Path(os.environ.get("FIXTURES_DIR", str(REPO_ROOT / "fixtures"))),
        web_dist=Path(os.environ.get("WEB_DIST", str(REPO_ROOT / "web" / "dist"))),
        force_replay=_flag("DEMO_REPLAY"),
        agent_model=os.environ.get("AGENT_MODEL", "claude-sonnet-5-5"),
        max_turns=_int("AGENT_MAX_TURNS", 12),
        approval_timeout_s=_int("APPROVAL_TIMEOUT_S", 300),
        replay_delay_ms=_int("REPLAY_DELAY_MS", 450),
        eval_concurrency=_int("EVAL_CONCURRENCY", 3),
    )
