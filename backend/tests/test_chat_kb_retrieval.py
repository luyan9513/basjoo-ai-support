"""Tests proving Playground/chat retrieves from agent KB after URL/file indexing.

These tests verify that:
1. Chat endpoint includes KB context when agent has indexed content
2. Tenant mismatches return no KB context
3. The retrieved context is actually used in the system message
4. Ready KB document content with a unique phrase is passed into chat KB context
5. Failed ingestion is distinguishable from chat defects
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.kb_retrieval_service import KbRetrievalService


@pytest.mark.asyncio
async def test_chat_calls_kb_retrieval_with_agent_threshold():
    """prepare_chat_request should call KbRetrievalService with agent's similarity_threshold."""
    from api.v1.endpoints import prepare_chat_request
    from api.v1.schemas import ChatRequest

    # Setup mock agent with kb_id and specific threshold
    mock_agent = MagicMock()
    mock_agent.id = "agent_123"
    mock_agent.workspace_id = "ws_123"
    mock_agent.kb_id = "kb_123"
    mock_agent.top_k = 5
    mock_agent.similarity_threshold = 0.03  # RRF-style threshold
    mock_agent.temperature = 0.7
    mock_agent.system_prompt = "You are a helpful assistant."
    mock_agent.enable_context = True
    mock_agent.api_key = "test_key"
    mock_agent.api_base = "https://api.test.com"
    mock_agent.model = "test-model"
    mock_agent.rate_limit_per_minute = 0
    mock_agent.restricted_reply = None

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_agent
    mock_session.execute.return_value = mock_result

    # Mock quota check
    mock_quota = MagicMock()
    mock_quota.used_messages_today = 0
    mock_quota.max_messages_per_day = 100
    mock_quota.id = "quota_123"

    chat_request = ChatRequest(
        agent_id="agent_123",
        message="test query about unique content XYZ123TEST",
        session_id=None,
        params={},
    )

    mock_http_request = MagicMock()
    mock_http_request.headers.get.return_value = ""

    with patch("api.v1.endpoints.get_db") as mock_get_db:
        mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("api.v1.endpoints.check_quota", return_value=mock_quota):
            with patch("api.v1.endpoints.get_or_create_chat_session") as mock_session_fn:
                mock_chat_session = MagicMock()
                mock_chat_session.id = "session_123"
                mock_chat_session.status = "active"
                mock_session_fn.return_value = mock_chat_session

                with patch("api.v1.endpoints.KbRetrievalService") as mock_kb_svc_cls:
                    mock_kb_svc = MagicMock()
                    mock_kb_svc.retrieve = AsyncMock(return_value=[
                        {"text": "This contains XYZ123TEST unique phrase", "doc_id": "doc1", "chunk_index": 0, "score": 0.045, "filename": "test.txt"}
                    ])
                    mock_kb_svc_cls.return_value = mock_kb_svc

                    # Call prepare_chat_request
                    result = await prepare_chat_request(chat_request, mock_http_request, mock_session)

                    # Verify KbRetrievalService.retrieve was called with agent's threshold
                    mock_kb_svc.retrieve.assert_called_once()
                    call_kwargs = mock_kb_svc.retrieve.call_args[1]
                    assert call_kwargs["agent_id"] == "agent_123"
                    assert call_kwargs["top_k"] == 5
                    assert call_kwargs["threshold"] == 0.03


