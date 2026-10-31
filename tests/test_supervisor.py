import json

from backend import AGENT_ORDER, supervisor_agent


def run_supervisor(fake_llm, query="Plan a 5 day trip to Paris"):
    return supervisor_agent({"user_query": query, "llm_calls": 0})


def test_supervisor_filters_orders_and_completes_agent_list(fake_llm):
    fake_llm.supervisor = json.dumps(
        {
            "selected_agents": ["budget_agent", "made_up_agent", "flight_agent"],
            "trip_constraints": {"destination": "Paris", "budget": "$1500"},
            "reasoning": "Flights and budget only.",
        }
    )

    result = run_supervisor(fake_llm)

    # Unknown agent dropped, fixed order applied, itinerary always added.
    assert result["selected_agents"] == ["flight_agent", "budget_agent", "itinerary_agent"]
    assert result["trip_constraints"]["destination"] == "Paris"
    assert result["trip_constraints"]["budget"] == "$1500"
    # Missing constraint fields keep their empty defaults.
    assert result["trip_constraints"]["origin"] == ""
    assert result["llm_calls"] == 2


def test_supervisor_bad_json_falls_back_to_all_agents(fake_llm):
    fake_llm.supervisor = "Flights and hotels, probably."

    result = run_supervisor(fake_llm)

    assert result["guardrail_allowed"] is True
    assert result["selected_agents"] == AGENT_ORDER
    assert "fallback" in result["supervisor_reasoning"]


def test_guardrail_error_fails_open(fake_llm):
    fake_llm.guardrail = RuntimeError("Gemini timeout")

    result = run_supervisor(fake_llm)

    assert result["guardrail_allowed"] is True
    assert "fallback" in result["guardrail_reason"]


def test_guardrail_block_skips_supervisor_routing(fake_llm):
    fake_llm.guardrail = '{"allowed": false, "reason": "Not a travel request."}'

    result = run_supervisor(fake_llm, query="Write my chemistry homework")

    assert result["guardrail_allowed"] is False
    assert result["selected_agents"] == []
    assert result["final_response"] == "Not a travel request."
    # Only the guardrail call was made; the routing call never ran.
    assert len(fake_llm.calls) == 1
