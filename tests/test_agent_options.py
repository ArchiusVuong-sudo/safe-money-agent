"""How the agent is wired into the Claude Agent SDK.

These run with no network: they check the options object, and drive the real
SDK client against a scripted stand-in for the CLI to prove that a write tool
call reaches can_use_tool and our gate.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
from claude_agent_sdk import ClaudeSDKClient, ResultMessage
from claude_agent_sdk._internal.transport import Transport

from safemoney.agent.env import ALLOWED_ENV, child_env
from safemoney.agent.gate import Gate, ToolHost
from safemoney.agent.providers import build_options, build_server, make_can_use_tool
from safemoney.agent.trace import TraceRecorder
from safemoney.tools import READ_TOOLS, WRITE_TOOLS, ToolContext

from .conftest import make_gate


def options(ctx: ToolContext, recorder: TraceRecorder) -> Any:
    gate = make_gate(ctx, recorder)
    return build_options(
        model="claude-sonnet-5-5",
        max_turns=12,
        system_prompt="test",
        server=build_server(ToolHost(ctx, recorder)),
        can_use_tool=make_can_use_tool(gate),
        cwd="/tmp",
    )


def test_isolation_settings(ctx: ToolContext, recorder: TraceRecorder) -> None:
    o = options(ctx, recorder)
    assert o.tools == []  # no built-in Claude Code tools
    assert o.setting_sources == []  # no user, project or local settings, hooks or allow rules
    assert o.strict_mcp_config is True
    assert list(o.mcp_servers) == ["money"]
    assert o.permission_mode == "default"  # never bypassPermissions, acceptEdits, dontAsk or auto
    assert o.max_turns == 12
    assert o.extra_args == {"no-session-persistence": None}
    assert o.can_use_tool is not None


def test_allowed_tools_are_exactly_the_read_tools(ctx: ToolContext, recorder: TraceRecorder) -> None:
    o = options(ctx, recorder)
    assert o.allowed_tools == [
        "mcp__money__get_accounts",
        "mcp__money__search_transactions",
        "mcp__money__list_recurring",
        "mcp__money__forecast",
        "mcp__money__simulate",
    ]
    assert list(READ_TOOLS) == o.allowed_tools
    for entry in o.allowed_tools:
        # A server-level entry or a wildcard would also auto-allow the write tools.
        assert entry.count("__") == 2 and "*" not in entry and entry != "mcp__money"
        assert entry not in WRITE_TOOLS
    assert "mcp__money__move_money" not in o.allowed_tools
    assert "mcp__money__cancel_subscription" not in o.allowed_tools


def test_child_env_is_an_allowlist() -> None:
    src = {
        "PATH": "/bin",
        "HOME": "/h",
        "USER": "u",
        "LANG": "C",
        "TMPDIR": "/t",
        "CLAUDECODE": "1",
        "CLAUDE_CODE_ENTRYPOINT": "cli",
        "CLAUDE_CODE_OAUTH_TOKEN": "x",
        "AWS_SECRET_ACCESS_KEY": "y",
        "DEMO_REPLAY": "1",
    }
    env = child_env(src)
    assert set(env) == {"PATH", "HOME", "USER", "LANG", "TMPDIR"}
    assert child_env({**src, "ANTHROPIC_API_KEY": "k"})["ANTHROPIC_API_KEY"] == "k"
    assert set(ALLOWED_ENV) == {"PATH", "HOME", "USER", "LANG", "TMPDIR", "ANTHROPIC_API_KEY"}


class ScriptedCLI(Transport):
    """Stands in for the Claude Code CLI: on the user's message it asks
    can_use_tool about a move_money call, then ends the turn."""

    def __init__(self, tool_name: str, tool_input: dict[str, Any]) -> None:
        self.tool_name = tool_name
        self.tool_input = tool_input
        self.outbox: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self.permission_answers: list[dict[str, Any]] = []

    async def connect(self) -> None:
        return None

    async def write(self, data: str) -> None:
        for line in data.splitlines():
            msg = json.loads(line)
            if msg["type"] == "control_request":  # initialize, from the SDK
                await self.outbox.put(
                    {"type": "control_response", "response": {"subtype": "success", "request_id": msg["request_id"], "response": {}}}
                )
            elif msg["type"] == "user":
                await self.outbox.put(
                    {
                        "type": "control_request",
                        "request_id": "perm-1",
                        "request": {
                            "subtype": "can_use_tool",
                            "tool_name": self.tool_name,
                            "input": self.tool_input,
                            "tool_use_id": "toolu_1",
                        },
                    }
                )
            elif msg["type"] == "control_response":  # our answer to can_use_tool
                self.permission_answers.append(msg["response"])
                await self.outbox.put(
                    {
                        "type": "result",
                        "subtype": "success",
                        "duration_ms": 1,
                        "duration_api_ms": 1,
                        "is_error": False,
                        "num_turns": 1,
                        "session_id": "s",
                        "result": "done",
                        "usage": {"input_tokens": 1, "output_tokens": 1},
                    }
                )

    async def read_messages(self) -> AsyncIterator[dict[str, Any]]:
        while True:
            msg = await self.outbox.get()
            if msg is None:
                return
            yield msg

    async def close(self) -> None:
        await self.outbox.put(None)

    def is_ready(self) -> bool:
        return True

    async def end_input(self) -> None:
        return None


async def drive(gate: Gate, host: ToolHost, tool_input: dict[str, Any]) -> ScriptedCLI:
    o = build_options(
        model="m", max_turns=3, system_prompt="t", server=build_server(host), can_use_tool=make_can_use_tool(gate), cwd="/tmp"
    )
    cli = ScriptedCLI("mcp__money__move_money", tool_input)
    async with ClaudeSDKClient(options=o, transport=cli) as client:
        await client.query("move money")
        async for m in client.receive_response():
            if isinstance(m, ResultMessage):
                break
    return cli


async def test_scripted_write_call_reaches_can_use_tool_and_the_policy(ctx: ToolContext, recorder: TraceRecorder, today: dt.date) -> None:
    gate = make_gate(ctx, recorder, "approved")
    # The model asks to send all savings to someone else's account.
    cli = await asyncio.wait_for(
        drive(
            gate,
            ToolHost(ctx, recorder),
            {"from_account": "sav", "to_account": "contact_riley", "amount_usd": 3800, "date": today.isoformat()},
        ),
        timeout=20,
    )
    [answer] = cli.permission_answers
    assert answer["response"]["behavior"] == "deny"
    assert "own_accounts" in answer["response"]["message"]
    assert gate.outcomes == ["policy_denied"]


@pytest.mark.parametrize(("decision", "behavior"), [("approved", "allow"), ("declined", "deny")])
async def test_scripted_safe_call_waits_for_the_person(
    ctx: ToolContext, recorder: TraceRecorder, today: dt.date, decision: str, behavior: str
) -> None:
    gate = make_gate(ctx, recorder, decision)
    cli = await asyncio.wait_for(
        drive(gate, ToolHost(ctx, recorder), {"from_account": "sav", "to_account": "chk", "amount_usd": 400, "date": today.isoformat()}),
        timeout=20,
    )
    [answer] = cli.permission_answers
    assert answer["response"]["behavior"] == behavior
    assert gate.outcomes == [decision]