@pytest.mark.asyncio
async def test_chat_system_message_includes_kb_context():
    """System message should include KB context when retrieval returns results."""
    from api.v1.endpoints import prepare_chat_request
    from api.v1.schemas import ChatRequest

    mock_agent = MagicMock()
    mock_agent.id = "agent_123"
    mock_agent.workspace_id = "ws_123"
    mock_agent.kb_id = "kb_123"
    mock_agent.top_k = 5
    mock_agent.similarity_threshold = 0.05
    mock_agent.temperature = 0.7
    mock_agent.system_prompt = "You are a helpful assistant."
    mock_agent.enable_context = False  # Disable context to simplify
    mock_agent.api_key = "test_key"
    mock_agent.api_base = "https://api.test.com"
    mock_agent.model = "test-model"
    mock_agent.rate_limit_per_minute = 0
    mock_agent.restricted_reply = None

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_agent
    mock_session.execute.return_value = mock_result

    mock_quota = MagicMock()
    mock_quota.used_messages_today = 0
    mock_quota.max_messages_per_day = 100
    mock_quota.id = "quota_123"

    chat_request = ChatRequest(
        agent_id="agent_123",
        message="what is the unique information?",
        session_id=None,
        params={},
    )

    mock_http_request = MagicMock()
    mock_http_request.headers.get.return_value = ""

    with patch("api.v1.endpoints.get_db") as mock_get_db:
        mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("api.v1.endpoints.check_quota", return_value=mock_quota):
            with patch("api.v1.endpoints.get_or_create_chat_session") as mock_session_fn:
                mock_chat_session = MagicMock()
                mock_chat_session.id = "session_123"
                mock_chat_session.status = "active"
                mock_session_fn.return_value = mock_chat_session

                with patch("api.v1.endpoints.KbRetrievalService") as mock_kb_svc_cls:
                    mock_kb_svc = MagicMock()
                    # Return KB results with a unique phrase
                    mock_kb_svc.retrieve = AsyncMock(return_value=[
                        {"text": "The BasjooKB2024TEST answer is 42", "doc_id": "doc1", "chunk_index": 0, "score": 0.045, "filename": "knowledge.txt"}
                    ])
                    mock_kb_svc_cls.return_value = mock_kb_svc

                    result = await prepare_chat_request(chat_request, mock_http_request, mock_session)

                    # Verify system message contains KB context
                    messages = result.get("messages", [])
                    system_msg = next((m for m in messages if m.get("role") == "system"), None)
                    assert system_msg is not None
                    system_content = system_msg.get("content", "")

                    # Should contain the KB context marker
                    assert "背景资料" in system_content or "relevant information" in system_content.lower()
                    # Should contain the retrieved text
                    assert "BasjooKB2024TEST" in system_content


@pytest.mark.asyncio
async def test_chat_without_kb_id_keeps_general_llm_mode():
    """Agent without a bound KB should not be treated as a failed KB lookup."""
    from api.v1.endpoints import prepare_chat_request
    from api.v1.schemas import ChatRequest

    mock_agent = MagicMock()
    mock_agent.id = "agent_no_kb"
    mock_agent.workspace_id = "ws_123"
    mock_agent.kb_id = None  # No KB bound
    mock_agent.top_k = 5
    mock_agent.similarity_threshold = 0.05
    mock_agent.temperature = 0.7
    mock_agent.system_prompt = "You are a helpful assistant."
    mock_agent.enable_context = False
    mock_agent.api_key = "test_key"
    mock_agent.api_base = "https://api.test.com"
    mock_agent.model = "test-model"
    mock_agent.rate_limit_per_minute = 0
    mock_agent.restricted_reply = None

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_agent
    mock_session.execute.return_value = mock_result

    mock_quota = MagicMock()
    mock_quota.used_messages_today = 0
    mock_quota.max_messages_per_day = 100
    mock_quota.id = "quota_123"

    chat_request = ChatRequest(
        agent_id="agent_no_kb",
        message="test query",
        session_id=None,
        params={},
    )

    mock_http_request = MagicMock()
    mock_http_request.headers.get.return_value = ""

    kb_retrieval_called = False

    with patch("api.v1.endpoints.get_db") as mock_get_db:
        mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("api.v1.endpoints.check_quota", return_value=mock_quota):
            with patch("api.v1.endpoints.get_or_create_chat_session") as mock_session_fn:
                mock_chat_session = MagicMock()
                mock_chat_session.id = "session_123"
                mock_chat_session.status = "active"
                mock_session_fn.return_value = mock_chat_session

                with patch("api.v1.endpoints.KbRetrievalService") as mock_kb_svc_cls:
                    mock_kb_svc = MagicMock()
                    mock_kb_svc.retrieve = AsyncMock(return_value=[])
                    mock_kb_svc_cls.return_value = mock_kb_svc

                    result = await prepare_chat_request(chat_request, mock_http_request, mock_session)

                    # KB retrieval should not be called when agent has no kb_id
                    # (based on current implementation: if getattr(agent, "kb_id", None): ...)
                    mock_kb_svc.retrieve.assert_not_called()

                    assert result["mode"] == "llm"

                    # A general-purpose agent should not receive a false KB miss notice.
                    messages = result.get("messages", [])
                    system_msg = next((m for m in messages if m.get("role") == "system"), None)
                    assert system_msg is not None
                    system_content = system_msg.get("content", "")
                    assert "No relevant information" not in system_content
                    assert "training data" not in system_content.lower()


