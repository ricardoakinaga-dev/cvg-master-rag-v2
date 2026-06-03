"""
Qdrant Vector Service — handles dense + sparse (BM25) indexing and hybrid search.
"""
import hashlib
import math
import os
import json
import time
import re
import socket
from typing import Optional
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    NamedSparseVector, SparseVector, Batch,
    Filter, FieldCondition, MatchValue,
    SparseIndexParams, SparseVectorParams,
    NamedVector, Range
)
from core.config import (
    QDRANT_HOST, QDRANT_PORT, QDRANT_COLLECTION,
    EMBEDDING_DIM, RRF_K, DEFAULT_TOP_K, QDRANT_CHECK_COMPATIBILITY,
    DOCUMENTS_DIR, EMBEDDING_MODEL, RERANKING_ENABLED, RERANKING_METHOD,
)
from models.schemas import Chunk, SearchRequest, SearchResponse, SearchResultItem
from services.document_registry import (
    get_document_registry as _registry_get_document_registry,
    get_document_metadata as _registry_get_document_metadata,
    list_document_items as _registry_list_document_items,
    get_corpus_overview as _registry_get_corpus_overview,
)

# Module-level reranker instances (lazy-initialized on first use), keyed by method name
_bm25f_reranker: Optional["BM25FReranker"] = None
_neural_reranker: Optional["NeuralReranker"] = None


def _get_reranker(method: str) -> Optional[object]:
    """
    Return the reranker instance for the given method.
    Returns None for "none" or if the reranker cannot be initialized.
    """
    global _bm25f_reranker, _neural_reranker
    if method == "bm25f":
        if _bm25f_reranker is None:
            _bm25f_reranker = BM25FReranker()
        return _bm25f_reranker
    elif method == "neural":
        if _neural_reranker is None:
            _neural_reranker = NeuralReranker()
        return _neural_reranker
    return None

SPARSE_MODULUS = 100_000
MEANINGLESS_QUERY_TOKENS = {
    "a", "ao", "aos", "as", "ate", "até", "com", "como", "da", "das", "de", "do", "dos",
    "e", "em", "essa", "esse", "esta", "este", "foi", "na", "nas", "no", "nos", "o", "os",
    "ou", "para", "por", "qual", "quais", "quando", "quanto", "que", "se", "sem", "ser",
    "sao", "são", "sua", "suas", "seu", "seus", "uma", "um", "usa", "usada", "usado",
    "utiliza", "utilizado",
}
LOW_SIGNAL_DOMAIN_TOKENS = {
    "animal", "animais", "paciente", "pacientes",
    "gato", "gatos", "felino", "felinos", "cat", "cats", "feline", "felines",
    "cao", "caes", "cão", "cães", "cachorro", "cachorros", "cachorra", "cachorras",
    "canino", "caninos", "dog", "dogs", "canine", "canines",
    "sintoma", "sintomas", "sinal", "sinais",
    "doenca", "doenças", "doença", "doencas",
    "protocolo", "protocolos", "protocol", "protocols", "approach", "management",
}


_client: Optional[QdrantClient] = None
_document_metadata_cache: dict[tuple[str, str], dict] = {}
QDRANT_UPSERT_BATCH_SIZE = max(1, int(os.getenv("QDRANT_UPSERT_BATCH_SIZE", "128")))
QDRANT_COLLECTION_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def validate_qdrant_collection_name(collection_name: str | None) -> str:
    """Return a safe Qdrant collection name or raise ValueError."""
    if not isinstance(collection_name, str):
        collection_name = None
    normalized = (collection_name or QDRANT_COLLECTION).strip()
    if not QDRANT_COLLECTION_NAME_PATTERN.fullmatch(normalized):
        raise ValueError("qdrant_collection must use 1-64 letters, numbers, '_' or '-'")
    return normalized


def list_qdrant_collections() -> list[str]:
    """List existing Qdrant collection names."""
    client = get_client()
    collections = client.get_collections()
    return sorted(collection.name for collection in collections.collections)


def _sparse_hash(token: str) -> int:
    """Deterministic hash for sparse vector indexing (MD5-based)."""
    return int(hashlib.md5(token.encode()).hexdigest(), 16) % SPARSE_MODULUS


def _tokenize_terms(text: str, min_len: int = 2) -> list[str]:
    """Tokenize and drop low-signal terms that pollute lexical retrieval."""
    tokens = []
    for token in re.findall(r"\w{2,}", text.lower()):
        if len(token) < min_len:
            continue
        if token in MEANINGLESS_QUERY_TOKENS:
            continue
        tokens.append(token)
    return tokens


def _content_query_terms(text: str) -> set[str]:
    """Higher-signal query terms used to reject generic overlap."""
    return {
        token for token in _tokenize_terms(text, min_len=2)
        if token not in LOW_SIGNAL_DOMAIN_TOKENS and not token.isdigit()
    }


def _lexical_diversity_ratio(text: str) -> float:
    """
    Estimate how repetitive a chunk is.

    Very repetitive operational chunks can dominate dense retrieval even when they
    carry almost no discriminative signal for the query. We only penalize this
    pattern for dense-only evidence later on.
    """
    tokens = _tokenize_terms(text, min_len=2)
    if len(tokens) < 20:
        return 1.0
    return len(set(tokens)) / len(tokens)


