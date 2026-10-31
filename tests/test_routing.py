import pytest

from backend import _json_from_llm, route_after_agent, route_from_supervisor


def test_blocked_request_routes_to_guardrail_message():
    state = {"guardrail_allowed": False, "selected_agents": ["flight_agent"]}
    assert route_from_supervisor(state) == "guardrail_blocked"


def test_selected_agents_run_in_fixed_order():
    # The supervisor listed weather before flight; AGENT_ORDER still wins.
    state = {
        "guardrail_allowed": True,
        "selected_agents": ["weather_agent", "flight_agent", "itinerary_agent"],
    }

    assert route_from_supervisor(state) == "flight_agent"
    assert route_after_agent("flight_agent")(state) == "weather_agent"
    assert route_after_agent("weather_agent")(state) == "itinerary_agent"


def test_unselected_agents_are_skipped():
    state = {
        "guardrail_allowed": True,
        "selected_agents": ["hotel_agent", "budget_agent", "itinerary_agent"],
    }

    assert route_from_supervisor(state) == "hotel_agent"
    assert route_after_agent("hotel_agent")(state) == "budget_agent"


def test_no_specialists_goes_straight_to_itinerary():
    state = {"guardrail_allowed": True, "selected_agents": []}
    assert route_from_supervisor(state) == "itinerary_agent"


def test_json_from_llm_handles_code_fences_and_extra_text():
    text = 'Sure! Here it is:\n```json\n{"allowed": false, "reason": "off-topic"}\n```'
    assert _json_from_llm(text) == {"allowed": False, "reason": "off-topic"}


def test_json_from_llm_rejects_non_json():
    with pytest.raises(ValueError):
        _json_from_llm("I cannot answer that.")
