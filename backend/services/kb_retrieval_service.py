"""KB retrieval service: validate agent/kb/tenant, embed query, Qdrant search + threshold filter."""

import logging
import re
import unicodedata
from typing import Any

from sqlalchemy import select

from database import AsyncSessionLocal
from models import Agent, KnowledgeBase
from services.document_parser import DocumentParser
from services.kb_document_processor import get_embedding_api_key
from services.kb_service import KbService
from services.qdrant_service import QdrantKbService

logger = logging.getLogger(__name__)

DOCUMENT_DIVERSITY_SCORE_RATIO = 0.85
EXACT_IDENTIFIER_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)+(?![A-Za-z0-9])"
)
QUERY_NOISE_PHRASES = (
    "请分别告诉我",
    "请告诉我",
    "请问",
    "是什么",
    "是多少",
    "多少",
    "什么",
)
ENGLISH_CODE_INTENT_PATTERN = re.compile(
    r"\b(?:verification|validation)\s+code\b",
    re.IGNORECASE,
)
ENGLISH_CODE_TOPIC_PHRASES = (
    (
        re.compile(r"\b(?:human|customer)\s+support\b|\bhuman\s+agent\b"),
        "人工服务资料校验码",
    ),
    (re.compile(r"\b(?:shipping|delivery)\b"), "配送资料校验码"),
    (re.compile(r"\breturns?\b"), "退货资料校验码"),
    (re.compile(r"\bpayment\b"), "支付资料校验码"),
    (re.compile(r"\bproduct\b"), "产品资料校验码"),
)
MIN_EXACT_PHRASE_LENGTH = 6
MAX_DECOMPOSED_QUERIES = 8
PARALLEL_QUERY_MARKERS = ("各自", "分别")
PARALLEL_QUERY_PREFIX_PATTERN = re.compile(
    r"^(?:请)?(?:列出|说明|提供|告诉我|帮我列出)"
)
PARALLEL_QUERY_COUNT_SUFFIX_PATTERN = re.compile(
    r"(?:\d+|[一二三四五六七八九十]+)份资料$"
)


def _select_diverse_hits(
    raw_hits: list[dict[str, Any]],
    *,
    top_k: int,
    threshold: float,
) -> list[dict[str, Any]]:
    """Prefer each document's best chunk, then fill remaining slots by rank."""
    eligible_hits = [
        hit for hit in raw_hits if hit.get("score", 0.0) >= threshold
    ]
    if not eligible_hits:
        return []

    diversity_cutoff = (
        eligible_hits[0].get("score", 0.0) * DOCUMENT_DIVERSITY_SCORE_RATIO
    )
    priority_hits = [
        hit for hit in eligible_hits if hit.get("score", 0.0) >= diversity_cutoff
    ]
    diverse_hits: list[dict[str, Any]] = []
    seen_documents: set[str] = set()

    for rank, hit in enumerate(priority_hits):
        payload = hit.get("payload", {})
        document_key = str(
            payload.get("doc_id")
            or payload.get("filename")
            or payload.get("source_url")
            or f"unscoped-hit:{rank}"
        )
        if document_key in seen_documents:
            continue
        seen_documents.add(document_key)
        diverse_hits.append(hit)

    if len(diverse_hits) < top_k:
        selected_hit_ids = {id(hit) for hit in diverse_hits}
        remaining_hits = [
            hit for hit in eligible_hits if id(hit) not in selected_hit_ids
        ]
        diverse_hits.extend(remaining_hits[: top_k - len(diverse_hits)])

    return diverse_hits[:top_k]