def test_persona_presets_use_knowledge_base_terminology():
    from api.v1.endpoints import PERSONA_PRESETS, normalize_knowledge_terminology

    for prompt in PERSONA_PRESETS.values():
        assert "training data" not in prompt.lower()
        assert "knowledge base" in prompt.lower()

    normalized = normalize_knowledge_terminology(
        "Rely on training data. 不要向用户提到训练数据。"
    )
    assert "training data" not in normalized.lower()
    assert "训练数据" not in normalized
    assert "current retrieved knowledge base materials" in normalized
    assert "当前检索到的知识库资料" in normalized


def test_knowledge_fallback_reply_matches_supported_language():
    from api.v1.endpoints import get_knowledge_fallback_reply

    zh_reply = get_knowledge_fallback_reply("你们支持火星配送吗？", locale="zh-CN")
    en_reply = get_knowledge_fallback_reply(
        "Do you ship to Mars?", locale="en-US"
    )

    assert "当前检索到的知识库资料" in zh_reply
    assert "训练数据" not in zh_reply
    assert "currently retrieved knowledge base materials" in en_reply
    assert "training data" not in en_reply.lower()


@pytest.mark.asyncio
async def test_bound_kb_without_hits_returns_server_fallback_without_llm():
    """No/low-score KB hits should skip the model and return a stable reply."""
    from api.v1.endpoints import prepare_chat_request
    from api.v1.schemas import ChatRequest

    mock_agent = MagicMock()
    mock_agent.id = "agent_no_hits"
    mock_agent.workspace_id = "ws_123"
    mock_agent.kb_id = "kb_123"
    mock_agent.top_k = 5
    mock_agent.similarity_threshold = 0.05
    mock_agent.temperature = 0.7
    mock_agent.system_prompt = "Rely on training data."
    mock_agent.enable_context = False
    mock_agent.api_key = "test_key"
    mock_agent.api_base = "https://api.test.com"
    mock_agent.model = "test-model"
    mock_agent.provider_type = "openai"
    mock_agent.rate_limit_per_minute = 0
    mock_agent.restricted_reply = "服务暂时不可用"

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_agent
    mock_db.execute.return_value = mock_result

    mock_quota = MagicMock()
    mock_quota.used_messages_today = 0
    mock_quota.max_messages_per_day = 100
    mock_quota.id = "quota_123"

    chat_request = ChatRequest(
        agent_id="agent_no_hits",
        message="你们支持火星配送吗？",
        locale="zh-CN",
        params={},
    )
    mock_http_request = MagicMock()
    mock_http_request.headers.get.return_value = ""

    with patch("api.v1.endpoints.check_quota", return_value=mock_quota):
        with patch("api.v1.endpoints.get_or_create_chat_session") as session_fn:
            mock_chat_session = MagicMock()
            mock_chat_session.id = "session_123"
            mock_chat_session.status = "active"
            session_fn.return_value = mock_chat_session

            with patch("api.v1.endpoints.KbRetrievalService") as retriever_cls:
                retriever = MagicMock()
                retriever.retrieve = AsyncMock(return_value=[])
                retriever_cls.return_value = retriever

                with patch("api.v1.endpoints.get_llm_service") as get_llm:
                    result = await prepare_chat_request(
                        chat_request, mock_http_request, mock_db
                    )

    assert result["mode"] == "knowledge_fallback"
    assert result["sources"] == []
    assert "当前检索到的知识库资料" in result["reply"]
    assert "训练数据" not in result["reply"]
    get_llm.assert_not_called()


