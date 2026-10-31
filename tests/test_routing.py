import pytest

from backend import _json_from_llm, route_after_research, route_from_supervisor


def test_blocked_request_routes_to_guardrail_message():
    state = {"guardrail_allowed": False, "selected_agents": ["flight_agent"]}
    assert route_from_supervisor(state) == "guardrail_blocked"


def test_selected_research_agents_are_dispatched_together():
    # A list means LangGraph runs these nodes in parallel in the same step.
    state = {
        "guardrail_allowed": True,
        "selected_agents": ["weather_agent", "flight_agent", "itinerary_agent"],
    }
    assert route_from_supervisor(state) == ["flight_agent", "weather_agent"]


def test_budget_runs_after_research_only_when_selected():
    with_budget = {"selected_agents": ["hotel_agent", "budget_agent", "itinerary_agent"]}
    without_budget = {"selected_agents": ["hotel_agent", "itinerary_agent"]}

    assert route_after_research(with_budget) == "budget_agent"
    assert route_after_research(without_budget) == "itinerary_agent"


def test_budget_only_request_skips_research():
    state = {"guardrail_allowed": True, "selected_agents": ["budget_agent", "itinerary_agent"]}
    assert route_from_supervisor(state) == "budget_agent"


def test_no_specialists_goes_straight_to_itinerary():
    state = {"guardrail_allowed": True, "selected_agents": []}
    assert route_from_supervisor(state) == "itinerary_agent"


def test_json_from_llm_handles_code_fences_and_extra_text():
    text = 'Sure! Here it is:\n```json\n{"allowed": false, "reason": "off-topic"}\n```'
    assert _json_from_llm(text) == {"allowed": False, "reason": "off-topic"}


def test_json_from_llm_rejects_non_json():
    with pytest.raises(ValueError):
        _json_from_llm("I cannot answer that.")