def _query_overlap_stats(query: str, text: str) -> dict[str, float | int]:
    """
    Measure lexical support between the user query and a retrieved chunk.

    We separate numeric from non-numeric terms because incidental year/id matches
    are common in enterprise corpora and should not make an off-scope result look
    trustworthy on their own.
    """
    query_terms = set(_tokenize_terms(query, min_len=2))
    text_terms = set(_tokenize_terms(text, min_len=2))
    query_content_terms = _content_query_terms(query)
    matched_content_terms = query_content_terms.intersection(text_terms)

    matched_terms = query_terms.intersection(text_terms)
    query_non_numeric_terms = {term for term in query_terms if not term.isdigit()}
    matched_non_numeric_terms = {term for term in matched_terms if not term.isdigit()}

    non_numeric_total = len(query_non_numeric_terms)
    non_numeric_matched = len(matched_non_numeric_terms)

    return {
        "query_terms": len(query_terms),
        "matched_terms": len(matched_terms),
        "query_non_numeric_terms": non_numeric_total,
        "matched_non_numeric_terms": non_numeric_matched,
        "non_numeric_overlap_ratio": (
            non_numeric_matched / non_numeric_total if non_numeric_total else 0.0
        ),
        "query_content_terms": len(query_content_terms),
        "matched_content_terms": len(matched_content_terms),
        "content_overlap_ratio": (
            len(matched_content_terms) / len(query_content_terms) if query_content_terms else 0.0
        ),
    }


def _has_minimal_query_support(query: str, text: str) -> bool:
    """
    Return True when a candidate has at least some non-numeric lexical support
    for the query. Purely numeric overlap (years, IDs) does not count.
    """
    stats = _query_overlap_stats(query, text)
    if int(stats["query_content_terms"]) > 0:
        return int(stats["matched_content_terms"]) > 0
    if int(stats["query_non_numeric_terms"]) == 0:
        return True
    return int(stats["matched_non_numeric_terms"]) > 0


def _candidate_fingerprint(item: dict) -> tuple[str, str]:
    """
    Build a stable fingerprint for near-duplicate candidates.

    We deduplicate within the same document so that repeated chunks with identical
    text do not consume the entire top-k.
    """
    text = re.sub(r"\s+", " ", str(item.get("text", "")).strip().lower())
    return (str(item.get("document_id") or ""), text)


def _dedupe_redundant_candidates(candidates: list[dict]) -> list[dict]:
    """Keep the strongest candidate for each document/text fingerprint."""
    deduped: dict[tuple[str, str], dict] = {}
    for item in candidates:
        fingerprint = _candidate_fingerprint(item)
        current = deduped.get(fingerprint)
        if current is None:
            deduped[fingerprint] = item
            continue
        current_score = float(current.get("confidence_score", current.get("score", 0.0)) or 0.0)
        item_score = float(item.get("confidence_score", item.get("score", 0.0)) or 0.0)
        if item_score > current_score:
            deduped[fingerprint] = item
    return list(deduped.values())


