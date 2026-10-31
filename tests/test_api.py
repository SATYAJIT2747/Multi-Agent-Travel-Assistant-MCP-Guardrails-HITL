import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

import app as app_module


@pytest.fixture
def client():
    # The context manager keeps one event loop for all requests, like Uvicorn,
    # so a request that blocks the loop also blocks the others.
    with TestClient(app_module.app) as test_client:
        yield test_client


def test_health(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_empty_message_is_rejected(client):
    response = client.post("/api/travel", json={"message": "   "})

    assert response.status_code == 400
    assert response.json()["success"] is False


def test_reject_without_feedback_is_rejected(client):
    response = client.post(
        "/api/travel/approve",
        json={"thread_id": "t-1", "approved": False, "feedback": ""},
    )

    assert response.status_code == 400


def test_full_http_flow_plan_then_approve(client, fake_llm, tool_calls, memory_graph):
    plan = client.post("/api/travel", json={"message": "5 days in Paris"}).json()

    assert plan["success"] is True
    assert plan["requires_approval"] is True
    assert plan["thread_id"].startswith("user_")

    final = client.post(
        "/api/travel/approve",
        json={"thread_id": plan["thread_id"], "approved": True},
    ).json()

    assert final["success"] is True
    assert final["answer"] == "FINAL PLAN"


def test_slow_plan_does_not_block_other_requests(client, monkeypatch):
    started = threading.Event()
    finished = threading.Event()

    def slow_plan(user_input, thread_id=None):
        started.set()
        finished.wait(timeout=3)  # a 10-30 s Gemini/MCP run, shortened
        finished.set()
        return {"thread_id": "t-slow", "answer": "done"}

    monkeypatch.setattr(app_module, "run_travel_agent", slow_plan)

    with ThreadPoolExecutor(max_workers=1) as pool:
        plan = pool.submit(client.post, "/api/travel", json={"message": "5 days in Paris"})
        assert started.wait(timeout=3)

        health = client.get("/health")
        # /health must answer while the plan is still running.
        plan_still_running = not finished.is_set()

        finished.set()
        assert plan.result().status_code == 200

    assert health.status_code == 200
    assert plan_still_running
