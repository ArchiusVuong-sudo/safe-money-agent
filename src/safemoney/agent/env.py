"""The agent child process gets an environment built from an allowlist."""

from __future__ import annotations

import os

ALLOWED_ENV = ("PATH", "HOME", "USER", "LANG", "TMPDIR", "ANTHROPIC_API_KEY")


def child_env(source: dict[str, str] | None = None) -> dict[str, str]:
    src = os.environ if source is None else source
    return {k: src[k] for k in ALLOWED_ENV if src.get(k)}


def isolate_process_env() -> None:
    """Reduce this process's environment to the allowlist.

    The SDK merges the parent environment into the CLI's environment, so an
    allowlist passed through ``options.env`` alone would not drop anything.
    The server reads its own settings at startup, then calls this once before
    the first live run. CLAUDECODE and CLAUDE_CODE_* never reach the child.
    """
    keep = child_env()
    os.environ.clear()
    os.environ.update(keep)