def _qdrant_host_reachable(timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((QDRANT_HOST, QDRANT_PORT), timeout=timeout):
            return True
    except OSError:
        return False


def create_qdrant_client(timeout: float | None = 1.0) -> QdrantClient:
    """Create a Qdrant client compatible with both older and newer local clients."""
    client_kwargs = {
        "host": QDRANT_HOST,
        "port": QDRANT_PORT,
    }
    if timeout is not None:
        client_kwargs["timeout"] = timeout

    if QDRANT_CHECK_COMPATIBILITY:
        try:
            return QdrantClient(**client_kwargs, check_compatibility=True)
        except TypeError as exc:
            if "check_compatibility" not in str(exc):
                raise

    return QdrantClient(**client_kwargs)


def get_client() -> QdrantClient:
    global _client
    if _client is None:
        if not _qdrant_host_reachable():
            raise RuntimeError(f"Qdrant host {QDRANT_HOST}:{QDRANT_PORT} not reachable")
        _client = create_qdrant_client(timeout=1.0)
    return _client


def _collection_exists(client: QdrantClient, collection_name: str | None = None) -> bool:
    collection = validate_qdrant_collection_name(collection_name)
    collections = client.get_collections()
    return any(item.name == collection for item in collections.collections)


def get_document_registry(workspace_id: str = "default") -> dict[str, dict]:
    """Load document metadata from the canonical raw/chunk files on disk."""
    return _registry_get_document_registry(workspace_id)


def get_document_metadata(document_id: str, workspace_id: str = "default") -> Optional[dict]:
    """Return metadata for a single document from the canonical registry."""
    return _registry_get_document_metadata(document_id, workspace_id)


def _get_cached_document_metadata(document_id: str, workspace_id: str = "default") -> dict:
    cache_key = (workspace_id, document_id)
    if cache_key not in _document_metadata_cache:
        _document_metadata_cache[cache_key] = get_document_metadata(document_id, workspace_id) or {}
    return _document_metadata_cache[cache_key]


def _build_citation_payload(chunk: Chunk, workspace_id: str) -> dict:
    """Build source metadata stored with each Qdrant point for citations."""
    doc_meta = _get_cached_document_metadata(chunk.document_id, workspace_id)
    filename = doc_meta.get("filename")
    source_title = doc_meta.get("source_title") or filename
    page_hint = chunk.page_hint

    payload = {
        "document_filename": filename,
        "source_title": source_title,
        "source": source_title or filename,
        "source_type": doc_meta.get("source_type"),
        "catalog_scope": doc_meta.get("catalog_scope"),
        "document_page_count": doc_meta.get("page_count"),
        "publication_year": doc_meta.get("publication_year"),
        "edition": doc_meta.get("edition"),
        "authors": doc_meta.get("authors"),
        "publisher": doc_meta.get("publisher"),
        "isbn": doc_meta.get("isbn"),
        "tags": doc_meta.get("tags") or [],
    }

    if page_hint is not None:
        payload["page_start"] = page_hint
        payload["page_end"] = page_hint

    return {key: value for key, value in payload.items() if value not in (None, "", [])}


def list_document_items(
    workspace_id: str = "default",
    limit: int = 100,
    offset: int = 0,
    source_type: Optional[str] = None,
    status: Optional[str] = None,
    query: Optional[str] = None,
) -> dict:
    """Return a paginated, filterable document list from the canonical registry."""
    return _registry_list_document_items(
        workspace_id=workspace_id,
        limit=limit,
        offset=offset,
        source_type=source_type,
        status=status,
        query=query,
    )


def get_corpus_overview(workspace_id: str = "default") -> dict:
    """Return a compact overview of the canonical corpus on disk."""
    return _registry_get_corpus_overview(workspace_id)


def ensure_collection(
    vector_size: int = EMBEDDING_DIM,
    recreate: bool = False,
    collection_name: str | None = None,
):
    """
    Create collection if it doesn't exist.
    Uses dense vector (1536 dim) + sparse BM25 vector.
    """
    client = get_client()
    collection = validate_qdrant_collection_name(collection_name)

    if recreate:
        if _collection_exists(client, collection):
            try:
                client.delete_collection(collection_name=collection)
            except Exception:
                pass
            for _ in range(10):
                if not _collection_exists(client, collection):
                    break
                time.sleep(0.1)

    if not _collection_exists(client, collection):
        # Collection doesn't exist — create it
        client.create_collection(
            collection_name=collection,
            vectors_config={
                "dense": VectorParams(
                    size=vector_size,
                    distance=Distance.COSINE
                )
            },
            sparse_vectors_config={
                "sparse": SparseVectorParams(
                    index=SparseIndexParams(
                        on_disk=False
                    )
                )
            }
        )


def index_chunks(
    chunks: list[Chunk],
    embeddings: list[list[float]],
    workspace_id: str = "default",
    ingestion_id: str | None = None,
    collection_name: str | None = None,
):
    """
    Index chunks with dense + sparse (BM25) vectors into Qdrant.
    Each chunk gets a dense vector (OpenAI) and a sparse BM25 vector.
    """
    client = get_client()
    collection = validate_qdrant_collection_name(collection_name)
    ensure_collection(collection_name=collection)

    points = []
    for chunk, embedding in zip(chunks, embeddings):
        # BM25 sparse vector — tokenize and create sparse
        sparse_vec = _create_bm25_sparse(chunk.text)

        # Use hash of chunk_id as point ID to avoid collision across documents
        # Qdrant requires unsigned integer; chunk_index alone causes overwrite when
        # multiple documents have chunks 0-N with same indices
        payload = {
            "chunk_id": chunk.chunk_id,
            "document_id": chunk.document_id,
            "workspace_id": chunk.workspace_id,
            "text": chunk.text[:2000],  # truncate for payload
            "page_hint": chunk.page_hint,
            "chunk_index": chunk.chunk_index,
            "strategy": chunk.strategy,
            "qdrant_collection": collection,
            **_build_citation_payload(chunk, workspace_id),
        }
        if ingestion_id:
            payload["ingestion_id"] = ingestion_id

        point = PointStruct(
            id=abs(hash(chunk.chunk_id)) % (2**63),
            vector={
                "dense": embedding,
                "sparse": sparse_vec
            },
            payload=payload,
        )
        points.append(point)

    # Large documents can exceed Qdrant's request payload limit if every point is
    # sent in a single upsert. Split the write into smaller batches.
    for start in range(0, len(points), QDRANT_UPSERT_BATCH_SIZE):
        client.upsert(
            collection_name=collection,
            points=points[start:start + QDRANT_UPSERT_BATCH_SIZE]
        )


def _create_bm25_sparse(text: str) -> SparseVector:
    """
    Create BM25 sparse vector from text.
    Simple tokenization + tf weighting.
    """
    import math
    # Simple tokenization
    tokens = _tokenize_terms(text, min_len=2)

    # Count frequencies
    freq = {}
    for tok in tokens:
        freq[tok] = freq.get(tok, 0) + 1

    # Create sparse vector (indices + values)
    # Handle hash collisions by aggregating values for same index
    index_scores: dict[int, float] = {}
    for tok, count in freq.items():
        idx = _sparse_hash(tok)
        tf_score = math.log(1 + count)
        if idx in index_scores:
            index_scores[idx] += tf_score  # sum for collision
        else:
            index_scores[idx] = tf_score

    indices = list(index_scores.keys())
    values = list(index_scores.values())

    return SparseVector(
        indices=indices,
        values=values
    )


def search_hybrid(
    request: SearchRequest,
    workspace_filter: str = "default"
) -> SearchResponse:
    """
    Perform hybrid search: dense + sparse with RRF fusion.
    Returns top_k results with scores.
    """
    start_time = time.time()
    metadata_map = {
        **{
            item["document_id"]: item
            for item in list_document_items(request.workspace_id, limit=10000, offset=0).get("items", [])
        },
        **get_document_registry(request.workspace_id),
    }
    query_filter = _build_qdrant_filter(request.workspace_id, request.filters)
    candidate_limit = max(request.top_k * 10, 20)
    canonical_only = bool(request.filters and request.filters.get("catalog_scope") == "canonical")

    # 1. Dense search (embedding query)
    dense_results = []
    qdrant_available = True
    client = None
    try:
        client = get_client()
        ensure_collection()
        query_embedding = _embed_query(request.query)
        dense_results = client.query_points(
            collection_name=QDRANT_COLLECTION,
            query=query_embedding,
            using="dense",
            limit=candidate_limit,
            query_filter=query_filter
        ).points
    except Exception:
        qdrant_available = False

    # 2. Sparse search (BM25 on query terms)
    sparse_results = []
    try:
        sparse_results = _bm25_search(
            request.query,
            request.workspace_id,
            limit=candidate_limit,
            filters=request.filters,
        )
    except Exception:
        sparse_results = []

    # 3. If dense retrieval is unavailable, keep BM25/sparse results.
    # Only fallback to local chunks when sparse retrieval also yields nothing.
    if not qdrant_available and not dense_results and not sparse_results:
        sparse_results = _search_chunks_on_disk(
            query=request.query,
            workspace_id=request.workspace_id,
            limit=candidate_limit,
            filters=request.filters,
            metadata_map=metadata_map,
            canonical_only=canonical_only,
        )

    # 4. RRF Fusion
    fused = _rrf_fusion(dense_results, sparse_results, k=RRF_K)
    fused = _apply_post_filters(fused, request.filters, metadata_map)
    for item in fused:
        item["confidence_score"] = _compute_confidence_score(item, request.query)
        doc_meta = metadata_map.get(item.get("document_id"), {})
        # Enrich with canonical document metadata for reranker (filename, tags).
        # Operational uploads should not overwrite canonical ranking context when
        # the query is expected to resolve against the canonical corpus.
        item["document_filename"] = doc_meta.get("filename")
        item["tags"] = doc_meta.get("tags") or []
    fused = _dedupe_redundant_candidates(fused)
    fused.sort(
        key=lambda item: (
            float(item.get("confidence_score", 0.0) or 0.0),
            float(item.get("score", 0.0) or 0.0),
        ),
        reverse=True,
    )

    # 4b. Optional reranking — runs on all candidates before top-k cut
    # Applies if: request explicitly requests it, OR global config enables it and request doesn't override
    reranking_requested = (
        request.reranking is True
        or (RERANKING_ENABLED and request.reranking is not False)
    )
    should_rerank = fused and reranking_requested
    reranking_applied = False
    reranking_method: str | None = None
    # Determine effective method: request override takes precedence over global config
    effective_method = request.reranking_method if request.reranking_method else RERANKING_METHOD
    reranker = _get_reranker(effective_method) if effective_method != "none" else None
    if reranking_requested and effective_method != "none" and reranker is not None:
        reranking_applied = True
        reranking_method = effective_method
    if should_rerank and reranker is not None:
        if reranker is not None:
            fused = reranker.rerank(request.query, fused)

    # 5. Apply top_k
    top_results = fused[:request.top_k]

    # 6. Build response
    results = []
    for item in top_results:
        doc_meta = metadata_map.get(item["document_id"], {})
        # Use the score produced by reranking (blended) when reranking was applied,
        # otherwise use the pre-computed confidence score.
        if reranking_applied:
            final_score = item.get("score", item.get("confidence_score", 0.0))
        else:
            final_score = item.get("confidence_score", 0.0)
        results.append(SearchResultItem(
            chunk_id=item["chunk_id"],
            document_id=item["document_id"],
            text=item["text"],
            score=final_score,
            page_hint=item.get("page_hint"),
            source=f"dense+sparse_rrf+{reranking_method}" if reranking_applied else "dense+sparse_rrf",
            document_filename=doc_meta.get("filename"),
            workspace_id=request.workspace_id,
            source_type=doc_meta.get("source_type"),
            tags=doc_meta.get("tags") or [],
        ))

    # RRF scores are rank-based, not probabilities.
    # low_confidence is True when retrieval fails to find relevant content.
    #
    # Detection rules:
    # 1. No results → low_confidence
    # 2. Top score extremely low (dense similarity < 0.01) → low_confidence
    # 3. Sparse found nothing AND dense score < 0.05 → low_confidence
    #    (query terms not in corpus, even if vector similarity is decent)
    # 4. Large gap between top-1 and top-2 (top/score < 0.3) → low_confidence
    low_confidence = False
    sparse_hits = len(sparse_results) > 0
    top_score = results[0].score if results else 0.0
    second_score = results[1].score if len(results) >= 2 else 0.0
    quality_floor = request.threshold if request.threshold > 0 else 0.0
    strongest_sparse_signal = max((float(item.get("sparse_score", 0.0) or 0.0) for item in top_results), default=0.0)
    has_supported_result = any(_has_minimal_query_support(request.query, result.text) for result in results)
    query_has_numeric_token = any(token.isdigit() for token in _tokenize_terms(request.query, min_len=2))

    if len(results) == 0:
        low_confidence = True
    elif not has_supported_result and query_has_numeric_token:
        low_confidence = True
    elif not sparse_hits and top_score < 0.25:
        low_confidence = True
    elif top_score < 0.25 and strongest_sparse_signal < 0.5:
        low_confidence = True
    elif top_score < quality_floor:
        low_confidence = True
    elif second_score > 0 and top_score / second_score < 0.3:
        low_confidence = True

    retrieval_time = int((time.time() - start_time) * 1000)
    scores_breakdown = None
    if request.include_raw_scores:
        scores_breakdown = {
            "dense_max": max((item.get("dense_score", 0.0) for item in fused), default=0.0),
            "sparse_max": max((item.get("sparse_score", 0.0) for item in fused), default=0.0),
            "rrf_final_score": top_results[0]["score"] if top_results else 0.0,
            "confidence_final_score": top_results[0].get("confidence_score", 0.0) if top_results else 0.0,
        }

    return SearchResponse(
        query=request.query,
        workspace_id=request.workspace_id,
        results=results,
        total_candidates=len(fused),
        low_confidence=low_confidence,
        retrieval_time_ms=retrieval_time,
        method="híbrida",
        scores_breakdown=scores_breakdown,
        reranking_applied=reranking_applied,
        reranking_method=reranking_method,
    )


def _embed_query(query: str) -> list[float]:
    """Embed the query using OpenAI."""
    from services.embedding_service import get_embedding
    return get_embedding(query)


def _tokenize_for_fallback(text: str) -> set[str]:
    return set(_tokenize_terms(text, min_len=3))


def _search_chunks_on_disk(
    query: str,
    workspace_id: str,
    limit: int = 20,
    filters: Optional[dict] = None,
    metadata_map: Optional[dict[str, dict]] = None,
    canonical_only: bool = False,
) -> list[dict]:
    """Simple local keyword fallback when Qdrant is unreachable."""
    base_dir = DOCUMENTS_DIR / workspace_id
    chunk_files = list(base_dir.glob("*_chunks.json"))
    if not chunk_files:
        return []

    query_tokens = _tokenize_for_fallback(query)
    if not query_tokens:
        return []

    scored = []
    for chunk_file in chunk_files:
        try:
            with open(chunk_file, "r", encoding="utf-8") as f:
                chunks = json.load(f)
        except Exception:
            continue

        for chunk in chunks:
            if chunk.get("workspace_id") != workspace_id:
                continue
            if canonical_only:
                doc_meta = (metadata_map or {}).get(chunk.get("document_id"), {})
                if doc_meta.get("catalog_scope", "canonical") != "canonical":
                    continue

            chunk_text = str(chunk.get("text", ""))
            chunk_tokens = _tokenize_for_fallback(chunk_text)
            overlap = query_tokens.intersection(chunk_tokens)
            if not overlap:
                continue

            candidate = {
                "chunk_id": chunk.get("chunk_id"),
                "document_id": chunk.get("document_id"),
                "text": chunk_text[:2000],
                "score": len(overlap) / len(query_tokens),
                "page_hint": chunk.get("page_hint"),
                "strategy": chunk.get("strategy"),
            }
            if not _matches_filters(candidate, filters, metadata_map or {}):
                continue

            scored.append({
                **candidate,
                "dense_score": 0.0,
                "sparse_score": candidate["score"],
            })

    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:limit]


