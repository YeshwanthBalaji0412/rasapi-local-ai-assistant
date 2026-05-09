"""
Deterministic intent router (Phase 1, extended in Phase 3).

Maps a natural-language query to a known intent using simple keyword
matching. Each intent maps to exactly one of:
  - a safe allowlisted command, executed via command_runner, or
  - a built-in handler that takes (query, request_id) and returns text.

This is intentionally NOT an LLM. The LLM (Phase 2) only runs when the
router returns 'fallback' AND the operator has opted in.

Why keyword-based:
  - Fully deterministic, easy to audit, no model dependency
  - Demonstrates the security boundary in isolation
  - Memory writes go through this same path, so they remain explainable
    and never depend on a probabilistic model
"""

from dataclasses import dataclass
from typing import Callable

from briefing import generator as briefing_generator
from core import memory, tasks
from core.command_runner import run_command
from integrations import home_assistant as ha
from integrations import slack


# Handler signature: takes the original query and request_id, returns
# user-facing text. Greeting/help handlers ignore both args.
HandlerFn = Callable[[str, str], str]


@dataclass(frozen=True)
class Intent:
    name: str
    description: str
    keywords: tuple[str, ...]
    command: tuple[str, list[str]] | None = None
    handler: HandlerFn | None = None


def _greeting(_query: str, _request_id: str) -> str:
    return (
        "Hello. I'm RasaPi, your local AI assistant. Ask me about system "
        "status, save a memory, take a note, or manage tasks."
    )


def _help(_query: str, _request_id: str) -> str:
    lines = ["I can help with:"]
    for intent in INTENTS:
        if intent.name == "fallback":
            continue
        lines.append(f"  - {intent.description}")
    return "\n".join(lines)


# Order matters: the first intent whose keyword appears in the query wins.
# Memory/notes/tasks intents are listed before broader ones so phrases like
# "show memory" reach list_memory before any system-info intent.
INTENTS: tuple[Intent, ...] = (
    # ── Phase 3 — local memory ───────────────────────────────────────────
    Intent(
        name="save_memory",
        description="Remember something for later (\"remember that ...\")",
        keywords=(
            "remember that ",
            "remember to remember that ",
            "please remember that ",
            "remember ",
        ),
        handler=memory.save_memory_from_query,
    ),
    Intent(
        name="list_memory",
        description="List things you've asked me to remember",
        keywords=(
            "what do you remember",
            "what did i ask you to remember",
            "show memory",
            "list memory",
            "what do i remember",
        ),
        handler=memory.list_memory_text,
    ),
    # ── Phase 3 — notes ──────────────────────────────────────────────────
    Intent(
        name="save_note",
        description="Save a note (\"save note ...\", \"add note ...\")",
        keywords=("save note ", "take a note ", "note: ", "add note "),
        handler=memory.save_note_from_query,
    ),
    Intent(
        name="list_notes",
        description="Show your notes",
        keywords=("show notes", "list notes", "my notes"),
        handler=memory.list_notes_text,
    ),
    # ── Phase 3 — tasks ──────────────────────────────────────────────────
    Intent(
        name="complete_task",
        description="Mark a task as done (\"mark task 1 as done\")",
        keywords=(
            "mark task ",
            "complete task ",
            "finish task ",
            "task done",
        ),
        handler=tasks.complete_task_from_query,
    ),
    Intent(
        name="add_task",
        description="Add a task (\"add task ...\")",
        keywords=("add task ", "new task ", "create task ", "task: "),
        handler=tasks.add_task_from_query,
    ),
    Intent(
        name="list_tasks",
        description="Show your open tasks",
        keywords=("show tasks", "list tasks", "my tasks", "open tasks"),
        handler=tasks.list_tasks_text,
    ),
    # ── Phase 9 — integrations (Slack + Home Assistant) ─────────────────
    Intent(
        name="slack_send_test",
        description="Send a test notification to Slack",
        keywords=("send test slack", "test slack", "slack test"),
        handler=slack.handle_send_test,
    ),
    Intent(
        name="slack_send_briefing",
        description="Send the daily or per-category briefing to Slack",
        keywords=(
            "send today's briefing to slack",
            "send todays briefing to slack",
            "send daily briefing to slack",
            "send briefing to slack",
            "send ai briefing to slack",
            "send world news to slack",
            "send tech news to slack",
            "send developer news to slack",
            "send hacker news to slack",
            "send weather to slack",
            "send immigration to slack",
            "send to slack",
        ),
        handler=slack.handle_send_briefing,
    ),
    Intent(
        name="ha_status",
        description="Check Home Assistant reachability",
        keywords=("home assistant status", "is home assistant up", "ha status"),
        handler=ha.handle_ha_status,
    ),
    Intent(
        name="ha_turn_on",
        description="Turn on an allowed Home Assistant light or switch",
        keywords=("turn on ",),
        handler=ha.handle_ha_turn_on,
    ),
    Intent(
        name="ha_turn_off",
        description="Turn off an allowed Home Assistant light or switch",
        keywords=("turn off ",),
        handler=ha.handle_ha_turn_off,
    ),

    # ── Phase 4 — daily briefing ─────────────────────────────────────────
    Intent(
        name="immigration_briefing",
        description="Show official immigration / F-1 / OPT updates",
        keywords=(
            "immigration update",
            "immigration news",
            "f1 opt",
            "f-1 opt",
            "uscis",
            "opt update",
        ),
        handler=briefing_generator.handle_immigration_briefing,
    ),
    Intent(
        name="weather_briefing",
        description="Local weather briefing",
        keywords=("boston weather", "weather briefing", "weather today", "weather"),
        handler=briefing_generator.handle_weather_briefing,
    ),
    Intent(
        name="ai_briefing",
        description="Recent AI news",
        keywords=("ai news", "ai briefing", "ml news", "machine learning news"),
        handler=briefing_generator.handle_ai_briefing,
    ),
    Intent(
        name="developer_briefing",
        description="Developer / Hacker News briefing",
        keywords=("developer news", "hacker news", "dev news", "engineering news"),
        handler=briefing_generator.handle_developer_briefing,
    ),
    Intent(
        name="tech_briefing",
        description="General tech news",
        keywords=("tech news", "technology news", "tech briefing"),
        handler=briefing_generator.handle_tech_briefing,
    ),
    Intent(
        name="world_briefing",
        description="World news headlines",
        keywords=("world news", "world briefing", "global news"),
        handler=briefing_generator.handle_world_briefing,
    ),
    Intent(
        name="daily_briefing",
        description="Full daily briefing across all categories",
        keywords=(
            "daily briefing",
            "what's happening today",
            "what is happening today",
            "today's briefing",
            "morning briefing",
        ),
        handler=briefing_generator.handle_daily_briefing,
    ),
    # ── Phase 1 — system info ────────────────────────────────────────────
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
        name="memory_usage",
        description="Report system RAM usage",
        keywords=("ram", "free memory", "memory usage", "free ram"),
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
    # ── Phase 1 — built-ins ──────────────────────────────────────────────
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
    # Pad with a trailing space so keywords ending in " " (e.g. "remember ")
    # still match when the user typed exactly that prefix with no payload.
    q = query.lower().strip() + " "

    for intent in INTENTS:
        if any(kw in q for kw in intent.keywords):
            if intent.handler is not None:
                return RouteResult(
                    intent=intent.name,
                    response=intent.handler(query, request_id),
                )
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
