"""Workspace-scoped admin endpoints for observing and cancelling AgentRuns."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.endpoints.auth import require_chat_operator
from api.v1.schemas import (
    AgentRunDetail,
    AgentRunItem,
    AgentRunListResponse,
    AgentRunStatus,
    ApprovalRequestItem,
    ApprovalRequestListResponse,
)
from database import get_db
from models import AdminUser, AgentMember, AgentRun, ApprovalRequest
from services.agent_run_service import (
    AgentRunNotFound,
    InvalidAgentRunTransition,
    cancel_run,
)


router = APIRouter(prefix="/api/v1/admin", tags=["agent-runs"])


async def _member_agent_ids(db: AsyncSession, admin: AdminUser) -> list[str] | None:
    if not admin.workspace_id:
        raise HTTPException(status_code=404, detail="Agent run not found")
    if admin.role == "super_admin":
        return None
    result = await db.execute(
        select(AgentMember.agent_id).where(AgentMember.admin_user_id == admin.id)
    )
    return list(result.scalars().all())


async def _scoped_run(
    db: AsyncSession,
    run_id: str,
    admin: AdminUser,
    *,
    with_details: bool = False,
) -> AgentRun:
    member_agent_ids = await _member_agent_ids(db, admin)
    query = select(AgentRun).where(
        AgentRun.id == run_id,
        AgentRun.workspace_id == admin.workspace_id,
    )
    if member_agent_ids is not None:
        query = query.where(AgentRun.agent_id.in_(member_agent_ids or ["__none__"]))
    if with_details:
        query = query.options(
            selectinload(AgentRun.steps),
            selectinload(AgentRun.tool_calls),
            selectinload(AgentRun.approval_requests),
        )
    run = await db.scalar(query)
    if not run:
        # Deliberately hide whether a run exists outside the caller's scope.
        raise HTTPException(status_code=404, detail="Agent run not found")
    return run


@router.get("/agent-runs", response_model=AgentRunListResponse)
async def list_agent_runs(
    agent_id: str | None = None,
    run_status: AgentRunStatus | None = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: AdminUser = Depends(require_chat_operator),
    db: AsyncSession = Depends(get_db),
):
    member_agent_ids = await _member_agent_ids(db, current_user)
    query = select(AgentRun).where(AgentRun.workspace_id == current_user.workspace_id)
    if member_agent_ids is not None:
        query = query.where(
            AgentRun.agent_id.in_(member_agent_ids or ["__none__"])
        )
    if agent_id:
        if member_agent_ids is not None and agent_id not in member_agent_ids:
            raise HTTPException(status_code=404, detail="Agent run not found")
        query = query.where(AgentRun.agent_id == agent_id)
    if run_status:
        query = query.where(AgentRun.status == run_status)

    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    result = await db.execute(
        query.order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
        .offset(skip)
        .limit(limit)
    )
    return AgentRunListResponse(
        items=[AgentRunItem.model_validate(run) for run in result.scalars().all()],
        total=total,
    )


@router.get("/agent-runs/{run_id}", response_model=AgentRunDetail)
async def get_agent_run(
    run_id: str,
    current_user: AdminUser = Depends(require_chat_operator),
    db: AsyncSession = Depends(get_db),
):
    run = await _scoped_run(db, run_id, current_user, with_details=True)
    return AgentRunDetail.model_validate(run)


@router.post("/agent-runs/{run_id}/cancel", response_model=AgentRunItem)
async def cancel_agent_run(
    run_id: str,
    current_user: AdminUser = Depends(require_chat_operator),
    db: AsyncSession = Depends(get_db),
):
    run = await _scoped_run(db, run_id, current_user)
    try:
        run = await cancel_run(db, run.id, current_user.workspace_id)
    except AgentRunNotFound:
        raise HTTPException(status_code=404, detail="Agent run not found")
    except InvalidAgentRunTransition as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    return AgentRunItem.model_validate(run)


@router.get("/approval-requests", response_model=ApprovalRequestListResponse)
async def list_approval_requests(
    approval_status: str | None = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: AdminUser = Depends(require_chat_operator),
    db: AsyncSession = Depends(get_db),
):
    member_agent_ids = await _member_agent_ids(db, current_user)
    query = (
        select(ApprovalRequest)
        .join(AgentRun, AgentRun.id == ApprovalRequest.run_id)
        .where(AgentRun.workspace_id == current_user.workspace_id)
    )
    if member_agent_ids is not None:
        query = query.where(
            AgentRun.agent_id.in_(member_agent_ids or ["__none__"])
        )
    if approval_status:
        query = query.where(ApprovalRequest.status == approval_status)
    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    result = await db.execute(
        query.order_by(ApprovalRequest.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return ApprovalRequestListResponse(
        items=[
            ApprovalRequestItem.model_validate(item)
            for item in result.scalars().all()
        ],
        total=total,
    )