def _bm25_search(
    query: str,
    workspace_id: str,
    limit: int = 20,
    filters: Optional[dict] = None,
):
    """Simple BM25 search using sparse vector."""
    try:
        client = get_client()
    except Exception:
        return []

    # Tokenize query
    tokens = _tokenize_terms(query, min_len=2)
    if not tokens:
        return []

    # Create sparse vector from query terms
    # Handle hash collisions
    index_scores: dict[int, float] = {}
    for tok in tokens:
        idx = _sparse_hash(tok)
        index_scores[idx] = index_scores.get(idx, 0.0) + 1.0

    indices = list(index_scores.keys())
    values = list(index_scores.values())

    sparse_query = SparseVector(indices=indices, values=values)

    try:
        results = client.query_points(
            collection_name=QDRANT_COLLECTION,
            query=sparse_query,
            using="sparse",
            limit=limit,
            query_filter=_build_qdrant_filter(workspace_id, filters)
        ).points
        filtered = []
        for r in results:
            score = float(r.score or 0.0)
            text = r.payload.get("text", "")
            if score <= 0:
                continue
            if not _has_minimal_query_support(query, text):
                continue
            filtered.append({
                "chunk_id": r.payload["chunk_id"],
                "document_id": r.payload["document_id"],
                "text": text,
                "score": score,
                "page_hint": r.payload.get("page_hint"),
                "strategy": r.payload.get("strategy"),
                "dense_score": 0.0,
                "sparse_score": score,
                "document_filename": r.payload.get("document_filename"),
                "tags": r.payload.get("tags") or [],
            })
        return filtered
    except Exception:
        return []