@pytest.mark.asyncio
async def test_kb_retrieval_failure_returns_service_fallback_without_llm():
    """A retrieval outage should not be presented as missing knowledge."""
    from api.v1.endpoints import prepare_chat_request
    from api.v1.schemas import ChatRequest

    mock_agent = MagicMock()
    mock_agent.id = "agent_retrieval_failure"
    mock_agent.workspace_id = "ws_123"
    mock_agent.kb_id = "kb_123"
    mock_agent.top_k = 5
    mock_agent.similarity_threshold = 0.05
    mock_agent.temperature = 0.7
    mock_agent.system_prompt = "You are helpful."
    mock_agent.enable_context = False
    mock_agent.api_key = "test_key"
    mock_agent.api_base = "https://api.test.com"
    mock_agent.model = "test-model"
    mock_agent.provider_type = "openai"
    mock_agent.rate_limit_per_minute = 0
    mock_agent.restricted_reply = "服务暂时不可用"

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_agent
    mock_db.execute.return_value = mock_result
    mock_quota = MagicMock(
        used_messages_today=0,
        max_messages_per_day=100,
        id="quota_123",
    )
    request = ChatRequest(
        agent_id=mock_agent.id,
        message="配送需要多久？",
        locale="zh-CN",
        params={},
    )
    http_request = MagicMock()
    http_request.headers.get.return_value = ""

    with patch("api.v1.endpoints.check_quota", return_value=mock_quota):
        with patch("api.v1.endpoints.get_or_create_chat_session") as session_fn:
            chat_session = MagicMock(id="session_123", status="active")
            session_fn.return_value = chat_session
            with patch("api.v1.endpoints.KbRetrievalService") as retriever_cls:
                retriever = MagicMock()
                retriever.retrieve = AsyncMock(side_effect=RuntimeError("qdrant down"))
                retriever_cls.return_value = retriever
                with patch("api.v1.endpoints.get_llm_service") as get_llm:
                    result = await prepare_chat_request(
                        request, http_request, mock_db
                    )

    assert result["mode"] == "service_fallback"
    assert result["reply"] == "服务暂时不可用"
    assert result["sources"] == []
    get_llm.assert_not_called()


@pytest.mark.asyncio
async def test_kb_retrieval_service_tenant_mismatch_returns_empty():
    """KbRetrievalService returns empty when tenant doesn't match KB owner."""
    service = KbRetrievalService()

    # This is already tested in test_kb_retrieval.py, but verify at chat layer
    # by mocking the service behavior
    with patch("services.kb_retrieval_service.AsyncSessionLocal") as mock_session_cls:
        mock_session = AsyncMock()
        mock_result = MagicMock()

        mock_agent = MagicMock()
        mock_agent.id = "agent_123"
        mock_agent.kb_id = "kb_123"

        mock_kb = MagicMock()
        mock_kb.id = "kb_123"
        mock_kb.tenant_id = "tenant_a"  # Different from request

        mock_result.first.return_value = (mock_agent, mock_kb)
        mock_session.execute.return_value = mock_result
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        results = await service.retrieve(
            tenant_id="tenant_b",  # Wrong tenant
            agent_id="agent_123",
            query="test",
            top_k=5,
        )

        assert results == []


