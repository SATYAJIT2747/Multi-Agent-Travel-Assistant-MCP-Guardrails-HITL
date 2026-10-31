"""End-to-end runs of the real LangGraph flow with fake LLM, tools and checkpointer."""
import json
import threading

from backend import resume_travel_agent, run_travel_agent

QUERY = "Plan a 5 day trip to Paris from Dhaka under $1500"


def test_travel_request_pauses_for_approval(fake_llm, tool_calls, memory_graph):
    result = run_travel_agent(QUERY, thread_id="t-pause")

    assert result["requires_approval"] is True
    assert result["answer"] == "DRAFT ITINERARY"
    assert result["thread_id"] == "t-pause"
    # No final plan is written before a human reviews the draft.
    assert fake_llm.prompts_for("booking assistant") == []


def test_approval_resumes_thread_and_produces_final_plan(fake_llm, tool_calls, memory_graph):
    run_travel_agent(QUERY, thread_id="t-approve")
    result = resume_travel_agent("t-approve", approved=True)

    assert result["requires_approval"] is False
    assert result["approved"] is True
    assert result["answer"] == "FINAL PLAN"
    # State from the first request survived the pause via the checkpointer.
    assert result["hotel_results"] == "Hotel A, Hotel B"
    [final_prompt] = fake_llm.prompts_for("booking assistant")
    assert "The user approved the draft" in final_prompt


def test_revision_feedback_reaches_final_agent(fake_llm, tool_calls, memory_graph):
    run_travel_agent(QUERY, thread_id="t-revise")
    result = resume_travel_agent("t-revise", approved=False, feedback="Make it cheaper")

    assert result["approved"] is False
    assert result["human_feedback"] == "Make it cheaper"
    [final_prompt] = fake_llm.prompts_for("booking assistant")
    assert "Make it cheaper" in final_prompt


def test_blocked_request_never_calls_tools_or_specialists(fake_llm, tool_calls, memory_graph):
    fake_llm.guardrail = '{"allowed": false, "reason": "Only travel requests are supported."}'

    result = run_travel_agent("How do I pick a lock?", thread_id="t-blocked")

    assert result["requires_approval"] is False
    assert result["guardrail_allowed"] is False
    assert result["answer"] == "Only travel requests are supported."
    assert tool_calls == []
    assert len(fake_llm.calls) == 1


def test_only_selected_specialists_run(fake_llm, tool_calls, memory_graph):
    fake_llm.supervisor = json.dumps(
        {
            "selected_agents": ["weather_agent", "itinerary_agent"],
            "trip_constraints": {"destination": "Paris"},
            "reasoning": "Weather question only.",
        }
    )

    result = run_travel_agent("What's the weather in Paris next week?", thread_id="t-weather")

    assert result["selected_agents"] == ["weather_agent", "itinerary_agent"]
    assert {name for name, _ in tool_calls} == {"weather", "forecast"}
    assert result["flight_results"] == ""
    assert result["hotel_results"] == ""


def test_failed_mcp_server_still_produces_draft(fake_llm, tool_calls, memory_graph, monkeypatch):
    import backend

    async def broken_tavily(query):
        raise ConnectionError("Tavily MCP unreachable")

    monkeypatch.setattr(backend, "tavily_mcp_search", broken_tavily)

    result = run_travel_agent(QUERY, thread_id="t-mcp-down")

    assert result["requires_approval"] is True
    assert result["answer"] == "DRAFT ITINERARY"
    assert "temporarily unavailable" in result["hotel_results"]


def test_research_agents_run_in_parallel(fake_llm, tool_calls, memory_graph, monkeypatch):
    import backend

    # Opens only when flight, hotel and weather are all inside a tool call at
    # the same time. Run one after another, the first one would time out.
    barrier = threading.Barrier(3, timeout=5)

    async def flight_tool(tool_name, tool_args=None):
        if tool_name == "list_airports":
            barrier.wait()
        return f"{tool_name} data"

    async def hotel_tool(query):
        barrier.wait()
        return "Hotel A, Hotel B"

    async def weather_tool(city):
        barrier.wait()
        return "Sunny, 22C"

    monkeypatch.setattr(backend, "aviation_mcp_call", flight_tool)
    monkeypatch.setattr(backend, "tavily_mcp_search", hotel_tool)
    monkeypatch.setattr(backend, "weather_mcp_search", weather_tool)

    result = run_travel_agent(QUERY, thread_id="t-parallel")

    # A broken barrier would have pushed the agents into their fallback text.
    assert "unavailable" not in result["flight_results"]
    assert result["hotel_results"] == "Hotel A, Hotel B"
    assert "Sunny, 22C" in result["weather_results"]

    # Fan-in: budget runs once, after all three, and sees every result.
    [budget_prompt] = fake_llm.prompts_for("budget analyst")
    assert "Hotel A, Hotel B" in budget_prompt
    assert "Sunny, 22C" in budget_prompt
    assert len(fake_llm.prompts_for("expert travel planner")) == 1


def test_llm_calls_are_counted_per_run(fake_llm, tool_calls, memory_graph):
    # guardrail + supervisor + flight + weather + budget + itinerary = 6
    # (hotel makes no LLM call; final runs after approval).
    first = run_travel_agent(QUERY, thread_id="t-count")
    assert first["llm_calls"] == 6

    assert resume_travel_agent("t-count", approved=True)["llm_calls"] == 7

    # A new plan on the same thread starts counting from zero again.
    assert run_travel_agent(QUERY, thread_id="t-count")["llm_calls"] == 6


def test_parallel_research_takes_as_long_as_the_slowest_agent(fake_llm, tool_calls, memory_graph, monkeypatch):
    import asyncio
    import time

    import backend

    async def slow_tool(*args, **kwargs):
        await asyncio.sleep(0.5)
        return "tool data"

    for name in ("aviation_mcp_call", "tavily_mcp_search", "weather_mcp_search", "forecast_mcp_search"):
        monkeypatch.setattr(backend, name, slow_tool)

    # Flight 2 calls (1.0s) + hotel 1 call (0.5s) + weather 2 calls (1.0s):
    # 2.5s one after another, about 1.0s (the slowest agent) in parallel.
    start = time.perf_counter()
    run_travel_agent(QUERY, thread_id="t-timing")
    elapsed = time.perf_counter() - start

    assert elapsed < 2.0, f"research took {elapsed:.2f}s; agents are not running in parallel"