def _rrf_fusion(
    dense_results: list,
    sparse_results: list,
    k: int = 60
) -> list[dict]:
    """
    Reciprocal Rank Fusion combining dense and sparse rankings.
    """
    scores = {}

    # Process dense results
    for rank, result in enumerate(dense_results):
        payload = result.payload if hasattr(result, "payload") else result
        chunk_id = payload["chunk_id"]
        score = 1.0 / (k + rank + 1)
        if chunk_id not in scores:
            scores[chunk_id] = {
                "chunk_id": chunk_id,
                "document_id": payload.get("document_id"),
                "text": payload.get("text", ""),
                "page_hint": payload.get("page_hint"),
                "strategy": payload.get("strategy"),
                "document_filename": payload.get("document_filename"),
                "tags": payload.get("tags") or [],
                "score": 0.0,
                "dense_score": 0.0,
                "sparse_score": 0.0,
            }
        scores[chunk_id]["score"] += score
        scores[chunk_id]["dense_score"] = max(
            scores[chunk_id]["dense_score"],
            getattr(result, "score", 0.0),
        )

    # Process sparse results
    for rank, result in enumerate(sparse_results):
        chunk_id = result["chunk_id"]
        score = 1.0 / (k + rank + 1)
        if chunk_id in scores:
            scores[chunk_id]["score"] += score
        else:
            scores[chunk_id] = {
                "chunk_id": chunk_id,
                "document_id": result.get("document_id"),
                "text": result.get("text", ""),
                "page_hint": result.get("page_hint"),
                "strategy": result.get("strategy"),
                "document_filename": result.get("document_filename"),
                "tags": result.get("tags") or [],
                "score": score,
                "dense_score": 0.0,
                "sparse_score": 0.0,
            }
        scores[chunk_id]["sparse_score"] = max(
            scores[chunk_id]["sparse_score"],
            result.get("sparse_score", result.get("score", 0.0)),
        )

    # Sort by combined score
    ranked = sorted(scores.values(), key=lambda x: x["score"], reverse=True)
    return ranked


