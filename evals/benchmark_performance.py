"""Measure the two performance fixes, old design vs new design.

1. Parallel research agents: the old sequential chain vs the current graph.
2. Plan endpoints: the old `async def` endpoint vs the current `def` endpoint,
   with several travellers requesting plans at the same time.

Gemini and the MCP tools are replaced by sleeps with typical latencies, so the
results are repeatable and free. No API keys, MCP servers or database needed.

Usage:
    uv run python evals/benchmark_performance.py
"""
import asyncio
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GOOGLE_API_KEY", "benchmark")
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402
from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402
from langgraph.graph import END, START, StateGraph  # noqa: E402

import app as app_module  # noqa: E402
import backend  # noqa: E402

LLM_SECONDS = 1.5   # one Gemini call
MCP_SECONDS = 1.0   # one MCP tool call
PLAN_SECONDS = 3.0  # one plan request in the endpoint benchmark (shortened)
CONCURRENT_USERS = 5

RESULTS_DIR = Path(__file__).with_name("results")
ALL_AGENTS = json.dumps(
    {
        "selected_agents": backend.AGENT_ORDER,
        "trip_constraints": {"destination": "Paris"},
        "reasoning": "Full trip plan.",
    }
)


# ---------------------------------------------------------------------------
# Simulated Gemini and MCP latency
# ---------------------------------------------------------------------------
class SlowLLM:
    def invoke(self, messages):
        time.sleep(LLM_SECONDS)
        system = messages[0].content
        if "input guardrail" in system:
            return AIMessage(content='{"allowed": true, "reason": ""}')
        if "route work" in system:
            return AIMessage(content=ALL_AGENTS)
        return AIMessage(content="specialist output")


async def slow_mcp(*args, **kwargs):
    await asyncio.sleep(MCP_SECONDS)
    return "tool data"


def slow_extract_destination(query):
    time.sleep(LLM_SECONDS)
    return "Paris"


backend.llm = SlowLLM()
backend.tavily_mcp_search = slow_mcp
backend.aviation_mcp_call = slow_mcp
backend.weather_mcp_search = slow_mcp
backend.forecast_mcp_search = slow_mcp
backend.extract_destination = slow_extract_destination


# ---------------------------------------------------------------------------
# 1. Sequential chain (old) vs parallel research (current)
# ---------------------------------------------------------------------------
def build_sequential_graph():
    """The previous design: every selected agent waits for the one before it."""
    graph = StateGraph(backend.TravelState)
    chain = [
        ("supervisor", backend.supervisor_agent),
        ("flight_agent", backend.flight_agent),
        ("hotel_agent", backend.hotel_agent),
        ("weather_agent", backend.weather_agent),
        ("budget_agent", backend.budget_agent),
        ("itinerary_agent", backend.itinerary_agent),
        ("human_approval", backend.human_approval_agent),
    ]
    for name, fn in chain:
        graph.add_node(name, fn)
    graph.add_edge(START, chain[0][0])
    for (a, _), (b, _) in zip(chain, chain[1:]):
        graph.add_edge(a, b)
    graph.add_edge(chain[-1][0], END)
    return graph


def time_draft(graph_builder, label):
    graph = graph_builder().compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": label}}
    start = time.perf_counter()
    graph.invoke({"user_query": "Plan 5 days in Paris from Dhaka", "llm_calls": None}, config)
    return time.perf_counter() - start


# ---------------------------------------------------------------------------
# 2. async def endpoint (old) vs def endpoint (current app.py)
# ---------------------------------------------------------------------------
def slow_plan(user_input, thread_id=None):
    time.sleep(PLAN_SECONDS)  # blocking work, like the LangGraph run
    return {"thread_id": "t", "answer": "plan"}


def build_old_app():
    """Same shape as the previous app.py: blocking work inside `async def`."""
    old = FastAPI()

    @old.post("/api/travel")
    async def travel_planner(body: dict):
        return slow_plan(body["message"])

    @old.get("/health")
    async def health():
        return {"status": "ok"}

    return old


def time_concurrent_users(fastapi_app):
    with TestClient(fastapi_app) as client, ThreadPoolExecutor(CONCURRENT_USERS) as pool:
        start = time.perf_counter()
        plans = [
            pool.submit(client.post, "/api/travel", json={"message": f"trip {i}"})
            for i in range(CONCURRENT_USERS)
        ]
        time.sleep(0.2)  # let the plans start

        health_start = time.perf_counter()
        client.get("/health")
        health_seconds = time.perf_counter() - health_start

        for plan in plans:
            plan.result()
        total_seconds = time.perf_counter() - start

    return total_seconds, health_seconds


def main():
    print("Running... (about a minute)")

    seq = time_draft(build_sequential_graph, "sequential")
    par = time_draft(backend.build_graph, "parallel")

    app_module.run_travel_agent = slow_plan
    old_total, old_health = time_concurrent_users(build_old_app())
    new_total, new_health = time_concurrent_users(app_module.app)

    lines = [
        f"Performance benchmark - {datetime.now():%Y-%m-%d %H:%M}",
        f"Simulated latency: Gemini call {LLM_SECONDS}s, MCP call {MCP_SECONDS}s",
        "",
        "1. TIME TO DRAFT ITINERARY (all specialists selected)",
        f"   Sequential chain (old):     {seq:5.1f}s",
        f"   Parallel research (new):    {par:5.1f}s",
        f"   -> {100 * (seq - par) / seq:.0f}% faster",
        "",
        f"2. {CONCURRENT_USERS} TRAVELLERS REQUEST A PLAN AT THE SAME TIME ({PLAN_SECONDS:.0f}s per plan)",
        f"   All plans done, async def (old): {old_total:5.1f}s",
        f"   All plans done, def (new):       {new_total:5.1f}s",
        f"   /health while plans run, old:    {old_health:5.2f}s",
        f"   /health while plans run, new:    {new_health:5.2f}s",
        f"   -> plans finish {old_total / new_total:.1f}x sooner; the server stays responsive",
    ]
    report = "\n".join(lines)
    print("\n" + report)

    RESULTS_DIR.mkdir(exist_ok=True)
    (RESULTS_DIR / "performance_benchmark.txt").write_text(report + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
