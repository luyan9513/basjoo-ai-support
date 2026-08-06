"""Persistence and transition rules for the restricted single-agent runtime."""

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models import (
    AGENT_RUN_STATUSES,
    APPROVAL_RISK_LEVELS,
    Agent,
    AgentRun,
    AgentStep,
    ApprovalRequest,
    ChatMessage,
    ChatSession,
    ToolCall,
)


class AgentRunError(Exception):
    """Base error for AgentRun persistence operations."""


class AgentRunNotFound(AgentRunError):
    """The run is absent or outside the requested workspace scope."""


class AgentRunScopeError(AgentRunError):
    """Referenced objects do not belong to the requested workspace/agent."""


class InvalidAgentRunTransition(AgentRunError):
    """The requested state transition is not allowed."""


RUN_TRANSITIONS: dict[str, frozenset[str]] = {
    "queued": frozenset({"running", "cancelled"}),
    "running": frozenset(
        {
            "waiting_for_user",
            "waiting_for_approval",
            "succeeded",
            "failed",
            "cancelled",
        }
    ),
    "waiting_for_user": frozenset({"running", "failed", "cancelled"}),
    "waiting_for_approval": frozenset({"running", "failed", "cancelled"}),
    "succeeded": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
}
TERMINAL_RUN_STATUSES = frozenset({"succeeded", "failed", "cancelled"})


async def create_run(
    db: AsyncSession,
    *,
    workspace_id: int,
    agent_id: str,
    chat_session_id: str | None = None,
    user_message_id: int | None = None,
    idempotency_key: str | None = None,
    trace_id: str | None = None,
    max_steps: int = 8,
    deadline_at: datetime | None = None,
) -> tuple[AgentRun, bool]:
    """Create one run, returning the existing row for a repeated client request."""
    if not 1 <= max_steps <= 32:
        raise ValueError("max_steps must be between 1 and 32")
    if idempotency_key is not None:
        idempotency_key = idempotency_key.strip()
        if not idempotency_key or len(idempotency_key) > 128:
            raise ValueError("idempotency_key must contain 1-128 characters")

    agent = await db.scalar(
        select(Agent).where(
            Agent.id == agent_id,
            Agent.workspace_id == workspace_id,
            Agent.deleted_at.is_(None),
        )
    )
    if not agent:
        raise AgentRunScopeError("Agent is outside the requested workspace")

    if chat_session_id:
        chat_session = await db.scalar(
            select(ChatSession).where(
                ChatSession.id == chat_session_id,
                ChatSession.agent_id == agent_id,
            )
        )
        if not chat_session:
            raise AgentRunScopeError("Chat session does not belong to the agent")

    if user_message_id is not None:
        if not chat_session_id:
            raise AgentRunScopeError("user_message_id requires chat_session_id")
        message = await db.scalar(
            select(ChatMessage).where(
                ChatMessage.id == user_message_id,
                ChatMessage.session_id == chat_session_id,
            )
        )
        if not message:
            raise AgentRunScopeError("User message does not belong to the chat session")

    if idempotency_key:
        existing = await db.scalar(
            select(AgentRun).where(
                AgentRun.workspace_id == workspace_id,
                AgentRun.idempotency_key == idempotency_key,
            )
        )
        if existing:
            return existing, False

    run = AgentRun(
        workspace_id=workspace_id,
        agent_id=agent_id,
        chat_session_id=chat_session_id,
        user_message_id=user_message_id,
        idempotency_key=idempotency_key,
        trace_id=trace_id or uuid.uuid4().hex,
        max_steps=max_steps,
        deadline_at=deadline_at,
    )
    db.add(run)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        if not idempotency_key:
            raise
        existing = await db.scalar(
            select(AgentRun).where(
                AgentRun.workspace_id == workspace_id,
                AgentRun.idempotency_key == idempotency_key,
            )
        )
        if not existing:
            raise
        return existing, False

    await db.refresh(run)
    return run, True


