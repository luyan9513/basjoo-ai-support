"""Fail-closed deletion tests across Qdrant, SQLite, and stored files."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import database
from models import Agent, KbDocument, URLSource
from services.kb_document_processor import KbDocumentProcessor
from services.kb_service import KbService
from services.qdrant_service import QdrantKbService
from sqlalchemy import select


def qdrant_service_with_client(client):
    service = object.__new__(QdrantKbService)
    service.client = client
    return service


@pytest.mark.asyncio
async def test_qdrant_point_delete_propagates_service_failure():
    client = MagicMock()
    client.collection_exists = AsyncMock(return_value=True)
    client.delete = AsyncMock(side_effect=RuntimeError("qdrant unavailable"))
    service = qdrant_service_with_client(client)

    with pytest.raises(RuntimeError, match="qdrant unavailable"):
        await service.delete_points_by_doc_id("kb-1", "doc-1")


@pytest.mark.asyncio
async def test_qdrant_point_delete_reports_missing_collection():
    client = MagicMock()
    client.collection_exists = AsyncMock(return_value=False)
    client.delete = AsyncMock()
    service = qdrant_service_with_client(client)

    result = await service.delete_points_by_doc_id("kb-1", "doc-1")

    assert result == "not_found"
    client.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_qdrant_point_delete_waits_for_completion():
    client = MagicMock()
    client.collection_exists = AsyncMock(return_value=True)
    client.delete = AsyncMock(return_value=MagicMock())
    service = qdrant_service_with_client(client)

    result = await service.delete_points_by_doc_id("kb-1", "doc-1")

    assert result == "deleted"
    assert client.delete.await_args.kwargs["wait"] is True


@pytest.mark.asyncio
async def test_qdrant_collection_delete_propagates_service_failure():
    client = MagicMock()
    client.collection_exists = AsyncMock(return_value=True)
    client.delete_collection = AsyncMock(side_effect=RuntimeError("qdrant unavailable"))
    service = qdrant_service_with_client(client)

    with pytest.raises(RuntimeError, match="qdrant unavailable"):
        await service.delete_collection("kb-1")


@pytest.mark.asyncio
async def test_qdrant_collection_delete_reports_missing_collection():
    client = MagicMock()
    client.collection_exists = AsyncMock(return_value=False)
    client.delete_collection = AsyncMock()
    service = qdrant_service_with_client(client)

    result = await service.delete_collection("kb-1")

    assert result == "not_found"
    client.delete_collection.assert_not_awaited()


@pytest.mark.asyncio
async def test_document_commit_failure_keeps_stored_file(tmp_path):
    stored_file = tmp_path / "document.txt"
    stored_file.write_text("keep until sqlite commits", encoding="utf-8")
    doc = MagicMock(
        id="doc-1",
        kb_id="kb-1",
        tenant_id="tenant-1",
        storage_path=str(stored_file),
    )
    doc_result = MagicMock()
    doc_result.scalar_one_or_none.return_value = doc
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[doc_result, MagicMock()])
    db.delete = AsyncMock()
    db.commit = AsyncMock(side_effect=RuntimeError("sqlite commit failed"))
    db.rollback = AsyncMock()
    processor = KbDocumentProcessor()
    processor.qdrant = MagicMock()
    processor.qdrant.delete_points_by_doc_id = AsyncMock(return_value="deleted")

    with pytest.raises(RuntimeError, match="sqlite commit failed"):
        await processor.delete_document("tenant-1", "kb-1", "doc-1", db)

    assert stored_file.exists()
    db.rollback.assert_awaited_once()


async def create_agent_kb_with_document(default_agent_id, filename, storage_path):
    async with database.AsyncSessionLocal() as session:
        service = KbService(session=session)
        tenant, kb = await service.get_or_create_agent_kb(
            default_agent_id, session=session
        )
        agent = (
            await session.execute(select(Agent).where(Agent.id == default_agent_id))
        ).scalar_one()
        doc = KbDocument(
            tenant_id=tenant.id,
            kb_id=kb.id,
            filename=filename,
            storage_path=str(storage_path),
            status="ready",
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)
        return agent.id, kb.id, str(doc.id)


@pytest.mark.asyncio
async def test_clear_files_does_not_claim_success_when_qdrant_fails(
    client, default_agent_id, tmp_path
):
    stored_file = tmp_path / "manual.txt"
    stored_file.write_text("manual knowledge", encoding="utf-8")
    _, _, doc_id = await create_agent_kb_with_document(
        default_agent_id, "manual.txt", stored_file
    )

    with patch.object(
        KbDocumentProcessor,
        "delete_document",
        new=AsyncMock(side_effect=RuntimeError("qdrant unavailable")),
    ):
        with pytest.raises(RuntimeError, match="qdrant unavailable"):
            await client.post(f"/api/v1/files:clear_all?agent_id={default_agent_id}")

    async with database.AsyncSessionLocal() as session:
        assert await session.get(KbDocument, doc_id) is not None
    assert stored_file.exists()


@pytest.mark.asyncio
async def test_clear_urls_does_not_delete_records_when_qdrant_fails(
    client, default_agent_id, tmp_path
):
    stored_file = tmp_path / "url.txt"
    stored_file.write_text("url knowledge", encoding="utf-8")
    async with database.AsyncSessionLocal() as session:
        url_source = URLSource(
            agent_id=default_agent_id,
            url="https://example.com/private-order",
            normalized_url="https://example.com/private-order",
            status="success",
        )
        session.add(url_source)
        await session.commit()
        await session.refresh(url_source)
        url_id = url_source.id

    _, _, doc_id = await create_agent_kb_with_document(
        default_agent_id, f"url_{url_id}.txt", stored_file
    )

    with patch(
        "services.qdrant_service.QdrantKbService.delete_points_by_doc_id",
        new=AsyncMock(side_effect=RuntimeError("qdrant unavailable")),
    ):
        with pytest.raises(RuntimeError, match="qdrant unavailable"):
            await client.post(f"/api/v1/urls:clear_all?agent_id={default_agent_id}")

    async with database.AsyncSessionLocal() as session:
        assert await session.get(URLSource, url_id) is not None
        assert await session.get(KbDocument, doc_id) is not None
    assert stored_file.exists()


@pytest.mark.asyncio
async def test_delete_single_url_removes_its_document_vector_and_file(
    client, default_agent_id, tmp_path
):
    stored_file = tmp_path / "single-url.txt"
    stored_file.write_text("single url knowledge", encoding="utf-8")
    async with database.AsyncSessionLocal() as session:
        url_source = URLSource(
            agent_id=default_agent_id,
            url="https://example.com/single",
            normalized_url="https://example.com/single",
            status="success",
        )
        session.add(url_source)
        await session.commit()
        await session.refresh(url_source)
        url_id = url_source.id
    _, _, doc_id = await create_agent_kb_with_document(
        default_agent_id, f"url_{url_id}.txt", stored_file
    )

    with patch(
        "services.qdrant_service.QdrantKbService.delete_points_by_doc_id",
        new=AsyncMock(return_value="deleted"),
    ):
        response = await client.delete(
            f"/api/v1/urls:delete?agent_id={default_agent_id}&url_id={url_id}"
        )

    assert response.status_code == 200
    async with database.AsyncSessionLocal() as session:
        assert await session.get(URLSource, url_id) is None
        assert await session.get(KbDocument, doc_id) is None
    assert not stored_file.exists()


@pytest.mark.asyncio
async def test_delete_single_url_keeps_all_records_when_qdrant_fails(
    client, default_agent_id, tmp_path
):
    stored_file = tmp_path / "single-url-failure.txt"
    stored_file.write_text("keep on qdrant failure", encoding="utf-8")
    async with database.AsyncSessionLocal() as session:
        url_source = URLSource(
            agent_id=default_agent_id,
            url="https://example.com/single-failure",
            normalized_url="https://example.com/single-failure",
            status="success",
        )
        session.add(url_source)
        await session.commit()
        await session.refresh(url_source)
        url_id = url_source.id
    _, _, doc_id = await create_agent_kb_with_document(
        default_agent_id, f"url_{url_id}.txt", stored_file
    )

    with patch(
        "services.qdrant_service.QdrantKbService.delete_points_by_doc_id",
        new=AsyncMock(side_effect=RuntimeError("qdrant unavailable")),
    ):
        with pytest.raises(RuntimeError, match="qdrant unavailable"):
            await client.delete(
                f"/api/v1/urls:delete?agent_id={default_agent_id}&url_id={url_id}"
            )

    async with database.AsyncSessionLocal() as session:
        assert await session.get(URLSource, url_id) is not None
        assert await session.get(KbDocument, doc_id) is not None
    assert stored_file.exists()
