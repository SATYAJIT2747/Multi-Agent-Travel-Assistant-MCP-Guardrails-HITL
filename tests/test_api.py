import pytest
from fastapi.testclient import TestClient

import app as app_module


@pytest.fixture
def client():
    return TestClient(app_module.app)


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
