"""AGENT-02 admin API authorization and cancellation tests."""

import pytest
from sqlalchemy import select

import database
from models import AdminUser, Agent, Workspace
from services.agent_run_service import (
    append_step,
    create_approval_request,
    create_run,
    record_tool_call,
)


@pytest.mark.asyncio
async def test_admin_can_list_read_and_cancel_workspace_run(
    client, default_agent_id
):
    async with database.AsyncSessionLocal() as session:
        agent = await session.get(Agent, default_agent_id)
        run, _ = await create_run(
            session,
            workspace_id=agent.workspace_id,
            agent_id=agent.id,
            idempotency_key="endpoint-own-run",
        )
        run_id = run.id

    response = await client.get("/api/v1/admin/agent-runs")
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == run_id

    response = await client.get(f"/api/v1/admin/agent-runs/{run_id}")
    assert response.status_code == 200
    assert response.json()["trace_id"]
    assert response.json()["steps"] == []

    response = await client.post(f"/api/v1/admin/agent-runs/{run_id}/cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"

    # Cancellation is intentionally idempotent for retries from the admin UI.
    response = await client.post(f"/api/v1/admin/agent-runs/{run_id}/cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cross_workspace_run_is_hidden_from_admin(client, default_agent_id):
    async with database.AsyncSessionLocal() as session:
        workspace = Workspace(
            name="Hidden Workspace", owner_email="hidden-agent-run@example.com"
        )
        session.add(workspace)
        await session.flush()
        agent = Agent(workspace_id=workspace.id, name="Hidden Agent")
        session.add(agent)
        await session.commit()
        hidden_run, _ = await create_run(
            session, workspace_id=workspace.id, agent_id=agent.id
        )
        hidden_run_id = hidden_run.id

    response = await client.get(f"/api/v1/admin/agent-runs/{hidden_run_id}")
    assert response.status_code == 404

    response = await client.get("/api/v1/admin/agent-runs")
    assert response.status_code == 200
    assert all(item["id"] != hidden_run_id for item in response.json()["items"])


@pytest.mark.asyncio
async def test_support_without_membership_cannot_see_run(
    support_client, default_agent_id
):
    async with database.AsyncSessionLocal() as session:
        agent = await session.get(Agent, default_agent_id)
        run, _ = await create_run(
            session, workspace_id=agent.workspace_id, agent_id=agent.id
        )
        run_id = run.id

    response = await support_client.get(f"/api/v1/admin/agent-runs/{run_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_agent_run_admin_api_requires_login(public_client):
    response = await public_client.get("/api/v1/admin/agent-runs")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_can_read_sanitized_approval_queue(client, default_agent_id):
    async with database.AsyncSessionLocal() as session:
        agent = await session.get(Agent, default_agent_id)
        run, _ = await create_run(
            session, workspace_id=agent.workspace_id, agent_id=agent.id
        )
        step = await append_step(
            session, run_id=run.id, sequence=1, step_type="approval"
        )
        tool_call = await record_tool_call(
            session,
            run_id=run.id,
            step_id=step.id,
            call_id="approval-call",
            tool_name="create_refund_draft",
        )
        approval = await create_approval_request(
            session,
            run_id=run.id,
            tool_call_id=tool_call.id,
            action_type="create_refund_draft",
            risk_level="high",
            request_summary={"amount_bucket": "100-500"},
        )

    response = await client.get("/api/v1/admin/approval-requests?status=pending")
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"] == [
        {
            "id": approval.id,
            "run_id": run.id,
            "tool_call_id": tool_call.id,
            "action_type": "create_refund_draft",
            "risk_level": "high",
            "request_summary": {"amount_bucket": "100-500"},
            "status": "pending",
            "reviewer_id": None,
            "decision_reason": None,
            "requested_at": response.json()["items"][0]["requested_at"],
            "decided_at": None,
        }
    ]