class BM25FReranker:
    """
    Local BM25F reranker. Reorders retrieval candidates using
    bag-of-words overlap with IDF weighting and positional decay.

    Does NOT require external API calls. Deterministic and fast.

    scoring:
    - Term overlap score = sum(IDF(t) * tf(t) * pos_decay(t)) for each query term
    - IDF derived from corpus (computed from candidates + query).
    - Position decay: earlier occurrence = higher weight.
    - Fields: body text weighted higher than filename/tags.
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75, avg_doc_len: int = 200):
        self.k1 = k1  # term frequency saturation
        self.b = b    # document length normalization
        self.avg_doc_len = avg_doc_len
        self._idf_cache: dict[str, float] = {}

    def rerank(self, query: str, candidates: list[dict]) -> list[dict]:
        if not candidates:
            return candidates

        query_terms = self._content_terms(query)
        if not query_terms:
            return candidates

        # Build IDF from candidates
        idf = self._compute_idf(query_terms, [c.get("text", "") for c in candidates])

        # Score each candidate
        scored = []
        for cand in candidates:
            text = cand.get("text", "")
            filename = cand.get("document_filename", "") or ""
            tags = " ".join(cand.get("tags", []))
            doc_len = len(text.split())

            body_score = self._bm25f_term(
                query_terms, text, idf, doc_len,
                field_weight=1.0, pos_decay=True
            )
            filename_score = self._bm25f_term(
                query_terms, filename, idf, max(len(filename.split()), 1),
                field_weight=0.3, pos_decay=False
            )
            tags_score = self._bm25f_term(
                query_terms, tags, idf, max(len(tags.split()), 1),
                field_weight=0.2, pos_decay=False
            )

            bm25f_score = body_score + filename_score + tags_score

            # Preserve original score for comparison
            new_cand = dict(cand)
            new_cand["original_score"] = cand.get("score", 0.0)
            new_cand["bm25f_score"] = bm25f_score
            # Blend: geometric mean of confidence_score (normalized) and BM25F score,
            # so the blend stays in the 0-1 range and is comparable to confidence_score.
            confidence = cand.get("confidence_score", 0.0)
            if confidence > 0 and bm25f_score > 0:
                new_cand["score"] = (confidence * bm25f_score) ** 0.5
            else:
                new_cand["score"] = max(confidence, bm25f_score)
            scored.append(new_cand)

        # Sort by the final blended score (geometric mean of original and BM25F),
        # descending. Tie-break by original score for stability.
        scored.sort(key=lambda x: (x.get("score", 0.0), x.get("original_score", 0.0)), reverse=True)
        return scored

    def _bm25f_term(
        self,
        terms: list[str],
        field_text: str,
        idf: dict[str, float],
        doc_len: int,
        field_weight: float,
        pos_decay: bool,
    ) -> float:
        field_terms = self._tokenize(field_text)
        if not field_terms:
            return 0.0
        score = 0.0
        for rank, term in enumerate(field_terms):
            if term not in terms:
                continue
            tf = field_terms.count(term)
            tf_norm = (tf * (self.k1 + 1)) / (tf + self.k1 * (1 - self.b + self.b * doc_len / max(self.avg_doc_len, 1)))
            pos = 1.0 / (rank + 1) if pos_decay else 1.0
            score += idf.get(term, 0.0) * tf_norm * pos * field_weight
        return score

    def _compute_idf(self, query_terms: list[str], texts: list[str]) -> dict[str, float]:
        texts_digest = hashlib.md5("\x1f".join(texts).encode("utf-8")).hexdigest()
        cache_key = (tuple(sorted(set(query_terms))), len(texts), texts_digest)
        if cache_key in self._idf_cache:
            return self._idf_cache[cache_key]

        n = len(texts)
        if n == 0:
            idf = {t: 1.0 for t in query_terms}
            self._idf_cache[cache_key] = idf
            return idf

        idf = {}
        all_terms = set(query_terms)
        for text in texts:
            all_terms.update(self._tokenize(text))

        for term in all_terms:
            df = sum(1 for text in texts if term in self._tokenize(text))
            # Smoothed IDF: log((n - df + 0.5) / (df + 0.5))
            import math
            idf[term] = math.log((n - df + 0.5) / (df + 0.5) + 1.0)

        self._idf_cache[cache_key] = idf
        return idf

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return _tokenize_terms(text, min_len=2)

    @staticmethod
    def _content_terms(text: str) -> list[str]:
        terms = [
            term for term in _tokenize_terms(text, min_len=2)
            if term not in LOW_SIGNAL_DOMAIN_TOKENS and not term.isdigit()
        ]
        return terms or _tokenize_terms(text, min_len=2)


def _normalize_sparse_score(score: float) -> float:
    """Map open-ended BM25-like scores into a stable 0-1 range without saturation."""
    if score <= 0:
        return 0.0
    return max(0.0, min(1.0, math.tanh(score / 4.0)))


def _normalize_rrf_score(score: float) -> float:
    """Expose rank-only RRF evidence on a comparable 0-1 scale."""
    if score <= 0:
        return 0.0
    return max(0.0, min(1.0, math.tanh(score * 30.0)))


def _compute_confidence_score(item: dict, query: str | None = None) -> float:
    """
    Convert dense/sparse evidence into a human-readable confidence score.

    We keep RRF as the ranking mechanism, but expose a score that can be
    compared against the documented retrieval threshold.
    """
    dense = max(0.0, min(1.0, float(item.get("dense_score", 0.0) or 0.0)))
    sparse = _normalize_sparse_score(float(item.get("sparse_score", 0.0) or 0.0))
    rrf = _normalize_rrf_score(float(item.get("score", 0.0) or 0.0))
    diversity = _lexical_diversity_ratio(item.get("text", ""))
    has_minimal_support = True
    if query:
        has_minimal_support = _has_minimal_query_support(query, item.get("text", ""))

    if dense <= 0 and sparse <= 0:
        return max(0.0, min(1.0, rrf))

    if dense > 0 and sparse > 0:
        stronger = max(dense, sparse)
        weaker = min(dense, sparse)
        combined = stronger + (weaker * 0.15) + (rrf * 0.10)
        if sparse > 0 and not has_minimal_support and dense < 0.55:
            combined = min(combined, 0.19)
        return max(0.0, min(1.0, combined))

    score = max(dense, sparse)
    if dense > 0 and sparse <= 0:
        # Dense-only hits with extremely repetitive text are usually spurious.
        if diversity < 0.2:
            score *= max(0.1, diversity / 0.2)
        score += rrf * 0.10
    elif sparse > 0 and not has_minimal_support and dense < 0.55:
        score = min(score, 0.19)
    else:
        score += rrf * 0.10

    return max(0.0, min(1.0, score))


class NeuralReranker:
    """
    Neural cross-encoder-style reranker.

    Reorders candidates by computing embedding similarity between the query
    and each candidate text. Uses the existing embedding infrastructure
    (OpenAI-compatible API via embedding_service) so no new external
    dependency is required.

    Scoring:
    - Embed query + candidate text (truncated to 8000 tokens)
    - Cosine similarity between query embedding and candidate embedding
    - Blend: geometric mean of confidence_score and neural similarity

    The blend keeps scores in 0-1 range and is comparable to BM25F blend.
    Falls back to returning candidates unchanged if embeddings are unavailable
    (offline mode or no API key).
    """

    def __init__(self, embed_batch_size: int = 8):
        self.embed_batch_size = embed_batch_size
        self._embedding_cache: dict[str, list[float]] = {}

    def rerank(self, query: str, candidates: list[dict]) -> list[dict]:
        if not candidates or not query:
            return candidates

        # Try to get embeddings; fall back to unchanged on failure
        try:
            query_emb = self._embed_text(query)
        except Exception:
            # Embedding failed (offline, no API key, etc.) — return unchanged
            return candidates

        # Batch-embed candidate texts
        texts = [c.get("text", "")[:8000] for c in candidates]
        try:
            cand_embs = self._embed_batch(texts)
        except Exception:
            return candidates

        scored = []
        for cand, cand_emb in zip(candidates, cand_embs):
            try:
                sim = self._cosine(query_emb, cand_emb)
            except Exception:
                sim = 0.0

            new_cand = dict(cand)
            new_cand["original_score"] = cand.get("score", 0.0)
            new_cand["neural_score"] = sim
            # Blend: geometric mean of confidence_score (normalized) and neural similarity,
            # so the blend stays in 0-1 range and is comparable to BM25F blend.
            confidence = cand.get("confidence_score", 0.0)
            if confidence > 0 and sim > 0:
                new_cand["score"] = (confidence * sim) ** 0.5
            else:
                new_cand["score"] = max(confidence, sim)
            scored.append(new_cand)

        scored.sort(key=lambda x: (x.get("score", 0.0), x.get("original_score", 0.0)), reverse=True)
        return scored

    def _embed_text(self, text: str) -> list[float]:
        """Embed a single text, with simple in-process caching."""
        if text in self._embedding_cache:
            return self._embedding_cache[text]
        from services.embedding_service import get_embedding
        emb = get_embedding(text)
        self._embedding_cache[text] = emb
        return emb

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts."""
        from services.embedding_service import get_embeddings_batch
        return get_embeddings_batch(texts)

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        """Cosine similarity between two vectors."""
        import math
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)


