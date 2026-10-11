"""Model providers: live (Claude Agent SDK) and replay (recorded live runs).

Both drive the same gate and tool host. Live hands them to the SDK: the read
tools are auto-allowed by full name, the write tools reach ``can_use_tool``.
Replay walks a recorded run: read tools run directly, write tools go through
the gate first, exactly as the SDK would. The app logic (policy, approvals,
ledger, forecast) always runs for real; only the model's words are replayed.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import random
import re
import shutil
import subprocess
import tempfile
import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from ..tools import READ_TOOLS, SERVER_NAME, TOOLS, full_name
from .dates import shift_obj, shift_text
from .env import child_env, isolate_process_env
from .gate import Gate, ToolHost
from .trace import TraceRecorder

# The SDK warns that allowed tools skip can_use_tool. That is the intent for
# the read tools, and the reason the write tools are never listed.
try:
    from claude_agent_sdk.types import CanUseToolShadowedWarning

    warnings.filterwarnings("ignore", category=CanUseToolShadowedWarning)
except ImportError:  # older SDKs have no such warning
    pass

RETRY_STATUSES = {429, 500, 502, 503, 504, 529}
RETRY_WORDS = ("overloaded", "rate limit", "rate_limit", "529", "503", "502", "500 ", "internal server error")


@dataclass
class AgentRequest:
    message: str  # what the user typed
    prompt: str  # message plus recent history
    system_prompt: str
    fixture_key: str  # replay lookup: eval case id or normalized message


@dataclass
class ProviderResult:
    final_text: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    cost_usd: float | None = None
    duration_ms: int | None = None
    num_turns: int | None = None
    script: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    note: str | None = None


class Provider(Protocol):
    name: str
    model: str

    async def run(self, req: AgentRequest, host: ToolHost, gate: Gate, recorder: TraceRecorder) -> ProviderResult: ...


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9$ ]+", "", re.sub(r"\s+", " ", text.lower())).strip()


def usage_from(raw: dict[str, Any] | None) -> dict[str, int]:
    raw = raw or {}
    return {
        "input_tokens": int(raw.get("input_tokens") or 0),
        "output_tokens": int(raw.get("output_tokens") or 0),
        "cache_creation_tokens": int(raw.get("cache_creation_input_tokens") or 0),
        "cache_read_tokens": int(raw.get("cache_read_input_tokens") or 0),
    }


# ---------------------------------------------------------------------- live


def build_options(
    *,
    model: str,
    max_turns: int,
    system_prompt: str,
    server: Any,
    can_use_tool: Any,
    cwd: str,
    stderr: Any = None,
) -> Any:
    """The SDK options for one run. Tests assert every isolation setting here."""
    from claude_agent_sdk import ClaudeAgentOptions

    return ClaudeAgentOptions(
        tools=[],
        allowed_tools=list(READ_TOOLS),
        mcp_servers={SERVER_NAME: server},
        strict_mcp_config=True,
        setting_sources=[],
        permission_mode="default",
        can_use_tool=can_use_tool,
        cwd=cwd,
        max_turns=max_turns,
        model=model,
        system_prompt=system_prompt,
        env=child_env(),
        extra_args={"no-session-persistence": None},
        stderr=stderr,
    )


def build_server(host: ToolHost) -> Any:
    from claude_agent_sdk import create_sdk_mcp_server, tool

    sdk_tools = []
    for spec in TOOLS:

        def make(name: str) -> Any:
            async def handler(args: dict[str, Any]) -> dict[str, Any]:
                payload, is_error = await host.call(full_name(name), args)
                return {"content": [{"type": "text", "text": json.dumps(payload)}], "is_error": is_error}

            return handler

        sdk_tools.append(tool(spec.name, spec.description, spec.json_schema())(make(spec.name)))
    return create_sdk_mcp_server(SERVER_NAME, version="0.1.0", tools=sdk_tools)


def make_can_use_tool(gate: Gate) -> Any:
    from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny

    async def can_use_tool(tool_name: str, tool_input: dict[str, Any], context: Any) -> Any:
        decision = await gate.check(tool_name, tool_input)
        if decision.allow:
            return PermissionResultAllow(updated_input=decision.updated_input)
        return PermissionResultDeny(message=decision.message)

    return can_use_tool


def _retryable(text: str | None, status: int | None) -> bool:
    if status in RETRY_STATUSES:
        return True
    low = (text or "").lower()
    return any(w in low for w in RETRY_WORDS)


class LiveProvider:
    name = "live"

    def __init__(self, model: str, max_turns: int, retries: int = 3) -> None:
        self.model = model
        self.max_turns = max_turns
        self.retries = retries
        isolate_process_env()

    async def run(self, req: AgentRequest, host: ToolHost, gate: Gate, recorder: TraceRecorder) -> ProviderResult:
        attempt = 0
        while True:
            gated_before = len(gate.outcomes)
            result = await self._attempt(req, host, gate, recorder)
            # Retry only on transient API errors, and only when no write request was made.
            if (
                result.error
                and _retryable(result.error, result.script.get("api_error_status"))
                and len(gate.outcomes) == gated_before
                and attempt < self.retries
            ):
                attempt += 1
                wait = min(20.0, 2.0 * 2 ** (attempt - 1)) + random.uniform(0, 1)
                await recorder.step("retry", "", {"attempt": attempt, "wait_s": round(wait, 1), "error": result.error[:300]})
                await asyncio.sleep(wait)
                continue
            return result

    async def _attempt(self, req: AgentRequest, host: ToolHost, gate: Gate, recorder: TraceRecorder) -> ProviderResult:
        from claude_agent_sdk import (
            AssistantMessage,
            ClaudeSDKClient,
            RateLimitEvent,
            ResultMessage,
            SystemMessage,
            TextBlock,
            ToolUseBlock,
        )

        out = ProviderResult()
        turns: list[dict[str, Any]] = []
        texts_since_tool: list[str] = []
        stderr_lines: list[str] = []
        cwd = tempfile.mkdtemp(prefix="safe-money-run-")
        started = time.perf_counter()
        options = build_options(
            model=self.model,
            max_turns=self.max_turns,
            system_prompt=req.system_prompt,
            server=build_server(host),
            can_use_tool=make_can_use_tool(gate),
            cwd=cwd,
            stderr=lambda line: stderr_lines.append(line[-500:]),
        )
        try:
            async with ClaudeSDKClient(options=options) as client:
                await client.query(req.prompt)
                async for msg in client.receive_response():
                    if isinstance(msg, SystemMessage) and msg.subtype == "init":
                        await recorder.step(
                            "init",
                            "",
                            {
                                "tools": msg.data.get("tools", []),
                                "model": msg.data.get("model"),
                                "permission_mode": msg.data.get("permissionMode"),
                                "mcp_servers": msg.data.get("mcp_servers"),
                            },
                        )
                        out.script["init_tools"] = msg.data.get("tools", [])
                    elif isinstance(msg, AssistantMessage):
                        if msg.error:
                            out.error = f"assistant error: {msg.error}"
                        for block in msg.content:
                            if isinstance(block, TextBlock) and block.text.strip():
                                turns.append({"type": "text", "text": block.text})
                                texts_since_tool.append(block.text)
                                await recorder.step("assistant_text", "", {"text": block.text})
                            elif isinstance(block, ToolUseBlock):
                                turns.append({"type": "tool_use", "name": block.name, "input": block.input})
                                texts_since_tool = []
                    elif isinstance(msg, RateLimitEvent):
                        if msg.rate_limit_info.status == "rejected":
                            await recorder.step("rate_limit", "", {"status": "rejected", "resets_at": msg.rate_limit_info.resets_at})
                    elif isinstance(msg, ResultMessage):
                        out.usage = usage_from(msg.usage)
                        out.cost_usd = msg.total_cost_usd
                        out.duration_ms = msg.duration_ms
                        out.num_turns = msg.num_turns
                        out.script["api_error_status"] = msg.api_error_status
                        if msg.is_error:
                            out.error = " ".join([msg.result or "", *(msg.errors or [])]).strip() or msg.subtype
                        elif msg.subtype != "success":
                            out.note = f"stopped: {msg.subtype}"
                        out.final_text = "\n\n".join(texts_since_tool).strip() or (msg.result or "").strip()
        except Exception as exc:  # SDK or CLI failure
            tail = " | ".join(stderr_lines[-3:])
            out.error = f"{type(exc).__name__}: {exc}" + (f" ({tail})" if tail else "")
        finally:
            shutil.rmtree(cwd, ignore_errors=True)
        if out.duration_ms is None:
            out.duration_ms = round((time.perf_counter() - started) * 1000)
        out.script.update({"turns": turns, "decisions": list(gate.outcomes), "model": self.model})
        return out


def live_login_available() -> bool:
    """True when the SDK can reach Claude: an API key, or a logged-in local CLI."""
    env = child_env()
    if env.get("ANTHROPIC_API_KEY"):
        return True
    try:
        import claude_agent_sdk

        bundled = Path(claude_agent_sdk.__file__).parent / "_bundled" / "claude"
        cli = str(bundled) if bundled.exists() else shutil.which("claude")
        if not cli:
            return False
        proc = subprocess.run([cli, "auth", "status"], capture_output=True, text=True, timeout=20, env=env)
        text = (proc.stdout + proc.stderr).lower()
        if proc.returncode != 0:
            return False
        try:
            data = json.loads(proc.stdout)
            return bool(data.get("loggedIn") or data.get("logged_in"))
        except json.JSONDecodeError:
            return "logged in" in text and "not logged in" not in text
    except Exception:
        return False


# ---------------------------------------------------------------------- replay


@dataclass
class Fixture:
    key: str
    prompt: str
    variant: str
    recorded_on: dt.date
    model: str
    turns: list[dict[str, Any]]
    decisions: list[str]
    usage: dict[str, int]
    cost_usd: float | None
    duration_ms: int | None
    num_turns: int | None
    init_tools: list[str]

    @classmethod
    def load(cls, path: Path) -> Fixture:
        d = json.loads(path.read_text())
        return cls(
            key=d["key"],
            prompt=d["prompt"],
            variant=d.get("variant", "default"),
            recorded_on=dt.date.fromisoformat(d["recorded_on"]),
            model=d.get("model", ""),
            turns=d["turns"],
            decisions=d.get("decisions", []),
            usage=d.get("usage", {}),
            cost_usd=d.get("cost_usd"),
            duration_ms=d.get("duration_ms"),
            num_turns=d.get("num_turns"),
            init_tools=d.get("init_tools", []),
        )

    def gated_positions(self) -> list[int]:
        return [i for i, t in enumerate(self.turns) if t["type"] == "tool_use" and t["name"] not in READ_TOOLS]


def load_fixtures(directory: Path) -> dict[str, list[Fixture]]:
    found: dict[str, list[Fixture]] = {}
    if directory.exists():
        for path in sorted(directory.glob("*.json")):
            fx = Fixture.load(path)
            found.setdefault(fx.key, []).append(fx)
    return found


NO_RECORDING = (
    "Replay mode has no recording for this message. Try one of the suggested prompts, or run the app with a Claude login for live answers."
)


class ReplayProvider:
    name = "replay"

    def __init__(self, fixtures_dir: Path, today: dt.date, delay_ms: int = 450) -> None:
        self.fixtures = load_fixtures(fixtures_dir)
        self.today = today
        self.delay_s = delay_ms / 1000
        models = {f.model for fs in self.fixtures.values() for f in fs if f.model}
        self.model = sorted(models)[0] if models else "replay"

    def has(self, key: str) -> bool:
        return key in self.fixtures

    async def _pause(self, factor: float = 1.0) -> None:
        if self.delay_s:
            await asyncio.sleep(self.delay_s * factor)

    async def run(self, req: AgentRequest, host: ToolHost, gate: Gate, recorder: TraceRecorder) -> ProviderResult:
        candidates = self.fixtures.get(req.fixture_key, [])
        if not candidates:
            await self._pause()
            await recorder.step("assistant_text", "", {"text": NO_RECORDING})
            return ProviderResult(final_text=NO_RECORDING, note="no recording", script={"turns": [], "decisions": []})

        current = candidates[0]
        delta = (self.today - current.recorded_on).days
        await recorder.step(
            "init",
            "",
            {"tools": current.init_tools, "model": current.model, "replay_of": current.recorded_on.isoformat(), "variant": current.variant},
        )
        texts_since_tool: list[str] = []
        pos = 0
        gated_index = 0
        note = None
        while pos < len(current.turns):
            turn = current.turns[pos]
            pos += 1
            await self._pause()
            if turn["type"] == "text":
                text = shift_text(turn["text"], delta, current.recorded_on)
                texts_since_tool.append(text)
                await recorder.step("assistant_text", "", {"text": text})
                continue
            name = turn["name"]
            args = shift_obj(turn["input"], delta, current.recorded_on)
            texts_since_tool = []
            if name in READ_TOOLS:
                await host.call(name, args)
                continue
            decision = await gate.check(name, args)
            # Follow the recording whose decision at this point matches what really happened.
            matching = [f for f in candidates if gated_index < len(f.decisions) and f.decisions[gated_index] == decision.outcome]
            if current not in matching:
                if not matching:
                    note = f"replay has no recording after a '{decision.outcome}' decision"
                    text = (
                        "Nothing moved." if decision.outcome in {"declined", "expired"} else ""
                    ) + " Replay mode has no recording for this path; live mode would continue here."
                    texts_since_tool = [text.strip()]
                    await recorder.step("assistant_text", "", {"text": text.strip()})
                    break
                current = matching[0]
                delta = (self.today - current.recorded_on).days
                pos = current.gated_positions()[gated_index] + 1
            gated_index += 1
            if decision.allow:
                await host.call(name, decision.updated_input or args)
        return ProviderResult(
            final_text="\n\n".join(texts_since_tool).strip(),
            usage=dict(current.usage),
            cost_usd=current.cost_usd,
            duration_ms=current.duration_ms,
            num_turns=current.num_turns,
            note=note or f"replay of a live run recorded on {current.recorded_on.isoformat()}",
            script={"turns": current.turns, "decisions": list(gate.outcomes), "variant": current.variant},
        )
