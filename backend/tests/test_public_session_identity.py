"""Public chat sessions must be bound to a signed visitor token."""

import logging

import pytest

from middleware.rate_limit import hash_log_identifier


def visitor_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def create_public_session(public_client, agent_id: str, visitor_id: str):
    response = await public_client.post(
        "/api/v1/chat",
        json={
            "agent_id": agent_id,
            "message": "Create a private visitor session",
            "visitor_id": visitor_id,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"]
    assert payload["visitor_token"]
    return payload["session_id"], payload["visitor_token"]


@pytest.mark.asyncio
async def test_public_history_requires_matching_visitor_token(
    public_client, default_agent_id
):
    session_id, token = await create_public_session(
        public_client, default_agent_id, "visitor_history_owner"
    )

    missing = await public_client.get(
        f"/api/v1/chat/messages?session_id={session_id}"
    )
    tampered = await public_client.get(
        f"/api/v1/chat/messages?session_id={session_id}",
        headers=visitor_headers(f"{token}tampered"),
    )
    allowed = await public_client.get(
        f"/api/v1/chat/messages?session_id={session_id}",
        headers=visitor_headers(token),
    )

    assert missing.status_code == 404
    assert tampered.status_code == 404
    assert allowed.status_code == 200
    assert allowed.json()


@pytest.mark.asyncio
async def test_public_chat_continuation_requires_matching_visitor_token(
    public_client, default_agent_id
):
    session_id, token = await create_public_session(
        public_client, default_agent_id, "visitor_chat_owner"
    )
    continuation = {
        "agent_id": default_agent_id,
        "message": "Continue my existing session",
        "session_id": session_id,
        "visitor_id": "visitor_chat_owner",
    }

    missing = await public_client.post("/api/v1/chat", json=continuation)
    allowed = await public_client.post(
        "/api/v1/chat", json=continuation, headers=visitor_headers(token)
    )

    assert missing.status_code == 404
    assert allowed.status_code == 200
    assert allowed.json()["session_id"] == session_id
    assert allowed.json()["visitor_token"]


@pytest.mark.asyncio
async def test_public_token_cannot_cross_sessions(public_client, default_agent_id):
    first_session, first_token = await create_public_session(
        public_client, default_agent_id, "visitor_first"
    )
    second_session, _ = await create_public_session(
        public_client, default_agent_id, "visitor_second"
    )

    response = await public_client.get(
        f"/api/v1/chat/messages?session_id={second_session}",
        headers=visitor_headers(first_token),
    )

    assert first_session != second_session
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_handoff_requires_matching_visitor_token(
    public_client, default_agent_id
):
    visitor_id = "visitor_handoff_owner"
    session_id, token = await create_public_session(
        public_client, default_agent_id, visitor_id
    )
    payload = {
        "agent_id": default_agent_id,
        "session_id": session_id,
        "visitor_id": visitor_id,
        "locale": "en-US",
    }

    missing = await public_client.post("/api/v1/chat/handoff", json=payload)
    allowed = await public_client.post(
        "/api/v1/chat/handoff", json=payload, headers=visitor_headers(token)
    )

    assert missing.status_code == 404
    assert allowed.status_code == 200
    assert allowed.json()["status"] == "handoff_requested"


@pytest.mark.asyncio
async def test_public_stream_logs_only_hashed_session_identity(
    public_client, default_agent_id, caplog
):
    visitor_id = "visitor_log_secret"
    session_id, token = await create_public_session(
        public_client, default_agent_id, visitor_id
    )
    caplog.clear()
    caplog.set_level(logging.INFO)

    response = await public_client.post(
        "/api/v1/chat/stream",
        json={
            "agent_id": default_agent_id,
            "message": "Continue without logging my raw identity",
            "session_id": session_id,
            "visitor_id": visitor_id,
        },
        headers=visitor_headers(token),
    )

    assert response.status_code == 200
    assert session_id not in caplog.text
    assert visitor_id not in caplog.text
    assert hash_log_identifier(session_id) in caplog.text
