"""End-to-end runs of the real LangGraph flow with fake LLM, tools and checkpointer."""
import json

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
