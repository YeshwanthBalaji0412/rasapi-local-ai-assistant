"""
Deterministic intent router (Phase 1).

Maps a natural-language query to a known intent using simple keyword
matching. Each intent maps to either:
  - a safe allowlisted command, executed via command_runner, or
  - a built-in handler (e.g. greeting), which returns a static string.

This is intentionally NOT an LLM. Phase 2 will add an LLM layer that
proposes an intent and falls back to this router when uncertain.

Why keyword-based for Phase 1:
  - Fully deterministic, easy to audit, no model dependency
  - Demonstrates the security boundary in isolation
  - Works on a Pi with no model loaded
"""

from dataclasses import dataclass
from typing import Callable

from core.command_runner import run_command


@dataclass(frozen=True)
class Intent:
    name: str
    description: str
    keywords: tuple[str, ...]
    # Either a (command, args) tuple to execute, or a builtin handler
    command: tuple[str, list[str]] | None = None
    handler: Callable[[], str] | None = None


def _greeting() -> str:
    return "Hello. I'm RasaPi, your local AI assistant. Ask me about system status, time, or device info."


def _help() -> str:
    lines = ["I can help with:"]
    for intent in INTENTS:
        if intent.name == "fallback":
            continue
        lines.append(f"  - {intent.description}")
    return "\n".join(lines)


INTENTS: tuple[Intent, ...] = (
    Intent(
        name="time",
        description="Tell the current date and time",
        keywords=("time", "date", "what day", "what's today"),
        command=("date", []),
    ),
    Intent(
        name="uptime",
        description="Show how long the device has been running",
        keywords=("uptime", "how long", "been running", "been up"),
        command=("uptime", []),
    ),
    Intent(
        name="cpu_temp",
        description="Read the CPU temperature (Pi only)",
        keywords=("temperature", "cpu temp", "how hot", "thermal"),
        command=("vcgencmd", ["measure_temp"]),
    ),
    Intent(
        name="disk",
        description="Report disk space usage",
        keywords=("disk", "storage", "space left", "free space"),
        command=("df", ["-h"]),
    ),
    Intent(
        name="memory",
        description="Report memory usage",
        keywords=("memory", "ram", "free memory"),
        command=("free", ["-h"]),
    ),
    Intent(
        name="hostname",
        description="Show the device hostname",
        keywords=("hostname", "device name", "machine name"),
        command=("hostname", []),
    ),
    Intent(
        name="system",
        description="Show system / kernel info",
        keywords=("system info", "kernel", "os version", "uname"),
        command=("uname", ["-a"]),
    ),
    Intent(
        name="greeting",
        description="Greet the assistant",
        keywords=("hello", "hi ", "hey", "good morning", "good evening"),
        handler=_greeting,
    ),
    Intent(
        name="help",
        description="List what the assistant can do",
        keywords=("help", "what can you do", "commands", "capabilities"),
        handler=_help,
    ),
)


@dataclass
class RouteResult:
    intent: str
    response: str


def route(query: str, request_id: str) -> RouteResult:
    q = query.lower().strip()

    for intent in INTENTS:
        if any(kw in q for kw in intent.keywords):
            if intent.handler is not None:
                return RouteResult(intent=intent.name, response=intent.handler())
            assert intent.command is not None
            cmd, args = intent.command
            output = run_command(request_id=request_id, command=cmd, args=args)
            return RouteResult(intent=intent.name, response=output)

    return RouteResult(
        intent="fallback",
        response=(
            "I don't understand that yet. Phase 1 only supports a fixed set of "
            "intents — try 'help' to see them. Free-form understanding arrives in Phase 2."
        ),
    )


def list_intents() -> list[dict]:
    return [
        {"name": i.name, "description": i.description, "keywords": list(i.keywords)}
        for i in INTENTS
        if i.name != "fallback"
    ]