def delete_document_chunks(document_id: str, collection_name: str | None = None):
    """Delete all chunks for a document from Qdrant."""
    client = get_client()
    collection = validate_qdrant_collection_name(collection_name)
    try:
        client.delete(
            collection_name=collection,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="document_id",
                        match=MatchValue(value=document_id)
                    )
                ]
            )
        )
    except Exception:
        pass


def delete_ingestion_points(
    ingestion_id: str,
    workspace_id: str = "default",
    collection_name: str | None = None,
):
    """Delete all Qdrant points produced by a specific ingestion attempt."""
    client = get_client()
    collection = validate_qdrant_collection_name(collection_name)
    try:
        client.delete(
            collection_name=collection,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="ingestion_id",
                        match=MatchValue(value=ingestion_id),
                    ),
                    FieldCondition(
                        key="workspace_id",
                        match=MatchValue(value=workspace_id),
                    ),
                ]
            )
        )
    except Exception:
        pass


def delete_workspace_chunks(workspace_id: str, collection_name: str | None = None):
    """Delete all chunks for a workspace from Qdrant."""
    client = get_client()
    collection = validate_qdrant_collection_name(collection_name)
    try:
        client.delete(
            collection_name=collection,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="workspace_id",
                        match=MatchValue(value=workspace_id)
                    )
                ]
            )
        )
    except Exception:
        pass


