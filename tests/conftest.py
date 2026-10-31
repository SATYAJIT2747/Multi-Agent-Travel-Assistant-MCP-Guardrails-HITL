import json
import os
import sys
from pathlib import Path

import pytest

# Dummy key so the Gemini client can be constructed in CI. Tests never call it:
# backend.llm is replaced with FakeLLM below.
os.environ.setdefault("GOOGLE_API_KEY", "test-key")
# load_dotenv() does not override existing vars, so this keeps fake test runs
# out of the LangSmith dashboard even when .env enables tracing.
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from langchain_core.messages import AIMessage  # noqa: E402
from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402

import backend  # noqa: E402


ALL_AGENTS_JSON = json.dumps(
    {
        "selected_agents": [
            "flight_agent",
            "hotel_agent",
            "weather_agent",
            "budget_agent",
            "itinerary_agent",
        ],
        "trip_constraints": {"destination": "Paris", "duration": "5 days"},
        "reasoning": "Full trip plan requested.",
    }
)

ALLOWED_JSON = '{"allowed": true, "reason": ""}'


class FakeLLM:
    """Stands in for Gemini. Answers depend on the agent's system prompt.

    `guardrail` and `supervisor` can be a string (returned as the reply) or an
    Exception (raised), to exercise the fallback paths.
    """

    def __init__(self, guardrail=ALLOWED_JSON, supervisor=ALL_AGENTS_JSON):
        self.guardrail = guardrail
        self.supervisor = supervisor
        self.calls = []  # (system_prompt, user_prompt)

    def _reply(self, value):
        if isinstance(value, Exception):
            raise value
        # Gemini (langchain-google-genai 4.x) returns a list of content blocks,
        # not a plain string; mirror that so tests catch str(content) bugs.
        return AIMessage(content=[{"type": "text", "text": value, "extras": {"signature": "x"}}])

    def invoke(self, messages):
        system = messages[0].content
        user = messages[-1].content
        self.calls.append((system, user))

        if "input guardrail" in system:
            return self._reply(self.guardrail)
        if "route work" in system:
            return self._reply(self.supervisor)
        if "expert travel planner" in system:
            return self._reply("DRAFT ITINERARY")
        if "booking assistant" in system:
            return self._reply("FINAL PLAN")
        return self._reply(f"specialist output ({system})")

    def prompts_for(self, system_fragment):
        return [user for system, user in self.calls if system_fragment in system]


@pytest.fixture
def fake_llm(monkeypatch):
    llm = FakeLLM()
    monkeypatch.setattr(backend, "llm", llm)
    return llm


@pytest.fixture
def tool_calls(monkeypatch):
    """Replace every MCP call with a fake and record which ones ran."""
    calls = []

    async def fake_tavily(query):
        calls.append(("tavily", query))
        return "Hotel A, Hotel B"

    async def fake_aviation(tool_name, tool_args=None):
        calls.append(("aviation", tool_name))
        return f"{tool_name} data"

    async def fake_weather(city):
        calls.append(("weather", city))
        return "Sunny, 22C"

    async def fake_forecast(city):
        calls.append(("forecast", city))
        return "Sunny all week"

    monkeypatch.setattr(backend, "tavily_mcp_search", fake_tavily)
    monkeypatch.setattr(backend, "aviation_mcp_call", fake_aviation)
    monkeypatch.setattr(backend, "weather_mcp_search", fake_weather)
    monkeypatch.setattr(backend, "forecast_mcp_search", fake_forecast)
    monkeypatch.setattr(backend, "extract_destination", lambda query: "Paris")
    return calls


@pytest.fixture
def memory_graph(monkeypatch):
    """Use the real graph with an in-memory checkpointer instead of Postgres."""
    graph = backend.build_graph().compile(checkpointer=InMemorySaver())
    monkeypatch.setattr(backend, "_travel_graph", graph)
    return graph
