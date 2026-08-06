"""AGENT-02 persistence and state-machine tests."""

import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

import database
from models import Agent, AgentStep, ApprovalRequest, ToolCall, Workspace
from services.agent_run_service import (
    AgentRunScopeError,
    InvalidAgentRunTransition,
    append_step,
    create_approval_request,
    create_run,
    record_tool_call,
    transition_run,
)


@pytest.mark.asyncio
async def test_run_lifecycle_persists_steps_tools_and_approval(
    setup_test_db, default_agent_id
):
    async with database.AsyncSessionLocal() as session:
        agent = await session.get(Agent, default_agent_id)
        run, created = await create_run(
            session,
            workspace_id=agent.workspace_id,
            agent_id=agent.id,
            idempotency_key="order-1001:message-1",
            trace_id="trace-agent-02",
        )
        assert created is True
        assert run.status == "queued"

        run = await transition_run(
            session, run.id, agent.workspace_id, target_status="running"
        )
        step = await append_step(
            session,
            run_id=run.id,
            sequence=1,
            step_type="intent",
            input_summary={"message_type": "return_request"},
        )
        tool_call = await record_tool_call(
            session,
            run_id=run.id,
            step_id=step.id,
            call_id="call-policy-1",
            tool_name="lookup_return_policy",
            arguments_summary={"order_ref": "sha256:demo"},
        )
        approval = await create_approval_request(
            session,
            run_id=run.id,
            tool_call_id=tool_call.id,
            action_type="create_refund_draft",
            risk_level="high",
            request_summary={"amount_bucket": "100-500"},
        )
        run = await transition_run(
            session, run.id, agent.workspace_id, target_status="waiting_for_approval"
        )

        assert run.status == "waiting_for_approval"
        assert step.status == "pending"
        assert tool_call.status == "pending"
        assert approval.status == "pending"


@pytest.mark.asyncio
async def test_run_creation_is_idempotent_and_concurrency_safe(
    setup_test_db, default_agent_id
):
    async with database.AsyncSessionLocal() as session:
        agent = await session.get(Agent, default_agent_id)
        workspace_id = agent.workspace_id

    async def create_once():
        async with database.AsyncSessionLocal() as session:
            run, created = await create_run(
                session,
                workspace_id=workspace_id,
                agent_id=default_agent_id,
                idempotency_key="same-client-request",
            )
            return run.id, created

    first, second = await asyncio.gather(create_once(), create_once())
    assert first[0] == second[0]
    assert sorted([first[1], second[1]]) == [False, True]


@pytest.mark.asyncio
async def test_illegal_transition_and_cross_workspace_creation_are_rejected(
    setup_test_db, default_agent_id
):
    async with database.AsyncSessionLocal() as session:
        agent = await session.get(Agent, default_agent_id)
        run, _ = await create_run(
            session, workspace_id=agent.workspace_id, agent_id=agent.id
        )

        with pytest.raises(InvalidAgentRunTransition):
            await transition_run(
                session, run.id, agent.workspace_id, target_status="succeeded"
            )

        other_workspace = Workspace(
            name="Other", owner_email="agent-02-other@example.com"
        )
        session.add(other_workspace)
        await session.commit()

        with pytest.raises(AgentRunScopeError):
            await create_run(
                session,
                workspace_id=other_workspace.id,
                agent_id=agent.id,
            )


@pytest.mark.asyncio
async def test_step_and_tool_call_unique_constraints_block_duplicates(
    setup_test_db, default_agent_id
):
    async with database.AsyncSessionLocal() as session:
        agent = await session.get(Agent, default_agent_id)
        run, _ = await create_run(
            session, workspace_id=agent.workspace_id, agent_id=agent.id
        )
        step = await append_step(
            session, run_id=run.id, sequence=1, step_type="intent"
        )
        await record_tool_call(
            session,
            run_id=run.id,
            step_id=step.id,
            call_id="same-call-id",
            tool_name="lookup_order",
        )
        run_id = run.id
        step_id = step.id

        session.add(AgentStep(run_id=run_id, sequence=1, step_type="plan"))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

        session.add(
            ToolCall(
                run_id=run_id,
                step_id=step_id,
                call_id="same-call-id",
                tool_name="lookup_order",
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

        approvals = await session.execute(
            select(ApprovalRequest).where(ApprovalRequest.run_id == run_id)
        )
        assert approvals.scalars().all() == []