def _build_qdrant_filter(workspace_id: str, filters: Optional[dict] = None) -> Optional[Filter]:
    """Build Qdrant filter for fields that are actually indexed in payload."""
    must = []
    if workspace_id:
        must.append(
            FieldCondition(
                key="workspace_id",
                match=MatchValue(value=workspace_id),
            )
        )

    filters = filters or {}
    if filters.get("document_id"):
        must.append(
            FieldCondition(
                key="document_id",
                match=MatchValue(value=filters["document_id"]),
            )
        )

    if filters.get("strategy"):
        must.append(
            FieldCondition(
                key="strategy",
                match=MatchValue(value=filters["strategy"]),
            )
        )

    page_min = filters.get("page_hint_min")
    page_max = filters.get("page_hint_max")
    if page_min is not None or page_max is not None:
        must.append(
            FieldCondition(
                key="page_hint",
                range=Range(
                    gte=page_min,
                    lte=page_max,
                ),
            )
        )

    return Filter(must=must) if must else None


def _apply_post_filters(candidates: list[dict], filters: Optional[dict], metadata_map: dict[str, dict]) -> list[dict]:
    if not candidates:
        return []

    normalized_filters = dict(filters or {})
    return [item for item in candidates if _matches_filters(item, normalized_filters, metadata_map)]


def _matches_filters(item: dict, filters: Optional[dict], metadata_map: dict[str, dict]) -> bool:
    """Return True when the item matches the supported retrieval filters."""
    if not filters:
        return True

    document_id = item.get("document_id")
    page_hint = item.get("page_hint")
    metadata = metadata_map.get(document_id, {})
    catalog_scope = metadata.get("catalog_scope", "canonical")

    if filters.get("document_id") and document_id != filters["document_id"]:
        return False

    if filters.get("catalog_scope") and catalog_scope != filters["catalog_scope"]:
        return False

    if filters.get("source_type") and metadata.get("source_type") != filters["source_type"]:
        return False

    if filters.get("strategy") and item.get("strategy") != filters["strategy"]:
        return False

    page_min = filters.get("page_hint_min")
    if page_min is not None and (page_hint is None or page_hint < page_min):
        return False

    page_max = filters.get("page_hint_max")
    if page_max is not None and (page_hint is None or page_hint > page_max):
        return False

    required_tags = filters.get("tags") or []
    if required_tags:
        available_tags = set(metadata.get("tags") or [])
        if not available_tags.intersection(required_tags):
            return False

    return True
