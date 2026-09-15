"""Integration test for SPEC.md acceptance scenario 1, run against a live
Agent Relay server and its real database over real HTTP -- not the ASGI
TestClient used in test_agent_relay.py.

Requires a running server (e.g. `uv run uvicorn main:app --port 8000`).
Point RELAY_TEST_BASE_URL at a different instance if needed.
"""

from __future__ import annotations

import os

import httpx
import pytest

BASE_URL = os.environ.get("RELAY_TEST_BASE_URL", "http://127.0.0.1:8000")


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        try:
            client.get("/health").raise_for_status()
        except httpx.HTTPError as exc:
            pytest.skip(f"Agent Relay server not reachable at {BASE_URL}: {exc}")
        yield client


def register(client: httpx.Client, name: str) -> tuple[str, dict[str, str]]:
    response = client.post("/api/v1/agents", json={"name": name})
    assert response.status_code == 201
    data = response.json()
    return data["agent_id"], {"Authorization": f"Bearer {data['token']}"}


def test_scenario_1_two_agents_exchange_a_task_and_its_result(client: httpx.Client):
    sender_id, sender_headers = register(client, "integration-sender")
    recipient_id, recipient_headers = register(client, "integration-uppercase")

    sent = client.post(
        "/api/v1/tasks",
        headers=sender_headers,
        json={"to": recipient_id, "input": "integration: uppercase me"},
    )
    assert sent.status_code == 201
    task = sent.json()
    assert task["status"] == "queued"
    task_id = task["task_id"]

    claim = client.post(
        "/api/v1/tasks/claim",
        headers=recipient_headers,
        json={"worker_id": "integration-worker", "wait_seconds": 0},
    )
    assert claim.status_code == 200
    claim_data = claim.json()
    assert claim_data["task_id"] == task_id
    assert claim_data["from"] == sender_id

    output = claim_data["input"].upper()
    complete = client.post(
        f"/api/v1/tasks/{task_id}/complete",
        headers=recipient_headers,
        json={"claim_token": claim_data["claim_token"], "output": output},
    )
    assert complete.status_code == 200
    assert complete.json()["status"] == "completed"

    result = client.get(f"/api/v1/tasks/{task_id}", headers=sender_headers)
    assert result.status_code == 200
    result_data = result.json()
    assert result_data["status"] == "completed"
    assert result_data["output"] == "INTEGRATION: UPPERCASE ME"
    assert result_data["error"] is None
