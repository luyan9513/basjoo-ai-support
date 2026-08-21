"""HTTP and service regressions for workspace-scoped tenant authorization."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

import database
from models import Agent, AgentMember, KnowledgeBase, Tenant, Workspace, WorkspaceQuota
from services.auth_service import AuthService
from services.kb_service import KbService


async def _build_tenant_graph(slug: str, *, use_existing_workspace: bool):
    async with database.AsyncSessionLocal() as session:
        if use_existing_workspace:
            workspace = (
                await session.execute(select(Workspace).order_by(Workspace.id).limit(1))
            ).scalar_one()
            agent = (
                await session.execute(
                    select(Agent)
                    .where(Agent.workspace_id == workspace.id)
                    .order_by(Agent.created_at)
                    .limit(1)
                )
            ).scalar_one()
            token = None
        else:
            workspace = Workspace(
                name=f"Workspace {slug}", owner_email=f"{slug}@example.com"
            )
            session.add(workspace)
            await session.flush()
            session.add(WorkspaceQuota(workspace_id=workspace.id))
            agent = Agent(workspace_id=workspace.id, name=f"Agent {slug}")
            session.add(agent)
            await session.flush()
            admin = await AuthService(session).create_admin(
                email=f"admin-{slug}@example.com",
                password="testpassword123",
                name=f"Admin {slug}",
                role="super_admin",
                workspace_id=workspace.id,
            )
            token = AuthService(session).create_access_token({"sub": str(admin.id)})

        tenant = Tenant(
            name=f"Tenant {slug}", slug=slug, workspace_id=workspace.id
        )
        session.add(tenant)
        await session.flush()
        kb = KnowledgeBase(
            tenant_id=tenant.id,
            name=f"KB {slug}",
            qdrant_collection=f"kb_{slug}",
        )
        session.add(kb)
        await session.flush()
        agent.kb_id = kb.id
        await session.commit()
        return {
            "workspace_id": workspace.id,
            "tenant_id": tenant.id,
            "kb_id": kb.id,
            "agent_id": agent.id,
            "token": token,
        }


@pytest.mark.asyncio
async def test_tenant_http_endpoints_allow_own_workspace(
    client, default_agent_id, monkeypatch
):
    own = await _build_tenant_graph("tenant-own", use_existing_workspace=True)
    monkeypatch.setattr(
        "api.v1.kb_document_endpoints.retrieval_svc.retrieve",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "api.v1.kb_document_endpoints.processor.process_document", AsyncMock()
    )
    monkeypatch.setattr(
        "api.v1.kb_document_endpoints.processor.save_uploaded_file",
        lambda *_args, **_kwargs: "/tmp/tenant-own.txt",
    )

    list_response = await client.get(
        f"/api/tenants/{own['tenant_id']}/knowledge_bases/{own['kb_id']}/documents"
    )
    assert list_response.status_code == 200

    upload_response = await client.post(
        f"/api/tenants/{own['tenant_id']}/knowledge_bases/{own['kb_id']}/documents",
        files={"files": ("tenant-own.txt", b"safe test content", "text/plain")},
    )
    assert upload_response.status_code == 200

    retrieve_response = await client.post(
        f"/api/tenants/{own['tenant_id']}/agents/{own['agent_id']}/retrieve",
        json={"query": "test", "top_k": 5},
    )
    assert retrieve_response.status_code == 200


@pytest.mark.asyncio
async def test_tenant_http_endpoints_hide_other_workspace(
    client, default_agent_id, monkeypatch
):
    other = await _build_tenant_graph("tenant-other", use_existing_workspace=False)
    monkeypatch.setattr(
        "api.v1.kb_document_endpoints.retrieval_svc.retrieve",
        AsyncMock(return_value=[]),
    )

    list_response = await client.get(
        f"/api/tenants/{other['tenant_id']}/knowledge_bases/{other['kb_id']}/documents"
    )
    assert list_response.status_code == 404

    upload_response = await client.post(
        f"/api/tenants/{other['tenant_id']}/knowledge_bases/{other['kb_id']}/documents",
        files={"files": ("cross-tenant.txt", b"must be rejected", "text/plain")},
    )
    assert upload_response.status_code == 404

    retrieve_response = await client.post(
        f"/api/tenants/{other['tenant_id']}/agents/{other['agent_id']}/retrieve",
        json={"query": "test", "top_k": 5},
    )
    assert retrieve_response.status_code == 404


@pytest.mark.asyncio
async def test_workspace_admin_requires_agent_admin_membership(
    client, default_agent_id
):
    from main import app

    own = await _build_tenant_graph(
        "tenant-member-check", use_existing_workspace=True
    )
    async with database.AsyncSessionLocal() as session:
        admin = await AuthService(session).create_admin(
            email="tenant-member-admin@example.com",
            password="testpassword123",
            name="Tenant Member Admin",
            role="admin",
            workspace_id=own["workspace_id"],
        )
        token = AuthService(session).create_access_token({"sub": str(admin.id)})
        admin_id = admin.id

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as admin_client:
        admin_client.headers.update({"Authorization": f"Bearer {token}"})
        url = (
            f"/api/tenants/{own['tenant_id']}"
            f"/knowledge_bases/{own['kb_id']}/documents"
        )
        without_membership = await admin_client.get(url)
        assert without_membership.status_code == 404

        async with database.AsyncSessionLocal() as session:
            session.add(
                AgentMember(
                    agent_id=own["agent_id"],
                    admin_user_id=admin_id,
                    role="admin",
                )
            )
            await session.commit()

        with_membership = await admin_client.get(url)
        assert with_membership.status_code == 200


@pytest.mark.asyncio
async def test_delete_kb_with_wrong_tenant_does_not_delete_target(setup_test_db):
    async with database.AsyncSessionLocal() as session:
        workspace = (
            await session.execute(select(Workspace).order_by(Workspace.id).limit(1))
        ).scalar_one()
        tenant_a = Tenant(
            name="Tenant delete A", slug="tenant-delete-a", workspace_id=workspace.id
        )
        tenant_b = Tenant(
            name="Tenant delete B", slug="tenant-delete-b", workspace_id=workspace.id
        )
        session.add_all([tenant_a, tenant_b])
        await session.flush()
        kb_a = KnowledgeBase(
            tenant_id=tenant_a.id,
            name="KB delete A",
            qdrant_collection="kb_delete_a",
        )
        session.add(kb_a)
        await session.commit()
        kb_a_id = kb_a.id

        service = KbService(session=session)
        with patch.object(
            service.qdrant, "delete_collection", new=AsyncMock(return_value="deleted")
        ):
            await service.delete_knowledge_base(tenant_b.id, kb_a_id)

        remaining = await session.get(KnowledgeBase, kb_a_id)
        assert remaining is not None


@pytest.mark.asyncio
async def test_other_workspace_admin_cannot_delete_kb(
    client, default_agent_id, monkeypatch
):
    from main import app

    own = await _build_tenant_graph("tenant-delete-own", use_existing_workspace=True)
    other = await _build_tenant_graph("tenant-delete-other", use_existing_workspace=False)
    monkeypatch.setattr(
        "api.v1.kb_document_endpoints.kb_svc.qdrant.delete_collection",
        AsyncMock(return_value="deleted"),
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as other_client:
        other_client.headers.update(
            {"Authorization": f"Bearer {other['token']}"}
        )
        response = await other_client.delete(
            f"/api/tenants/{own['tenant_id']}/knowledge_bases/{own['kb_id']}"
        )

    assert response.status_code == 404
    async with database.AsyncSessionLocal() as session:
        assert await session.get(KnowledgeBase, own["kb_id"]) is not None