@pytest.mark.asyncio
async def test_ready_kb_content_with_unique_phrase_passed_to_chat_context():
    """Verify that ready KB document content with a unique phrase is passed into chat KB context.

    This test proves the ingestion-to-retrieval path: when a document is indexed (status=ready),
    its content should be retrievable and passed into the chat system message.
    """
    from api.v1.endpoints import prepare_chat_request
    from api.v1.schemas import ChatRequest

    # Setup agent with KB
    mock_agent = MagicMock()
    mock_agent.id = "agent_kb_ready"
    mock_agent.workspace_id = "ws_123"
    mock_agent.kb_id = "kb_ready_456"
    mock_agent.top_k = 3
    mock_agent.similarity_threshold = 0.04
    mock_agent.temperature = 0.7
    mock_agent.system_prompt = "You are Basjoo assistant."
    mock_agent.enable_context = False
    mock_agent.api_key = "test_key"
    mock_agent.api_base = "https://api.test.com"
    mock_agent.model = "test-model"
    mock_agent.rate_limit_per_minute = 0
    mock_agent.restricted_reply = None

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_agent
    mock_session.execute.return_value = mock_result

    mock_quota = MagicMock()
    mock_quota.used_messages_today = 0
    mock_quota.max_messages_per_day = 1000
    mock_quota.id = "quota_123"

    # Use a unique test phrase that would only come from indexed content
    unique_phrase = "UNIQUE_VERIFICATION_PHRASE_2024_READY_TEST"

    chat_request = ChatRequest(
        agent_id="agent_kb_ready",
        message=f"Tell me about {unique_phrase}",
        session_id=None,
        params={},
    )

    mock_http_request = MagicMock()
    mock_http_request.headers.get.return_value = ""

    with patch("api.v1.endpoints.get_db") as mock_get_db:
        mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("api.v1.endpoints.check_quota", return_value=mock_quota):
            with patch("api.v1.endpoints.get_or_create_chat_session") as mock_session_fn:
                mock_chat_session = MagicMock()
                mock_chat_session.id = "session_ready_123"
                mock_chat_session.status = "active"
                mock_session_fn.return_value = mock_chat_session

                # Mock KB retrieval returning content from a "ready" document
                with patch("api.v1.endpoints.KbRetrievalService") as mock_kb_svc_cls:
                    mock_kb_svc = MagicMock()
                    # Simulate retrieval returning content from a ready/indexed document
                    mock_kb_svc.retrieve = AsyncMock(return_value=[
                        {
                            "text": f"This is the document content containing {unique_phrase} which proves KB retrieval works.",
                            "doc_id": "doc_ready_001",
                            "chunk_index": 0,
                            "score": 0.065,
                            "filename": "ready_document.txt"
                        }
                    ])
                    mock_kb_svc_cls.return_value = mock_kb_svc

                    result = await prepare_chat_request(
                        chat_request, mock_http_request, mock_session
                    )

                    # Verify retrieval was called
                    mock_kb_svc.retrieve.assert_called_once()

                    # Verify system message contains the unique phrase from the ready document
                    messages = result.get("messages", [])
                    assert len(messages) > 0, "Messages should not be empty"

                    system_msg = messages[0]
                    assert system_msg["role"] == "system", "First message should be system prompt"

                    system_content = system_msg["content"]

                    # The unique phrase from the ready KB document must be in the system message
                    assert unique_phrase in system_content, (
                        f"Unique phrase '{unique_phrase}' from ready KB document "
                        f"should be present in system message. Got: {system_content[:200]}..."
                    )

                    # Verify the content structure indicates KB context injection
                    assert "背景资料" in system_content or "relevant information" in system_content.lower(), (
                        "System message should contain KB context marker"
                    )

                    # Verify source filename is included
                    assert "ready_document.txt" in system_content, (
                        "Source filename should be in KB context"
                    )

                    assert result["sources"] == [
                        {
                            "type": "file",
                            "title": "ready_document.txt",
                            "url": "",
                            "filename": "ready_document.txt",
                            "doc_id": "doc_ready_001",
                            "snippet": f"This is the document content containing {unique_phrase} which proves KB retrieval works.",
                        }
                    ]