def _normalize_lexical_text(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def _extract_exact_identifiers(query: str) -> list[str]:
    identifiers = EXACT_IDENTIFIER_PATTERN.findall(query)
    return [
        identifier
        for identifier in identifiers
        if any(character.isalpha() for character in identifier)
        and any(character.isdigit() for character in identifier)
    ]


def _extract_exact_phrases(query: str) -> list[str]:
    phrases: list[str] = []
    for segment in re.split(r"[，,。！？!?；;：:\n]", query):
        cleaned = segment
        for noise in QUERY_NOISE_PHRASES:
            cleaned = cleaned.replace(noise, "")
        cleaned = re.sub(r"[^\w\u3400-\u9fff]+", "", cleaned)
        if len(cleaned) >= MIN_EXACT_PHRASE_LENGTH:
            phrases.append(cleaned)
    return phrases


def _expand_cross_language_query(query: str) -> str:
    """Add one Chinese metadata phrase for explicit English code queries."""
    normalized_query = _normalize_lexical_text(query)
    if not ENGLISH_CODE_INTENT_PATTERN.search(normalized_query):
        return query

    for topic_pattern, canonical_phrase in ENGLISH_CODE_TOPIC_PHRASES:
        if topic_pattern.search(normalized_query):
            return f"{query} {canonical_phrase}"
    return query


def _strong_lexical_score(query: str, text: str) -> int:
    """Return a score only for exact identifiers or long, complete phrases."""
    normalized_query = _normalize_lexical_text(query)
    normalized_text = _normalize_lexical_text(text)

    matched_identifiers = [
        identifier
        for identifier in _extract_exact_identifiers(normalized_query)
        if identifier in normalized_text
    ]
    if matched_identifiers:
        return 10_000 + sum(len(identifier) for identifier in matched_identifiers)

    compact_text = re.sub(r"[^\w\u3400-\u9fff]+", "", normalized_text)
    matched_phrases = [
        phrase
        for phrase in _extract_exact_phrases(normalized_query)
        if phrase in compact_text
    ]
    return max((len(phrase) for phrase in matched_phrases), default=0)


def _hit_key(hit: dict[str, Any]) -> tuple[Any, ...]:
    payload = hit.get("payload", {})
    scoped_key = (
        payload.get("doc_id"),
        payload.get("chunk_index"),
        payload.get("filename"),
        payload.get("source_url"),
    )
    if any(value is not None for value in scoped_key):
        return scoped_key
    return ("unscoped-hit", id(hit))


def _decompose_parallel_query(query: str) -> list[str]:
    """Split explicit Chinese parallel requests into focused retrieval queries."""
    marker = next(
        (candidate for candidate in PARALLEL_QUERY_MARKERS if candidate in query),
        None,
    )
    if marker is None:
        return []

    subjects_text, target_text = query.split(marker, maxsplit=1)
    subjects_text = PARALLEL_QUERY_PREFIX_PATTERN.sub("", subjects_text.strip())
    subjects_text = PARALLEL_QUERY_COUNT_SUFFIX_PATTERN.sub("", subjects_text)
    subjects_text = subjects_text.removesuffix("资料").strip()
    target_text = target_text.strip().removeprefix("的")
    target_text = re.sub(r"[。！？!?]+$", "", target_text).strip()
    if not subjects_text or not target_text:
        return []

    subjects = [
        subject.strip()
        for subject in re.split(r"[、，,]|(?:以及|和)", subjects_text)
        if subject.strip()
    ]
    if not 3 <= len(subjects) <= MAX_DECOMPOSED_QUERIES:
        return []
    if any(len(subject) > 16 for subject in subjects) or len(target_text) > 24:
        return []

    return [f"{subject}资料{target_text}" for subject in subjects]


def _merge_decomposed_hits(
    query_hits: list[list[dict[str, Any]]],
    *,
    top_k: int,
) -> list[dict[str, Any]]:
    """Prefer one distinct document per subquery, then fill remaining slots."""
    merged: list[dict[str, Any]] = []
    seen_documents: set[str] = set()

    for hits in query_hits:
        for rank, hit in enumerate(hits):
            payload = hit.get("payload", {})
            document_key = str(
                payload.get("doc_id")
                or payload.get("filename")
                or payload.get("source_url")
                or f"unscoped-hit:{id(hits)}:{rank}"
            )
            if document_key in seen_documents:
                continue
            seen_documents.add(document_key)
            merged.append(hit)
            break

        if len(merged) >= top_k:
            return merged[:top_k]

    selected_keys = {_hit_key(hit) for hit in merged}
    for hits in query_hits:
        for hit in hits:
            hit_key = _hit_key(hit)
            if hit_key in selected_keys:
                continue
            selected_keys.add(hit_key)
            merged.append(hit)
            if len(merged) >= top_k:
                return merged[:top_k]

    return merged


def _apply_lexical_rescue(
    query: str,
    raw_hits: list[dict[str, Any]],
    selected_hits: list[dict[str, Any]],
    *,
    top_k: int,
    threshold: float,
) -> list[dict[str, Any]]:
    """Keep dense retrieval, but rescue strong exact matches from its candidate pool."""
    lexical_matches = []
    for rank, hit in enumerate(raw_hits):
        if hit.get("score", 0.0) < threshold:
            continue
        text = str(hit.get("payload", {}).get("text") or "")
        lexical_score = _strong_lexical_score(query, text)
        if lexical_score:
            lexical_matches.append((lexical_score, rank, hit))

    if not lexical_matches:
        return selected_hits

    lexical_matches.sort(key=lambda item: (-item[0], item[1]))
    rescued_hits = [item[2] for item in lexical_matches]
    rescued_keys = {_hit_key(hit) for hit in rescued_hits}
    rescued_hits.extend(
        hit for hit in selected_hits if _hit_key(hit) not in rescued_keys
    )
    return rescued_hits[:top_k]


class KbRetrievalService:
    def __init__(self):
        self.parser = DocumentParser()
        self.qdrant = QdrantKbService()
        self.kb_svc = KbService()
        self.default_threshold = 0.6  # Fallback default, but agent threshold is preferred

    async def retrieve(
        self,
        tenant_id: str | None,
        agent_id: str,
        query: str,
        top_k: int = 5,
        threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve top-K chunks from agent's bound KB with double isolation.

        If tenant_id is None (chat path), the effective tenant for the Qdrant
        payload filter is derived from the agent's KB (ensuring isolation is still
        enforced by the specific KB's tenant_id).

        Returns: [{"text":, "doc_id":, "chunk_index":, "score":, "filename":?}, ...]
        Returns [] if agent has no kb_id bound or validation fails.
        """
        if not agent_id:
            return []

        async with AsyncSessionLocal() as session:
            # 1. Validate agent exists and get kb_id (outer join so agent without kb still found)
            stmt = (
                select(Agent, KnowledgeBase)
                .join(KnowledgeBase, Agent.kb_id == KnowledgeBase.id, isouter=True)
                .where(Agent.id == agent_id)
            )
            res = await session.execute(stmt)
            row = res.first()
            if not row or not row[0]:
                logger.info(f"Agent {agent_id} not found")
                return []
            agent, kb = row[0], row[1]

            if not agent.kb_id or not kb:
                logger.info(
                    f"Agent {agent_id} has no kb_id bound, returning empty retrieval"
                )
                return []

            # 2. Derive effective tenant and enforce match
            # When tenant_id is None (chat path), derive from KB to allow retrieval
            # When tenant_id is explicit, it must match KB's tenant
            effective_tenant = tenant_id or kb.tenant_id
            if tenant_id is not None and kb.tenant_id != tenant_id:
                logger.warning(
                    f"Tenant mismatch: requested {tenant_id} but KB {kb.id} belongs to {kb.tenant_id}"
                )
                return []

            # 3. Decompose explicit parallel requests, then embed in one batch.
            # Get decrypted API key from agent based on embedding_provider
            api_key = get_embedding_api_key(agent)
            decomposed_queries = _decompose_parallel_query(query)[:top_k]
            retrieval_queries = decomposed_queries or [
                _expand_cross_language_query(query)
            ]
            if decomposed_queries:
                logger.info(
                    "KB retrieval decomposed parallel query into %s parts",
                    len(decomposed_queries),
                )

            try:
                embeddings = await self.parser.embed_texts(
                    retrieval_queries,
                    kb.embedding_model,
                    kb.embedding_base_url,
                    api_key=api_key,
                )
                if not embeddings or len(embeddings) != len(retrieval_queries):
                    return []
            except Exception as e:
                logger.warning(f"Query embed failed: {e}")
                return []

            # 4. Resolve the effective threshold once for every subquery.
            # Use explicit threshold > agent config > service default
            agent_threshold = getattr(agent, "similarity_threshold", None)
            if threshold is not None:
                eff_threshold = threshold
            elif agent_threshold is not None:
                eff_threshold = agent_threshold
            else:
                eff_threshold = self.default_threshold

            # 5. Search every focused query with the same tenant/KB isolation.
            query_hits: list[list[dict[str, Any]]] = []
            for retrieval_query, query_vec in zip(
                retrieval_queries, embeddings, strict=True
            ):
                raw_hits = await self.qdrant.search_kb(
                    kb_id=kb.id,
                    tenant_id=effective_tenant,
                    query_vector=query_vec,
                    top_k=top_k * 2,
                )
                selected_for_query = _select_diverse_hits(
                    raw_hits,
                    top_k=top_k,
                    threshold=eff_threshold,
                )
                selected_for_query = _apply_lexical_rescue(
                    retrieval_query,
                    raw_hits,
                    selected_for_query,
                    top_k=top_k,
                    threshold=eff_threshold,
                )
                query_hits.append(selected_for_query)

            selected_hits = (
                _merge_decomposed_hits(query_hits, top_k=top_k)
                if decomposed_queries
                else query_hits[0]
            )
            results = []
            for h in selected_hits:
                p = h.get("payload", {})
                score = h.get("score", 0.0)
                results.append(
                    {
                        "text": p.get("text", ""),
                        "doc_id": p.get("doc_id", ""),
                        "chunk_index": p.get("chunk_index", 0),
                        "score": round(score, 4),
                        "filename": p.get("filename"),
                        # Include source info for proper display
                        "source_type": p.get("source_type", "file"),
                        "source_url": p.get("source_url", ""),
                        "source_title": p.get("source_title", ""),
                    }
                )

            logger.info(
                f"KB retrieve tenant={tenant_id} agent={agent_id} kb={kb.id} "
                f"got {len(results)} chunks (threshold={eff_threshold})"
            )
            return results