async def get_run(
    db: AsyncSession, run_id: str, workspace_id: int
) -> AgentRun:
    run = await db.scalar(
        select(AgentRun).where(
            AgentRun.id == run_id, AgentRun.workspace_id == workspace_id
        ).execution_options(populate_existing=True)
    )
    if not run:
        raise AgentRunNotFound("Agent run not found")
    return run


async def transition_run(
    db: AsyncSession,
    run_id: str,
    workspace_id: int,
    *,
    target_status: str,
    error_code: str | None = None,
) -> AgentRun:
    """Apply a compare-and-set transition so stale workers cannot overwrite state."""
    if target_status not in AGENT_RUN_STATUSES:
        raise InvalidAgentRunTransition(f"Unknown target status: {target_status}")

    run = await get_run(db, run_id, workspace_id)
    current_status = run.status
    if target_status not in RUN_TRANSITIONS[current_status]:
        raise InvalidAgentRunTransition(
            f"Cannot transition AgentRun from {current_status} to {target_status}"
        )

    now = datetime.now(timezone.utc)
    values: dict[str, Any] = {"status": target_status, "updated_at": now}
    if current_status == "queued" and target_status == "running":
        values["started_at"] = now
    if target_status in TERMINAL_RUN_STATUSES:
        values["completed_at"] = now
    if error_code is not None:
        values["error_code"] = error_code

    result = await db.execute(
        update(AgentRun)
        .where(
            AgentRun.id == run_id,
            AgentRun.workspace_id == workspace_id,
            AgentRun.status == current_status,
        )
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        await db.rollback()
        raise InvalidAgentRunTransition("AgentRun state changed concurrently")
    await db.commit()
    return await get_run(db, run_id, workspace_id)


async def cancel_run(
    db: AsyncSession, run_id: str, workspace_id: int
) -> AgentRun:
    run = await get_run(db, run_id, workspace_id)
    if run.status == "cancelled":
        return run
    return await transition_run(
        db, run_id, workspace_id, target_status="cancelled"
    )


async def append_step(
    db: AsyncSession,
    *,
    run_id: str,
    sequence: int,
    step_type: str,
    input_summary: dict[str, Any] | None = None,
) -> AgentStep:
    step = AgentStep(
        run_id=run_id,
        sequence=sequence,
        step_type=step_type,
        input_summary=input_summary,
    )
    db.add(step)
    await db.commit()
    await db.refresh(step)
    return step


async def record_tool_call(
    db: AsyncSession,
    *,
    run_id: str,
    step_id: int | None,
    call_id: str,
    tool_name: str,
    arguments_summary: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> ToolCall:
    if step_id is not None:
        step = await db.scalar(
            select(AgentStep).where(
                AgentStep.id == step_id, AgentStep.run_id == run_id
            )
        )
        if not step:
            raise AgentRunScopeError("Agent step does not belong to the run")
    tool_call = ToolCall(
        run_id=run_id,
        step_id=step_id,
        call_id=call_id,
        tool_name=tool_name,
        arguments_summary=arguments_summary,
        idempotency_key=idempotency_key,
    )
    db.add(tool_call)
    await db.commit()
    await db.refresh(tool_call)
    return tool_call


async def create_approval_request(
    db: AsyncSession,
    *,
    run_id: str,
    tool_call_id: int | None,
    action_type: str,
    risk_level: str,
    request_summary: dict[str, Any] | None = None,
) -> ApprovalRequest:
    if risk_level not in APPROVAL_RISK_LEVELS:
        raise ValueError("Unknown approval risk level")
    if tool_call_id is not None:
        tool_call = await db.scalar(
            select(ToolCall).where(
                ToolCall.id == tool_call_id, ToolCall.run_id == run_id
            )
        )
        if not tool_call:
            raise AgentRunScopeError("Tool call does not belong to the run")
    approval = ApprovalRequest(
        run_id=run_id,
        tool_call_id=tool_call_id,
        action_type=action_type,
        risk_level=risk_level,
        request_summary=request_summary,
    )
    db.add(approval)
    await db.commit()
    await db.refresh(approval)
    return approval
