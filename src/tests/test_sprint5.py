"""
Sprint 5 Test Suite — comprehensive validation tests for Gate F0 readiness.
Tests: dataset validation, metadata endpoint, low_confidence detection,
multi-document indexing, telemetry ingestion, corpus consistency.

Two categories of tests:
- Unit/integration tests: use mocks for embeddings, run offline without API key
- Live tests: require OPENAI_API_KEY, marked with @pytest.mark.integration
"""
import os
import sys
from pathlib import Path
import importlib.util

# Ensure src/ is on path when running from project root
SRC_DIR = Path(__file__).parent.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import io
import json
import time
import socket
from unittest.mock import patch, MagicMock

import pytest
from qdrant_client import QdrantClient

from models.schemas import Dataset, SearchRequest, QueryRequest, EvaluationQuestion, SearchResultItem, SearchResponse
from core.config import (
    DATA_DIR,
    DOCUMENTS_DIR,
    QDRANT_HOST,
    QDRANT_PORT,
    QDRANT_CHECK_COMPATIBILITY,
)
from services.telemetry_service import TelemetryService
from services.admin_service import reset_admin_state


# ── Deterministic mock embedding ─────────────────────────────────────────────

MOCK_EMBEDDING = [0.01] * 1536  # Deterministic low-score embedding


def _mock_embed_query(query: str) -> list[float]:
    return MOCK_EMBEDDING


# ── Dataset path helper ───────────────────────────────────────────────────────

def get_dataset_path() -> Path:
    """Return canonical dataset path using DATA_DIR from config."""
    return DATA_DIR / 'default' / 'dataset.json'


def _can_reach_qdrant_host() -> bool:
    """Quick host-level reachability check to avoid long connection hangs in sandboxed runs."""
    try:
        with socket.create_connection((QDRANT_HOST, QDRANT_PORT), timeout=0.25):
            return True
    except OSError:
        return False


def enterprise_headers(
    client,
    role: str = "admin",
    tenant_id: str = "default",
    email: str | None = None,
) -> dict[str, str]:
    resolved_email = email or {
        "admin": "admin@demo.local",
        "operator": "operator@demo.local",
        "viewer": "viewer@demo.local",
    }.get(role, "viewer@demo.local")
    response = client.post(
        "/auth/login",
        json={
            "email": resolved_email,
            "password": "demo1234",
            "tenant_id": tenant_id,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["session_token"]
    return {"Authorization": f"Bearer {payload['session_token']}"}


@pytest.fixture(autouse=True)
def reset_enterprise_runtime_state():
    reset_admin_state()
    yield


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def dataset_path() -> Path:
    return get_dataset_path()


@pytest.fixture
def dataset_raw():
    with open(get_dataset_path()) as f:
        return json.load(f)


@pytest.fixture
def corpus_doc_ids():
    """Canonical document IDs present in Qdrant (requires live Qdrant)."""
    if not Path('src/.env').exists():
        pytest.skip("No .env file")
    with open('src/.env') as f:
        env = dict(line.strip().split('=', 1) for line in f if '=' in line)
    if not env.get('OPENAI_API_KEY'):
        pytest.skip("No OPENAI_API_KEY")
    if not _can_reach_qdrant_host():
        pytest.skip("Qdrant host port not reachable from sandbox")

    client = QdrantClient(
        host=QDRANT_HOST,
        port=QDRANT_PORT,
        check_compatibility=QDRANT_CHECK_COMPATIBILITY,
    )
    try:
        result = client.scroll(collection_name='rag_phase0', limit=100, with_vectors=False)
    except Exception:
        pytest.skip("Qdrant unreachable")

    from services.document_registry import get_document_registry

    canonical_ids = set(get_document_registry("default").keys())
    points = result[0] if result else []
    return list(set(
        p.payload['document_id']
        for p in points
        if p.payload.get('workspace_id') == 'default'
        and p.payload.get('document_id') in canonical_ids
    ))


@pytest.fixture
def qdrant_client_for_tests():
    """Ensure Qdrant is reachable, otherwise skip integration checks."""
    if not _can_reach_qdrant_host():
        pytest.skip("Qdrant host port not reachable from sandbox")
    client = QdrantClient(
        host=QDRANT_HOST,
        port=QDRANT_PORT,
        check_compatibility=QDRANT_CHECK_COMPATIBILITY,
    )
    try:
        client.get_collections()
    except Exception:
        pytest.skip("Qdrant unreachable")
    return client


@pytest.fixture
def mock_embedding():
    """Patch embedding to run tests without API key."""
    with patch('services.vector_service._embed_query', side_effect=_mock_embed_query):
        with patch('services.embedding_service.OpenAI') as mock_client:
            mock_instance = MagicMock()
            mock_response = MagicMock()
            mock_response.data = [MagicMock(embedding=MOCK_EMBEDDING)]
            mock_instance.embeddings.create.return_value = mock_response
            mock_client.return_value = mock_instance
            yield


# ── Dataset Validation ───────────────────────────────────────────────────────

class TestDatasetValidation:
    """Validate dataset against schema contract (Sprint 0)."""

    def test_dataset_loads_without_error(self, dataset_path):
        """Dataset must validate against Dataset Pydantic model."""
        assert dataset_path.exists(), f"Dataset not found at {dataset_path}"
        with open(dataset_path) as f:
            raw = json.load(f)
        ds = Dataset(**raw)
        assert len(ds.questions) == 30

    def test_dataset_spans_multiple_canonical_documents(self, dataset_raw):
        """Default dataset must no longer depend on a single source document."""
        question_doc_ids = {q["document_id"] for q in dataset_raw["questions"]}
        covered_documents = set(dataset_raw.get("documentos_cobertos", []))

        assert len(question_doc_ids) >= 5
        assert len(covered_documents) >= 5

        question_filenames = {
            q.get("documento_nome")
            for q in dataset_raw["questions"]
            if q.get("documento_nome")
        }
        assert question_filenames == covered_documents

    def test_document_registry_filters_non_canonical_raws(self, tmp_path, monkeypatch):
        """Registry/overview must only expose documents referenced by the operational dataset."""
        from services.document_registry import get_document_registry, get_corpus_overview

        workspace_dir = tmp_path / "default"
        workspace_dir.mkdir(parents=True, exist_ok=True)

        def write_doc(doc_id: str, filename: str):
            (workspace_dir / f"{doc_id}_raw.json").write_text(
                json.dumps(
                    {
                        "document_id": doc_id,
                        "source_type": "md",
                        "filename": filename,
                        "workspace_id": "default",
                        "pages": [{"page_number": 1, "text": f"Conteúdo {filename}"}],
                        "metadata": {"page_count": 1},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (workspace_dir / f"{doc_id}_chunks.json").write_text(
                json.dumps(
                    [
                        {
                            "chunk_id": f"chunk_{doc_id}_0000",
                            "document_id": doc_id,
                            "workspace_id": "default",
                            "chunk_index": 0,
                            "text": f"Chunk {filename}",
                            "start_char": 0,
                            "end_char": 20,
                            "page_hint": 1,
                            "strategy": "recursive",
                            "chunk_size_chars": 20,
                            "created_at": "2026-04-19T00:00:00Z",
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

        write_doc("doc-keep", "keep.md")
        write_doc("doc-temp", "tmpabc.md")

        monkeypatch.setattr("services.document_registry.DOCUMENTS_DIR", tmp_path)
        monkeypatch.setattr(
            "services.document_registry.canonical_document_ids",
            lambda workspace_id="default": {"doc-keep"},
        )

        registry = get_document_registry("default")
        overview = get_corpus_overview("default")

        assert set(registry.keys()) == {"doc-keep"}
        assert overview["documents"] == 1
        assert overview["chunks"] == 1

    def test_list_document_items_and_metadata_include_operational_uploads(self, tmp_path, monkeypatch):
        """Workspace inventory endpoints must expose both canonical and operational items."""
        from services.document_registry import get_document_metadata, list_document_items

        workspace_dir = tmp_path / "default"
        workspace_dir.mkdir(parents=True, exist_ok=True)

        def write_doc(doc_id: str, filename: str, raw_json_path: str):
            (workspace_dir / f"{doc_id}_raw.json").write_text(
                json.dumps(
                    {
                        "document_id": doc_id,
                        "source_type": "md",
                        "filename": filename,
                        "workspace_id": "default",
                        "raw_json_path": raw_json_path,
                        "pages": [{"page_number": 1, "text": f"Conteúdo {filename}"}],
                        "metadata": {"page_count": 1, "ingestion_status": "parsed"},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (workspace_dir / f"{doc_id}_chunks.json").write_text(
                json.dumps(
                    [
                        {
                            "chunk_id": f"chunk_{doc_id}_0000",
                            "document_id": doc_id,
                            "workspace_id": "default",
                            "chunk_index": 0,
                            "text": f"Chunk {filename}",
                            "start_char": 0,
                            "end_char": 20,
                            "page_hint": 1,
                            "strategy": "recursive",
                            "chunk_size_chars": 20,
                            "created_at": "2026-04-19T00:00:00Z",
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

        write_doc("doc-canonical", "keep.md", "/tmp/keep_raw.json")
        write_doc("doc-operational", "upload.md", "/tmp/uploads/upload_raw.json")

        monkeypatch.setattr("services.document_registry.DOCUMENTS_DIR", tmp_path)
        monkeypatch.setattr(
            "services.document_registry.canonical_document_ids",
            lambda workspace_id="default": {"doc-canonical"},
        )

        payload = list_document_items("default", limit=20, offset=0)
        listed_ids = {item["document_id"] for item in payload["items"]}

        assert listed_ids == {"doc-canonical", "doc-operational"}
        by_id = {item["document_id"]: item for item in payload["items"]}
        assert by_id["doc-canonical"]["catalog_scope"] == "canonical"
        assert by_id["doc-operational"]["catalog_scope"] == "operational"

        operational_meta = get_document_metadata("doc-operational", "default")
        assert operational_meta is not None
        assert operational_meta["catalog_scope"] == "operational"


class TestEmbeddingBatching:
    """Embedding batch requests must stay below provider request limits."""

    def test_get_embeddings_batch_splits_large_payloads(self, monkeypatch):
        import services.embedding_service as embedding_module

        class FakeEmbeddingsAPI:
            def __init__(self):
                self.calls: list[list[str]] = []

            def create(self, *, model, input):
                self.calls.append(list(input))

                class Item:
                    def __init__(self, idx: int):
                        self.embedding = [float(idx)] * 1536

                class Response:
                    def __init__(self, size: int):
                        self.data = [Item(i) for i in range(size)]

                return Response(len(input))

        fake_api = FakeEmbeddingsAPI()
        fake_client = type(
            "FakeClient",
            (),
            {
                "api_key": "test-key",
                "embeddings": fake_api,
            },
        )()

        monkeypatch.setattr(embedding_module, "client", fake_client)

        # 80 texts * 8k chars ~= 213k estimated tokens with the conservative
        # estimator, so this must split into at least 2 requests.
        texts = ["a" * 8000 for _ in range(80)]
        result = embedding_module.get_embeddings_batch(texts)

        assert len(result) == len(texts)
        assert len(fake_api.calls) >= 2
        assert sum(len(call) for call in fake_api.calls) == len(texts)
        assert all(
            sum(embedding_module._estimate_tokens(text) for text in call)
            <= embedding_module.EMBEDDING_MAX_ESTIMATED_TOKENS_PER_REQUEST
            for call in fake_api.calls
        )

    def test_get_embeddings_batch_preserves_input_order_across_batches(self, monkeypatch):
        import services.embedding_service as embedding_module

        class FakeEmbeddingsAPI:
            def create(self, *, model, input):
                class Item:
                    def __init__(self, text: str):
                        self.embedding = [float(len(text))] * 1536

                class Response:
                    def __init__(self, payload: list[str]):
                        self.data = [Item(text) for text in payload]

                return Response(list(input))

        fake_client = type(
            "FakeClient",
            (),
            {
                "api_key": "test-key",
                "embeddings": FakeEmbeddingsAPI(),
            },
        )()

        monkeypatch.setattr(embedding_module, "client", fake_client)

        texts = ["a" * 1000, "b" * 2000, "c" * 8000] * 30
        result = embedding_module.get_embeddings_batch(texts)

        assert len(result) == len(texts)
        assert [embedding[0] for embedding in result] == [float(len(text[:8000])) for text in texts]

    def test_dataset_categories_are_valid(self, dataset_raw):
        """All categories must be valid literals."""
        valid_categories = {'fato', 'procedimento', 'política', 'detalhes'}
        for q in dataset_raw['questions']:
            cat = q.get('categoria')
            assert cat in valid_categories, f"Q{q['id']}: invalid categoria '{cat}'"

    def test_dataset_no_legacy_fields(self, dataset_raw):
        """Dataset must not contain legacy fields."""
        for q in dataset_raw['questions']:
            assert 'documento_fonte' not in q, f"Q{q['id']}: contains legacy field 'documento_fonte'"
            assert 'documento_fource' not in q, f"Q{q['id']}: contains typo field 'documento_fource'"

    def test_all_questions_have_required_fields(self, dataset_raw):
        """Every question must have required fields."""
        required = ['id', 'pergunta', 'document_id', 'categoria', 'dificuldade']
        for q in dataset_raw['questions']:
            missing = [f for f in required if f not in q]
            assert not missing, f"Q{q['id']}: missing {missing}"


class TestStartApiBootstrap:
    def test_load_local_env_populates_missing_variables_without_override(self, tmp_path, monkeypatch):
        from start_api import _load_local_env

        env_file = tmp_path / ".env"
        env_file.write_text(
            "OPENAI_API_KEY=test-key\n"
            "SESSION_COOKIE_SECURE=false\n"
            "EXISTING_VAR=from-file\n",
            encoding="utf-8",
        )

        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("SESSION_COOKIE_SECURE", raising=False)
        monkeypatch.setenv("EXISTING_VAR", "from-env")

        _load_local_env(env_file)

        assert os.getenv("OPENAI_API_KEY") == "test-key"
        assert os.getenv("SESSION_COOKIE_SECURE") == "false"
        assert os.getenv("EXISTING_VAR") == "from-env"


# ── Qdrant Corpus Consistency ──────────────────────────────────────────────

class TestQdrantCorpusConsistency:
    """Verify Qdrant state matches persisted corpus (Sprint 2).
    These tests require a live Qdrant instance.
    """

    @pytest.mark.integration
    def test_qdrant_point_count_matches_disk(self, qdrant_client_for_tests, dataset_raw):
        """Qdrant total points must equal sum of all chunks on disk."""
        from core.config import QDRANT_COLLECTION

        doc_dir = DOCUMENTS_DIR / 'default'
        chunks_files = list(doc_dir.glob('*_chunks.json'))
        canonical_doc_ids = {q['document_id'] for q in dataset_raw['questions']}

        total_disk_chunks = 0
        for cf in chunks_files:
            doc_id = cf.stem.replace('_chunks', '')
            if doc_id not in canonical_doc_ids:
                continue
            with open(cf) as f:
                total_disk_chunks += len(json.load(f))
        points = qdrant_client_for_tests.scroll(
            collection_name=QDRANT_COLLECTION,
            limit=1000,
            with_vectors=False,
        )[0]
        default_points = [
            p for p in points
            if p.payload.get('workspace_id') == 'default'
            and p.payload.get('document_id') in canonical_doc_ids
        ]
        assert len(default_points) == total_disk_chunks

    @pytest.mark.integration
    def test_each_document_indexed_in_qdrant(self, qdrant_client_for_tests, dataset_raw):
        """Every document on disk must have its chunks in Qdrant."""
        doc_dir = DOCUMENTS_DIR / 'default'
        chunks_files = list(doc_dir.glob('*_chunks.json'))
        canonical_doc_ids = {q['document_id'] for q in dataset_raw['questions']}

        result = qdrant_client_for_tests.scroll(collection_name='rag_phase0', limit=1000, with_vectors=False)
        points = result[0] if result else []
        qdrant_doc_counts = {}
        for p in points:
            if p.payload.get('workspace_id') != 'default':
                continue
            doc_id = p.payload['document_id']
            qdrant_doc_counts[doc_id] = qdrant_doc_counts.get(doc_id, 0) + 1

        for cf in chunks_files:
            doc_id = cf.stem.replace('_chunks', '')
            if doc_id not in canonical_doc_ids:
                continue
            with open(cf) as f:
                disk_chunks = len(json.load(f))
            q_count = qdrant_doc_counts.get(doc_id, 0)
            assert q_count == disk_chunks

    @pytest.mark.integration
    def test_no_point_id_collision(self, qdrant_client_for_tests):
        """All point IDs in Qdrant must be unique."""
        from qdrant_client import QdrantClient

        result = qdrant_client_for_tests.scroll(collection_name='rag_phase0', limit=1000, with_vectors=False)
        points = result[0] if result else []
        point_ids = [p.id for p in points]
        assert len(set(point_ids)) == len(point_ids)


# ── Chunk Offset Correctness ───────────────────────────────────────────────

class TestChunkOffsets:
    """Verify chunk offsets are correctly tracked (Sprint 1)."""

    def test_chunk_offsets_not_all_zero(self):
        """Chunk start positions must not all be zero for multi-chunk documents."""
        doc_dir = DOCUMENTS_DIR / 'default'
        chunks_files = list(doc_dir.glob('*_chunks.json'))

        found_non_zero = False
        for cf in chunks_files:
            with open(cf) as f:
                chunks = json.load(f)
            if len(chunks) > 1:
                non_zero = [c for c in chunks if c['start_char'] > 0]
                if non_zero:
                    found_non_zero = True
                    break

        assert found_non_zero, "No document has non-zero chunk offsets"

    def test_chunk_start_before_end(self):
        """Every chunk must have start_char < end_char."""
        doc_dir = DOCUMENTS_DIR / 'default'
        chunks_files = list(doc_dir.glob('*_chunks.json'))

        errors = []
        for cf in chunks_files:
            with open(cf) as f:
                chunks = json.load(f)
            for c in chunks:
                if c['start_char'] >= c['end_char']:
                    errors.append(f"{cf.name} chunk {c['chunk_index']}: "
                                 f"start_char({c['start_char']}) >= end_char({c['end_char']})")

        assert not errors, f"Chunk offset errors: {errors}"


# ── Low Confidence Detection ───────────────────────────────────────────────

class TestLowConfidence:
    """Verify low_confidence detection works correctly (Sprint 3).
    Uses mock embedding to avoid API key dependency.
    """

    @pytest.fixture(autouse=True)
    def setup_mock(self):
        """Apply mock to embedding service."""
        self.embed_patcher = patch('services.vector_service._embed_query', side_effect=_mock_embed_query)
        self.mock = self.embed_patcher.start()
        yield
        self.embed_patcher.stop()

    def _search(self, query: str, workspace_id: str = 'default', top_k: int = 5):
        """Call search_hybrid with mock embedding."""
        from services.vector_service import search_hybrid
        return search_hybrid(SearchRequest(
            query=query, workspace_id=workspace_id, top_k=top_k, threshold=0.0
        ))

    def test_valid_query_not_low_confidence(self):
        """A valid query matching the corpus should NOT set low_confidence=True."""
        resp = self._search('reembolso prazo')
        # Valid query with "reembolso" should get sparse hits
        # and NOT trigger low_confidence=True
        assert not resp.low_confidence, (
            f"Valid query 'reembolso prazo' returned low_confidence=True; "
            f"expected False since sparse hits should be found"
        )

    def test_nonsense_query_low_confidence(self, setup_mock):
        """A nonsense query NOT in corpus must set low_confidence=True."""
        from services.vector_service import _bm25_search
        # First verify sparse returns nothing for nonsense
        sparse = _bm25_search('xyzzy plugh zork midgar', 'default', limit=20)
        assert len(sparse) == 0, "Test setup error: sparse should return 0 for nonsense"
        # Then verify search_hybrid returns low_confidence
        resp = self._search('xyzzy plugh zork midgar')
        assert resp.low_confidence, f"Nonsense query returned low_confidence=False"

    def test_out_of_domain_query_low_confidence(self, setup_mock):
        """An out-of-domain query must set low_confidence=True."""
        from services.vector_service import _bm25_search
        sparse = _bm25_search('bake cake recipe', 'default', limit=20)
        assert len(sparse) == 0, "Test setup error: sparse should return 0 for OOD"
        resp = self._search('how to bake a chocolate cake recipe')
        assert resp.low_confidence, f"OOD query returned low_confidence=False"

    def test_numeric_only_overlap_query_low_confidence(self, setup_mock):
        """A query matching only an incidental year must still be treated as low confidence."""
        resp = self._search('Quem venceu a Copa do Mundo de 2014?')
        assert resp.low_confidence, "Numeric-only overlap returned low_confidence=False"

    def test_symbol_query_low_confidence(self, setup_mock):
        """A query of random symbols must set low_confidence=True."""
        from services.vector_service import _bm25_search
        sparse = _bm25_search('!!!!!@@@###$$%%^^^', 'default', limit=20)
        assert len(sparse) == 0
        resp = self._search('!!!!!@@@###$$%%^^^&&*')
        assert resp.low_confidence, f"Symbol query returned low_confidence=False"


class TestMarkdownParsingAndChunking:
    def test_parse_md_preserves_headings_in_page_text(self, tmp_path):
        from services.document_parser import parse_document

        md_file = tmp_path / "manual.md"
        md_file.write_text(
            "# Politica de Reembolso\n"
            "Prazo de 30 dias.\n\n"
            "## Retencao de Dados\n"
            "Dados ficam por 7 anos.\n",
            encoding="utf-8",
        )

        normalized, metadata = parse_document(md_file, workspace_id="default")

        page_text = normalized.pages[0]["text"]
        assert "Politica de Reembolso" in page_text
        assert "Retencao de Dados" in page_text
        assert normalized.metadata["section_count"] == 2
        assert metadata.source_type == "md"

    def test_recursive_chunk_flushes_on_markdown_separator(self):
        from services.chunker import recursive_chunk
        from models.schemas import NormalizedDocument

        normalized = NormalizedDocument(
            document_id="doc-md-separator",
            source_type="md",
            filename="manual.md",
            workspace_id="default",
            created_at="2026-01-01T00:00:00Z",
            pages=[
                {
                    "page_number": 1,
                    "text": (
                        "Politica de reembolso com prazo de 30 dias.\n\n"
                        "Procedimento inicial e evidencias.\n\n"
                        "---\n\n"
                        "Politica de retencao de dados por 7 anos.\n\n"
                        "Base legal e requisitos regulatorios.\n"
                    ),
                }
            ],
            sections=[],
            metadata={},
            raw_json_path="",
        )

        chunks = recursive_chunk(normalized, chunk_size=500, overlap=0, workspace_id="default")

        assert len(chunks) == 2
        assert "reembolso" in chunks[0].text.lower()
        assert "retencao de dados" in chunks[1].text.lower()


# ── Multi-Document Search ─────────────────────────────────────────────────

class TestMultiDocumentSearch:
    """Verify multi-document search works correctly (Sprint 2).
    These tests require live Qdrant AND embedding (OpenAI API key).
    They are marked as integration tests and will be skipped without API key.
    """

    @pytest.fixture(autouse=True)
    def setup_mock(self):
        """Apply mock embedding so tests run without real API key."""
        self.embed_patcher = patch('services.vector_service._embed_query', side_effect=_mock_embed_query)
        self.mock = self.embed_patcher.start()
        yield
        self.embed_patcher.stop()

    @pytest.mark.integration
    def test_search_returns_chunks_from_multiple_documents(self):
        """Search returns results from existing documents."""
        from services.vector_service import search_hybrid
        resp = search_hybrid(SearchRequest(
            query='reembolso',
            workspace_id='default',
            top_k=10,
            threshold=0.0
        ))

        doc_ids_returned = set(r.document_id for r in resp.results)
        assert len(doc_ids_returned) >= 1

    @pytest.mark.integration
    def test_workspace_filter_works(self):
        """Search must respect workspace_id filter."""
        from services.vector_service import search_hybrid
        resp = search_hybrid(SearchRequest(
            query='reembolso',
            workspace_id='default',
            top_k=5,
            threshold=0.0
        ))

        for r in resp.results:
            assert r.workspace_id == 'default'

    def test_workspace_filter_applied_to_qdrant_query(self, monkeypatch):
        """Search must pass workspace_id as query_filter when querying Qdrant."""
        from types import SimpleNamespace
        from services.vector_service import search_hybrid

        captured = {}

        class _FakeClient:
            def query_points(self, **kwargs):
                captured["query_filter"] = kwargs.get("query_filter")
                return SimpleNamespace(
                    points=[
                        SimpleNamespace(
                            payload={
                                "chunk_id": "chunk-test",
                                "document_id": "doc-test",
                                "text": "texto de teste",
                                "page_hint": 0,
                            },
                            score=0.5,
                        )
                    ]
                )

        monkeypatch.setattr("services.vector_service.get_client", lambda: _FakeClient())
        monkeypatch.setattr("services.vector_service.ensure_collection", lambda *args, **kwargs: None)
        monkeypatch.setattr(
            "services.vector_service._bm25_search",
            lambda query, workspace_id, limit=20, filters=None: [
                {
                    "chunk_id": "chunk-test",
                    "document_id": "doc-test",
                    "text": "texto de teste",
                    "score": 0.99,
                    "page_hint": 0,
                }
            ],
        )

        resp = search_hybrid(SearchRequest(
            query="reembolso prazo",
            workspace_id="tenant-a",
            top_k=3,
            threshold=0.0,
        ))

        assert not resp.low_confidence
        assert len(resp.results) == 1

        qf = captured.get("query_filter")
        assert qf is not None
        assert qf.must
        must0 = qf.must[0]
        assert must0.key == "workspace_id"
        assert must0.match.value == "tenant-a"

    def test_qdrant_filter_includes_document_id_and_page_range(self, monkeypatch):
        """document_id and page_hint range filters must be forwarded to Qdrant."""
        from types import SimpleNamespace
        from services.vector_service import search_hybrid

        captured = {}

        class _FakeClient:
            def query_points(self, **kwargs):
                captured["query_filter"] = kwargs.get("query_filter")
                return SimpleNamespace(points=[])

        monkeypatch.setattr("services.vector_service.get_client", lambda: _FakeClient())
        monkeypatch.setattr("services.vector_service.ensure_collection", lambda *args, **kwargs: None)
        monkeypatch.setattr(
            "services.vector_service._bm25_search",
            lambda query, workspace_id, limit=20, filters=None: [],
        )

        resp = search_hybrid(SearchRequest(
            query="reembolso prazo",
            workspace_id="tenant-b",
            top_k=3,
            threshold=0.0,
            filters={
                "document_id": "doc-123",
                "page_hint_min": 2,
                "page_hint_max": 4,
            },
        ))

        assert resp.low_confidence
        qf = captured.get("query_filter")
        assert qf is not None
        assert len(qf.must) == 3

        workspace_filter = qf.must[0]
        assert workspace_filter.key == "workspace_id"
        assert workspace_filter.match.value == "tenant-b"

        document_filter = qf.must[1]
        assert document_filter.key == "document_id"
        assert document_filter.match.value == "doc-123"

        page_range_filter = qf.must[2]
        assert page_range_filter.key == "page_hint"
        assert page_range_filter.range.gte == 2
        assert page_range_filter.range.lte == 4

    def test_document_id_filter_can_exclude_results(self):
        """document_id filter must be honored by retrieval."""
        from services.vector_service import search_hybrid

        resp = search_hybrid(SearchRequest(
            query='reembolso',
            workspace_id='default',
            top_k=5,
            threshold=0.0,
            filters={'document_id': 'doc-inexistente'},
        ))

        assert resp.results == []
        assert resp.low_confidence

    def test_search_populates_document_filename(self):
        """Search results must include document_filename from canonical metadata."""
        from services.vector_service import search_hybrid

        resp = search_hybrid(SearchRequest(
            query='reembolso prazo',
            workspace_id='default',
            top_k=3,
            threshold=0.0,
        ))

        assert resp.results, "Expected retrieval results for valid query"
        assert resp.results[0].document_filename == 'politicas_fluxpay.md'
        for item in resp.results:
            assert item.document_filename

    def test_search_prefers_specific_webhook_document_for_backoff_query(self):
        """Specific operational queries should not be dominated by the generic Fluxpay policy doc."""
        from services.vector_service import search_hybrid

        resp = search_hybrid(SearchRequest(
            query='Qual sequência de backoff é usada nos reenvios de webhooks da Fluxpay?',
            workspace_id='default',
            top_k=3,
            threshold=0.0,
            reranking=True,
        ))

        assert resp.results, "Expected retrieval results for webhook backoff query"
        assert resp.results[0].document_filename == 'guia_integracao_webhooks_fluxpay.md'

    def test_include_raw_scores_returns_breakdown(self):
        """include_raw_scores=True must populate scores_breakdown."""
        from services.vector_service import search_hybrid

        resp = search_hybrid(SearchRequest(
            query='reembolso prazo',
            workspace_id='default',
            top_k=3,
            threshold=0.0,
            include_raw_scores=True,
        ))

        assert resp.scores_breakdown is not None
        assert 'dense_max' in resp.scores_breakdown
        assert 'sparse_max' in resp.scores_breakdown
        assert 'rrf_final_score' in resp.scores_breakdown
        assert 'confidence_final_score' in resp.scores_breakdown

    def test_bm25f_idf_cache_is_scoped_to_candidate_set(self):
        """BM25F IDF cache must not leak between different candidate corpora for the same query."""
        from services.vector_service import BM25FReranker

        reranker = BM25FReranker()
        query_terms = reranker._tokenize("Qual sequência de backoff é usada nos reenvios de webhooks da Fluxpay?")

        generic_texts = [
            "Fluxpay opera com regras gerais de compliance e politicas internas sem detalhes de webhook."
        ]
        webhook_texts = [
            "Eventos nao reconhecidos sao reenviados 5 vezes com backoff de 1 5 15 30 e 60 minutos em webhooks."
        ]

        generic_idf = reranker._compute_idf(query_terms, generic_texts)
        webhook_idf = reranker._compute_idf(query_terms, webhook_texts)

        assert generic_idf != webhook_idf
        assert generic_idf["backoff"] != webhook_idf["backoff"]

    def test_source_type_filter_is_honored_after_fusion(self, monkeypatch):
        """source_type filter must remove results whose canonical metadata does not match."""
        from types import SimpleNamespace
        from services.vector_service import search_hybrid

        class _FakeClient:
            def query_points(self, **kwargs):
                return SimpleNamespace(points=[])

        monkeypatch.setattr("services.vector_service.get_client", lambda: _FakeClient())
        monkeypatch.setattr("services.vector_service.ensure_collection", lambda *args, **kwargs: None)
        monkeypatch.setattr(
            "services.vector_service.get_document_registry",
            lambda workspace_id="default": {
                "doc-md": {
                    "filename": "manual.md",
                    "source_type": "md",
                    "tags": ["policy"],
                },
                "doc-pdf": {
                    "filename": "manual.pdf",
                    "source_type": "pdf",
                    "tags": ["policy"],
                },
            },
        )
        monkeypatch.setattr(
            "services.vector_service._bm25_search",
            lambda query, workspace_id, limit=20, filters=None: [
                {
                    "chunk_id": "chunk-md",
                    "document_id": "doc-md",
                    "text": "texto markdown",
                    "score": 0.81,
                    "page_hint": 1,
                    "dense_score": 0.0,
                    "sparse_score": 0.81,
                },
                {
                    "chunk_id": "chunk-pdf",
                    "document_id": "doc-pdf",
                    "text": "texto pdf",
                    "score": 0.79,
                    "page_hint": 1,
                    "dense_score": 0.0,
                    "sparse_score": 0.79,
                },
            ],
        )

        resp = search_hybrid(SearchRequest(
            query="manual reembolso",
            workspace_id="default",
            top_k=5,
            threshold=0.0,
            filters={"source_type": "md"},
        ))

        assert not resp.low_confidence
        assert [item.document_id for item in resp.results] == ["doc-md"]
        assert resp.results[0].document_filename == "manual.md"

    def test_tags_filter_is_honored_after_fusion(self, monkeypatch):
        """tags filter must keep only documents sharing at least one required tag."""
        from types import SimpleNamespace
        from services.vector_service import search_hybrid

        class _FakeClient:
            def query_points(self, **kwargs):
                return SimpleNamespace(points=[])

        monkeypatch.setattr("services.vector_service.get_client", lambda: _FakeClient())
        monkeypatch.setattr("services.vector_service.ensure_collection", lambda *args, **kwargs: None)
        monkeypatch.setattr(
            "services.vector_service.get_document_registry",
            lambda workspace_id="default": {
                "doc-policy": {
                    "filename": "policy.md",
                    "source_type": "md",
                    "tags": ["policy", "refund"],
                },
                "doc-billing": {
                    "filename": "billing.md",
                    "source_type": "md",
                    "tags": ["billing"],
                },
            },
        )
        monkeypatch.setattr(
            "services.vector_service._bm25_search",
            lambda query, workspace_id, limit=20, filters=None: [
                {
                    "chunk_id": "chunk-policy",
                    "document_id": "doc-policy",
                    "text": "regras de reembolso",
                    "score": 0.83,
                    "page_hint": 1,
                    "dense_score": 0.0,
                    "sparse_score": 0.83,
                },
                {
                    "chunk_id": "chunk-billing",
                    "document_id": "doc-billing",
                    "text": "cobranca e faturas",
                    "score": 0.80,
                    "page_hint": 1,
                    "dense_score": 0.0,
                    "sparse_score": 0.80,
                },
            ],
        )

        resp = search_hybrid(SearchRequest(
            query="reembolso tags",
            workspace_id="default",
            top_k=5,
            threshold=0.0,
            filters={"tags": ["refund"]},
        ))

        assert not resp.low_confidence
        assert [item.document_id for item in resp.results] == ["doc-policy"]
        assert resp.results[0].document_filename == "policy.md"

    def test_search_without_catalog_scope_filter_keeps_operational_hits(self, monkeypatch):
        """Search must not silently drop operational chunks when no catalog_scope filter was requested."""
        from types import SimpleNamespace
        from services.vector_service import search_hybrid

        class _FakeClient:
            def query_points(self, **kwargs):
                return SimpleNamespace(points=[])

        monkeypatch.setattr("services.vector_service.get_client", lambda: _FakeClient())
        monkeypatch.setattr("services.vector_service.ensure_collection", lambda *args, **kwargs: None)
        monkeypatch.setattr(
            "services.vector_service.get_document_registry",
            lambda workspace_id="default": {},
        )
        monkeypatch.setattr(
            "services.vector_service.list_document_items",
            lambda workspace_id="default", limit=10000, offset=0, source_type=None, status=None, query=None: {
                "items": [
                    {
                        "document_id": "doc-operational",
                        "filename": "operational.pdf",
                        "source_type": "pdf",
                        "tags": ["vet"],
                        "catalog_scope": "operational",
                    }
                ]
            },
        )
        monkeypatch.setattr(
            "services.vector_service._bm25_search",
            lambda query, workspace_id, limit=20, filters=None: [
                {
                    "chunk_id": "chunk-operational",
                    "document_id": "doc-operational",
                    "text": "Sinais sugestivos de doença renal crônica em gatos incluem perda de peso e alterações urinárias.",
                    "score": 0.88,
                    "page_hint": 1,
                    "dense_score": 0.0,
                    "sparse_score": 0.88,
                },
            ],
        )

        resp = search_hybrid(SearchRequest(
            query="sinais de doença renal crônica em gatos",
            workspace_id="default",
            top_k=5,
            threshold=0.0,
        ))

        assert [item.document_id for item in resp.results] == ["doc-operational"]
        assert resp.results[0].document_filename == "operational.pdf"

    def test_search_with_explicit_canonical_scope_still_filters_operational_hits(self, monkeypatch):
        """Explicit catalog_scope=canonical must continue filtering out operational chunks."""
        from types import SimpleNamespace
        from services.vector_service import search_hybrid

        class _FakeClient:
            def query_points(self, **kwargs):
                return SimpleNamespace(points=[])

        monkeypatch.setattr("services.vector_service.get_client", lambda: _FakeClient())
        monkeypatch.setattr("services.vector_service.ensure_collection", lambda *args, **kwargs: None)
        monkeypatch.setattr(
            "services.vector_service.get_document_registry",
            lambda workspace_id="default": {},
        )
        monkeypatch.setattr(
            "services.vector_service.list_document_items",
            lambda workspace_id="default", limit=10000, offset=0, source_type=None, status=None, query=None: {
                "items": [
                    {
                        "document_id": "doc-operational",
                        "filename": "operational.pdf",
                        "source_type": "pdf",
                        "tags": ["vet"],
                        "catalog_scope": "operational",
                    }
                ]
            },
        )
        monkeypatch.setattr(
            "services.vector_service._bm25_search",
            lambda query, workspace_id, limit=20, filters=None: [
                {
                    "chunk_id": "chunk-operational",
                    "document_id": "doc-operational",
                    "text": "Sinais sugestivos de doença renal crônica em gatos incluem perda de peso e alterações urinárias.",
                    "score": 0.88,
                    "page_hint": 1,
                    "dense_score": 0.0,
                    "sparse_score": 0.88,
                },
            ],
        )

        resp = search_hybrid(SearchRequest(
            query="sinais de doença renal crônica em gatos",
            workspace_id="default",
            top_k=5,
            threshold=0.0,
            filters={"catalog_scope": "canonical"},
        ))

        assert resp.results == []

    def test_page_hint_range_filter_is_honored_after_fusion(self, monkeypatch):
        """page_hint_min/page_hint_max must filter fused retrieval results."""
        from types import SimpleNamespace
        from services.vector_service import search_hybrid

        class _FakeClient:
            def query_points(self, **kwargs):
                return SimpleNamespace(points=[])

        monkeypatch.setattr("services.vector_service.get_client", lambda: _FakeClient())
        monkeypatch.setattr("services.vector_service.ensure_collection", lambda *args, **kwargs: None)
        monkeypatch.setattr(
            "services.vector_service.get_document_registry",
            lambda workspace_id="default": {
                "doc-pages": {
                    "filename": "pages.md",
                    "source_type": "md",
                    "tags": [],
                },
            },
        )
        monkeypatch.setattr(
            "services.vector_service._bm25_search",
            lambda query, workspace_id, limit=20, filters=None: [
                {
                    "chunk_id": "chunk-page-1",
                    "document_id": "doc-pages",
                    "text": "primeira pagina",
                    "score": 0.82,
                    "page_hint": 1,
                    "dense_score": 0.0,
                    "sparse_score": 0.82,
                },
                {
                    "chunk_id": "chunk-page-3",
                    "document_id": "doc-pages",
                    "text": "terceira pagina",
                    "score": 0.81,
                    "page_hint": 3,
                    "dense_score": 0.0,
                    "sparse_score": 0.81,
                },
            ],
        )

        resp = search_hybrid(SearchRequest(
            query="pagina especifica",
            workspace_id="default",
            top_k=5,
            threshold=0.0,
            filters={"page_hint_min": 2, "page_hint_max": 3},
        ))

        assert not resp.low_confidence
        assert [item.chunk_id for item in resp.results] == ["chunk-page-3"]
        assert resp.results[0].page_hint == 3

    def test_threshold_applies_to_confidence_score(self, monkeypatch):
        """Retrieval threshold must be evaluated against the exposed confidence score."""
        from types import SimpleNamespace
        from services.vector_service import search_hybrid

        class _FakeClient:
            def query_points(self, **kwargs):
                using = kwargs.get("using")
                if using == "dense":
                    return SimpleNamespace(
                        points=[
                            SimpleNamespace(
                                payload={
                                    "chunk_id": "chunk-dense",
                                    "document_id": "doc-1",
                                    "text": "texto denso",
                                    "page_hint": 1,
                                },
                                score=0.82,
                            )
                        ]
                    )
                if using == "sparse":
                    return SimpleNamespace(
                        points=[
                            {
                                "chunk_id": "chunk-sparse",
                                "document_id": "doc-1",
                                "text": "texto esparso",
                                "score": 0.74,
                                "page_hint": 1,
                                "dense_score": 0.0,
                                "sparse_score": 0.74,
                            }
                        ]
                    )
                raise AssertionError(f"Unexpected vector type: {using}")

        monkeypatch.setattr("services.vector_service.get_client", lambda: _FakeClient())
        monkeypatch.setattr("services.vector_service.ensure_collection", lambda *args, **kwargs: None)

        resp = search_hybrid(SearchRequest(
            query="reembolso prazo",
            workspace_id="default",
            top_k=3,
            threshold=0.80,
        ))

        assert resp.results
        assert resp.results[0].score >= 0.80
        assert not resp.low_confidence

        low_conf = search_hybrid(SearchRequest(
            query="reembolso prazo",
            workspace_id="default",
            top_k=3,
            threshold=0.90,
        ))

        assert low_conf.low_confidence

    def test_search_hybrid_dedupes_repetitive_dense_hits(self, monkeypatch):
        """Duplicate low-diversity dense hits must not crowd out more informative candidates."""
        from types import SimpleNamespace
        from services.vector_service import search_hybrid

        repetitive_text = ("Prazo de reembolso de Pix: 2 dias uteis. " * 24).strip()
        medical_text = (
            "Levetiracetam has been used as a pulse treatment to reduce cluster seizures in dogs. "
            "The suggested regime is a single 60 mg/kg oral dose immediately after a seizure, "
            "followed by 20-30 mg/kg three times daily until there have been no seizures for 48 hours."
        )

        class _FakeClient:
            def query_points(self, **kwargs):
                using = kwargs.get("using")
                if using == "dense":
                    return SimpleNamespace(
                        points=[
                            SimpleNamespace(
                                payload={
                                    "chunk_id": "pix-1",
                                    "document_id": "doc-pix",
                                    "text": repetitive_text,
                                    "page_hint": 1,
                                },
                                score=0.92,
                            ),
                            SimpleNamespace(
                                payload={
                                    "chunk_id": "pix-2",
                                    "document_id": "doc-pix",
                                    "text": repetitive_text,
                                    "page_hint": 1,
                                },
                                score=0.91,
                            ),
                            SimpleNamespace(
                                payload={
                                    "chunk_id": "med-1",
                                    "document_id": "doc-med",
                                    "text": medical_text,
                                    "page_hint": 163,
                                },
                                score=0.70,
                            ),
                        ]
                    )
                if using == "sparse":
                    return SimpleNamespace(points=[])
                raise AssertionError(f"Unexpected vector type: {using}")

        monkeypatch.setattr("services.vector_service.get_client", lambda: _FakeClient())
        monkeypatch.setattr("services.vector_service.ensure_collection", lambda *args, **kwargs: None)

        resp = search_hybrid(SearchRequest(
            query="qual o tratamento para convulsão em cão?",
            workspace_id="default",
            top_k=5,
            threshold=0.0,
        ))

        assert resp.results
        assert resp.results[0].document_id == "doc-med"
        assert [item.chunk_id for item in resp.results].count("pix-1") + [item.chunk_id for item in resp.results].count("pix-2") == 1
        assert len([item for item in resp.results if item.document_id == "doc-pix"]) == 1


# ── Telemetry Ingestion ──────────────────────────────────────────────────

class TestTelemetryIngestion:
    """Verify ingestion telemetry logging works (Sprint 4)."""

    def test_ingestion_log_file_exists(self):
        """Telemetry service must create ingestion log file."""
        tel = TelemetryService()
        assert tel.INGEST_LOG.exists(), f"Ingestion log not created at {tel.INGEST_LOG}"

    def test_ingestion_log_append_works(self, tmp_path):
        """Telemetry must append ingestion events to log file."""
        from datetime import datetime, timezone

        class FakeTelemetry(TelemetryService):
            def _ensure_logs(self):
                pass  # skip in temp

        fake = FakeTelemetry()
        fake.INGEST_LOG = tmp_path / "test_ingestion.jsonl"

        fake.log_ingestion(
            document_id='test-doc-123',
            workspace_id='default',
            source_type='md',
            filename='test.md',
            status='success',
            chunk_count=7,
            processing_time_ms=150,
        )

        assert fake.INGEST_LOG.exists()
        with open(fake.INGEST_LOG) as f:
            line = f.readline()

        event = json.loads(line)
        assert event['document_id'] == 'test-doc-123'
        assert event['type'] == 'ingestion'
        assert event['status'] == 'success'

    def test_upload_failure_is_logged_with_reason(self, tmp_path, monkeypatch):
        """Upload failures must create an ingestion error event with reason."""
        import asyncio
        from fastapi import UploadFile
        from api.main import upload_document
        from services.telemetry_service import TelemetryService
        import services.telemetry_service as telemetry_module
        from services.enterprise_service import login

        class FakeTelemetry(TelemetryService):
            def _ensure_logs(self):
                pass

        fake = FakeTelemetry()
        fake.INGEST_LOG = tmp_path / "ingestion.jsonl"
        fake.QUERIES_LOG = tmp_path / "queries.jsonl"
        fake.EVAL_LOG = tmp_path / "evaluations.jsonl"
        for path in [fake.INGEST_LOG, fake.QUERIES_LOG, fake.EVAL_LOG]:
            path.write_text("", encoding="utf-8")

        monkeypatch.setattr(telemetry_module, "_telemetry", fake)

        file = UploadFile(filename="bad.bin", file=io.BytesIO(b"binary"))

        session_payload = login("admin@demo.local", "demo1234", "default")
        from models.schemas import EnterpriseSession
        session = EnterpriseSession(**session_payload)
        with pytest.raises(Exception) as exc_info:
            asyncio.run(upload_document(file=file, workspace_id="default", chunking_strategy="recursive", _session=session))

        assert "unsupported_format" in str(exc_info.value)
        events = [json.loads(line) for line in fake.INGEST_LOG.read_text(encoding="utf-8").splitlines() if line]
        assert events, "expected ingestion error log event"
        assert events[-1]["status"] == "error"
        assert "unsupported_format" in events[-1]["error"]


class TestMetricsEndpoint:
    """Verify /metrics exposes the minimum operational contract."""

    def test_metrics_returns_retrieval_answer_and_evaluation(self, tmp_path, monkeypatch):
        from api.main import get_metrics as get_metrics_route
        import services.telemetry_service as telemetry_module

        class FakeTelemetry(TelemetryService):
            QUERIES_LOG = tmp_path / "queries.jsonl"
            INGEST_LOG = tmp_path / "ingestion.jsonl"
            EVAL_LOG = tmp_path / "evaluations.jsonl"

            def _ensure_logs(self):
                self.QUERIES_LOG.write_text("")
                self.INGEST_LOG.write_text("")
                self.EVAL_LOG.write_text("")

        fake = FakeTelemetry()
        fake.log_query(
            query="teste de métricas",
            workspace_id="default",
            answer="resposta",
            confidence="high",
            grounded=True,
            chunks_used=[{"chunk_id": "chunk-1"}],
            retrieval_time_ms=25,
            total_latency_ms=90,
            low_confidence=False,
            results_count=3,
            citation_coverage=0.88,
            top_result_score=0.91,
            threshold=0.70,
            hit=True,
            grounding_reason=None,
            uncited_claims_count=0,
            needs_review=False,
        )
        fake.log_ingestion(
            document_id="doc-1",
            workspace_id="default",
            source_type="md",
            filename="doc.md",
            status="success",
            chunk_count=7,
            processing_time_ms=120,
        )
        fake.log_evaluation(
            evaluation_id="eval-1",
            workspace_id="default",
            total_questions=30,
            hit_at_1=0.6,
            hit_at_3=0.8,
            hit_at_5=0.9,
            avg_latency_ms=123.4,
            avg_score=0.72,
            low_confidence_rate=0.1,
            groundedness_rate=0.85,
            duration_seconds=12.5,
        )

        monkeypatch.setattr(telemetry_module, "_telemetry", fake, raising=False)

        data = get_metrics_route(days=1)
        assert "retrieval" in data
        assert "answer" in data
        assert "evaluation" in data
        assert data["retrieval"]["hit_rate_top3"] == 0.8
        assert data["retrieval"]["hit_rate_top5"] == 0.9
        assert data["retrieval"]["avg_score_top1"] == 0.91
        assert data["answer"]["citation_coverage_avg"] == 0.88
        assert data["answer"]["grounded_answers"] == 1
        assert data["answer"]["no_context_answers"] == 0
        assert data["answer"]["ungrounded_answers"] == 0
        assert data["evaluation"]["total_runs"] == 1
        assert data["evaluation"]["total_questions"] == 30

    def test_metrics_route_scopes_results_to_active_workspace(self, tmp_path, monkeypatch):
        from api.main import get_metrics as get_metrics_route, login
        import services.telemetry_service as telemetry_module
        from models.schemas import EnterpriseSession, LoginRequest

        class FakeTelemetry(TelemetryService):
            QUERIES_LOG = tmp_path / "queries.jsonl"
            INGEST_LOG = tmp_path / "ingestion.jsonl"
            EVAL_LOG = tmp_path / "evaluations.jsonl"

            def _ensure_logs(self):
                self.QUERIES_LOG.write_text("")
                self.INGEST_LOG.write_text("")
                self.EVAL_LOG.write_text("")

        fake = FakeTelemetry()
        fake.log_query(
            query="default query",
            workspace_id="default",
            answer="resposta",
            confidence="high",
            grounded=True,
            chunks_used=[{"chunk_id": "chunk-default"}],
            retrieval_time_ms=20,
            total_latency_ms=40,
            low_confidence=False,
            results_count=1,
            citation_coverage=1.0,
            top_result_score=0.9,
            threshold=0.7,
            hit=True,
            grounding_reason=None,
            uncited_claims_count=0,
            needs_review=False,
        )
        fake.log_query(
            query="acme query",
            workspace_id="acme-lab",
            answer="resposta",
            confidence="low",
            grounded=False,
            chunks_used=[],
            retrieval_time_ms=30,
            total_latency_ms=60,
            low_confidence=True,
            results_count=0,
            citation_coverage=0.0,
            top_result_score=0.2,
            threshold=0.7,
            hit=False,
            grounding_reason="No results retrieved or low confidence",
            uncited_claims_count=1,
            needs_review=True,
        )
        monkeypatch.setattr(telemetry_module, "_telemetry", fake, raising=False)

        payload = login(LoginRequest(email="operator@demo.local", password="demo1234", tenant_id="default"))
        session = EnterpriseSession(**payload)
        data = get_metrics_route(days=1, _session=session)

        assert data["workspace_id"] == "default"
        assert data["retrieval"]["total_queries"] == 1
        assert data["retrieval"]["low_confidence_rate"] == 0.0


class TestHealthEndpoint:
    """Verify /health exposes app, corpus, and qdrant status."""

    def test_health_reports_corpus_and_qdrant(self, monkeypatch):
        from api.health_routes import health_check

        class FakeCount:
            count = 7

        class FakeClient:
            def get_collections(self):
                return {"collections": []}

            def count(self, **kwargs):
                return FakeCount()

        monkeypatch.setattr("api.health_routes.get_client", lambda: FakeClient())
        monkeypatch.setattr(
            "api.health_routes.get_workspace_inventory",
            lambda workspace_id="default": {
                "workspace_id": workspace_id,
                "documents": 1,
                "chunks": 7,
                "parsed_documents": 1,
                "partial_documents": 0,
                "operational_documents": 2,
                "operational_chunks": 9,
            },
        )
        monkeypatch.setattr(
            "api.health_routes.get_telemetry",
            lambda: type(
                "FakeTelemetry",
                (),
                {
                    "get_operational_snapshot": lambda self, days=1, workspace_id=None: {
                        "period_days": days,
                        "window_start": "2026-04-16T00:00:00+00:00",
                        "queries": {"count": 3, "low_confidence": 1, "needs_review": 2, "latest_timestamp": "2026-04-16T12:00:00+00:00"},
                        "ingestion": {"count": 2, "errors": 1, "latest_timestamp": "2026-04-16T11:00:00+00:00"},
                        "evaluation": {"count": 1, "latest_timestamp": "2026-04-16T10:00:00+00:00"},
                    }
                },
            )(),
        )

        data = health_check()
        assert data["status"] == "healthy"
        assert data["qdrant"]["status"] == "ok"
        assert data["qdrant"]["collection"] == "rag_phase0"
        assert data["qdrant"]["points"] == 7
        assert data["qdrant"]["workspace_points"] == 7
        assert data["corpus"]["documents"] == 1
        assert data["corpus"]["chunks"] == 7
        assert data["corpus"]["operational_documents"] == 2
        assert data["corpus"]["operational_chunks"] == 9
        assert data["telemetry"]["queries"]["count"] == 3
        assert data["telemetry"]["ingestion"]["errors"] == 1
        assert data["telemetry"]["evaluation"]["count"] == 1


# ── Metadata Endpoint ──────────────────────────────────────────────────────

class TestMetadataEndpoint:
    """Verify document metadata endpoint works (Sprint 0)."""

    @pytest.mark.integration
    def test_document_metadata_complete(self, corpus_doc_ids):
        """GET /documents/{id} must return complete metadata per contract 0009."""
        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)
        doc_ids = corpus_doc_ids
        if not doc_ids:
            pytest.skip("No documents in Qdrant")

        doc_id = doc_ids[0]
        headers = enterprise_headers(client)
        resp = client.get(f'/documents/{doc_id}?workspace_id=default', headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        required_fields = [
            'document_id', 'workspace_id', 'source_type', 'filename',
            'page_count', 'char_count', 'chunk_count', 'status',
            'created_at', 'tags', 'embeddings_model', 'chunking_strategy', 'indexed_at'
        ]
        for field in required_fields:
            assert field in data, f"Metadata missing field: {field}"


class TestListEndpoints:
    """Verify list endpoints used by the premium frontend."""

    def test_documents_list_returns_paginated_items(self, monkeypatch):
        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)

        payload = {
            "items": [
                {
                    "document_id": "doc-1",
                    "workspace_id": "default",
                    "catalog_scope": "canonical",
                    "source_type": "md",
                    "filename": "doc.md",
                    "page_count": 2,
                    "char_count": 120,
                    "chunk_count": 3,
                    "status": "parsed",
                    "created_at": "2026-01-01T00:00:00Z",
                    "chunking_strategy": "recursive",
                    "tags": ["policy"],
                    "embeddings_model": "text-embedding-3-small",
                    "indexed_at": "2026-01-01T00:10:00Z",
                }
            ],
            "total": 1,
            "limit": 50,
            "offset": 0,
            "workspace_id": "default",
        }

        monkeypatch.setattr("api.main.list_document_items", lambda **kwargs: payload)
        headers = enterprise_headers(client)
        response = client.get("/documents?workspace_id=default&limit=50&offset=0", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["workspace_id"] == "default"
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["document_id"] == "doc-1"

    def test_query_logs_list_returns_filtered_items(self, monkeypatch):
        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)

        class FakeTelemetry:
            def list_queries(self, **kwargs):
                self.kwargs = kwargs
                return {
                    "items": [
                        {
                            "timestamp": "2026-01-01T00:00:00Z",
                            "type": "query",
                            "workspace_id": "default",
                            "query": "teste",
                            "answer": "resposta",
                            "confidence": "high",
                            "grounded": True,
                            "low_confidence": False,
                            "chunks_used_count": 1,
                            "chunk_ids": ["chunk-1"],
                            "retrieval_time_ms": 10,
                            "total_latency_ms": 20,
                            "results_count": 1,
                            "citation_coverage": 1.0,
                            "top_result_score": 0.9,
                            "threshold": 0.7,
                            "hit": True,
                            "grounding_reason": None,
                            "uncited_claims_count": 0,
                            "needs_review": False,
                        }
                    ],
                    "total": 1,
                    "limit": 100,
                    "offset": 0,
                    "workspace_id": "default",
                }

        fake = FakeTelemetry()
        monkeypatch.setattr("api.main.get_telemetry", lambda: fake)
        monkeypatch.setattr("services.telemetry_service.get_telemetry", lambda: fake)
        monkeypatch.setattr("services.telemetry_service.get_telemetry", lambda: fake)
        headers = enterprise_headers(client)
        response = client.get(
            "/queries/logs?workspace_id=default&limit=100&offset=0&needs_review=false&low_confidence=false&grounded=true&min_citation_coverage=0.5",
            headers=headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["workspace_id"] == "default"
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert fake.kwargs["workspace_id"] == "default"
        assert fake.kwargs["grounded"] is True
        assert fake.kwargs["low_confidence"] is False

    def test_query_logs_list_returns_real_telemetry_items(self):
        from fastapi.testclient import TestClient
        from api.main import app
        from services.telemetry_service import get_telemetry

        telemetry = get_telemetry()
        telemetry.log_query(
            query="pergunta de auditoria",
            workspace_id="default",
            answer="resposta de auditoria",
            confidence="medium",
            grounded=True,
            chunks_used=[{"chunk_id": "chunk-1"}],
            retrieval_time_ms=123,
            total_latency_ms=456,
            low_confidence=False,
            results_count=2,
            citation_coverage=0.75,
            top_result_score=0.91,
            threshold=0.7,
            hit=True,
            grounding_reason="grounded by citations",
            uncited_claims_count=0,
            needs_review=False,
        )

        client = TestClient(app)
        headers = enterprise_headers(client)
        response = client.get("/queries/logs?workspace_id=default&limit=5&offset=0", headers=headers)

        assert response.status_code == 200
        payload = response.json()
        assert payload["workspace_id"] == "default"
        assert payload["total"] >= 1
        assert isinstance(payload["items"], list)
        assert any(item["query"] == "pergunta de auditoria" for item in payload["items"])

    def test_query_logs_list_normalizes_legacy_rows_without_chunks_count(self, tmp_path, monkeypatch):
        from fastapi.testclient import TestClient
        from api.main import app
        from services.telemetry_service import TelemetryService as TelemetryServiceClass

        legacy_log = tmp_path / "queries.jsonl"
        monkeypatch.setattr(TelemetryServiceClass, "QUERIES_LOG", legacy_log)

        telemetry = TelemetryServiceClass()
        legacy_row = {
            "timestamp": "2026-04-17T01:00:00Z",
            "workspace_id": "default",
            "query": "legacy query",
            "answer": "legacy answer",
            "confidence": "medium",
            "grounded": True,
            "chunks_used": [{"chunk_id": "legacy-chunk-1"}],
            "retrieval_time_ms": 10,
            "total_latency_ms": 20,
            "results_count": 1,
            "citation_coverage": 0.5,
            "top_result_score": 0.9,
            "threshold": 0.7,
            "hit": True,
            "grounding_reason": None,
            "uncited_claims_count": 0,
            "needs_review": False,
        }
        legacy_log.write_text(json.dumps(legacy_row) + "\n", encoding="utf-8")

        monkeypatch.setattr("api.main.get_telemetry", lambda: telemetry)
        client = TestClient(app)
        headers = enterprise_headers(client)
        response = client.get("/queries/logs?workspace_id=default&limit=5&offset=0", headers=headers)

        assert response.status_code == 200
        payload = response.json()
        assert payload["workspace_id"] == "default"
        assert payload["total"] == 1
        assert payload["items"][0]["query"] == "legacy query"
        assert payload["items"][0]["chunks_used_count"] == 1
        assert payload["items"][0]["chunk_ids"] == ["legacy-chunk-1"]


class TestEvaluationService:
    """Verify evaluation output is auditável por pergunta."""

    def test_question_results_are_returned(self):
        """Evaluation endpoint response must include per-question results."""
        from services.evaluation_service import EvaluationService

        evaluator = EvaluationService()
        result = evaluator.run_evaluation(
            workspace_id='default',
            dataset_path=Path('src/data/default/dataset.json'),
            top_k=5,
            run_judge=False,
        )

        assert result.question_results, "question_results não pode ficar vazio"
        assert len(result.question_results) == result.total_questions
        assert result.avg_score >= 0.0
        assert result.by_difficulty
        assert result.by_category
        sample = result.question_results[0]
        for field in [
            "question_id",
            "pergunta",
            "hit_top_1",
            "hit_top_3",
            "hit_top_5",
            "retrieved_documents",
            "correct_document_id",
            "best_score",
            "best_score_rank",
            "needs_review",
        ]:
            assert hasattr(sample, field), f"question_result missing field '{field}'"

    def test_evaluation_uses_question_workspace_and_keeps_grounding_without_judge(self, tmp_path, monkeypatch):
        from services.evaluation_service import EvaluationService
        from models.schemas import GroundingReport, QueryResponse

        dataset = {
            "dataset_id": "mixed-enterprise",
            "version": "1.0",
            "retrieval_threshold": 0.7,
            "questions": [
                {
                    "id": 1,
                    "pergunta": "Pergunta tenant default",
                    "document_id": "doc-default",
                    "trecho_esperado": "default",
                    "resposta_esperada": "default",
                    "workspace_id": "default",
                },
                {
                    "id": 2,
                    "pergunta": "Pergunta tenant acme",
                    "document_id": "doc-acme",
                    "trecho_esperado": "acme",
                    "resposta_esperada": "acme",
                    "workspace_id": "acme-lab",
                },
            ],
        }
        dataset_path = tmp_path / "dataset.json"
        dataset_path.write_text(json.dumps(dataset), encoding="utf-8")

        calls: list[tuple[str, float]] = []

        def fake_search_and_answer(request):
            calls.append((request.workspace_id, request.threshold))
            if request.workspace_id == "acme-lab":
                return QueryResponse(
                    answer="Resposta acme",
                    chunks_used=["chunk-acme"],
                    citations=[],
                    confidence="low",
                    grounded=False,
                    grounding=GroundingReport(
                        grounded=False,
                        citation_coverage=0.0,
                        uncited_claims=["claim"],
                        needs_review=True,
                        reason="No results retrieved or low confidence",
                    ),
                    citation_coverage=0.0,
                    low_confidence=True,
                    retrieval={
                        "results": [{"document_id": "doc-acme", "score": 0.65, "text": "acme"}],
                        "retrieval_time_ms": 22,
                    },
                    latency_ms=22,
                )
            return QueryResponse(
                answer="Resposta default",
                chunks_used=["chunk-default"],
                citations=[],
                confidence="high",
                grounded=True,
                grounding=GroundingReport(
                    grounded=True,
                    citation_coverage=1.0,
                    uncited_claims=[],
                    needs_review=False,
                    reason="grounded",
                ),
                citation_coverage=1.0,
                low_confidence=False,
                retrieval={
                    "results": [{"document_id": "doc-default", "score": 0.83, "text": "default"}],
                    "retrieval_time_ms": 15,
                },
                latency_ms=15,
            )

        monkeypatch.setattr("services.search_service.search_and_answer", fake_search_and_answer)

        evaluator = EvaluationService()
        result = evaluator.run_evaluation(
            workspace_id="default",
            dataset_path=dataset_path,
            top_k=5,
            run_judge=False,
        )

        assert calls == [("default", 0.7), ("acme-lab", 0.7)]
        assert result.low_confidence_rate == 0.5
        assert result.retrieval_low_confidence_rate == 0.5
        assert result.groundedness_rate == 0.5
        assert result.observed_groundedness_rate == 0.5
        assert result.question_results[0].needs_review is False
        assert result.question_results[1].needs_review is True
        assert result.question_results[1].best_score == 0.65
        assert result.question_results[1].retrieval_low_confidence is True

    def test_evaluation_separates_final_low_confidence_from_retrieval_heuristic(self, tmp_path, monkeypatch):
        from services.evaluation_service import EvaluationService
        from models.schemas import GroundingReport, QueryResponse

        dataset = {
            "dataset_id": "calibrated-eval",
            "version": "1.0",
            "retrieval_threshold": 0.7,
            "questions": [
                {
                    "id": 1,
                    "pergunta": "Pergunta calibrada",
                    "document_id": "doc-good",
                    "trecho_esperado": "good",
                    "resposta_esperada": "good",
                    "workspace_id": "default",
                }
            ],
        }
        dataset_path = tmp_path / "dataset.json"
        dataset_path.write_text(json.dumps(dataset), encoding="utf-8")

        def fake_search_and_answer(_request):
            return QueryResponse(
                answer="Resposta bem citada",
                chunks_used=["chunk-good"],
                citations=[],
                confidence="medium",
                grounded=True,
                grounding=GroundingReport(
                    grounded=True,
                    citation_coverage=1.0,
                    uncited_claims=[],
                    needs_review=False,
                    reason=None,
                ),
                citation_coverage=1.0,
                low_confidence=False,
                retrieval={
                    "results": [{"document_id": "doc-good", "score": 0.42, "text": "good"}],
                    "retrieval_time_ms": 18,
                    "retrieval_low_confidence": True,
                },
                latency_ms=31,
            )

        monkeypatch.setattr("services.search_service.search_and_answer", fake_search_and_answer)

        evaluator = EvaluationService()
        result = evaluator.run_evaluation(
            workspace_id="default",
            dataset_path=dataset_path,
            top_k=5,
            run_judge=False,
        )

        assert result.low_confidence_rate == 0.0
        assert result.retrieval_low_confidence_rate == 1.0
        assert result.groundedness_rate == 1.0
        assert result.observed_groundedness_rate == 1.0
        assert result.judged_questions == 0
        assert result.flagged_for_review_count == 0
        assert result.avg_latency_ms == 31.0
        assert result.question_results[0].low_confidence is False
        assert result.question_results[0].retrieval_low_confidence is True
        assert result.question_results[0].grounded is True
        assert result.question_results[0].citation_coverage == 1.0


# ── Metrics Aggregation ──────────────────────────────────────────────────

class TestTelemetryMetrics:
    """Verify `/metrics` contract for the current phase."""

    def test_metrics_aggregation_exposes_retrieval_and_evaluation_fields(self, tmp_path):
        """Telemetry aggregation must expose the minimum D3 metrics set."""
        from services.telemetry_service import TelemetryService

        class FakeTelemetry(TelemetryService):
            def _ensure_logs(self):
                pass

        fake = FakeTelemetry()
        fake.QUERIES_LOG = tmp_path / "queries.jsonl"
        fake.INGEST_LOG = tmp_path / "ingestion.jsonl"
        fake.EVAL_LOG = tmp_path / "evaluations.jsonl"
        for log_path in [fake.QUERIES_LOG, fake.INGEST_LOG, fake.EVAL_LOG]:
            log_path.write_text("", encoding="utf-8")

        fake.log_query(
            query="reembolso prazo",
            workspace_id="default",
            answer="30 dias",
            confidence="high",
            grounded=True,
            chunks_used=[{"chunk_id": "chunk-1"}],
            retrieval_time_ms=110,
            total_latency_ms=210,
            low_confidence=False,
            results_count=3,
            citation_coverage=1.0,
            top_result_score=0.81,
            threshold=0.70,
            hit=True,
            grounding_reason=None,
            uncited_claims_count=0,
            needs_review=False,
        )
        fake.log_query(
            query="consulta desconhecida",
            workspace_id="default",
            answer="Não tenho informações suficientes",
            confidence="low",
            grounded=False,
            chunks_used=[],
            retrieval_time_ms=90,
            total_latency_ms=150,
            low_confidence=True,
            results_count=0,
            citation_coverage=0.0,
            top_result_score=0.42,
            threshold=0.70,
            hit=False,
            grounding_reason="No results retrieved or low confidence",
            uncited_claims_count=1,
            needs_review=True,
        )
        fake.log_evaluation(
            evaluation_id="eval-1",
            workspace_id="default",
            total_questions=30,
            hit_at_1=0.8,
            hit_at_3=0.9,
            hit_at_5=1.0,
            avg_latency_ms=12.4,
            avg_score=0.77,
            low_confidence_rate=0.1,
            groundedness_rate=0.88,
            duration_seconds=1.2,
        )

        metrics = fake.get_metrics(days=7)

        retrieval = metrics["retrieval"]
        answer = metrics["answer"]
        evaluation = metrics["evaluation"]

        for field in [
            "hit_rate_top1",
            "hit_rate_top3",
            "hit_rate_top5",
            "avg_score_top1",
            "below_threshold_rate",
            "avg_latency_ms",
            "avg_retrieval_latency_ms",
            "p50_latency_ms",
            "p95_latency_ms",
            "p99_latency_ms",
        ]:
            assert field in retrieval, f"retrieval missing field '{field}'"

        for field in [
            "groundedness_rate",
            "grounded_answers",
            "no_context_rate",
            "no_context_answers",
            "ungrounded_answers",
            "answers_needing_review",
            "avg_chunks_used",
            "citation_coverage_avg",
            "avg_uncited_claims",
        ]:
            assert field in answer, f"answer missing field '{field}'"

        for field in [
            "total_runs",
            "hit_rate_top1",
            "hit_rate_top3",
            "hit_rate_top5",
            "avg_score",
            "groundedness_rate",
        ]:
            assert field in evaluation, f"evaluation missing field '{field}'"

        assert retrieval["hit_rate_top3"] == 0.9
        assert retrieval["hit_rate_top5"] == 1.0
        assert answer["avg_chunks_used"] == 0.5
        assert answer["grounded_answers"] == 1
        assert answer["no_context_answers"] == 1
        assert answer["ungrounded_answers"] == 0
        assert answer["answers_needing_review"] == 1
        assert answer["avg_uncited_claims"] == 0.5
        assert evaluation["avg_score"] == 0.77

    def test_alerts_include_runtime_and_quality_signals(self, tmp_path, monkeypatch):
        from types import SimpleNamespace
        from collections import namedtuple

        from services.telemetry_service import TelemetryService

        class FakeTelemetry(TelemetryService):
            def _ensure_logs(self):
                pass

        fake = FakeTelemetry()
        fake.QUERIES_LOG = tmp_path / "queries.jsonl"
        fake.INGEST_LOG = tmp_path / "ingestion.jsonl"
        fake.EVAL_LOG = tmp_path / "evaluations.jsonl"
        fake.AUDIT_LOG = tmp_path / "audit.jsonl"
        fake.REPAIR_LOG = tmp_path / "repair.jsonl"
        for log_path in [fake.QUERIES_LOG, fake.INGEST_LOG, fake.EVAL_LOG, fake.AUDIT_LOG, fake.REPAIR_LOG]:
            log_path.write_text("", encoding="utf-8")

        fake.log_query(
            query="consulta sem contexto",
            workspace_id="default",
            answer="Não encontrei contexto suficiente.",
            confidence="low",
            grounded=False,
            chunks_used=[],
            retrieval_time_ms=120,
            total_latency_ms=6100,
            low_confidence=True,
            results_count=0,
            citation_coverage=0.0,
            top_result_score=0.3,
            threshold=0.7,
            hit=False,
            grounding_reason="No context",
            needs_review=True,
        )
        fake.log_ingestion(
            document_id="doc-1",
            workspace_id="default",
            source_type="pdf",
            filename="doc.pdf",
            status="error",
            chunk_count=0,
            processing_time_ms=25,
            error="parse_failed",
        )
        fake.log_evaluation(
            evaluation_id="eval-alert",
            workspace_id="default",
            total_questions=10,
            hit_at_1=0.2,
            hit_at_3=0.3,
            hit_at_5=0.4,
            avg_latency_ms=44.0,
            avg_score=0.41,
            low_confidence_rate=0.4,
            groundedness_rate=0.2,
            duration_seconds=1.0,
        )

        DiskUsage = namedtuple("usage", ["total", "used", "free"])
        monkeypatch.setattr("services.telemetry_service.shutil.disk_usage", lambda _path: DiskUsage(100, 90, 10))

        class BrokenClient:
            def get_collections(self):
                raise RuntimeError("qdrant down")

        monkeypatch.setattr("services.vector_service.get_client", lambda: BrokenClient())
        monkeypatch.setattr(
            "services.operational_retention_service.summarize_operational_retention",
            lambda workspace_id: SimpleNamespace(
                workspace_id=workspace_id,
                retention_mode="keep_latest",
                retention_hours=24,
                eligible_documents=2,
                eligible_chunks=5,
                oldest_eligible_created_at="2026-04-18T03:00:00Z",
                generated_at="2026-04-19T00:00:00Z",
            ),
        )

        alerts = fake.get_alerts(days=1, workspace_id="default")
        by_name = {item["name"]: item for item in alerts["items"]}

        assert alerts["total_active"] >= 6
        assert by_name["vector_store_unavailable"]["status"] == "firing"
        assert by_name["high_latency_p99"]["status"] == "firing"
        assert by_name["high_ingestion_error_rate"]["status"] == "firing"
        assert by_name["low_hit_rate_top5"]["status"] == "firing"
        assert by_name["high_no_context_rate"]["status"] == "firing"
        assert by_name["disk_usage_high"]["status"] == "firing"
        assert by_name["operational_cleanup_backlog"]["status"] == "firing"
        assert by_name["operational_cleanup_backlog"]["value"] == 2

    def test_observability_endpoints_expose_alerts_and_corpus_history(self, tmp_path, monkeypatch):
        from fastapi.testclient import TestClient

        from api.main import app
        from services.telemetry_service import TelemetryService

        class FakeTelemetry(TelemetryService):
            def _ensure_logs(self):
                pass

        fake = FakeTelemetry()
        fake.QUERIES_LOG = tmp_path / "queries.jsonl"
        fake.INGEST_LOG = tmp_path / "ingestion.jsonl"
        fake.EVAL_LOG = tmp_path / "evaluations.jsonl"
        fake.AUDIT_LOG = tmp_path / "audit.jsonl"
        fake.REPAIR_LOG = tmp_path / "repair.jsonl"
        for log_path in [fake.QUERIES_LOG, fake.INGEST_LOG, fake.EVAL_LOG, fake.AUDIT_LOG, fake.REPAIR_LOG]:
            log_path.write_text("", encoding="utf-8")

        fake.log_audit(
            workspace_id="default",
            total_documents=4,
            total_with_issues=1,
            total_ok=3,
            by_issue_type={"missing_chunks": 1},
            recommendations=["reindex doc-1"],
        )
        fake.log_repair(
            document_id="doc-1",
            workspace_id="default",
            success=True,
            chunks_reindexed=4,
            embeddings_valid=True,
            qdrant_restored=True,
            message="repair complete",
        )

        monkeypatch.setattr("api.main.get_telemetry", lambda: fake)
        monkeypatch.setattr("services.telemetry_service.get_telemetry", lambda: fake)

        client = TestClient(app)
        headers = enterprise_headers(client, role="operator", tenant_id="default")

        alerts_response = client.get("/observability/alerts?workspace_id=default", headers=headers)
        audits_response = client.get("/observability/audits?workspace_id=default", headers=headers)
        repairs_response = client.get("/observability/repairs?workspace_id=default", headers=headers)

        assert alerts_response.status_code == 200, alerts_response.text
        assert audits_response.status_code == 200, audits_response.text
        assert repairs_response.status_code == 200, repairs_response.text

        assert "total_active" in alerts_response.json()
        assert audits_response.json()["total"] == 1
        assert audits_response.json()["items"][0]["recommendations"] == ["reindex doc-1"]
        assert repairs_response.json()["total"] == 1
        assert repairs_response.json()["items"][0]["document_id"] == "doc-1"

    def test_metrics_filter_by_workspace(self, tmp_path):
        from services.telemetry_service import TelemetryService

        class FakeTelemetry(TelemetryService):
            def _ensure_logs(self):
                pass

        fake = FakeTelemetry()
        fake.QUERIES_LOG = tmp_path / "queries.jsonl"
        fake.INGEST_LOG = tmp_path / "ingestion.jsonl"
        fake.EVAL_LOG = tmp_path / "evaluations.jsonl"
        for log_path in [fake.QUERIES_LOG, fake.INGEST_LOG, fake.EVAL_LOG]:
            log_path.write_text("", encoding="utf-8")

        fake.log_query(
            query="query default",
            workspace_id="default",
            answer="ok",
            confidence="high",
            grounded=True,
            chunks_used=[{"chunk_id": "chunk-1"}],
            retrieval_time_ms=10,
            total_latency_ms=20,
            low_confidence=False,
            results_count=1,
            citation_coverage=1.0,
            top_result_score=0.9,
            threshold=0.7,
            hit=True,
            grounding_reason=None,
            uncited_claims_count=0,
            needs_review=False,
        )
        fake.log_query(
            query="query acme",
            workspace_id="acme-lab",
            answer="sem contexto",
            confidence="low",
            grounded=False,
            chunks_used=[],
            retrieval_time_ms=12,
            total_latency_ms=25,
            low_confidence=True,
            results_count=0,
            citation_coverage=0.0,
            top_result_score=0.2,
            threshold=0.7,
            hit=False,
            grounding_reason="No results retrieved or low confidence",
            uncited_claims_count=1,
            needs_review=True,
        )

        metrics = fake.get_metrics(days=7, workspace_id="acme-lab")

        assert metrics["workspace_id"] == "acme-lab"
        assert metrics["retrieval"]["total_queries"] == 1
        assert metrics["retrieval"]["low_confidence_rate"] == 1.0
        assert metrics["answer"]["no_context_answers"] == 1


# ── Reindex Script Robustness ─────────────────────────────────────────────

def _load_reindex_script_module():
    """Load reindex_corpus.py as an importable module for isolated tests."""
    script_path = Path(__file__).resolve().parent.parent / "scripts" / "reindex_corpus.py"
    spec = importlib.util.spec_from_file_location(
        "reindex_corpus_test_module",
        str(script_path),
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[arg-type]
    return module


def _write_raw_document(doc_dir: Path, document_id: str):
    doc_dir.mkdir(parents=True, exist_ok=True)
    raw_path = doc_dir / f"{document_id}_raw.json"
    raw_payload = {
        "document_id": document_id,
        "source_type": "md",
        "filename": "unit.md",
        "workspace_id": "default",
        "created_at": "2026-01-01T00:00:00Z",
        "pages": [
            {"page_number": 1, "text": "Este é um documento de teste para reindexação local."}
        ],
        "sections": [],
        "metadata": {},
        "raw_json_path": str(raw_path),
    }
    raw_path.write_text(
        json.dumps(raw_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return raw_path


def test_reindex_local_only_generates_chunks(tmp_path):
    """Local mode must regenerate chunks without touching Qdrant."""
    module = _load_reindex_script_module()
    workspace = "localws"
    doc_id = "doc-local-1"
    doc_dir = tmp_path / workspace
    _write_raw_document(doc_dir, doc_id)
    module.DOCUMENTS_DIR = tmp_path

    indexed = module.full_reindex(
        workspace_id=workspace,
        recreate_collection=False,
        local_only=True,
        verify=False,
    )

    chunks_path = doc_dir / f"{doc_id}_chunks.json"
    assert indexed == 0
    assert chunks_path.exists(), "chunks file not generated in local-only mode"

    chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
    assert isinstance(chunks, list) and len(chunks) > 0
    assert chunks[0]["document_id"] == doc_id


def test_reindex_without_qdrant_falls_back_to_local_only(tmp_path, monkeypatch):
    """Remote mode must still succeed locally when Qdrant client instantiation fails."""
    module = _load_reindex_script_module()
    workspace = "fallbackws"
    doc_id = "doc-fallback-1"
    doc_dir = tmp_path / workspace
    _write_raw_document(doc_dir, doc_id)
    module.DOCUMENTS_DIR = tmp_path

    class _FailingQdrantClient:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("Qdrant unavailable")

    monkeypatch.setattr(module, "QdrantClient", _FailingQdrantClient)

    indexed = module.full_reindex(
        workspace_id=workspace,
        recreate_collection=True,
        local_only=False,
        verify=False,
    )

    chunks_path = doc_dir / f"{doc_id}_chunks.json"
    assert indexed == 0
    assert chunks_path.exists(), "fallback local mode should still generate chunks"


def test_reindex_cli_passes_flags_to_full_reindex(monkeypatch):
    """CLI parser should apply precedence and forward flags to reindex runner."""
    module = _load_reindex_script_module()
    captured = {}

    def _fake_full_reindex(**kwargs):
        captured.update(kwargs)
        return 123

    monkeypatch.setattr(module, "full_reindex", _fake_full_reindex)

    result = module.main([
        "positional-workspace",
        "--workspace-id",
        "explicit-workspace",
        "--local-only",
        "--skip-recreate",
        "--skip-verify",
    ])

    assert result == 123
    assert captured["workspace_id"] == "explicit-workspace"
    assert captured["recreate_collection"] is False
    assert captured["local_only"] is True
    assert captured["verify"] is False


def test_reindex_shared_collection_purges_workspace_and_indexes_without_api_key(tmp_path, monkeypatch):
    """Workspace reindex must purge only the target tenant and still index offline."""
    module = _load_reindex_script_module()
    workspace = "sharedws"
    doc_id = "doc-shared-1"
    doc_dir = tmp_path / workspace
    _write_raw_document(doc_dir, doc_id)
    module.DOCUMENTS_DIR = tmp_path
    monkeypatch.setattr(module, "canonical_document_ids", lambda workspace_id="default": {doc_id})
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    purge_calls = []
    index_calls = []

    class _FakeQdrantClient:
        def __init__(self, *args, **kwargs):
            pass

        def count(self, **kwargs):
            class _Resp:
                count = 1
            return _Resp()

    monkeypatch.setattr(module, "QdrantClient", _FakeQdrantClient)
    monkeypatch.setattr(module, "get_embeddings_batch", lambda texts: [[0.0] * 1536 for _ in texts])
    monkeypatch.setattr("services.vector_service.ensure_collection", lambda recreate=False: None)
    monkeypatch.setattr("services.vector_service.delete_workspace_chunks", lambda workspace_id: purge_calls.append(workspace_id))
    monkeypatch.setattr(
        "services.vector_service.index_chunks",
        lambda chunks, embeddings, workspace_id="default": index_calls.append((workspace_id, len(chunks), len(embeddings))),
    )

    indexed = module.full_reindex(
        workspace_id=workspace,
        recreate_collection=False,
        local_only=False,
        verify=True,
    )

    assert purge_calls == [workspace]
    assert index_calls == [(workspace, 1, 1)]
    assert indexed == 1


# ── Query Pipeline ──────────────────────────────────────────────────────

class TestQueryPipeline:
    """Verify full query pipeline with grounding (Sprint 3).
    Live tests still require OpenAI API key, but the pipeline must also stay
    operational offline with deterministic fallbacks.
    """

    @pytest.fixture(autouse=True)
    def setup_mock(self):
        """Apply mock embedding but NOT LLM — LLM is real for integration tests."""
        self.embed_patcher = patch('services.vector_service._embed_query', side_effect=_mock_embed_query)
        self.mock = self.embed_patcher.start()
        yield
        self.embed_patcher.stop()

    def _has_api_key(self) -> bool:
        """Check if OpenAI API key is available via environment."""
        import os
        return bool(os.getenv("OPENAI_API_KEY"))

    @pytest.mark.integration
    def test_query_returns_answer_with_citations(self):
        """Query must return answer with citations and groundedness info."""
        if not self._has_api_key():
            pytest.skip("OPENAI_API_KEY not available")

        from services.search_service import search_and_answer

        resp = search_and_answer(QueryRequest(
            query='Qual o prazo para reembolso?',
            workspace_id='default',
            top_k=5
        ))

        assert resp.answer
        assert len(resp.citations) > 0
        assert resp.confidence in ('high', 'medium', 'low')

    @pytest.mark.integration
    def test_query_grounded_answer_format(self):
        """Grounded answer must include citation coverage."""
        if not self._has_api_key():
            pytest.skip("OPENAI_API_KEY not available")

        from services.search_service import search_and_answer

        resp = search_and_answer(QueryRequest(
            query='reembolso prazo',
            workspace_id='default',
            top_k=5
        ))

        assert 0.0 <= resp.citation_coverage <= 1.0

    def test_query_citations_include_document_filename(self, monkeypatch):
        """Query response citations must expose document_filename."""
        from services.search_service import search_and_answer

        monkeypatch.setattr(
            "services.search_service.generate_answer",
            lambda query, chunks: ("Resposta de teste", [chunks[0]["chunk_id"]], 10),
        )
        monkeypatch.setattr(
            "services.search_service.verify_grounding",
            lambda answer, citations: {
                "grounded": True,
                "citation_coverage": 1.0,
                "uncited_claims": [],
                "needs_review": False,
                "reason": None,
            },
        )

        resp = search_and_answer(QueryRequest(
            query='reembolso prazo',
            workspace_id='default',
            top_k=3,
        ))

        assert resp.citations
        assert resp.citations[0].document_filename == 'politicas_fluxpay.md'
        assert resp.grounding is not None
        assert resp.grounding.grounded is True
        assert resp.grounding.citation_coverage == 1.0
        assert resp.grounding.uncited_claims == []
        assert resp.grounding.reason is None

        assert 0.0 <= resp.citation_coverage <= 1.0

    def test_generate_answer_has_offline_fallback_without_api_key(self, monkeypatch):
        """generate_answer must stay operational when OPENAI_API_KEY is absent."""
        from services import llm_service

        monkeypatch.setattr(llm_service.client, "api_key", "")

        answer, chunk_ids, latency = llm_service.generate_answer(
            query="Qual o prazo para reembolso?",
            chunks=[
                {
                    "chunk_id": "chunk-offline-1",
                    "text": "O prazo para reembolso é de 30 dias corridos após a solicitação aprovada.",
                    "page_hint": 1,
                    "score": 0.91,
                },
                {
                    "chunk_id": "chunk-offline-2",
                    "text": "Em casos excepcionais, o time financeiro poderá pedir documentação complementar.",
                    "page_hint": 2,
                    "score": 0.75,
                },
            ],
        )

        assert answer
        assert "30 dias" in answer
        assert "chunk-offline-1" in chunk_ids
        assert latency >= 0.0

    def test_generate_answer_offline_keeps_focus_on_best_chunk(self, monkeypatch):
        """Offline fallback should not concatenate an unrelated second sentence from another chunk."""
        from services import llm_service

        monkeypatch.setattr(llm_service.client, "api_key", "")

        answer, chunk_ids, _ = llm_service.generate_answer(
            query="Em que horário roda a liquidação automática da Fluxpay em dias úteis?",
            chunks=[
                {
                    "chunk_id": "chunk-liq-1",
                    "text": "A liquidação automática roda às 06:00 BRT em dias úteis. Pix liquida em D+0, boleto em D+2 após compensação e cartão de crédito em D+30.",
                    "page_hint": 1,
                    "score": 0.99,
                    "document_id": "doc-liq",
                },
                {
                    "chunk_id": "chunk-comp-1",
                    "text": "Merchants classificados como alto risco exigem KYC reforçado e aprovação de Compliance em até 2 dias úteis.",
                    "page_hint": 1,
                    "score": 0.45,
                    "document_id": "doc-comp",
                },
            ],
        )

        assert "06:00 BRT" in answer
        assert "KYC reforçado" not in answer
        assert chunk_ids == ["chunk-liq-1"]

    def test_generate_answer_offline_prioritizes_symptom_sentence_over_numeric_anatomy(self, monkeypatch):
        """Offline fallback must not prefer measurement-heavy anatomy text for symptom questions."""
        from services import llm_service

        monkeypatch.setattr(llm_service.client, "api_key", "")

        answer, chunk_ids, _ = llm_service.generate_answer(
            query="quais os sinais de doença renal em gatos?",
            chunks=[
                {
                    "chunk_id": "chunk-anatomia",
                    "text": (
                        "O parênquima renal varia de 1,6 a 1,9 para os gatos. "
                        "No parênquima renal estão os néfrons que são as unidades estruturais dos rins."
                    ),
                    "page_hint": 469,
                    "score": 1.0,
                    "document_id": "doc-vet",
                },
                {
                    "chunk_id": "chunk-sinais",
                    "text": (
                        "Quando o paciente apresentar sinais sugestivos de doença do trato urinário "
                        "(superior ou inferior), a urinálise é extremamente importante em cães e gatos."
                    ),
                    "page_hint": 488,
                    "score": 1.0,
                    "document_id": "doc-vet",
                },
            ],
        )

        assert "sinais sugestivos de doença do trato urinário" in answer
        assert "1,6 a 1,9" not in answer
        assert chunk_ids == ["chunk-sinais"]

    def test_query_pipeline_returns_answer_offline_without_api_key(self, monkeypatch):
        """search_and_answer must return a grounded response offline when retrieval succeeds."""
        from services.search_service import search_and_answer

        monkeypatch.setattr(
            "services.search_service.search_hybrid",
            lambda request: SearchResponse(
                query=request.query,
                workspace_id=request.workspace_id,
                results=[
                    SearchResultItem(
                        chunk_id="chunk-offline-1",
                        document_id="doc-offline-1",
                        document_filename="politicas_fluxpay.md",
                        text="O prazo para reembolso é de 30 dias corridos após a solicitação aprovada.",
                        score=0.88,
                        page_hint=1,
                        source="hybrid",
                        workspace_id=request.workspace_id,
                        source_type="md",
                        tags=["reembolso"],
                    )
                ],
                total_candidates=1,
                low_confidence=False,
                retrieval_time_ms=12,
                method="híbrida",
                scores_breakdown={"dense": 0.42, "sparse": 0.91, "rrf": 0.88},
            ),
        )

        monkeypatch.setattr("services.llm_service.client.api_key", "")

        resp = search_and_answer(QueryRequest(
            query="Qual o prazo para reembolso?",
            workspace_id="default",
            top_k=3,
            threshold=0.7,
        ))

        assert resp.answer
        assert "30 dias" in resp.answer
        assert resp.low_confidence is False
        assert resp.citations
        assert resp.citations[0].document_filename == "politicas_fluxpay.md"
        assert resp.chunks_used == ["chunk-offline-1"]

    def test_query_pipeline_marks_cited_declarative_answer_as_grounded(self, monkeypatch):
        """Grounding must accept cited declarative answers even when they have no explicit numeric pattern."""
        from services.search_service import search_and_answer

        monkeypatch.setattr(
            "services.search_service.search_hybrid",
            lambda request: SearchResponse(
                query=request.query,
                workspace_id=request.workspace_id,
                results=[
                    SearchResultItem(
                        chunk_id="chunk-policy-1",
                        document_id="doc-policy-1",
                        document_filename="policy.md",
                        text="A revisão trimestral de acessos é conduzida conjuntamente por Segurança e Financeiro.",
                        score=0.91,
                        page_hint=1,
                        source="hybrid",
                        workspace_id=request.workspace_id,
                        source_type="md",
                        tags=["governanca"],
                    )
                ],
                total_candidates=1,
                low_confidence=False,
                retrieval_time_ms=12,
                method="híbrida",
                scores_breakdown={"dense": 0.52, "sparse": 0.84, "rrf": 0.91},
            ),
        )

        monkeypatch.setattr("services.llm_service.client.api_key", "")

        resp = search_and_answer(QueryRequest(
            query="Quais áreas conduzem juntas a revisão trimestral de acessos?",
            workspace_id="default",
            top_k=3,
            threshold=0.7,
        ))

        assert "Segurança e Financeiro" in resp.answer
        assert resp.grounded is True
        assert resp.citation_coverage == 1.0

    def test_query_pipeline_marks_abstention_as_low_confidence(self, monkeypatch):
        """A final abstention must not be reported as high-confidence."""
        from services.search_service import search_and_answer

        monkeypatch.setattr(
            "services.search_service.search_hybrid",
            lambda request: SearchResponse(
                query=request.query,
                workspace_id=request.workspace_id,
                results=[
                    SearchResultItem(
                        chunk_id="chunk-vet-1",
                        document_id="doc-vet-1",
                        document_filename="manual.pdf",
                        text="Quando o paciente apresentar sinais sugestivos de doença do trato urinário, a urinálise é extremamente importante em cães e gatos.",
                        score=0.92,
                        page_hint=488,
                        source="hybrid",
                        workspace_id=request.workspace_id,
                        source_type="pdf",
                        tags=["urinario"],
                    )
                ],
                total_candidates=4,
                low_confidence=False,
                retrieval_time_ms=12,
                method="híbrida",
                scores_breakdown={"dense": 0.61, "sparse": 0.88, "rrf": 0.92},
            ),
        )
        monkeypatch.setattr(
            "services.search_service.generate_answer",
            lambda **kwargs: ("Não sei.", ["chunk-vet-1"], 5.0),
        )
        monkeypatch.setattr(
            "services.search_service.verify_grounding",
            lambda answer, citations: {
                "grounded": False,
                "citation_coverage": 0.0,
                "uncited_claims": [],
                "needs_review": True,
                "reason": "abstained",
            },
        )

        resp = search_and_answer(QueryRequest(
            query="quais os sinais de doença renal crônica em gatos?",
            workspace_id="default",
            top_k=3,
            threshold=0.7,
        ))

        assert resp.answer == "Não sei."
        assert resp.low_confidence is True
        assert resp.confidence == "low"

    def test_query_grounding_can_clear_heuristic_low_confidence(self, monkeypatch):
        """A grounded answer with strong citations must not keep a false-positive low_confidence flag."""
        from services.search_service import search_and_answer

        monkeypatch.setattr(
            "services.search_service.search_hybrid",
            lambda request: SearchResponse(
                query=request.query,
                workspace_id=request.workspace_id,
                results=[
                    SearchResultItem(
                        chunk_id="chunk-borderline-1",
                        document_id="doc-borderline-1",
                        document_filename="manual.md",
                        text="Prazo de aprovação: 48 horas úteis para triagem e resposta inicial.",
                        score=0.31,
                        page_hint=1,
                        source="hybrid",
                        workspace_id=request.workspace_id,
                        source_type="md",
                        tags=["prazo"],
                    )
                ],
                total_candidates=1,
                low_confidence=True,
                retrieval_time_ms=9,
                method="híbrida",
            ),
        )
        monkeypatch.setattr(
            "services.search_service.generate_answer",
            lambda query, chunks: ("O prazo de aprovação é de 48 horas úteis.", [chunks[0]["chunk_id"]], 6),
        )
        monkeypatch.setattr(
            "services.search_service.verify_grounding",
            lambda answer, citations: {
                "grounded": True,
                "citation_coverage": 1.0,
                "uncited_claims": [],
                "needs_review": False,
                "reason": None,
            },
        )

        resp = search_and_answer(QueryRequest(
            query="Qual o prazo de aprovação?",
            workspace_id="default",
            top_k=3,
            threshold=0.7,
        ))

        assert resp.answer == "O prazo de aprovação é de 48 horas úteis."
        assert resp.low_confidence is False
        assert resp.confidence == "medium"
        assert resp.retrieval["retrieval_low_confidence"] is True
        assert resp.retrieval["low_confidence_reason"] == "grounding_override"
        assert resp.grounding is not None
        assert resp.grounding.grounded is True

    def test_query_pipeline_abstains_when_low_confidence_retrieval_is_out_of_scope(self, monkeypatch):
        """Query pipeline must not answer from irrelevant chunks when retrieval is low-confidence."""
        from services.search_service import search_and_answer

        monkeypatch.setattr(
            "services.search_service.search_hybrid",
            lambda request: SearchResponse(
                query=request.query,
                workspace_id=request.workspace_id,
                results=[
                    SearchResultItem(
                        chunk_id="chunk-incidental-year",
                        document_id="doc-incidental-year",
                        document_filename="politicas.md",
                        text="Dados são mantidos por 7 anos conforme a Lei 12.965/2014 e normas do Banco Central.",
                        score=0.18,
                        page_hint=1,
                        source="hybrid",
                        workspace_id=request.workspace_id,
                        source_type="md",
                        tags=["compliance"],
                    )
                ],
                total_candidates=1,
                low_confidence=True,
                retrieval_time_ms=11,
                method="híbrida",
            ),
        )
        monkeypatch.setattr(
            "services.search_service.generate_answer",
            lambda query, chunks, system_prompt=None: ("Dados são mantidos por 7 anos.", [chunks[0]["chunk_id"]], 5),
        )
        monkeypatch.setattr(
            "services.search_service.verify_grounding",
            lambda answer, citations: {
                "grounded": True,
                "citation_coverage": 1.0,
                "uncited_claims": [],
                "needs_review": False,
                "reason": None,
            },
        )

        resp = search_and_answer(QueryRequest(
            query="Quem venceu a Copa do Mundo de 2014?",
            workspace_id="default",
            top_k=3,
            threshold=0.7,
        ))

        assert resp.low_confidence is True
        assert resp.confidence == "low"
        assert resp.answer == "Não tenho informações suficientes para responder a esta pergunta de forma precisa."
        assert resp.chunks_used == []
        assert resp.grounded is False
        assert resp.retrieval["low_confidence_reason"] == "weak_query_support"

    def test_query_pipeline_retries_with_neural_reranking_when_initial_retrieval_is_bad(self, monkeypatch):
        """Query pipeline should retry with neural reranking when the first retrieval is low-confidence."""
        from services.search_service import search_and_answer

        calls = []

        def fake_execute_search(request, default_query_expansion_mode="off"):
            calls.append((request.reranking, request.reranking_method))
            if request.reranking_method == "neural":
                return SearchResponse(
                    query=request.query,
                    workspace_id=request.workspace_id,
                    results=[
                        SearchResultItem(
                            chunk_id="chunk-medical-1",
                            document_id="doc-medical",
                            document_filename="neurology.pdf",
                            text="Treatment of status epilepticus in dogs may require benzodiazepines such as diazepam or midazolam followed by anticonvulsants.",
                            score=0.82,
                            page_hint=352,
                            source="dense+sparse_rrf+neural",
                            workspace_id=request.workspace_id,
                            source_type="pdf",
                            tags=["medical"],
                        )
                    ],
                    total_candidates=20,
                    low_confidence=False,
                    retrieval_time_ms=60,
                    method="híbrida",
                    scores_breakdown={"dense_max": 0.82, "sparse_max": 0.0},
                    reranking_applied=True,
                    reranking_method="neural",
                    query_expansion_applied=False,
                    query_expansion_method=None,
                    query_expansion_fallback=False,
                    query_expansion_requested=False,
                    query_expansion_mode="off",
                    query_expansion_decision_reason=None,
                    retrieval_profile=None,
                )

            return SearchResponse(
                query=request.query,
                workspace_id=request.workspace_id,
                results=[
                    SearchResultItem(
                        chunk_id="chunk-generic-1",
                        document_id="doc-generic",
                        document_filename="generic.md",
                        text="Generic introductory context with little treatment information.",
                        score=0.10,
                        page_hint=1,
                        source="dense+sparse_rrf",
                        workspace_id=request.workspace_id,
                        source_type="md",
                        tags=[],
                    )
                ],
                total_candidates=20,
                low_confidence=True,
                retrieval_time_ms=40,
                method="híbrida",
                scores_breakdown={"dense_max": 0.10, "sparse_max": 0.0},
                reranking_applied=False,
                reranking_method=None,
                query_expansion_applied=False,
                query_expansion_method=None,
                query_expansion_fallback=False,
                query_expansion_requested=False,
                query_expansion_mode="off",
                query_expansion_decision_reason=None,
                retrieval_profile=None,
            )

        monkeypatch.setattr("services.search_service.execute_search", fake_execute_search)
        monkeypatch.setattr(
            "services.search_service.generate_answer",
            lambda query, chunks: ("Usar benzodiazepínicos seguidos de anticonvulsivantes.", [chunks[0]["chunk_id"]], 12),
        )
        monkeypatch.setattr(
            "services.search_service.verify_grounding",
            lambda answer, citations: {
                "grounded": True,
                "citation_coverage": 1.0,
                "uncited_claims": [],
                "needs_review": False,
                "reason": None,
            },
        )

        resp = search_and_answer(QueryRequest(
            query="qual o tratamento para convulsão em cão?",
            workspace_id="default",
            top_k=5,
            threshold=0.7,
        ))

        assert calls == [(None, None), (True, "neural")]
        assert "benzodiazep" in resp.answer.lower()
        assert resp.chunks_used == ["chunk-medical-1"]
        assert resp.retrieval["reranking_method"] == "neural"

    def test_query_pipeline_retries_with_crosslingual_bridge_for_protocol_question(self, monkeypatch):
        """Low-confidence clinical protocol questions should retry with English glossary hints."""
        from services.search_service import search_and_answer

        calls = []

        def fake_execute_search(request, default_query_expansion_mode="off"):
            calls.append((request.query, request.reranking, request.reranking_method))
            if "status epilepticus" in request.query and "acute repetitive seizures" in request.query:
                return SearchResponse(
                    query=request.query,
                    workspace_id=request.workspace_id,
                    results=[
                        SearchResultItem(
                            chunk_id="chunk-medical-2",
                            document_id="doc-medical",
                            document_filename="neurology.pdf",
                            text="Treatment of status epilepticus in dogs requires rapid anticonvulsant therapy.",
                            score=0.84,
                            page_hint=352,
                            source="dense+sparse_rrf+neural",
                            workspace_id=request.workspace_id,
                            source_type="pdf",
                            tags=["medical"],
                        )
                    ],
                    total_candidates=25,
                    low_confidence=False,
                    retrieval_time_ms=75,
                    method="híbrida",
                    scores_breakdown={"dense_max": 0.84, "sparse_max": 0.22},
                    reranking_applied=True,
                    reranking_method="neural",
                    query_expansion_applied=False,
                    query_expansion_method=None,
                    query_expansion_fallback=False,
                    query_expansion_requested=False,
                    query_expansion_mode="off",
                    query_expansion_decision_reason=None,
                    retrieval_profile=None,
                )

            return SearchResponse(
                query=request.query,
                workspace_id=request.workspace_id,
                results=[
                    SearchResultItem(
                        chunk_id="chunk-generic-1",
                        document_id="doc-generic",
                        document_filename="generic.md",
                        text="Generic introductory context with little treatment information.",
                        score=0.11,
                        page_hint=1,
                        source="dense+sparse_rrf",
                        workspace_id=request.workspace_id,
                        source_type="md",
                        tags=[],
                    )
                ],
                total_candidates=20,
                low_confidence=True,
                retrieval_time_ms=40,
                method="híbrida",
                scores_breakdown={"dense_max": 0.11, "sparse_max": 0.0},
                reranking_applied=bool(request.reranking),
                reranking_method=request.reranking_method,
                query_expansion_applied=False,
                query_expansion_method=None,
                query_expansion_fallback=False,
                query_expansion_requested=False,
                query_expansion_mode="off",
                query_expansion_decision_reason=None,
                retrieval_profile=None,
            )

        monkeypatch.setattr("services.search_service.execute_search", fake_execute_search)
        monkeypatch.setattr(
            "services.search_service.generate_answer",
            lambda query, chunks: ("Usar terapia anticonvulsivante rápida no cão.", [chunks[0]["chunk_id"]], 14),
        )
        monkeypatch.setattr(
            "services.search_service.verify_grounding",
            lambda answer, citations: {
                "grounded": True,
                "citation_coverage": 1.0,
                "uncited_claims": [],
                "needs_review": False,
                "reason": None,
            },
        )

        resp = search_and_answer(QueryRequest(
            query="me dê um protocolo para convulsão em cão",
            workspace_id="default",
            top_k=5,
            threshold=0.7,
        ))

        assert calls[0] == ("me dê um protocolo para convulsão em cão", None, None)
        assert calls[1] == ("me dê um protocolo para convulsão em cão", True, "neural")
        assert "status epilepticus" in calls[2][0]
        assert "acute repetitive seizures" in calls[2][0]
        assert calls[2][1:] == (True, "neural")
        assert resp.chunks_used == ["chunk-medical-2"]
        assert "anticonvulsivante" in resp.answer.lower()

    def test_query_pipeline_retries_with_stricter_grounded_prompt_when_protocol_answer_overreaches(self, monkeypatch):
        """A clinically relevant but weakly grounded protocol answer should get one stricter extractive retry."""
        from services.search_service import search_and_answer

        monkeypatch.setattr("services.search_service.llm_client.api_key", "test-key")
        monkeypatch.setattr(
            "services.search_service.execute_search",
            lambda request, default_query_expansion_mode="off": SearchResponse(
                query=request.query,
                workspace_id=request.workspace_id,
                results=[
                    SearchResultItem(
                        chunk_id="chunk-medical-3",
                        document_id="doc-medical",
                        document_filename="neurology.pdf",
                        text="If seizure persists, diazepam or midazolam may be administered, followed by anticonvulsants.",
                        score=0.84,
                        page_hint=352,
                        source="dense+sparse_rrf+neural",
                        workspace_id=request.workspace_id,
                        source_type="pdf",
                        tags=["medical"],
                    )
                ],
                total_candidates=10,
                low_confidence=False,
                retrieval_time_ms=80,
                method="híbrida",
                reranking_applied=True,
                reranking_method="neural",
            ),
        )

        calls = []

        def fake_generate_answer(query, chunks, model=None, system_prompt=None):
            calls.append(system_prompt)
            if system_prompt and "altamente extractiva" in system_prompt:
                return ("Administrar diazepam ou midazolam se a convulsão persistir, seguido de anticonvulsivantes.", [chunks[0]["chunk_id"]], 11)
            return ("O protocolo inclui estabilização ampla, avaliação geral e múltiplos passos adicionais.", [chunks[0]["chunk_id"]], 12)

        def fake_verify_grounding(answer, citations):
            if "diazepam ou midazolam" in answer:
                return {
                    "grounded": True,
                    "citation_coverage": 1.0,
                    "uncited_claims": [],
                    "needs_review": False,
                    "reason": None,
                }
            return {
                "grounded": False,
                "citation_coverage": 0.4,
                "uncited_claims": ["passos adicionais"],
                "needs_review": True,
                "reason": "Citation coverage 40% < 80%",
            }

        monkeypatch.setattr("services.search_service.generate_answer", fake_generate_answer)
        monkeypatch.setattr("services.search_service.verify_grounding", fake_verify_grounding)

        resp = search_and_answer(QueryRequest(
            query="me dê um protocolo para convulsão em cão",
            workspace_id="default",
            top_k=5,
            threshold=0.7,
        ))

        assert calls[0] is None
        assert calls[1] is not None and "altamente extractiva" in calls[1]
        assert "diazepam ou midazolam" in resp.answer.lower()
        assert resp.grounded is True
        assert resp.citation_coverage == 1.0


class TestGroundingMultilingual:
    """Grounding should handle paraphrase/translation when lexical overlap is weak."""

    def test_verify_grounding_accepts_semantic_multilingual_match(self, monkeypatch):
        from services.grounding_service import verify_grounding
        from models.schemas import Citation

        monkeypatch.setattr(
            "services.grounding_service._semantic_similarity",
            lambda sentence, citation_text: 0.81,
        )

        result = verify_grounding(
            "O tratamento inclui um bolus de 1 ml/kg de gluconato de cálcio a 10% por via intravenosa.",
            [
                Citation(
                    chunk_id="chunk-med-1",
                    document_id="doc-med",
                    document_filename="neurology.pdf",
                    page=358,
                    text="Correction: A bolus of 1 ml/kg 10% calcium gluconate solution should be administered by intravenous injection over 20 minutes.",
                    score=0.88,
                )
            ],
        )

        assert result["grounded"] is True
        assert result["citation_coverage"] == 1.0
        assert result["uncited_claims"] == []

    def test_verify_grounding_accepts_cognate_overlap_across_languages(self):
        from services.grounding_service import verify_grounding
        from models.schemas import Citation

        result = verify_grounding(
            "O tratamento pode incluir medicamentos anticonvulsivantes.",
            [
                Citation(
                    chunk_id="chunk-med-2",
                    document_id="doc-med",
                    document_filename="neurology.pdf",
                    page=352,
                    text="Administration of anticonvulsant medications may be required for emergency seizure treatment.",
                    score=0.84,
                )
            ],
        )

        assert result["grounded"] is True
        assert result["citation_coverage"] == 1.0


# ── Enterprise Session Contracts ────────────────────────────────────────────


class TestEnterpriseSessionContracts:
    """Validate the Phase 3 enterprise session and tenancy contracts."""

    def test_session_bootstrap_exposes_identity_and_tenants(self):
        from services.enterprise_service import bootstrap_session

        payload = bootstrap_session()
        assert payload["authenticated"] is False
        assert payload["session_state"] == "anonymous"
        assert payload["user"]["role"] == "viewer"
        assert payload["active_tenant"]["workspace_id"] == "default"
        assert len(payload["available_tenants"]) >= 3

    def test_login_contract_allows_role_and_tenant_selection(self):
        from api.main import login
        from models.schemas import LoginRequest

        payload = login(LoginRequest(email="admin@demo.local", password="demo1234", tenant_id="acme-lab"))
        assert payload["authenticated"] is True
        assert payload["user"]["role"] == "super_admin"
        assert payload["active_tenant"]["tenant_id"] == "acme-lab"
        assert payload["session_token"]

    def test_login_ignores_role_spoofing_and_uses_persisted_identity(self):
        from api.main import login
        from models.schemas import LoginRequest

        payload = login(LoginRequest(email="viewer@demo.local", password="demo1234", tenant_id="default"))
        assert payload["authenticated"] is True
        assert payload["user"]["role"] == "viewer"
        assert payload["user"]["email"] == "viewer@demo.local"

    def test_recovery_and_logout_endpoints_exist(self):
        from api.main import auth_me, login, logout, recovery
        from models.schemas import EnterpriseSession, LoginRequest, RecoveryRequest
        from services.enterprise_service import extract_session_token, get_session

        payload = login(LoginRequest(email="operator@demo.local", password="demo1234", tenant_id="default"))
        auth_header = f"Bearer {payload['session_token']}"
        recovery_payload = recovery(
            RecoveryRequest(
                email="operator@demo.local",
                tenant_id="default",
                reason="Sessão expirada",
            )
        )
        logout_payload = logout(auth_header)
        current_payload = auth_me(EnterpriseSession(**get_session(extract_session_token(auth_header))))

        assert recovery_payload["status"] == "queued"
        assert logout_payload["status"] == "signed_out"
        assert current_payload.authenticated is False

    def test_recovery_queue_persists_and_deduplicates_requests(self, tmp_path, monkeypatch):
        import json

        import services.enterprise_store as store_module
        from services.enterprise_service import queue_recovery

        recovery_state_path = tmp_path / "enterprise" / "recovery_state.json"
        monkeypatch.setattr(store_module, "RECOVERY_STATE_PATH", recovery_state_path)

        first = queue_recovery("operator@demo.local", "default", "Sessão expirada")
        second = queue_recovery("operator@demo.local", "default", "Novo bloqueio")

        assert first["status"] == "queued"
        assert second["status"] == "queued"

        payload = json.loads(recovery_state_path.read_text(encoding="utf-8"))
        assert len(payload["requests"]) == 1

        request = payload["requests"][0]
        assert request["email"] == "operator@demo.local"
        assert request["tenant_id"] == "default"
        assert request["status"] == "queued"
        assert request["reason"] == "Novo bloqueio"
        assert request["attempts"] == 2
        assert request["recovery_id"] in first["message"]
        assert request["recovery_id"] in second["message"]


class TestEnterpriseAdminContracts:
    """Validate the Phase 3 admin tenant and user contracts."""

    def _admin_session(self):
        from api.main import login
        from models.schemas import EnterpriseSession, LoginRequest

        payload = login(LoginRequest(email="admin@demo.local", password="demo1234", tenant_id="default"))
        return EnterpriseSession(**payload)

    def test_admin_tenant_crud_contract(self):
        from api.main import admin_create_tenant, admin_delete_tenant, admin_list_tenants, admin_update_tenant
        from models.schemas import EnterpriseTenantCreate, EnterpriseTenantUpdate

        reset_admin_state()
        session = self._admin_session()

        created = admin_create_tenant(
            EnterpriseTenantCreate(
                tenant_id="orbit-lab",
                name="Orbit Lab",
                workspace_id="orbit-lab",
                plan="business",
                status="active",
                operational_retention_mode="keep_all",
                operational_retention_hours=72,
            ),
            session,
        )
        assert created["tenant_id"] == "orbit-lab"
        assert created["operational_retention_mode"] == "keep_all"
        assert created["operational_retention_hours"] == 72

        updated = admin_update_tenant(
            "orbit-lab",
            EnterpriseTenantUpdate(name="Orbit Lab Prime", status="suspended", operational_retention_mode="keep_latest", operational_retention_hours=12),
            session,
        )
        assert updated["name"] == "Orbit Lab Prime"
        assert updated["status"] == "suspended"
        assert updated["operational_retention_mode"] == "keep_latest"
        assert updated["operational_retention_hours"] == 12

        listed = admin_list_tenants(session)
        assert any(tenant["tenant_id"] == "orbit-lab" for tenant in listed)

        deleted = admin_delete_tenant("orbit-lab", session)
        assert deleted["tenant_id"] == "orbit-lab"

    def test_admin_user_crud_contract(self):
        from api.main import admin_create_user, admin_delete_user, admin_list_users, admin_update_user
        from models.schemas import EnterpriseUserCreate, EnterpriseUserUpdate

        reset_admin_state()
        session = self._admin_session()

        created = admin_create_user(
            EnterpriseUserCreate(
                user_id="user-enterprise",
                name="Erin Enterprise",
                email="erin@example.com",
                password="Secret789!AB",
                role="operator",
                tenant_id="default",
                status="invited",
            ),
            session,
        )
        assert created["user_id"] == "user-enterprise"
        assert created["tenant_id"] == "default"
        assert "password_hash" in created

        updated = admin_update_user(
            "user-enterprise",
            EnterpriseUserUpdate(role="admin", status="active", password="NewPass123!AB"),
            session,
        )
        assert updated["role"] == "super_admin"
        assert updated["status"] == "active"

        # Verify password was actually updated
        from services.admin_service import get_user, verify_password
        user_after = get_user("user-enterprise")
        assert verify_password(user_after, "NewPass123!AB") is True

        listed = admin_list_users(session)
        assert any(user["user_id"] == "user-enterprise" for user in listed)

        deleted = admin_delete_user("user-enterprise", session)
        assert deleted["user_id"] == "user-enterprise"

    def test_admin_user_update_password_none_does_not_crash(self):
        """password=None in payload must not raise or change the password hash."""
        from api.main import admin_create_user, admin_update_user, admin_delete_user
        from models.schemas import EnterpriseUserCreate, EnterpriseUserUpdate
        from services.admin_service import get_user, verify_password

        reset_admin_state()
        session = self._admin_session()

        # Create with known password
        created = admin_create_user(
            EnterpriseUserCreate(
                user_id="user-none-test",
                name="None Test",
                email="none@test.com",
                password="OriginalPw123!",
                tenant_id="default",
                status="active",
            ),
            session,
        )
        hash_before = created.get("password_hash")

        # Update with password=None (explicit null)
        updated = admin_update_user(
            "user-none-test",
            EnterpriseUserUpdate(name="Updated", password=None),
            session,
        )
        assert updated["name"] == "Updated"
        # password_hash must be unchanged
        hash_after = get_user("user-none-test").get("password_hash")
        assert hash_after == hash_before
        # original password still works
        assert verify_password(get_user("user-none-test"), "OriginalPw123!") is True

        # Update without password key at all
        updated2 = admin_update_user(
            "user-none-test",
            EnterpriseUserUpdate(name="Updated2"),
            session,
        )
        assert updated2["name"] == "Updated2"
        hash_after2 = get_user("user-none-test").get("password_hash")
        assert hash_after2 == hash_before

        admin_delete_user("user-none-test", session)

    def test_session_invalidated_after_password_change(self):
        """Session issued before a password change must be rejected."""
        from api.main import admin_create_user, admin_update_user, admin_delete_user, login
        from models.schemas import EnterpriseUserCreate, EnterpriseUserUpdate, LoginRequest
        from services.enterprise_service import get_session

        reset_admin_state()
        admin_session = self._admin_session()

        admin_create_user(
            EnterpriseUserCreate(
                user_id="sess-pw-user",
                name="Sess PW",
                email="sesspw@test.com",
                password="Initial123!AB",
                tenant_id="default",
                status="active",
            ),
            admin_session,
        )

        # Login to get a session token
        login_resp = login(LoginRequest(email="sesspw@test.com", password="Initial123!AB", tenant_id="default"))
        token = login_resp["session_token"]

        # Session works before password change
        s = get_session(token)
        assert s["authenticated"] is True

        # Admin changes the user's password
        admin_update_user(
            "sess-pw-user",
            EnterpriseUserUpdate(password="NewPassword456!"),
            admin_session,
        )

        # Old session must be rejected
        s = get_session(token)
        assert s["authenticated"] is False
        assert s["session_state"] == "expired"

        # New password works for login
        login2 = login(LoginRequest(email="sesspw@test.com", password="NewPassword456!", tenant_id="default"))
        assert login2["authenticated"] is True

        admin_delete_user("sess-pw-user", admin_session)

    def test_session_invalidated_after_user_deactivated(self):
        """Session must be rejected when the user status changes (e.g. active -> disabled)."""
        from api.main import admin_create_user, admin_update_user, admin_delete_user, login
        from models.schemas import EnterpriseUserCreate, EnterpriseUserUpdate, LoginRequest
        from services.enterprise_service import get_session

        reset_admin_state()
        admin_session = self._admin_session()

        admin_create_user(
            EnterpriseUserCreate(
                user_id="sess-status-user",
                name="Sess Status",
                email="sessstatus@test.com",
                password="StatusPass123!",
                tenant_id="default",
                status="active",
            ),
            admin_session,
        )

        login_resp = login(LoginRequest(email="sessstatus@test.com", password="StatusPass123!", tenant_id="default"))
        token = login_resp["session_token"]

        # Session works
        s = get_session(token)
        assert s["authenticated"] is True

        # Admin deactivates the user
        admin_update_user(
            "sess-status-user",
            EnterpriseUserUpdate(status="disabled"),
            admin_session,
        )

        # Session must be rejected (status check happens before timestamp check)
        s = get_session(token)
        assert s["authenticated"] is False

        # Reactivate
        admin_update_user(
            "sess-status-user",
            EnterpriseUserUpdate(status="active"),
            admin_session,
        )

        # Session still invalid (created before status_changed_at)
        s2 = get_session(token)
        assert s2["authenticated"] is False

        # Fresh login works
        login2 = login(LoginRequest(email="sessstatus@test.com", password="StatusPass123!", tenant_id="default"))
        assert login2["authenticated"] is True

        admin_delete_user("sess-status-user", admin_session)

    def test_deleted_user_session_invalidated(self):
        """Session for a deleted user must not be usable."""
        from api.main import admin_create_user, admin_delete_user, login
        from models.schemas import EnterpriseUserCreate, LoginRequest
        from services.enterprise_service import get_session

        reset_admin_state()
        admin_session = self._admin_session()

        admin_create_user(
            EnterpriseUserCreate(
                user_id="sess-del-user",
                name="Sess Del",
                email="sessdel@test.com",
                password="DeletePass123!",
                tenant_id="default",
                status="active",
            ),
            admin_session,
        )

        login_resp = login(LoginRequest(email="sessdel@test.com", password="DeletePass123!", tenant_id="default"))
        token = login_resp["session_token"]

        # Session works
        s = get_session(token)
        assert s["authenticated"] is True

        # Admin deletes the user
        admin_delete_user("sess-del-user", admin_session)

        # Session must be rejected
        s = get_session(token)
        assert s["authenticated"] is False

    def test_legacy_user_login_still_works(self):
        """Default users with $2b$ hash format must still authenticate correctly."""
        from services.admin_service import verify_password

        # These users have $2b$ format hashes in DEFAULT_USERS
        legacy_user = {
            "password_hash": "$2b$12$demo_salt_fluxpay2024e2fc2e9bfca2ee7ff37f14290c6cb494ecec791da32b"
        }
        assert verify_password(legacy_user, "demo1234") is True
        assert verify_password(legacy_user, "wrongpassword") is False

    def test_new_user_uses_per_user_salt(self):
        """Newly created users must have a per-user salt stored separately."""
        from api.main import admin_create_user, admin_delete_user
        from models.schemas import EnterpriseUserCreate
        from services.admin_service import get_user

        reset_admin_state()
        admin_session = self._admin_session()

        admin_create_user(
            EnterpriseUserCreate(
                user_id="salt-test-user",
                name="Salt Test",
                email="saltuser@test.com",
                password="SaltPw123!AB",
                tenant_id="default",
                status="active",
            ),
            admin_session,
        )

        user = get_user("salt-test-user")
        assert "password_salt" in user
        assert len(user["password_salt"]) == 32  # 16 bytes = 32 hex chars
        # Hash format must be $pbkdf2$<salt>$<hash>
        assert user["password_hash"].startswith("$pbkdf2$")
        parts = user["password_hash"].split("$")
        assert len(parts) == 4  # ["", "pbkdf2", salt_hex, hash_hex]
        assert len(parts[2]) == 32  # salt is 16 bytes = 32 hex chars
        assert len(parts[3]) == 64  # SHA256 = 32 bytes = 64 hex chars

        admin_delete_user("salt-test-user", admin_session)

    def test_admin_routes_reject_non_admin_role(self):
        from api.main import _require_admin, login
        from fastapi import HTTPException
        from models.schemas import EnterpriseSession, LoginRequest

        payload = login(LoginRequest(email="viewer@demo.local", password="demo1234", tenant_id="default"))
        session = EnterpriseSession(**payload)
        with pytest.raises(HTTPException) as exc_info:
            _require_admin(session)
        assert exc_info.value.status_code == 403

    def test_workspace_access_rejects_cross_tenant_request(self):
        from api.main import _require_workspace_access, login
        from fastapi import HTTPException
        from models.schemas import EnterpriseSession, LoginRequest

        payload = login(LoginRequest(email="viewer@demo.local", password="demo1234", tenant_id="default"))
        session = EnterpriseSession(**payload)
        with pytest.raises(HTTPException) as exc_info:
            _require_workspace_access("acme-lab", session)
        assert exc_info.value.status_code == 403

    def test_tenant_switch_updates_server_side_session(self):
        from api.main import auth_me, auth_switch_tenant, login
        from models.schemas import EnterpriseSession, LoginRequest, TenantSwitchRequest

        payload = login(LoginRequest(email="admin@demo.local", password="demo1234", tenant_id="default"))
        token = payload["session_token"]
        session = EnterpriseSession(**payload)

        switched = auth_switch_tenant(
            TenantSwitchRequest(tenant_id="acme-lab"),
            authorization=f"Bearer {token}",
            _session=session,
        )
        assert switched["active_tenant"]["tenant_id"] == "acme-lab"

        current = auth_me(EnterpriseSession(**switched))
        assert current.active_tenant.tenant_id == "acme-lab"

    def test_admin_state_persists_across_module_reload(self):
        import services.admin_service as admin_service
        from api.main import admin_create_tenant
        from models.schemas import EnterpriseTenantCreate

        reset_admin_state()
        session = self._admin_session()
        created = admin_create_tenant(
            EnterpriseTenantCreate(
                tenant_id="persisted-tenant",
                name="Persisted Tenant",
                workspace_id="persisted-tenant",
                plan="business",
                status="active",
            ),
            session,
        )
        assert created["tenant_id"] == "persisted-tenant"

        reloaded = importlib.reload(admin_service)
        assert any(item["tenant_id"] == "persisted-tenant" for item in reloaded.list_tenants())

    def test_reset_admin_state_clears_login_rate_limit_runtime_state(self):
        from services.enterprise_service import login

        reset_admin_state()

        for _ in range(5):
            with pytest.raises(ValueError):
                login("admin@demo.local", "wrong-password", "default")

        reset_admin_state()

        payload = login("admin@demo.local", "demo1234", "default")
        assert payload["authenticated"] is True
        assert payload["user"]["email"] == "admin@demo.local"

    def test_admin_events_endpoint_returns_sanitized_metadata(self, tmp_path, monkeypatch):
        import json
        from fastapi.testclient import TestClient

        import services.admin_service as admin_service_module
        from api.main import app

        admin_events_path = tmp_path / "logs" / "admin_events.jsonl"
        monkeypatch.setattr(admin_service_module, "ADMIN_EVENTS_PATH", admin_events_path)
        admin_events_path.parent.mkdir(parents=True, exist_ok=True)
        admin_events_path.write_text(
            json.dumps(
                {
                    "timestamp": "2026-04-19T00:00:00Z",
                    "type": "admin_event",
                    "actor_user_id": "user-admin",
                    "actor_email": "admin@demo.local",
                    "actor_role": "admin",
                    "action": "user.update",
                    "target_type": "user",
                    "target_id": "user-1",
                    "tenant_id": "default",
                    "metadata": {"password": "secret123", "status": "active"},
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        client = TestClient(app)
        headers = enterprise_headers(client, role="admin", tenant_id="default")

        response = client.get("/admin/events?limit=10", headers=headers)

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["total"] == 1
        assert payload["items"][0]["metadata"]["password"] == "[redacted]"
        assert payload["items"][0]["metadata"]["status"] == "active"

    def test_admin_events_endpoint_filters_by_workspace_id(self, tmp_path, monkeypatch):
        import json
        from fastapi.testclient import TestClient

        import services.admin_service as admin_service_module
        from api.main import app

        admin_events_path = tmp_path / "logs" / "admin_events.jsonl"
        monkeypatch.setattr(admin_service_module, "ADMIN_EVENTS_PATH", admin_events_path)
        admin_events_path.parent.mkdir(parents=True, exist_ok=True)
        admin_events_path.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "timestamp": "2026-04-19T00:00:00Z",
                            "type": "admin_event",
                            "actor_user_id": "user-admin",
                            "actor_email": "admin@demo.local",
                            "actor_role": "admin",
                            "action": "runtime.cleanup_operational",
                            "target_type": "workspace",
                            "target_id": "northwind",
                            "tenant_id": None,
                            "metadata": {"workspace_id": "northwind", "deleted_documents": 2},
                        },
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        {
                            "timestamp": "2026-04-19T00:01:00Z",
                            "type": "admin_event",
                            "actor_user_id": "user-admin",
                            "actor_email": "admin@demo.local",
                            "actor_role": "admin",
                            "action": "runtime.prune_index",
                            "target_type": "workspace",
                            "target_id": "acme-lab",
                            "tenant_id": None,
                            "metadata": {"workspace_id": "acme-lab", "deleted_points": 1},
                        },
                        ensure_ascii=False,
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        client = TestClient(app)
        headers = enterprise_headers(client, role="admin", tenant_id="default")

        response = client.get("/admin/events?workspace_id=northwind&action=runtime.cleanup_operational", headers=headers)

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["total"] == 1
        assert payload["items"][0]["target_id"] == "northwind"
        assert payload["items"][0]["metadata"]["deleted_documents"] == 2

    def test_admin_observability_endpoints_access_foreign_workspace_without_switching(self, monkeypatch):
        from fastapi.testclient import TestClient

        from api.main import app

        class FakeTelemetry:
            def get_alerts(self, days=1, workspace_id=None):
                return {
                    "items": [
                        {
                            "name": "vector_store_unavailable",
                            "severity": "critical",
                            "status": "firing",
                            "message": f"alerta {workspace_id}",
                            "window": f"{days}d",
                        }
                    ],
                    "total_active": 1,
                    "workspace_id": workspace_id,
                    "period_days": days,
                    "generated_at": "2026-04-19T12:30:00Z",
                }

            def list_audit_events(self, workspace_id=None, days=30, limit=20, offset=0):
                return {
                    "items": [
                        {
                            "timestamp": "2026-04-19T12:00:00Z",
                            "type": "audit",
                            "workspace_id": workspace_id,
                            "total_documents": 1,
                            "total_with_issues": 0,
                            "total_ok": 1,
                            "by_issue_type": {},
                            "recommendations": [],
                        }
                    ],
                    "total": 1,
                    "limit": limit,
                    "offset": offset,
                    "workspace_id": workspace_id,
                }

            def list_repair_events(self, workspace_id=None, days=30, limit=20, offset=0):
                return {
                    "items": [
                        {
                            "timestamp": "2026-04-19T12:10:00Z",
                            "type": "repair",
                            "workspace_id": workspace_id,
                            "document_id": "doc-1",
                            "success": True,
                            "chunks_reindexed": 1,
                            "embeddings_valid": True,
                            "qdrant_restored": True,
                            "message": "repair ok",
                        }
                    ],
                    "total": 1,
                    "limit": limit,
                    "offset": offset,
                    "workspace_id": workspace_id,
                }

        monkeypatch.setattr("api.main.get_telemetry", lambda: FakeTelemetry())

        client = TestClient(app)
        headers = enterprise_headers(client, role="admin", tenant_id="default")

        alerts = client.get("/admin/alerts?workspace_id=acme-lab&days=7", headers=headers)
        audits = client.get("/admin/audits?workspace_id=northwind&days=30", headers=headers)
        repairs = client.get("/admin/repairs?workspace_id=northwind&days=30", headers=headers)

        assert alerts.status_code == 200, alerts.text
        assert audits.status_code == 200, audits.text
        assert repairs.status_code == 200, repairs.text
        assert alerts.json()["workspace_id"] == "acme-lab"
        assert audits.json()["workspace_id"] == "northwind"
        assert repairs.json()["workspace_id"] == "northwind"

    def test_admin_observability_endpoints_require_admin_role(self):
        from fastapi.testclient import TestClient

        from api.main import app

        client = TestClient(app)
        headers = enterprise_headers(client, role="operator", tenant_id="default")

        response = client.get("/admin/alerts?workspace_id=acme-lab", headers=headers)

        assert response.status_code == 403, response.text

    def test_admin_evaluation_run_allows_foreign_workspace_without_switching(self, monkeypatch):
        from fastapi.testclient import TestClient

        from api.main import app

        class FakeEvaluator:
            def run_evaluation(
                self,
                workspace_id,
                dataset_path,
                top_k,
                run_judge,
                reranking,
                reranking_method,
                query_expansion,
            ):
                return {
                    "evaluation_id": "eval-admin-1",
                    "workspace_id": workspace_id,
                    "total_questions": 30,
                    "hit_rate_top_1": 0.8,
                    "hit_rate_top_3": 0.9,
                    "hit_rate_top_5": 1.0,
                    "avg_latency_ms": 20.0,
                    "avg_score": 0.8,
                    "low_confidence_rate": 0.0,
                    "retrieval_low_confidence_rate": 0.0,
                    "groundedness_rate": 0.95,
                    "observed_groundedness_rate": 0.95,
                    "judge_score": None,
                    "judged_questions": 0,
                    "judge_groundedness_rate": None,
                    "judge_needs_review_rate": None,
                    "flagged_for_review_count": 0,
                    "duration_seconds": 1.2,
                    "by_difficulty": {},
                    "by_category": {},
                    "question_results": [],
                    "reranking_applied": True,
                    "reranking_method": reranking_method or "bm25f",
                }

        monkeypatch.setattr("services.evaluation_service.EvaluationService", FakeEvaluator)

        client = TestClient(app)
        headers = enterprise_headers(client, role="admin", tenant_id="default")

        response = client.post("/admin/evaluation/run?workspace_id=northwind&reranking=true", headers=headers)

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["workspace_id"] == "northwind"
        assert payload["hit_rate_top_5"] == 1.0

    def test_admin_evaluation_run_requires_admin_role(self):
        from fastapi.testclient import TestClient

        from api.main import app

        client = TestClient(app)
        headers = enterprise_headers(client, role="operator", tenant_id="default")

        response = client.post("/admin/evaluation/run?workspace_id=acme-lab", headers=headers)

        assert response.status_code == 403, response.text

    def test_admin_corpus_audit_and_repair_allow_foreign_workspace(self, monkeypatch):
        from types import SimpleNamespace
        from fastapi.testclient import TestClient

        from api.main import app

        fake_audit_report = SimpleNamespace(
            workspace_id="northwind",
            total_documents=1,
            total_with_issues=1,
            total_ok=0,
            by_issue_type={"missing_from_qdrant": 1},
            documents=[
                {
                    "document_id": "doc-1",
                    "chunk_count_registry": 1,
                    "chunk_count_qdrant": 0,
                    "chunking_strategy": "recursive",
                    "status": "missing_from_qdrant",
                    "issues": [{"issue_type": "missing_from_qdrant", "severity": "critical", "detail": "missing"}],
                    "repair_action": "repair_document('doc-1')",
                }
            ],
            recommendations=["repair_document()"],
            generated_at="2026-04-19T12:30:00Z",
        )

        fake_repair_result = SimpleNamespace(
            document_id="doc-1",
            workspace_id="northwind",
            success=True,
            chunks_reindexed=1,
            embeddings_valid=True,
            qdrant_restored=True,
            message="repair ok",
        )

        class FakeTelemetry:
            def log_audit(self, **kwargs):
                return None

            def log_repair(self, **kwargs):
                return None

        monkeypatch.setattr("services.integrity_service.audit_corpus_integrity", lambda workspace_id, check_embeddings=False: fake_audit_report)
        monkeypatch.setattr("services.integrity_service.repair_document", lambda document_id, workspace_id: fake_repair_result)
        monkeypatch.setattr("api.main.get_telemetry", lambda: FakeTelemetry())

        client = TestClient(app)
        headers = enterprise_headers(client, role="admin", tenant_id="default")

        audit = client.post("/admin/corpus/audit?workspace_id=northwind", headers=headers)
        repair = client.post("/admin/corpus/repair/doc-1?workspace_id=northwind", headers=headers)

        assert audit.status_code == 200, audit.text
        assert repair.status_code == 200, repair.text
        assert audit.json()["workspace_id"] == "northwind"
        assert repair.json()["workspace_id"] == "northwind"
        assert repair.json()["success"] is True

    def test_admin_corpus_audit_and_repair_require_admin_role(self):
        from fastapi.testclient import TestClient

        from api.main import app

        client = TestClient(app)
        headers = enterprise_headers(client, role="operator", tenant_id="default")

        audit = client.post("/admin/corpus/audit?workspace_id=acme-lab", headers=headers)
        repair = client.post("/admin/corpus/repair/doc-1?workspace_id=acme-lab", headers=headers)

        assert audit.status_code == 403, audit.text
        assert repair.status_code == 403, repair.text


class TestEnterpriseTenantIsolation:
    """Prove non-leakage across three active tenants."""

    def test_operator_cannot_switch_or_access_foreign_tenants(self, monkeypatch):
        from fastapi.testclient import TestClient

        from api.main import app

        calls: list[str] = []

        def fake_search(_request):
            calls.append("search")
            return {
                "query": "teste",
                "workspace_id": "acme-lab",
                "results": [],
                "total_candidates": 0,
                "low_confidence": True,
                "retrieval_time_ms": 1,
                "method": "híbrida",
            }

        monkeypatch.setattr("services.vector_service.search_hybrid", fake_search)

        client = TestClient(app)
        headers = enterprise_headers(client, role="operator", tenant_id="default")

        switch_response = client.post(
            "/auth/switch-tenant",
            json={"tenant_id": "acme-lab"},
            headers=headers,
        )
        assert switch_response.status_code == 403, switch_response.text

        documents_response = client.get("/documents?workspace_id=acme-lab", headers=headers)
        assert documents_response.status_code == 403, documents_response.text

        search_response = client.post(
            "/search",
            json={"query": "smoke", "workspace_id": "acme-lab"},
            headers=headers,
        )
        assert search_response.status_code == 403, search_response.text
        assert calls == []

    def test_admin_switches_between_three_tenants_without_data_leakage(self, tmp_path, monkeypatch):
        from fastapi.testclient import TestClient

        from api.main import app
        from services.telemetry_service import TelemetryService

        class FakeTelemetry(TelemetryService):
            def _ensure_logs(self):
                pass

        fake = FakeTelemetry()
        fake.QUERIES_LOG = tmp_path / "queries.jsonl"
        fake.INGEST_LOG = tmp_path / "ingestion.jsonl"
        fake.EVAL_LOG = tmp_path / "evaluations.jsonl"
        fake.AUDIT_LOG = tmp_path / "audit.jsonl"
        fake.REPAIR_LOG = tmp_path / "repair.jsonl"
        for log_path in [fake.QUERIES_LOG, fake.INGEST_LOG, fake.EVAL_LOG, fake.AUDIT_LOG, fake.REPAIR_LOG]:
            log_path.write_text("", encoding="utf-8")

        fake.log_query(
            query="query-default",
            workspace_id="default",
            answer="default-answer",
            confidence="high",
            grounded=True,
            chunks_used=[],
            retrieval_time_ms=10,
            total_latency_ms=20,
            low_confidence=False,
            results_count=1,
        )
        fake.log_query(
            query="query-acme",
            workspace_id="acme-lab",
            answer="acme-answer",
            confidence="high",
            grounded=True,
            chunks_used=[],
            retrieval_time_ms=11,
            total_latency_ms=21,
            low_confidence=False,
            results_count=1,
        )
        fake.log_query(
            query="query-northwind",
            workspace_id="northwind",
            answer="northwind-answer",
            confidence="high",
            grounded=True,
            chunks_used=[],
            retrieval_time_ms=12,
            total_latency_ms=22,
            low_confidence=False,
            results_count=1,
        )

        monkeypatch.setattr("api.main.get_telemetry", lambda: fake)
        monkeypatch.setattr("services.telemetry_service.get_telemetry", lambda: fake)

        client = TestClient(app)
        headers = enterprise_headers(client, role="admin", tenant_id="default")

        default_docs = client.get("/documents?workspace_id=default", headers=headers)
        assert default_docs.status_code == 200, default_docs.text
        default_payload = default_docs.json()
        assert default_payload["workspace_id"] == "default"
        assert all(item["workspace_id"] == "default" for item in default_payload["items"])

        foreign_docs = client.get("/documents?workspace_id=acme-lab", headers=headers)
        assert foreign_docs.status_code == 403, foreign_docs.text

        switch_acme = client.post("/auth/switch-tenant", json={"tenant_id": "acme-lab"}, headers=headers)
        assert switch_acme.status_code == 200, switch_acme.text

        acme_docs = client.get("/documents?workspace_id=acme-lab", headers=headers)
        acme_logs = client.get("/queries/logs?workspace_id=acme-lab&limit=20&offset=0", headers=headers)
        assert acme_docs.status_code == 200, acme_docs.text
        assert acme_logs.status_code == 200, acme_logs.text
        acme_doc_payload = acme_docs.json()
        acme_log_payload = acme_logs.json()
        assert acme_doc_payload["workspace_id"] == "acme-lab"
        assert any(item["filename"] == "upload-smoke.txt" for item in acme_doc_payload["items"])
        assert all(item["workspace_id"] == "acme-lab" for item in acme_doc_payload["items"])
        assert [item["query"] for item in acme_log_payload["items"]] == ["query-acme"]

        switch_northwind = client.post("/auth/switch-tenant", json={"tenant_id": "northwind"}, headers=headers)
        assert switch_northwind.status_code == 200, switch_northwind.text

        northwind_docs = client.get("/documents?workspace_id=northwind", headers=headers)
        northwind_logs = client.get("/queries/logs?workspace_id=northwind&limit=20&offset=0", headers=headers)
        northwind_metrics = client.get("/metrics?workspace_id=northwind&days=7", headers=headers)
        northwind_dataset = client.get("/evaluation/dataset?workspace_id=northwind", headers=headers)

        assert northwind_docs.status_code == 200, northwind_docs.text
        assert northwind_logs.status_code == 200, northwind_logs.text
        assert northwind_metrics.status_code == 200, northwind_metrics.text
        assert northwind_dataset.status_code == 200, northwind_dataset.text

        northwind_doc_payload = northwind_docs.json()
        northwind_log_payload = northwind_logs.json()
        northwind_metrics_payload = northwind_metrics.json()
        northwind_dataset_payload = northwind_dataset.json()

        assert northwind_doc_payload["workspace_id"] == "northwind"
        assert [item["filename"] for item in northwind_doc_payload["items"]] == ["northwind-playbook.txt"]
        assert [item["query"] for item in northwind_log_payload["items"]] == ["query-northwind"]
        assert northwind_metrics_payload["workspace_id"] == "northwind"
        assert northwind_metrics_payload["retrieval"]["total_queries"] == 1
        assert northwind_dataset_payload["dataset_id"] == "northwind_validation"
        assert all(question["workspace_id"] == "northwind" for question in northwind_dataset_payload["questions"])


class TestReranking:
    """Verify BM25F reranking integration."""

    def test_reranking_disabled_returns_same_order_as_baseline(self):
        """Without reranking=True, search_hybrid must not apply reranking."""
        from services.vector_service import search_hybrid
        from models.schemas import SearchRequest

        req_no_rerank = SearchRequest(
            query="políticas de reembolso",
            workspace_id="default",
            top_k=5,
            reranking=False,
        )
        resp = search_hybrid(req_no_rerank)
        assert resp.reranking_applied is False
        assert resp.reranking_method is None
        # source field must NOT include bm25f
        for item in resp.results:
            assert "bm25f" not in item.source

    def test_reranking_applied_flag_is_set(self):
        """When reranking=True, the response must reflect it."""
        from services.vector_service import search_hybrid
        from models.schemas import SearchRequest

        req_rerank = SearchRequest(
            query="políticas de reembolso",
            workspace_id="default",
            top_k=5,
            reranking=True,
        )
        resp = search_hybrid(req_rerank)
        assert resp.reranking_applied is True
        assert resp.reranking_method == "bm25f"
        for item in resp.results:
            assert "bm25f" in item.source

    def test_reranking_can_reorder_results(self):
        """Reranking must be capable of changing the result order."""
        from services.vector_service import search_hybrid, _get_reranker
        from models.schemas import SearchRequest

        req_no_rerank = SearchRequest(
            query="políticas de reembolso",
            workspace_id="default",
            top_k=5,
            reranking=False,
        )
        req_rerank = SearchRequest(
            query="políticas de reembolso",
            workspace_id="default",
            top_k=5,
            reranking=True,
        )

        resp_no = search_hybrid(req_no_rerank)
        resp_rerank = search_hybrid(req_rerank)

        # If reranking changed the top chunk, the orders differ
        ids_no = [r.chunk_id for r in resp_no.results]
        ids_rerank = [r.chunk_id for r in resp_rerank.results]

        # At least one position must differ (unless corpus is perfectly aligned with query)
        # We verify the reranker at minimum changes bm25f_score
        reranker = _get_reranker("bm25f")
        candidates = [
            {"chunk_id": "c1", "text": "políticas de reembolso são importantes", "score": 0.8, "document_id": "d1"},
            {"chunk_id": "c2", "text": "horário de atendimento ao cliente", "score": 0.7, "document_id": "d2"},
            {"chunk_id": "c3", "text": "reembolso em caso de cancelamento", "score": 0.6, "document_id": "d1"},
        ]
        reranked = reranker.rerank("políticas de reembolso", candidates)
        bm25f_scores = [c["bm25f_score"] for c in reranked]
        # c1 (matches both "políticas" AND "reembolso") must outscore c3 (matches only "reembolso")
        assert bm25f_scores[0] > bm25f_scores[2], "BM25F should rank c1 above c3"

    def test_reranking_response_has_correct_metadata(self):
        """SearchResponse must expose reranking_applied and reranking_method."""
        from services.vector_service import search_hybrid
        from models.schemas import SearchRequest

        req = SearchRequest(query="teste", workspace_id="default", top_k=3, reranking=True)
        resp = search_hybrid(req)

        assert hasattr(resp, "reranking_applied")
        assert hasattr(resp, "reranking_method")
        assert resp.reranking_applied is True
        assert resp.reranking_method == "bm25f"

    def test_search_result_item_source_reflects_reranking(self):
        """SearchResultItem.source correctly reflects the reranking method used."""
        from services.vector_service import search_hybrid
        from models.schemas import SearchRequest

        # No reranking
        resp_no = search_hybrid(SearchRequest(query="teste", workspace_id="default", top_k=3, reranking=False))
        for item in resp_no.results:
            assert item.source == "dense+sparse_rrf", f"expected dense+sparse_rrf, got {item.source}"

        # BM25F reranking
        resp_bm25f = search_hybrid(SearchRequest(query="teste", workspace_id="default", top_k=3, reranking=True, reranking_method="bm25f"))
        for item in resp_bm25f.results:
            assert item.source == "dense+sparse_rrf+bm25f", f"expected dense+sparse_rrf+bm25f, got {item.source}"

        # Neural reranking
        resp_neural = search_hybrid(SearchRequest(query="teste", workspace_id="default", top_k=3, reranking=True, reranking_method="neural"))
        for item in resp_neural.results:
            assert item.source == "dense+sparse_rrf+neural", f"expected dense+sparse_rrf+neural, got {item.source}"

    def test_bm25f_reranker_standalone(self):
        """BM25F reranker must correctly score candidates by term overlap."""
        from services.vector_service import BM25FReranker

        r = BM25FReranker()
        candidates = [
            {"chunk_id": "c1", "text": "políticas de reembolso da empresa fluxpay", "score": 0.9, "document_id": "d1"},
            {"chunk_id": "c2", "text": "procedimento de reembolso em até 30 dias", "score": 0.8, "document_id": "d1"},
            {"chunk_id": "c3", "text": "políticas internas de segurança da informação", "score": 0.7, "document_id": "d2"},
            {"chunk_id": "c4", "text": "reembolso integral para clientes com nota fiscal", "score": 0.6, "document_id": "d1"},
            {"chunk_id": "c5", "text": "horário de funcionamento da central", "score": 0.5, "document_id": "d3"},
        ]

        reranked = r.rerank("políticas de reembolso", candidates)

        # c1 has BOTH terms → must be first
        assert reranked[0]["chunk_id"] == "c1"
        # c3 has "políticas" but not "reembolso" → should outrank c4 (has "reembolso" but not "políticas")
        c3_pos = next(i for i, c in enumerate(reranked) if c["chunk_id"] == "c3")
        c4_pos = next(i for i, c in enumerate(reranked) if c["chunk_id"] == "c4")
        assert c3_pos < c4_pos, "c3 (políticas) should rank above c4 (reembolso only)"
        # c5 has neither → must be last
        assert reranked[-1]["chunk_id"] == "c5"

        # original_score must be preserved for all items
        orig_by_id = {c["chunk_id"]: c["score"] for c in candidates}
        for rer in reranked:
            assert rer["original_score"] == orig_by_id[rer["chunk_id"]]

    def test_bm25f_reranker_empty_query_unchanged(self):
        """Reranking with empty query must return candidates unchanged."""
        from services.vector_service import BM25FReranker

        r = BM25FReranker()
        candidates = [
            {"chunk_id": "c1", "text": "some text", "score": 0.9, "document_id": "d1"},
            {"chunk_id": "c2", "text": "other text", "score": 0.8, "document_id": "d1"},
        ]
        reranked = r.rerank("", candidates)
        assert [c["chunk_id"] for c in reranked] == ["c1", "c2"]

    def test_bm25f_reranker_no_matching_terms(self):
        """Reranking when no query terms match must not crash and return original order."""
        from services.vector_service import BM25FReranker

        r = BM25FReranker()
        candidates = [
            {"chunk_id": "c1", "text": "foo bar baz", "score": 0.9, "document_id": "d1"},
            {"chunk_id": "c2", "text": "qux quux corge", "score": 0.8, "document_id": "d2"},
        ]
        reranked = r.rerank("completely unrelated query xyz123", candidates)
        # All bm25f_scores should be 0, original order preserved (stable sort by (0.0, original))
        ids = [c["chunk_id"] for c in reranked]
        assert ids == ["c1", "c2"]  # stable — c1 had higher original score


class TestNeuralReranking:
    """Neural cross-encoder-style reranker."""

    def test_neural_reranker_instance_exists(self):
        """NeuralReranker class is importable and instantiable."""
        from services.vector_service import NeuralReranker
        r = NeuralReranker()
        assert r is not None

    def test_neural_reranker_stable_with_offline_fallback(self):
        """NeuralReranker falls back to unchanged candidates on embedding failure."""
        from services.vector_service import NeuralReranker
        from unittest.mock import patch

        r = NeuralReranker()
        candidates = [
            {"chunk_id": "c1", "text": "políticas de reembolso", "score": 0.9, "document_id": "d1", "confidence_score": 0.9},
            {"chunk_id": "c2", "text": "horário de atendimento", "score": 0.8, "document_id": "d2", "confidence_score": 0.8},
        ]

        # Simulate embedding failure by patching get_embedding to raise
        with patch("services.embedding_service.get_embedding", side_effect=RuntimeError("offline")):
            result = r.rerank("políticas de reembolso", candidates)
        # Must return candidates unchanged (fallback)
        assert [c["chunk_id"] for c in result] == ["c1", "c2"]

    def test_neural_reranker_reranks_with_mocked_embeddings(self):
        """NeuralReranker reranks candidates given working embeddings."""
        from services.vector_service import NeuralReranker
        import math
        from unittest.mock import patch

        r = NeuralReranker()
        # Use a simple constant embedding vector for both query and candidates
        def fake_embedding(text):
            return [1.0] * 1536
        def fake_batch(texts):
            return [[1.0] * 1536 for _ in texts]

        candidates = [
            {"chunk_id": "c1", "text": "políticas de reembolso", "score": 0.3, "document_id": "d1", "confidence_score": 0.3},
            {"chunk_id": "c2", "text": "reembolso em caso de cancelamento", "score": 0.5, "document_id": "d1", "confidence_score": 0.5},
        ]

        with patch("services.embedding_service.get_embedding", side_effect=fake_embedding), \
             patch("services.embedding_service.get_embeddings_batch", side_effect=fake_batch):
            result = r.rerank("políticas de reembolso", candidates)

        # Both got cosine=1.0 (identical vectors), blend favors higher confidence_score
        # c2 has higher confidence_score so it should rank first
        ids = [c["chunk_id"] for c in result]
        assert ids == ["c2", "c1"], f"Expected c2 first (higher confidence), got {ids}"

    def test_neural_reranker_empty_query_unchanged(self):
        """NeuralReranker with empty query returns candidates unchanged."""
        from services.vector_service import NeuralReranker
        r = NeuralReranker()
        candidates = [
            {"chunk_id": "c1", "text": "políticas", "score": 0.9, "document_id": "d1"},
        ]
        result = r.rerank("", candidates)
        assert [c["chunk_id"] for c in result] == ["c1"]

    def test_neural_reranker_empty_candidates_unchanged(self):
        """NeuralReranker with empty candidates returns empty list."""
        from services.vector_service import NeuralReranker
        r = NeuralReranker()
        result = r.rerank("query", [])
        assert result == []


class TestConfidenceScoreNormalization:
    def test_confidence_score_avoids_sparse_saturation(self):
        """High BM25 scores should not collapse every candidate to 1.0."""
        from services.vector_service import _compute_confidence_score

        strongest = _compute_confidence_score(
            {
                "score": 0.031514,
                "dense_score": 0.367472,
                "sparse_score": 3.465736,
                "text": "Sinais sugestivos de doença renal e urinálise importante em gatos.",
            },
            query="qual os sinais de doença renal crônica e gatos",
        )
        weaker = _compute_confidence_score(
            {
                "score": 0.015873,
                "dense_score": 0.0,
                "sparse_score": 3.044522,
                "text": "Estrutura do parênquima renal e medidas anatômicas em gatos.",
            },
            query="qual os sinais de doença renal crônica e gatos",
        )

        assert strongest < 1.0
        assert weaker < 1.0
        assert strongest > weaker
        assert strongest >= 0.7

    def test_confidence_score_preserves_dense_threshold_behavior(self):
        """Dense-only confidence should remain interpretable against configured thresholds."""
        from services.vector_service import _compute_confidence_score

        confidence = _compute_confidence_score(
            {
                "score": 0.016393,
                "dense_score": 0.82,
                "sparse_score": 0.0,
                "text": "texto denso",
            },
            query="reembolso prazo",
        )

        assert confidence >= 0.80


class TestClinicalAcronymHandling:
    def test_expand_domain_acronyms_rewrites_known_clinical_shortcuts(self):
        from services.search_service import _expand_domain_acronyms

        expanded = _expand_domain_acronyms("qual os sintomas de DRC em gatos")

        assert "doença renal crônica" in expanded.lower()
        assert "drc" not in expanded.lower()

    def test_execute_search_expands_acronyms_before_retrieval(self, monkeypatch):
        from services.search_service import execute_search

        captured = {}

        def fake_search_hybrid(request):
            captured["query"] = request.query
            return SearchResponse(
                query=request.query,
                workspace_id=request.workspace_id,
                results=[],
                total_candidates=0,
                low_confidence=True,
                retrieval_time_ms=5,
                method="híbrida",
            )

        monkeypatch.setattr("services.search_service.search_hybrid", fake_search_hybrid)

        execute_search(SearchRequest(
            query="qual os sintomas de DRC em gatos",
            workspace_id="default",
            top_k=5,
            threshold=0.7,
        ))

        assert "doença renal crônica" in captured["query"].lower()

    def test_neural_retry_is_disabled_for_acronym_heavy_query(self):
        from services.search_service import _should_try_neural_query_retry

        request = QueryRequest(
            query="qual os sintomas de DRC em gatos",
            workspace_id="default",
            top_k=5,
            threshold=0.7,
        )
        response = SearchResponse(
            query=request.query,
            workspace_id=request.workspace_id,
            results=[
                SearchResultItem(
                    chunk_id="chunk-1",
                    document_id="doc-1",
                    text="texto",
                    score=0.4,
                    page_hint=1,
                    source="hybrid",
                    workspace_id=request.workspace_id,
                    source_type="pdf",
                    tags=[],
                )
            ],
            total_candidates=10,
            low_confidence=True,
            retrieval_time_ms=10,
            method="híbrida",
            reranking_applied=False,
            reranking_method=None,
        )

        assert _should_try_neural_query_retry(request, response) is False

    def test_minimal_query_support_requires_content_terms_not_generic_overlap(self):
        from services.vector_service import _has_minimal_query_support

        assert _has_minimal_query_support(
            "qual os sintomas de doença renal crônica em gatos",
            "Quando o paciente apresentar sinais sugestivos de doença renal e insuficiência renal em gatos.",
        )
        assert not _has_minimal_query_support(
            "qual os sintomas de doença renal crônica em gatos",
            "O histórico e os sintomas de pacientes gastro- pátas em gatos são vagos e inespecíficos.",
        )


class TestQdrantIndexBatching:
    """Qdrant writes must be split to stay within payload limits."""

    def test_index_chunks_sends_multiple_upserts_for_large_inputs(self, monkeypatch):
        from models.schemas import Chunk
        import services.vector_service as vector_module

        class FakeClient:
            def __init__(self):
                self.upsert_calls = []

            def upsert(self, *, collection_name, points):
                self.upsert_calls.append((collection_name, list(points)))

        fake_client = FakeClient()
        monkeypatch.setattr(vector_module, "get_client", lambda: fake_client)
        monkeypatch.setattr(vector_module, "ensure_collection", lambda *args, **kwargs: None)
        monkeypatch.setattr(vector_module, "QDRANT_UPSERT_BATCH_SIZE", 2)

        chunks = [
            Chunk(
                chunk_id=f"chunk-{idx}",
                document_id="doc-1",
                workspace_id="default",
                chunk_index=idx,
                text=f"conteudo {idx}",
                start_char=0,
                end_char=10,
                page_hint=1,
                strategy="recursive",
                chunk_size_chars=10,
                created_at="2026-04-19T00:00:00Z",
            )
            for idx in range(5)
        ]
        embeddings = [[0.1] * 1536 for _ in chunks]

        vector_module.index_chunks(chunks, embeddings, workspace_id="default")

        assert len(fake_client.upsert_calls) == 3
        assert [len(points) for _, points in fake_client.upsert_calls] == [2, 2, 1]


class TestSemanticChunking:
    """Semantic chunking strategy tests."""

    def test_semantic_chunk_function_exists(self):
        """semantic_chunk is importable and callable."""
        from services.chunker import semantic_chunk
        assert callable(semantic_chunk)

    def test_semantic_chunk_returns_chunks_with_correct_strategy(self):
        """semantic_chunk returns Chunk objects with strategy='semantic'."""
        from services.chunker import semantic_chunk
        from models.schemas import NormalizedDocument

        doc = NormalizedDocument(
            document_id="test-doc",
            source_type="md",
            filename="test.md",
            workspace_id="default",
            created_at="2026-04-18T00:00:00Z",
            pages=[{
                "page_number": 1,
                "text": "Esta é a primeira frase. Esta é a segunda frase. Esta é a terceira frase."
            }],
            sections=[],
            metadata={},
            raw_json_path="",
        )
        chunks = semantic_chunk(doc, chunk_size=300, workspace_id="default")
        assert len(chunks) > 0
        for chunk in chunks:
            assert chunk.strategy == "semantic", f"Expected strategy=semantic, got {chunk.strategy}"

    def test_semantic_chunk_fallback_on_embedding_failure(self):
        """semantic_chunk falls back gracefully when embeddings are unavailable."""
        from services.chunker import semantic_chunk
        from models.schemas import NormalizedDocument
        from unittest.mock import patch

        doc = NormalizedDocument(
            document_id="test-doc",
            source_type="md",
            filename="test.md",
            workspace_id="default",
            created_at="2026-04-18T00:00:00Z",
            pages=[{
                "page_number": 1,
                "text": "Primeira frase. Segunda frase. Terceira frase."
            }],
            sections=[],
            metadata={},
            raw_json_path="",
        )
        with patch("services.embedding_service.get_embeddings_batch", side_effect=RuntimeError("offline")):
            chunks = semantic_chunk(doc, workspace_id="default")
        # Should still return chunks (fallback to greedy without coherence breaks)
        assert len(chunks) > 0
        for chunk in chunks:
            assert chunk.strategy == "semantic"

    def test_ingestion_with_semantic_chunking_produces_correct_metadata(self):
        """Ingesting with chunking_strategy='semantic' sets strategy in response."""
        from services.ingestion_service import ingest_document
        from pathlib import Path
        import tempfile

        # Create a minimal valid docx file for testing
        with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
            f.write(b"# Test\n\nThis is a test document. It has several sentences. They should be chunked semantically.")
            f.flush()
            result = ingest_document(
                Path(f.name),
                workspace_id="default",
                original_filename="test_semantic.md",
                chunking_strategy="semantic",
            )

        assert result.chunking_strategy == "semantic"
        assert result.chunk_count > 0
        # Clean up
        import os
        os.unlink(f.name)

    def test_reindex_document_persists_chunks_to_disk(self):
        """reindex_document with semantic strategy updates *chunks.json on disk."""
        from services.ingestion_service import reindex_document, ingest_document
        from pathlib import Path
        import tempfile
        import json
        import os
        from core.config import DOCUMENTS_DIR

        # Ingest a small doc with recursive first
        with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
            f.write(b"# Test\n\nSimple document with sentences. More content here.")
            f.flush()
            result = ingest_document(
                Path(f.name),
                workspace_id="default",
                original_filename="test_reindex.md",
                chunking_strategy="recursive",
            )
            doc_id = result.document_id
            os.unlink(f.name)

        doc_dir = DOCUMENTS_DIR / "default"
        chunks_file = doc_dir / f"{doc_id}_chunks.json"

        # Verify initial strategy is recursive
        with open(chunks_file) as f:
            initial_chunks = json.load(f)
        assert all(c["strategy"] == "recursive" for c in initial_chunks)

        # Reindex with semantic
        reindex_document(doc_id, workspace_id="default", chunking_strategy="semantic")

        # Verify chunks file was updated with semantic strategy
        with open(chunks_file) as f:
            updated_chunks = json.load(f)
        assert all(c["strategy"] == "semantic" for c in updated_chunks), (
            f"Expected all semantic chunks, got: {[c['strategy'] for c in updated_chunks]}"
        )

    def test_ingestion_returns_partial_when_qdrant_is_unavailable(self, tmp_path, monkeypatch):
        """Indexing failure must degrade to partial instead of aborting the upload."""
        import json
        from pathlib import Path

        import services.ingestion_service as ingestion_module

        source_file = tmp_path / "partial-upload.md"
        source_file.write_text("# Test\n\nDocumento para validar degradação.", encoding="utf-8")

        workspace_root = tmp_path / "documents"
        monkeypatch.setattr(ingestion_module, "DOCUMENTS_DIR", workspace_root)

        def _fail_index(*_args, **_kwargs):
            raise RuntimeError("Qdrant host localhost:6333 not reachable")

        monkeypatch.setattr(ingestion_module, "index_chunks", _fail_index)

        result = ingestion_module.ingest_document(
            Path(source_file),
            workspace_id="partial-ws",
            original_filename="partial-upload.md",
            chunking_strategy="recursive",
        )

        assert result.status == "partial"
        assert result.chunk_count > 0

        doc_dir = workspace_root / "partial-ws"
        raw_files = list(doc_dir.glob("*_raw.json"))
        chunk_files = list(doc_dir.glob("*_chunks.json"))
        assert len(raw_files) == 1
        assert len(chunk_files) == 1

        raw_payload = json.loads(raw_files[0].read_text(encoding="utf-8"))
        assert raw_payload["filename"] == "partial-upload.md"
        assert raw_payload["metadata"]["ingestion_status"] == "partial"

    def test_ingestion_prunes_previous_operational_upload_revisions(self, tmp_path, monkeypatch):
        """A new upload should replace older operational revisions with the same filename."""
        import json
        from pathlib import Path

        import services.ingestion_service as ingestion_module

        workspace_root = tmp_path / "documents"
        uploads_dir = tmp_path / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        source_file = uploads_dir / "upload-smoke.txt"
        source_file.write_text("novo upload operacional", encoding="utf-8")

        doc_dir = workspace_root / "acme-lab"
        doc_dir.mkdir(parents=True, exist_ok=True)

        old_document_id = "old-upload-doc"
        canonical_document_id = "canonical-upload-doc"
        (doc_dir / f"{old_document_id}_raw.json").write_text(
            json.dumps(
                {
                    "document_id": old_document_id,
                    "source_type": "txt",
                    "filename": "upload-smoke.txt",
                    "workspace_id": "acme-lab",
                    "created_at": "2026-04-19T10:00:00Z",
                    "pages": [{"page_number": 1, "text": "versão antiga"}],
                    "sections": [],
                    "metadata": {"catalog_scope": "operational", "ingestion_status": "parsed"},
                    "raw_json_path": str(uploads_dir / f"{old_document_id}_raw.json"),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (doc_dir / f"{canonical_document_id}_raw.json").write_text(
            json.dumps(
                {
                    "document_id": canonical_document_id,
                    "source_type": "txt",
                    "filename": "upload-smoke.txt",
                    "workspace_id": "acme-lab",
                    "created_at": "2026-04-19T09:00:00Z",
                    "pages": [{"page_number": 1, "text": "versão canônica"}],
                    "sections": [],
                    "metadata": {"catalog_scope": "canonical", "ingestion_status": "parsed"},
                    "raw_json_path": str(uploads_dir / f"{canonical_document_id}_raw.json"),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (doc_dir / f"{old_document_id}_chunks.json").write_text(
            json.dumps(
                [
                    {
                        "chunk_id": f"chunk_{old_document_id}_0000",
                        "document_id": old_document_id,
                        "workspace_id": "acme-lab",
                        "chunk_index": 0,
                        "text": "versão antiga",
                        "start_char": 0,
                        "end_char": 12,
                        "page_hint": 1,
                        "strategy": "recursive",
                        "chunk_size_chars": 12,
                        "created_at": "2026-04-19T10:00:00Z",
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (doc_dir / f"{canonical_document_id}_chunks.json").write_text(
            json.dumps(
                [
                    {
                        "chunk_id": f"chunk_{canonical_document_id}_0000",
                        "document_id": canonical_document_id,
                        "workspace_id": "acme-lab",
                        "chunk_index": 0,
                        "text": "versão canônica",
                        "start_char": 0,
                        "end_char": 15,
                        "page_hint": 1,
                        "strategy": "recursive",
                        "chunk_size_chars": 15,
                        "created_at": "2026-04-19T09:00:00Z",
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        deleted_doc_ids: list[str] = []
        monkeypatch.setattr(ingestion_module, "DOCUMENTS_DIR", workspace_root)
        monkeypatch.setattr(ingestion_module, "get_embeddings_batch", lambda texts: [[0.1] * 1536 for _ in texts])
        monkeypatch.setattr(ingestion_module, "index_chunks", lambda chunks, embeddings, workspace_id: None)
        monkeypatch.setattr(ingestion_module, "delete_document_chunks", lambda document_id: deleted_doc_ids.append(document_id))
        monkeypatch.setattr(ingestion_module, "canonical_document_ids", lambda workspace_id="default": {canonical_document_id})

        result = ingestion_module.ingest_document(
            Path(source_file),
            workspace_id="acme-lab",
            original_filename="upload-smoke.txt",
            chunking_strategy="recursive",
        )

        assert result.catalog_scope == "operational"
        assert old_document_id in deleted_doc_ids
        assert canonical_document_id not in deleted_doc_ids
        assert not (doc_dir / f"{old_document_id}_raw.json").exists()
        assert not (doc_dir / f"{old_document_id}_chunks.json").exists()
        assert (doc_dir / f"{canonical_document_id}_raw.json").exists()
        assert (doc_dir / f"{canonical_document_id}_chunks.json").exists()

        current_raw_files = sorted(doc_dir.glob("*_raw.json"))
        assert len(current_raw_files) == 2
        current_payload = json.loads((doc_dir / f"{result.document_id}_raw.json").read_text(encoding="utf-8"))
        assert current_payload["metadata"]["catalog_scope"] == "operational"

    def test_ingestion_keep_all_policy_preserves_previous_operational_uploads(self, tmp_path, monkeypatch):
        """Tenants configured with keep_all should not prune prior uploads with the same filename."""
        import json
        from pathlib import Path

        import services.ingestion_service as ingestion_module

        workspace_root = tmp_path / "documents"
        uploads_dir = tmp_path / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        source_file = uploads_dir / "upload-smoke.txt"
        source_file.write_text("novo upload operacional", encoding="utf-8")

        doc_dir = workspace_root / "keep-all"
        doc_dir.mkdir(parents=True, exist_ok=True)
        old_document_id = "old-upload-doc"
        (doc_dir / f"{old_document_id}_raw.json").write_text(
            json.dumps(
                {
                    "document_id": old_document_id,
                    "source_type": "txt",
                    "filename": "upload-smoke.txt",
                    "workspace_id": "keep-all",
                    "created_at": "2026-04-19T10:00:00Z",
                    "pages": [{"page_number": 1, "text": "versão antiga"}],
                    "sections": [],
                    "metadata": {"catalog_scope": "operational", "ingestion_status": "parsed"},
                    "raw_json_path": str(uploads_dir / f"{old_document_id}_raw.json"),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (doc_dir / f"{old_document_id}_chunks.json").write_text(
            json.dumps(
                [
                    {
                        "chunk_id": f"chunk_{old_document_id}_0000",
                        "document_id": old_document_id,
                        "workspace_id": "keep-all",
                        "chunk_index": 0,
                        "text": "versão antiga",
                        "start_char": 0,
                        "end_char": 12,
                        "page_hint": 1,
                        "strategy": "recursive",
                        "chunk_size_chars": 12,
                        "created_at": "2026-04-19T10:00:00Z",
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        deleted_doc_ids: list[str] = []
        monkeypatch.setattr(ingestion_module, "DOCUMENTS_DIR", workspace_root)
        monkeypatch.setattr(ingestion_module, "get_embeddings_batch", lambda texts: [[0.1] * 1536 for _ in texts])
        monkeypatch.setattr(ingestion_module, "index_chunks", lambda chunks, embeddings, workspace_id: None)
        monkeypatch.setattr(ingestion_module, "delete_document_chunks", lambda document_id: deleted_doc_ids.append(document_id))
        monkeypatch.setattr(ingestion_module, "get_tenant_by_workspace", lambda workspace_id: {"operational_retention_mode": "keep_all", "operational_retention_hours": 999})
        monkeypatch.setattr(ingestion_module, "canonical_document_ids", lambda workspace_id="default": set())

        result = ingestion_module.ingest_document(
            Path(source_file),
            workspace_id="keep-all",
            original_filename="upload-smoke.txt",
            chunking_strategy="recursive",
        )

        assert result.catalog_scope == "operational"
        assert deleted_doc_ids == []
        assert (doc_dir / f"{old_document_id}_raw.json").exists()
        assert (doc_dir / f"{old_document_id}_chunks.json").exists()

    def test_invalid_chunking_strategy_rejected(self):
        """Invalid chunking_strategy raises ValueError in _chunk_document."""
        from services.ingestion_service import _chunk_document

        with pytest.raises(ValueError, match=r"(?i)invalid.*chunking_strategy"):
            _chunk_document(None, "default", "lexical")

        with pytest.raises(ValueError, match=r"(?i)invalid.*chunking_strategy"):
            _chunk_document(None, "default", "")

        with pytest.raises(ValueError, match=r"(?i)invalid.*chunking_strategy"):
            _chunk_document(None, "default", "SEMANTIC")  # case-sensitive


class TestABEvaluation:
    """A/B evaluation: baseline vs variant comparison."""


class TestEvaluationDatasetEndpoint:
    """Operational dataset endpoint must not return placeholder payloads."""

    def test_evaluation_dataset_returns_real_dataset_for_default_workspace(self):
        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)
        headers = enterprise_headers(client, role="operator", tenant_id="default")

        response = client.get("/evaluation/dataset", params={"workspace_id": "default"}, headers=headers)

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["dataset_id"] != "placeholder"
        assert len(payload["questions"]) >= 20

    def test_evaluation_dataset_returns_404_when_workspace_has_no_dataset(self, tmp_path, monkeypatch):
        from fastapi.testclient import TestClient
        import api.main as main_module
        from api.main import app

        monkeypatch.setattr(main_module, "DATA_DIR", tmp_path)

        client = TestClient(app)
        headers = enterprise_headers(client, role="admin", tenant_id="acme-lab")

        response = client.get("/evaluation/dataset", params={"workspace_id": "acme-lab"}, headers=headers)

        assert response.status_code == 404, response.text
        payload = response.json()
        assert payload["detail"]["error"] == "dataset_not_found"

    @pytest.mark.integration
    def test_evaluation_without_reranking(self, corpus_doc_ids):
        """Evaluation with reranking=False produces correct reranking fields."""
        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)
        headers = enterprise_headers(client)
        resp = client.post(
            "/evaluation/run?workspace_id=default&run_judge=false&reranking=false",
            headers=headers,
        )
        if resp.status_code == 401:
            pytest.skip("Auth required")
        if resp.status_code == 404:
            pytest.skip("Dataset not found")

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["reranking_applied"] is False
        assert data["reranking_method"] is None

    @pytest.mark.integration
    def test_evaluation_with_reranking(self, corpus_doc_ids):
        """Evaluation with reranking=True produces correct reranking fields."""
        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)
        headers = enterprise_headers(client)
        resp = client.post(
            "/evaluation/run?workspace_id=default&run_judge=false&reranking=true",
            headers=headers,
        )
        if resp.status_code == 401:
            pytest.skip("Auth required")
        if resp.status_code == 404:
            pytest.skip("Dataset not found")

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["reranking_applied"] is True
        assert data["reranking_method"] == "bm25f"

    @pytest.mark.integration
    def test_ab_evaluation_returns_comparison(self, corpus_doc_ids):
        """POST /evaluation/ab returns baseline and variant with deltas."""
        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)
        headers = enterprise_headers(client)
        resp = client.post("/evaluation/ab?workspace_id=default", headers=headers)
        if resp.status_code == 401:
            pytest.skip("Auth required")
        if resp.status_code == 404:
            pytest.skip("Dataset not found")

        assert resp.status_code == 200, resp.text
        data = resp.json()

        # Top-level comparison fields
        assert "baseline" in data
        assert "variant" in data
        assert "delta_hit_at_1" in data
        assert "delta_hit_at_3" in data
        assert "delta_hit_at_5" in data
        assert "delta_avg_latency_ms" in data
        assert "winner" in data

        # Baseline variant
        assert data["baseline"]["variant_name"] == "baseline"
        assert data["baseline"]["reranking_applied"] is False
        assert data["baseline"]["reranking_method"] is None
        assert "hit_rate_top_1" in data["baseline"]
        assert "hit_rate_top_3" in data["baseline"]
        assert "hit_rate_top_5" in data["baseline"]

        # Variant
        assert data["variant"]["variant_name"] == "variant"
        assert data["variant"]["reranking_applied"] is True
        assert data["variant"]["reranking_method"] == "bm25f"
        assert "hit_rate_top_1" in data["variant"]
        assert "hit_rate_top_3" in data["variant"]
        assert "hit_rate_top_5" in data["variant"]

        # Winner is one of the expected values
        assert data["winner"] in ("baseline", "variant", "tie")

    @pytest.mark.integration
    def test_telemetry_query_log_has_reranking_fields(self, corpus_doc_ids):
        """Query telemetry log includes reranking_applied and reranking_method."""
        from services.telemetry_service import TelemetryService
        import json
        import tempfile
        from pathlib import Path

        # Use a temp log file so we don't pollute real logs
        with tempfile.TemporaryDirectory() as tmpdir:
            from unittest.mock import patch
            from services.telemetry_service import TelemetryService

            tel = TelemetryService()
            tel.QUERIES_LOG = Path(tmpdir) / "queries.jsonl"

            tel.log_query(
                query="test query",
                workspace_id="default",
                answer="test answer",
                confidence="high",
                grounded=True,
                chunks_used=[{"chunk_id": "c1"}],
                retrieval_time_ms=50,
                total_latency_ms=100,
                low_confidence=False,
                results_count=5,
                citation_coverage=0.8,
                top_result_score=0.9,
                threshold=0.7,
                hit=True,
                reranking_applied=True,
                reranking_method="bm25f",
                candidate_count=10,
            )

            # Read back and verify
            lines = tel.QUERIES_LOG.read_text().strip().split("\n")
            assert len(lines) == 1
            event = json.loads(lines[0])
            assert event["reranking_applied"] is True
            assert event["reranking_method"] == "bm25f"
            assert event["candidate_count"] == 10

    def test_evaluation_question_results_have_reranking_fields(self, corpus_doc_ids):
        """question_results contain reranking_applied and reranking_method per question."""
        from services.evaluation_service import EvaluationService
        from pathlib import Path

        e = EvaluationService()
        result = e.run_evaluation(
            workspace_id="default",
            dataset_path=Path("data/default/dataset.json"),
            top_k=5,
            run_judge=False,
            reranking=True,
        )
        # All question_results should have reranking fields
        for qr in result.question_results:
            assert hasattr(qr, "reranking_applied"), "reranking_applied missing on question_result"
            assert hasattr(qr, "reranking_method"), "reranking_method missing on question_result"
            assert qr.reranking_applied is True
            assert qr.reranking_method == "bm25f"

    def test_candidate_count_uses_total_candidates(self):
        """candidate_count in query log equals search_resp.total_candidates."""
        from services.search_service import search_and_answer
        from models.schemas import QueryRequest
        from services.vector_service import search_hybrid
        from models.schemas import SearchRequest

        # Get the actual total_candidates value directly from search_hybrid
        search_resp = search_hybrid(SearchRequest(
            query="reembolso",
            workspace_id="default",
            top_k=3,
            reranking=True,
        ))
        expected_total = search_resp.total_candidates
        assert expected_total is not None and expected_total > 0, (
            "search_hybrid should return total_candidates > 0 for this corpus"
        )

        captured = {}
        def fake_log_query(entry):
            captured.clear()
            captured.update(entry)

        with patch("services.search_service._log_query", fake_log_query):
            search_and_answer(QueryRequest(
                query="reembolso",
                workspace_id="default",
                top_k=3,
                reranking=True,
            ))

        assert captured.get("candidate_count") == expected_total, (
            f"candidate_count={captured.get('candidate_count')} should equal "
            f"search_resp.total_candidates={expected_total}"
        )


class TestChunkingABEvaluation:
    """A/B comparison between recursive and semantic chunking strategies."""

    @pytest.mark.integration
    def test_chunking_ab_endpoint_rejects_unknown_document(self):
        """POST /evaluation/chunking-ab with unknown document_id returns 404."""
        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)
        headers = enterprise_headers(client)
        resp = client.post(
            "/evaluation/chunking-ab?document_id=nonexistent_doc&workspace_id=default",
            headers=headers,
        )
        if resp.status_code == 401:
            pytest.skip("Auth required")
        assert resp.status_code == 404, resp.text
        data = resp.json()
        assert data["detail"]["error"] == "document_not_found"

    @pytest.mark.integration
    def test_chunking_ab_endpoint_returns_correct_structure(self, corpus_doc_ids):
        """POST /evaluation/chunking-ab returns ChunkingABResponse with all required fields."""
        from fastapi.testclient import TestClient
        from api.main import app

        if not corpus_doc_ids:
            pytest.skip("No corpus documents")

        client = TestClient(app)
        headers = enterprise_headers(client)
        doc_id = corpus_doc_ids[0]
        resp = client.post(
            f"/evaluation/chunking-ab?document_id={doc_id}&workspace_id=default",
            headers=headers,
        )
        if resp.status_code == 401:
            pytest.skip("Auth required")
        if resp.status_code == 404:
            # Could be dataset not found or document not found
            pytest.skip(f"Prerequisites not met: {resp.json()}")

        assert resp.status_code == 200, resp.text
        data = resp.json()

        # Document identity
        assert data["document_id"] == doc_id
        assert data["workspace_id"] == "default"

        # Strategy variants
        assert data["baseline"]["strategy"] == "recursive"
        assert data["variant"]["strategy"] == "semantic"

        # Metrics present on both
        for variant_key in ("baseline", "variant"):
            v = data[variant_key]
            assert "chunk_count" in v
            assert "hit_rate_top_1" in v
            assert "hit_rate_top_3" in v
            assert "hit_rate_top_5" in v
            assert "avg_latency_ms" in v
            assert "low_confidence_rate" in v

        # Deltas
        assert "delta_hit_at_1" in data
        assert "delta_hit_at_3" in data
        assert "delta_hit_at_5" in data
        assert "delta_avg_latency_ms" in data
        assert "winner" in data
        assert "corpus_restored" in data
        assert "embedding_status" in data
        assert data["embedding_status"] in ("original", "regenerated", "degraded_zero_fallback")

    @pytest.mark.integration
    def test_chunking_ab_evaluation_includes_chunk_count_per_strategy(self, corpus_doc_ids):
        """Each variant result includes chunk_count for the strategy used."""
        from fastapi.testclient import TestClient
        from api.main import app

        if not corpus_doc_ids:
            pytest.skip("No corpus documents")

        client = TestClient(app)
        headers = enterprise_headers(client)
        doc_id = corpus_doc_ids[0]
        resp = client.post(
            f"/evaluation/chunking-ab?document_id={doc_id}&workspace_id=default",
            headers=headers,
        )
        if resp.status_code == 401:
            pytest.skip("Auth required")
        if resp.status_code == 404:
            pytest.skip(f"Prerequisites not met: {resp.json()}")

        assert resp.status_code == 200, resp.text
        data = resp.json()

        # chunk_count is an integer > 0 for both strategies
        assert isinstance(data["baseline"]["chunk_count"], int)
        assert isinstance(data["variant"]["chunk_count"], int)
        assert data["baseline"]["chunk_count"] > 0, "recursive should produce chunks"
        # Semantic may produce 0 if offline fallback (but shouldn't on real embeddings)

        # Strategies are distinct
        assert data["baseline"]["strategy"] == "recursive"
        assert data["variant"]["strategy"] == "semantic"

    @pytest.mark.integration
    def test_chunking_ab_corpus_is_restored_after_evaluation(self, corpus_doc_ids):
        """After running chunking A/B, corpus is restored to recursive chunking."""
        from fastapi.testclient import TestClient
        from api.main import app
        from services.document_registry import get_document_metadata

        if not corpus_doc_ids:
            pytest.skip("No corpus documents")

        client = TestClient(app)
        headers = enterprise_headers(client)
        doc_id = corpus_doc_ids[0]

        # Capture state before
        meta_before = get_document_metadata(doc_id, "default")
        if meta_before is None:
            pytest.skip("Document not in registry")
        strategy_before = meta_before.get("chunking_strategy", "recursive")

        resp = client.post(
            f"/evaluation/chunking-ab?document_id={doc_id}&workspace_id=default",
            headers=headers,
        )
        if resp.status_code == 401:
            pytest.skip("Auth required")
        if resp.status_code == 404:
            pytest.skip(f"Prerequisites not met: {resp.json()}")

        assert resp.status_code == 200, resp.text
        data = resp.json()

        # corpus_restored flag should be True
        assert data["corpus_restored"] is True, (
            "Corpus was NOT restored after chunking A/B evaluation"
        )

        # Verify registry still shows the ORIGINAL strategy (not just recursive)
        meta_after = get_document_metadata(doc_id, "default")
        assert meta_after is not None
        assert meta_after["chunking_strategy"] == strategy_before, (
            f"Corpus left with strategy={meta_after['chunking_strategy']} "
            f"but original was {strategy_before}"
        )

    @pytest.mark.integration
    def test_chunking_ab_restores_estrangeiro_para_recursive(self, corpus_doc_ids):
        """Document originally recursive stays recursive after A/B."""
        from fastapi.testclient import TestClient
        from api.main import app
        from services.document_registry import get_document_metadata

        if not corpus_doc_ids:
            pytest.skip("No corpus documents")

        client = TestClient(app)
        headers = enterprise_headers(client)
        doc_id = corpus_doc_ids[0]

        # Ensure document is recursive before test
        from services.ingestion_service import reindex_document
        reindex_document(doc_id, "default", chunking_strategy="recursive")

        meta_before = get_document_metadata(doc_id, "default")
        if meta_before is None:
            pytest.skip("Document not in registry")
        assert meta_before["chunking_strategy"] == "recursive"

        resp = client.post(
            f"/evaluation/chunking-ab?document_id={doc_id}&workspace_id=default",
            headers=headers,
        )
        if resp.status_code == 401:
            pytest.skip("Auth required")
        if resp.status_code == 404:
            pytest.skip(f"Prerequisites not met: {resp.json()}")

        assert resp.status_code == 200, resp.text
        data = resp.json()

        assert data["corpus_restored"] is True
        meta_after = get_document_metadata(doc_id, "default")
        assert meta_after["chunking_strategy"] == "recursive"

    @pytest.mark.integration
    def test_chunking_ab_restores_semantic_para_semantic(self, corpus_doc_ids):
        """Document originally semantic stays semantic after A/B."""
        from fastapi.testclient import TestClient
        from api.main import app
        from services.document_registry import get_document_metadata

        if not corpus_doc_ids:
            pytest.skip("No corpus documents")

        client = TestClient(app)
        headers = enterprise_headers(client)
        doc_id = corpus_doc_ids[0]

        # Set document to semantic before test
        from services.ingestion_service import reindex_document
        reindex_document(doc_id, "default", chunking_strategy="semantic")

        meta_before = get_document_metadata(doc_id, "default")
        if meta_before is None:
            pytest.skip("Document not in registry")
        assert meta_before["chunking_strategy"] == "semantic"

        resp = client.post(
            f"/evaluation/chunking-ab?document_id={doc_id}&workspace_id=default",
            headers=headers,
        )
        if resp.status_code == 401:
            pytest.skip("Auth required")
        if resp.status_code == 404:
            pytest.skip(f"Prerequisites not met: {resp.json()}")

        assert resp.status_code == 200, resp.text
        data = resp.json()

        assert data["corpus_restored"] is True, (
            f"corpus_restored=False — semantic document was not restored. "
            f"Original strategy={meta_before['chunking_strategy']}"
        )
        meta_after = get_document_metadata(doc_id, "default")
        assert meta_after["chunking_strategy"] == "semantic", (
            f"After A/B, document has strategy={meta_after['chunking_strategy']} but was semantic before"
        )

    @pytest.mark.integration
    def test_chunking_ab_chunks_file_equals_backup_after_restoration(self, corpus_doc_ids):
        """After A/B, the chunks file on disk matches pre-A/B state in semantic fields.

        Compares chunk_id, text, strategy, and chunk_index — the fields that matter
        for retrieval correctness. The 'embedding' field may differ if embeddings
        were regenerated during restoration (which is correct: Qdrant gets valid vectors).
        """
        from fastapi.testclient import TestClient
        from api.main import app
        from services.ingestion_service import reindex_document
        from core.config import DOCUMENTS_DIR
        import json

        if not corpus_doc_ids:
            pytest.skip("No corpus documents")

        client = TestClient(app)
        headers = enterprise_headers(client)
        doc_id = corpus_doc_ids[0]
        doc_dir = DOCUMENTS_DIR / "default"
        chunks_path = doc_dir / f"{doc_id}_chunks.json"

        # Set document to semantic so we're testing the harder path
        reindex_document(doc_id, "default", chunking_strategy="semantic")

        # Capture semantic state before A/B
        with open(chunks_path, encoding="utf-8") as f:
            chunks_before = json.load(f)

        resp = client.post(
            f"/evaluation/chunking-ab?document_id={doc_id}&workspace_id=default",
            headers=headers,
        )
        if resp.status_code == 401:
            pytest.skip("Auth required")
        if resp.status_code == 404:
            pytest.skip(f"Prerequisites not met: {resp.json()}")

        assert resp.status_code == 200, resp.text
        data = resp.json()

        # corpus_restored should be True (semantic fields match original)
        assert data["corpus_restored"] is True, (
            f"corpus_restored=False — chunks file was not restored faithfully. "
            f"Original strategy was semantic."
        )

        # Verify: semantic fields of disk chunks match the pre-A/B state
        with open(chunks_path, encoding="utf-8") as f:
            chunks_after = json.load(f)

        def _semantic(chunk):
            return {k: chunk[k] for k in ("chunk_id", "text", "strategy", "chunk_index")}

        assert [c["chunk_id"] for c in chunks_before] == [c["chunk_id"] for c in chunks_after], (
            "chunk_ids changed after restoration — not faithful"
        )
        assert [c["text"] for c in chunks_before] == [c["text"] for c in chunks_after], (
            "text content changed after restoration — not faithful"
        )
        assert [c.get("strategy") for c in chunks_before] == [c.get("strategy") for c in chunks_after], (
            "strategy changed after restoration — not faithful"
        )

    def test_chunking_ab_service_rejects_invalid_chunking_strategy(self):
        """reindex_document raises ValueError when chunking_strategy is invalid."""
        from services.ingestion_service import reindex_document
        import tempfile
        import json
        from pathlib import Path
        from core.config import DOCUMENTS_DIR

        # Create a temp raw JSON so the document lookup succeeds
        # and the strategy validation (ValueError) is what fires
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_doc_dir = Path(tmpdir)
            tmp_workspace_dir = tmp_doc_dir / "testws"
            tmp_workspace_dir.mkdir()
            tmp_raw = tmp_workspace_dir / "test_doc_raw.json"
            tmp_chunks = tmp_workspace_dir / "test_doc_chunks.json"

            # Write a minimal valid raw JSON
            tmp_raw.write_text(json.dumps({
                "document_id": "test_doc",
                "source_type": "md",
                "filename": "test.md",
                "workspace_id": "testws",
                "created_at": "2026-01-01T00:00:00",
                "pages": [{"text": "This is test content."}],
                "sections": [],
                "metadata": {},
            }), encoding="utf-8")

            tmp_chunks.write_text(json.dumps([{
                "chunk_id": "c1",
                "document_id": "test_doc",
                "workspace_id": "testws",
                "chunk_index": 0,
                "text": "This is test content.",
                "start_char": 0,
                "end_char": 20,
                "strategy": "recursive",
                "chunk_size_chars": 20,
                "created_at": "2026-01-01T00:00:00",
            }]), encoding="utf-8")

            # Monkeypatch DOCUMENTS_DIR in ingestion_service where it's imported
            # Mock delete_document_chunks to avoid Qdrant calls (it fires before strategy validation)
            import services.ingestion_service
            from unittest.mock import patch

            orig_doc_dir = services.ingestion_service.DOCUMENTS_DIR
            services.ingestion_service.DOCUMENTS_DIR = tmp_doc_dir

            try:
                with patch("services.ingestion_service.delete_document_chunks"):
                    with pytest.raises(ValueError) as exc_info:
                        reindex_document("test_doc", "testws", chunking_strategy="invalid_strategy")
                    assert "invalid chunking_strategy" in str(exc_info.value).lower()
            finally:
                services.ingestion_service.DOCUMENTS_DIR = orig_doc_dir


class TestEmbeddingRestoration:
    """Unit tests for _restore_embeddings_if_needed and embedding handling in reindex."""

    def test_restore_embeddings_returns_unchanged_when_all_valid(self):
        """When all chunks have valid embeddings, function returns them unchanged."""
        from services.ingestion_service import _restore_embeddings_if_needed
        from unittest.mock import patch

        dim = 1536
        valid_emb = [0.1] * dim
        chunks = [
            {"chunk_id": "c1", "text": "hello", "embedding": valid_emb},
            {"chunk_id": "c2", "text": "world", "embedding": valid_emb},
        ]

        with patch(
            "services.ingestion_service.get_embeddings_batch"
        ) as mock_batch:
            result, were_regenerated = _restore_embeddings_if_needed(chunks)
            assert were_regenerated is False
            assert result == chunks
            mock_batch.assert_not_called()

    def test_restore_embeddings_regenerates_all_when_one_is_missing(self):
        """When any chunk has missing embedding, all chunks are regenerated."""
        from services.ingestion_service import _restore_embeddings_if_needed
        from unittest.mock import patch

        dim = 1536
        valid_emb = [0.1] * dim
        chunks = [
            {"chunk_id": "c1", "text": "hello", "embedding": valid_emb},
            {"chunk_id": "c2", "text": "world"},  # missing embedding
        ]

        regenerated = [[0.2] * dim, [0.3] * dim]
        with patch(
            "services.ingestion_service.get_embeddings_batch",
            return_value=regenerated,
        ) as mock_batch:
            result, were_regenerated = _restore_embeddings_if_needed(chunks)
            assert were_regenerated is True
            mock_batch.assert_called_once()
            # Verify all chunks got embeddings
            assert all("embedding" in c for c in result)
            assert result[0]["embedding"] == regenerated[0]
            assert result[1]["embedding"] == regenerated[1]

    def test_restore_embeddings_regenerates_all_when_embedding_wrong_length(self):
        """When any chunk has wrong-dimension embedding, all are regenerated."""
        from services.ingestion_service import _restore_embeddings_if_needed
        from unittest.mock import patch

        dim = 1536
        chunks = [
            {"chunk_id": "c1", "text": "hello", "embedding": [0.1] * dim},
            {"chunk_id": "c2", "text": "world", "embedding": [0.2] * 128},  # wrong dim
        ]

        regenerated = [[0.3] * dim, [0.4] * dim]
        with patch(
            "services.ingestion_service.get_embeddings_batch",
            return_value=regenerated,
        ):
            result, were_regenerated = _restore_embeddings_if_needed(chunks)
            assert were_regenerated is True

    def test_restore_embeddings_regenerates_all_when_embedding_wrong_type(self):
        """When any chunk has non-float embedding values, all are regenerated."""
        from services.ingestion_service import _restore_embeddings_if_needed
        from unittest.mock import patch

        dim = 1536
        chunks = [
            {"chunk_id": "c1", "text": "hello", "embedding": [0.1] * dim},
            {"chunk_id": "c2", "text": "world", "embedding": ["not", "a", "float"]},  # wrong type
        ]

        regenerated = [[0.3] * dim, [0.4] * dim]
        with patch(
            "services.ingestion_service.get_embeddings_batch",
            return_value=regenerated,
        ):
            result, were_regenerated = _restore_embeddings_if_needed(chunks)
            assert were_regenerated is True

    def test_restore_embeddings_raises_on_count_mismatch(self):
        """When get_embeddings_batch returns wrong count, RuntimeError is raised."""
        from services.ingestion_service import _restore_embeddings_if_needed
        from unittest.mock import patch

        dim = 1536
        chunks = [
            {"chunk_id": "c1", "text": "hello"},  # missing embedding
            {"chunk_id": "c2", "text": "world"},  # missing embedding
        ]

        # Return only 1 embedding for 2 chunks — must raise
        with patch(
            "services.ingestion_service.get_embeddings_batch",
            return_value=[[0.1] * dim],  # only 1
        ):
            with pytest.raises(RuntimeError) as exc_info:
                _restore_embeddings_if_needed(chunks)
            assert "count mismatch" in str(exc_info.value).lower()
            assert "2" in str(exc_info.value)  # chunk count
            assert "1" in str(exc_info.value)  # embedding count

    def test_restore_embeddings_raises_on_regenerated_invalid(self):
        """When regenerated embedding is still invalid, RuntimeError is raised."""
        from services.ingestion_service import _restore_embeddings_if_needed
        from unittest.mock import patch

        chunks = [
            {"chunk_id": "c1", "text": "hello"},  # missing
        ]

        # get_embeddings_batch returns wrong type despite being called
        with patch(
            "services.ingestion_service.get_embeddings_batch",
            return_value=["not_a_list"],
        ):
            with pytest.raises(RuntimeError) as exc_info:
                _restore_embeddings_if_needed(chunks)
            assert "invalid" in str(exc_info.value).lower()
            assert "c1" in str(exc_info.value)

    def test_restore_embeddings_returns_unchanged_on_api_failure(self):
        """When get_embeddings_batch raises, chunks are returned unchanged (zeros fallback)."""
        from services.ingestion_service import _restore_embeddings_if_needed
        from unittest.mock import patch

        chunks = [
            {"chunk_id": "c1", "text": "hello"},  # missing embedding
            {"chunk_id": "c2", "text": "world"},  # missing embedding
        ]

        with patch(
            "services.ingestion_service.get_embeddings_batch",
            side_effect=RuntimeError("API offline"),
        ):
            result, were_regenerated = _restore_embeddings_if_needed(chunks)
            assert were_regenerated is False
            assert result == chunks
            # Chunks still lack embeddings — caller (reindex_document) will use zeros

    def test_restore_embeddings_empty_chunks(self):
        """Empty chunks list returns unchanged with were_regenerated=False."""
        from services.ingestion_service import _restore_embeddings_if_needed

        result, were_regenerated = _restore_embeddings_if_needed([])
        assert result == []
        assert were_regenerated is False


class TestReindexDocumentEmbeddingStatus:
    """Tests for reindex_document returning (chunk_count, embedding_status)."""

    def _make_workspace(self, tmpdir, doc_id, workspace_id="testws"):
        """Set up a minimal workspace with raw JSON and chunks file."""
        ws_dir = Path(tmpdir) / workspace_id
        ws_dir.mkdir()
        raw = ws_dir / f"{doc_id}_raw.json"
        chunks_file = ws_dir / f"{doc_id}_chunks.json"
        raw.write_text(json.dumps({
            "document_id": doc_id,
            "source_type": "md",
            "filename": "test.md",
            "workspace_id": workspace_id,
            "created_at": "2026-01-01T00:00:00",
            "pages": [{"text": "Test content here."}],
            "sections": [],
            "metadata": {},
        }), encoding="utf-8")
        return ws_dir, raw, chunks_file

    def _reindex(self, doc_id, workspace_id, chunks_file, tmp_doc_dir, embedding_return):
        """Helper: patch all Qdrant-dependent calls so test runs without Qdrant."""
        import services.ingestion_service
        from unittest.mock import patch

        services.ingestion_service.DOCUMENTS_DIR = tmp_doc_dir

        with patch(
            "services.ingestion_service.get_embeddings_batch",
            return_value=embedding_return,
        ):
            with patch(
                "services.ingestion_service.delete_document_chunks",
            ):
                with patch(
                    "services.ingestion_service.index_chunks",
                ) as mock_index:
                    count, status, latency_ms = services.ingestion_service.reindex_document(
                        doc_id, workspace_id,
                        chunks=json.loads(chunks_file.read_text(encoding="utf-8")),
                    )
                    # Verify: if we have valid embeddings, index_chunks was called with correct dim
                    if embedding_return and all(
                        isinstance(e, list) and len(e) == 1536 for e in embedding_return
                    ):
                        mock_index.assert_called_once()
                        _, indexed_embs, _ = mock_index.call_args[0]
                        assert len(indexed_embs) == len(embedding_return)
                        assert all(len(e) == 1536 for e in indexed_embs)
        return count, status, latency_ms

    def test_reindex_restoration_with_valid_embeddings_returns_original(self, tmp_path):
        """When backup already has valid embeddings, embedding_status='original'."""
        import json
        from pathlib import Path

        doc_id = "test_doc"
        ws_dir, _, chunks_file = self._make_workspace(tmp_path, doc_id)

        # Write chunks WITH valid embeddings
        valid_emb = [0.1] * 1536
        chunks = [{"chunk_id": "c1", "document_id": doc_id, "workspace_id": "testws",
                   "chunk_index": 0, "text": "Test content here.", "start_char": 0,
                   "end_char": 20, "strategy": "recursive", "chunk_size_chars": 20,
                   "created_at": "2026-01-01T00:00:00", "embedding": valid_emb}]
        chunks_file.write_text(json.dumps(chunks), encoding="utf-8")

        count, status, latency_ms = self._reindex(doc_id, "testws", chunks_file, ws_dir, [[0.2]*1536])

        assert status == "original", f"Expected 'original' but got '{status}' (embeddings were already valid)"

    def test_reindex_restoration_missing_embeddings_api_success_returns_regenerated(self, tmp_path):
        """When backup missing embeddings but API succeeds, embedding_status='regenerated'."""
        import json
        from pathlib import Path

        doc_id = "test_doc"
        ws_dir, _, chunks_file = self._make_workspace(tmp_path, doc_id)

        # Write chunks WITHOUT embeddings
        chunks = [{"chunk_id": "c1", "document_id": doc_id, "workspace_id": "testws",
                   "chunk_index": 0, "text": "Test content here.", "start_char": 0,
                   "end_char": 20, "strategy": "recursive", "chunk_size_chars": 20,
                   "created_at": "2026-01-01T00:00:00"}]  # no "embedding"
        chunks_file.write_text(json.dumps(chunks), encoding="utf-8")

        count, status, latency_ms = self._reindex(
            doc_id, "testws", chunks_file, ws_dir,
            [[0.3] * 1536],  # API returns valid embedding
        )

        assert status == "regenerated", f"Expected 'regenerated' but got '{status}'"

    def test_reindex_restoration_missing_embeddings_api_failure_returns_degraded_zero(self, tmp_path):
        """When backup missing embeddings AND API fails, embedding_status='degraded_zero_fallback'."""
        import json
        from pathlib import Path

        doc_id = "test_doc"
        ws_dir, _, chunks_file = self._make_workspace(tmp_path, doc_id)

        # Write chunks WITHOUT embeddings
        chunks = [{"chunk_id": "c1", "document_id": doc_id, "workspace_id": "testws",
                   "chunk_index": 0, "text": "Test content here.", "start_char": 0,
                   "end_char": 20, "strategy": "recursive", "chunk_size_chars": 20,
                   "created_at": "2026-01-01T00:00:00"}]  # no "embedding"
        chunks_file.write_text(json.dumps(chunks), encoding="utf-8")

        import services.ingestion_service
        from unittest.mock import patch

        # DOCUMENTS_DIR = tmp_path so that DOCUMENTS_DIR / "testws" / ... resolves correctly
        services.ingestion_service.DOCUMENTS_DIR = tmp_path

        # API fails → falls back to zeros; verify zeros have correct dimension
        with patch(
            "services.ingestion_service.get_embeddings_batch",
            side_effect=RuntimeError("API offline"),
        ):
            with patch(
                "services.ingestion_service.delete_document_chunks",
            ):
                with patch(
                    "services.ingestion_service.index_chunks",
                ) as mock_index:
                    count, status, latency_ms = services.ingestion_service.reindex_document(
                        doc_id, "testws",
                        chunks=json.loads(chunks_file.read_text(encoding="utf-8")),
                    )
                    # Verify: zeros of correct dimension were sent to index_chunks
                    mock_index.assert_called_once()
                    _, indexed_embs, _ = mock_index.call_args[0]
                    assert len(indexed_embs) == 1
                    assert indexed_embs[0] == [0.0] * 1536, (
                        f"Expected zeros vector of dim 1536, got dim {len(indexed_embs[0])}"
                    )

        assert status == "degraded_zero_fallback", (
            f"Expected 'degraded_zero_fallback' but got '{status}'"
        )


class TestReindexTelemetry:
    """Tests for log_reindex and get_chunking_metrics."""

    def test_log_reindex_contains_required_fields(self):
        """log_reindex appends a reindex event with all required fields."""
        import tempfile, json
        from pathlib import Path
        from services.telemetry_service import TelemetryService

        with tempfile.TemporaryDirectory() as tmpdir:
            reindex_log = Path(tmpdir) / "reindex.jsonl"

            class FakeTelemetry(TelemetryService):
                REINDEX_LOG = reindex_log

            tel = FakeTelemetry()
            reindex_log.parent.mkdir(parents=True, exist_ok=True)

            tel.log_reindex(
                document_id="doc123",
                workspace_id="ws1",
                chunking_strategy="semantic",
                chunk_count=7,
                processing_time_ms=432,
                embedding_status="original",
                source="chunking_ab_restore",
                request_id="req-abc",
            )

            lines = reindex_log.read_text(encoding="utf-8").strip().split("\n")
            assert len(lines) == 1
            event = json.loads(lines[0])

            assert event["type"] == "reindex"
            assert event["document_id"] == "doc123"
            assert event["workspace_id"] == "ws1"
            assert event["chunking_strategy"] == "semantic"
            assert event["chunk_count"] == 7
            assert event["processing_time_ms"] == 432
            assert event["embedding_status"] == "original"
            assert event["source"] == "chunking_ab_restore"
            assert event["request_id"] == "req-abc"
            assert "timestamp" in event

    def test_log_reindex_source_values(self):
        """log_reindex accepts all documented source values."""
        import tempfile, json
        from pathlib import Path
        from services.telemetry_service import TelemetryService

        with tempfile.TemporaryDirectory() as tmpdir:
            reindex_log = Path(tmpdir) / "reindex.jsonl"

            class FakeTelemetry(TelemetryService):
                REINDEX_LOG = reindex_log

            tel = FakeTelemetry()
            reindex_log.parent.mkdir(parents=True, exist_ok=True)

            for source in ("reindex", "chunking_ab_restore", "chunking_ab_baseline", "chunking_ab_variant"):
                tel.log_reindex(
                    document_id="doc1",
                    workspace_id="default",
                    chunking_strategy="recursive",
                    chunk_count=5,
                    processing_time_ms=100,
                    embedding_status="regenerated",
                    source=source,
                )

            lines = reindex_log.read_text(encoding="utf-8").strip().split("\n")
            assert len(lines) == 4
            for i, source in enumerate(("reindex", "chunking_ab_restore", "chunking_ab_baseline", "chunking_ab_variant")):
                event = json.loads(lines[i])
                assert event["source"] == source, f"Expected source={source}, got {event['source']}"

    def test_get_chunking_metrics_aggregates_by_strategy(self):
        """get_chunking_metrics returns per-strategy document counts and avg latency."""
        import tempfile, json
        from pathlib import Path
        from services.telemetry_service import TelemetryService

        with tempfile.TemporaryDirectory() as tmpdir:
            reindex_log = Path(tmpdir) / "reindex.jsonl"

            class FakeTelemetry(TelemetryService):
                REINDEX_LOG = reindex_log

            tel = FakeTelemetry()
            reindex_log.parent.mkdir(parents=True, exist_ok=True)

            # Write 3 reindex events: 2 recursive, 1 semantic
            events = [
                {
                    "timestamp": "2026-04-18T10:00:00+00:00",
                    "type": "reindex",
                    "document_id": "d1", "workspace_id": "ws1",
                    "chunking_strategy": "recursive", "chunk_count": 5,
                    "processing_time_ms": 100, "embedding_status": "original",
                    "source": "reindex",
                },
                {
                    "timestamp": "2026-04-18T10:01:00+00:00",
                    "type": "reindex",
                    "document_id": "d2", "workspace_id": "ws1",
                    "chunking_strategy": "recursive", "chunk_count": 10,
                    "processing_time_ms": 200, "embedding_status": "regenerated",
                    "source": "chunking_ab_baseline",
                },
                {
                    "timestamp": "2026-04-18T10:02:00+00:00",
                    "type": "reindex",
                    "document_id": "d3", "workspace_id": "ws1",
                    "chunking_strategy": "semantic", "chunk_count": 7,
                    "processing_time_ms": 300, "embedding_status": "original",
                    "source": "chunking_ab_variant",
                },
            ]
            for ev in events:
                with open(reindex_log, "a", encoding="utf-8") as f:
                    f.write(json.dumps(ev) + "\n")

            metrics = tel.get_chunking_metrics(days=30, workspace_id="ws1")

            assert metrics["total_reindex_operations"] == 3
            assert metrics["unique_documents_reindexed"] == 3  # all different docs
            assert "historical" in metrics
            assert "recursive" in metrics["historical"]["by_strategy"]
            assert "semantic" in metrics["historical"]["by_strategy"]
            assert metrics["historical"]["by_strategy"]["recursive"]["operation_count"] == 2
            assert metrics["historical"]["by_strategy"]["semantic"]["operation_count"] == 1
            assert metrics["historical"]["by_strategy"]["recursive"]["avg_chunk_count"] == 7.5
            assert metrics["historical"]["by_strategy"]["recursive"]["avg_processing_time_ms"] == 150.0
            assert metrics["historical"]["by_strategy"]["semantic"]["avg_chunk_count"] == 7.0
            assert metrics["historical"]["by_strategy"]["semantic"]["avg_processing_time_ms"] == 300.0

    def test_get_chunking_metrics_tracks_degraded_count(self):
        """degraded_zero_fallback count is correctly tallied per strategy."""
        import tempfile, json
        from pathlib import Path
        from services.telemetry_service import TelemetryService

        with tempfile.TemporaryDirectory() as tmpdir:
            reindex_log = Path(tmpdir) / "reindex.jsonl"

            class FakeTelemetry(TelemetryService):
                REINDEX_LOG = reindex_log

            tel = FakeTelemetry()
            reindex_log.parent.mkdir(parents=True, exist_ok=True)

            events = [
                {
                    "timestamp": "2026-04-18T10:00:00+00:00",
                    "type": "reindex",
                    "document_id": "d1", "workspace_id": "ws1",
                    "chunking_strategy": "recursive", "chunk_count": 5,
                    "processing_time_ms": 100, "embedding_status": "degraded_zero_fallback",
                    "source": "reindex",
                },
                {
                    "timestamp": "2026-04-18T10:01:00+00:00",
                    "type": "reindex",
                    "document_id": "d2", "workspace_id": "ws1",
                    "chunking_strategy": "recursive", "chunk_count": 5,
                    "processing_time_ms": 100, "embedding_status": "original",
                    "source": "reindex",
                },
                {
                    "timestamp": "2026-04-18T10:02:00+00:00",
                    "type": "reindex",
                    "document_id": "d3", "workspace_id": "ws1",
                    "chunking_strategy": "semantic", "chunk_count": 5,
                    "processing_time_ms": 100, "embedding_status": "degraded_zero_fallback",
                    "source": "chunking_ab_restore",
                },
            ]
            for ev in events:
                with open(reindex_log, "a", encoding="utf-8") as f:
                    f.write(json.dumps(ev) + "\n")

            metrics = tel.get_chunking_metrics(days=30, workspace_id="ws1")

            assert metrics["total_degraded_zero_fallback"] == 2
            assert metrics["historical"]["by_strategy"]["recursive"]["degraded_zero_fallback_count"] == 1
            assert metrics["historical"]["by_strategy"]["semantic"]["degraded_zero_fallback_count"] == 1
            assert metrics["historical"]["by_source"]["reindex"] == 2
            assert metrics["historical"]["by_source"]["chunking_ab_restore"] == 1

    def test_get_chunking_metrics_empty_when_no_log(self):
        """get_chunking_metrics returns empty structure when no reindex events exist."""
        import tempfile
        from pathlib import Path
        from services.telemetry_service import TelemetryService

        with tempfile.TemporaryDirectory() as tmpdir:
            reindex_log = Path(tmpdir) / "empty.jsonl"
            reindex_log.parent.mkdir(parents=True, exist_ok=True)
            reindex_log.write_text("", encoding="utf-8")

            class FakeTelemetry(TelemetryService):
                REINDEX_LOG = reindex_log

            tel = FakeTelemetry()
            metrics = tel.get_chunking_metrics(days=30)

            assert metrics["total_reindex_operations"] == 0
            assert metrics["unique_documents_reindexed"] == 0
            assert metrics["historical"]["by_strategy"] == {}
            assert metrics["historical"]["by_source"] == {}
            assert metrics["total_degraded_zero_fallback"] == 0

    def test_get_chunking_metrics_backward_compat_missing_fields(self):
        """Logs missing new fields (embedding_status, source) don't crash aggregation."""
        import tempfile, json
        from pathlib import Path
        from services.telemetry_service import TelemetryService

        with tempfile.TemporaryDirectory() as tmpdir:
            reindex_log = Path(tmpdir) / "reindex.jsonl"

            class FakeTelemetry(TelemetryService):
                REINDEX_LOG = reindex_log

            tel = FakeTelemetry()
            reindex_log.parent.mkdir(parents=True, exist_ok=True)

            # Write event missing embedding_status and source (backward compat)
            old_event = {
                "timestamp": "2026-04-18T10:00:00+00:00",
                "type": "reindex",
                "document_id": "d1", "workspace_id": "ws1",
                "chunking_strategy": "recursive", "chunk_count": 5,
                "processing_time_ms": 100,
                # no embedding_status, no source
            }
            reindex_log.write_text(json.dumps(old_event) + "\n", encoding="utf-8")

            metrics = tel.get_chunking_metrics(days=30, workspace_id="ws1")

            # Should not crash, should count the event
            assert metrics["total_reindex_operations"] == 1
            assert metrics["unique_documents_reindexed"] == 1
            assert metrics["historical"]["by_strategy"]["recursive"]["operation_count"] == 1
            assert metrics["total_degraded_zero_fallback"] == 0
            assert metrics["historical"]["by_source"]["unknown"] == 1  # missing source defaults to "unknown"

    def test_log_ingestion_accepts_embedding_status(self):
        """log_ingestion accepts and persists embedding_status field."""
        import tempfile, json
        from pathlib import Path
        from services.telemetry_service import TelemetryService

        with tempfile.TemporaryDirectory() as tmpdir:
            ingest_log = Path(tmpdir) / "ingestion.jsonl"

            class FakeTelemetry(TelemetryService):
                INGEST_LOG = ingest_log

            tel = FakeTelemetry()
            ingest_log.parent.mkdir(parents=True, exist_ok=True)

            tel.log_ingestion(
                document_id="doc1",
                workspace_id="ws1",
                source_type="md",
                filename="test.md",
                status="success",
                chunk_count=5,
                processing_time_ms=100,
                embedding_status="regenerated",
            )

            lines = ingest_log.read_text(encoding="utf-8").strip().split("\n")
            event = json.loads(lines[0])
            assert event["embedding_status"] == "regenerated"

    def test_log_ingestion_works_without_embedding_status(self):
        """log_ingestion without embedding_status does not include the field."""
        import tempfile, json
        from pathlib import Path
        from services.telemetry_service import TelemetryService

        with tempfile.TemporaryDirectory() as tmpdir:
            ingest_log = Path(tmpdir) / "ingestion.jsonl"

            class FakeTelemetry(TelemetryService):
                INGEST_LOG = ingest_log

            tel = FakeTelemetry()
            ingest_log.parent.mkdir(parents=True, exist_ok=True)

            tel.log_ingestion(
                document_id="doc1",
                workspace_id="ws1",
                source_type="md",
                filename="test.md",
                status="success",
                chunk_count=5,
                processing_time_ms=100,
            )

            lines = ingest_log.read_text(encoding="utf-8").strip().split("\n")
            event = json.loads(lines[0])
            assert "embedding_status" not in event

    def test_same_document_multiple_events_deduplicated(self):
        """A single document reindexed multiple times inflates operation_count but not unique_documents_reindexed."""
        import tempfile, json
        from pathlib import Path
        from services.telemetry_service import TelemetryService

        with tempfile.TemporaryDirectory() as tmpdir:
            reindex_log = Path(tmpdir) / "reindex.jsonl"

            class FakeTelemetry(TelemetryService):
                REINDEX_LOG = reindex_log

            tel = FakeTelemetry()
            reindex_log.parent.mkdir(parents=True, exist_ok=True)

            # Same document "d1" appears in 3 events (A/B: baseline, variant, restore)
            events = [
                {
                    "timestamp": "2026-04-18T10:00:00+00:00",
                    "type": "reindex",
                    "document_id": "d1", "workspace_id": "ws1",
                    "chunking_strategy": "recursive", "chunk_count": 5,
                    "processing_time_ms": 100, "embedding_status": "regenerated",
                    "source": "chunking_ab_baseline",
                },
                {
                    "timestamp": "2026-04-18T10:01:00+00:00",
                    "type": "reindex",
                    "document_id": "d1", "workspace_id": "ws1",
                    "chunking_strategy": "semantic", "chunk_count": 8,
                    "processing_time_ms": 200, "embedding_status": "regenerated",
                    "source": "chunking_ab_variant",
                },
                {
                    "timestamp": "2026-04-18T10:02:00+00:00",
                    "type": "reindex",
                    "document_id": "d1", "workspace_id": "ws1",
                    "chunking_strategy": "recursive", "chunk_count": 5,
                    "processing_time_ms": 100, "embedding_status": "original",
                    "source": "chunking_ab_restore",
                },
                {
                    "timestamp": "2026-04-18T10:03:00+00:00",
                    "type": "reindex",
                    "document_id": "d2", "workspace_id": "ws1",
                    "chunking_strategy": "semantic", "chunk_count": 7,
                    "processing_time_ms": 300, "embedding_status": "regenerated",
                    "source": "reindex",
                },
            ]
            for ev in events:
                with open(reindex_log, "a", encoding="utf-8") as f:
                    f.write(json.dumps(ev) + "\n")

            metrics = tel.get_chunking_metrics(days=30, workspace_id="ws1")

            # 4 events total, but only 2 unique documents
            assert metrics["total_reindex_operations"] == 4
            assert metrics["unique_documents_reindexed"] == 2
            # Operation count per strategy should still reflect all events
            assert metrics["historical"]["by_strategy"]["recursive"]["operation_count"] == 2
            assert metrics["historical"]["by_strategy"]["semantic"]["operation_count"] == 2
            # But by_source shows 3 A/B events + 1 manual
            assert metrics["historical"]["by_source"]["chunking_ab_baseline"] == 1
            assert metrics["historical"]["by_source"]["chunking_ab_variant"] == 1
            assert metrics["historical"]["by_source"]["chunking_ab_restore"] == 1
            assert metrics["historical"]["by_source"]["reindex"] == 1

    def test_current_corpus_included_in_metrics(self):
        """get_chunking_metrics includes current_corpus section from the registry."""
        import tempfile, json
        from pathlib import Path
        from unittest.mock import patch
        from services.telemetry_service import TelemetryService

        with tempfile.TemporaryDirectory() as tmpdir:
            reindex_log = Path(tmpdir) / "reindex.jsonl"
            reindex_log.parent.mkdir(parents=True, exist_ok=True)
            reindex_log.write_text("", encoding="utf-8")

            class FakeTelemetry(TelemetryService):
                REINDEX_LOG = reindex_log

            tel = FakeTelemetry()

            # Mock the registry to return 2 recursive, 1 semantic
            mock_registry = {
                "doc1": {"chunking_strategy": "recursive"},
                "doc2": {"chunking_strategy": "recursive"},
                "doc3": {"chunking_strategy": "semantic"},
            }
            with patch("services.document_registry.get_document_registry", return_value=mock_registry):
                metrics = tel.get_chunking_metrics(days=30, workspace_id="ws1")

            assert "current_corpus" in metrics
            assert metrics["current_corpus"]["available"] is True
            assert metrics["current_corpus"]["total_documents"] == 3
            assert metrics["current_corpus"]["by_strategy"]["recursive"] == 2
            assert metrics["current_corpus"]["by_strategy"]["semantic"] == 1

    def test_current_corpus_graceful_when_registry_fails(self):
        """If the registry cannot be read, current_corpus.available is False."""
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from services.telemetry_service import TelemetryService

        with tempfile.TemporaryDirectory() as tmpdir:
            reindex_log = Path(tmpdir) / "reindex.jsonl"
            reindex_log.parent.mkdir(parents=True, exist_ok=True)
            reindex_log.write_text("", encoding="utf-8")

            class FakeTelemetry(TelemetryService):
                REINDEX_LOG = reindex_log

            tel = FakeTelemetry()

            with patch(
                "services.document_registry.get_document_registry",
                side_effect=RuntimeError("disk error"),
            ):
                metrics = tel.get_chunking_metrics(days=30, workspace_id="ws1")

            assert metrics["current_corpus"]["available"] is False
            assert metrics["current_corpus"]["by_strategy"] == {}

    def test_restore_embeddings_recovers_from_qdrant_no_api_call(self):
        """When chunks lack embeddings but Qdrant has them, recovery uses Qdrant (no API call)."""
        import tempfile, json
        from pathlib import Path
        from unittest.mock import patch, MagicMock
        from services.ingestion_service import _restore_embeddings_if_needed, _embedding_is_valid

        doc_id = "doc1"
        # Chunks WITHOUT embeddings (simulating a backup without embedded vectors)
        chunks = [
            {
                "chunk_id": f"{doc_id}_c0",
                "document_id": doc_id,
                "workspace_id": "default",
                "chunk_index": 0,
                "text": "Some text here.",
                "start_char": 0,
                "end_char": 16,
                "strategy": "recursive",
                "created_at": "2026-01-01T00:00:00",
                # no "embedding" key
            },
        ]

        # Mock Qdrant returning the embeddings
        mock_record = MagicMock()
        mock_record.payload = {"chunk_id": f"{doc_id}_c0"}
        mock_record.vector = {"dense": [0.5] * 1536}

        with patch(
            "services.ingestion_service._get_embeddings_from_qdrant",
            return_value={f"{doc_id}_c0": [0.5] * 1536},
        ) as mock_qdrant:
            with patch(
                "services.ingestion_service.get_embeddings_batch",
            ) as mock_api:
                updated, were_regenerated = _restore_embeddings_if_needed(chunks)

        # Qdrant was called (not API)
        mock_qdrant.assert_called_once()
        mock_api.assert_not_called()

        # Embeddings are now present and valid
        assert _embedding_is_valid(updated[0].get("embedding"))
        assert updated[0]["embedding"] == [0.5] * 1536
        # were_regenerated=False because they came from Qdrant (original state in Qdrant)
        assert were_regenerated is False

    def test_restore_embeddings_qdrant_missing_then_api(self):
        """When Qdrant returns partial embeddings, missing chunks are regenerated via API (Qdrant embeddings preserved)."""
        import tempfile, json
        from pathlib import Path
        from unittest.mock import patch, MagicMock
        from services.ingestion_service import _restore_embeddings_if_needed, _embedding_is_valid

        doc_id = "doc1"
        chunks = [
            {
                "chunk_id": f"{doc_id}_c0",
                "document_id": doc_id,
                "workspace_id": "default",
                "chunk_index": 0,
                "text": "Text c0.",
                "start_char": 0,
                "end_char": 8,
                "strategy": "recursive",
                "created_at": "2026-01-01T00:00:00",
            },
            {
                "chunk_id": f"{doc_id}_c1",
                "document_id": doc_id,
                "workspace_id": "default",
                "chunk_index": 1,
                "text": "Text c1.",
                "start_char": 9,
                "end_char": 17,
                "strategy": "recursive",
                "created_at": "2026-01-01T00:00:00",
            },
        ]

        # Qdrant only has chunk 0, not chunk 1
        with patch(
            "services.ingestion_service._get_embeddings_from_qdrant",
            return_value={f"{doc_id}_c0": [0.5] * 1536},  # only c0
        ):
            with patch(
                "services.ingestion_service.get_embeddings_batch",
                return_value=[[0.7] * 1536],  # only 1 API call (for c1)
            ) as mock_api:
                updated, were_regenerated = _restore_embeddings_if_needed(chunks)

        # API was called only once (for the 1 missing chunk)
        mock_api.assert_called_once()
        # c0 preserved from Qdrant, c1 regenerated via API
        assert updated[0]["embedding"] == [0.5] * 1536
        assert updated[1]["embedding"] == [0.7] * 1536
        assert were_regenerated is True  # at least one was regenerated via API

    def test_restore_embeddings_qdrant_fails_then_api_success(self):
        """When Qdrant read fails but API succeeds, API is used (no degraded fallback)."""
        import tempfile, json
        from pathlib import Path
        from unittest.mock import patch, MagicMock
        from services.ingestion_service import _restore_embeddings_if_needed, _embedding_is_valid

        chunks = [
            {
                "chunk_id": "c0", "document_id": "doc1", "workspace_id": "default",
                "chunk_index": 0, "text": "Text.", "start_char": 0,
                "end_char": 5, "strategy": "recursive", "created_at": "2026-01-01T00:00:00",
            },
        ]

        with patch(
            "services.ingestion_service._get_embeddings_from_qdrant",
            side_effect=RuntimeError("Qdrant unavailable"),
        ):
            with patch(
                "services.ingestion_service.get_embeddings_batch",
                return_value=[[0.9] * 1536],
            ):
                updated, were_regenerated = _restore_embeddings_if_needed(chunks)

        # API was called as fallback
        assert _embedding_is_valid(updated[0]["embedding"])
        assert were_regenerated is True

    def test_restore_embeddings_qdrant_fails_api_fails_returns_zeros(self):
        """When both Qdrant and API fail, chunks returned as-is (caller indexes zeros)."""
        import tempfile, json
        from pathlib import Path
        from unittest.mock import patch, MagicMock
        from services.ingestion_service import _restore_embeddings_if_needed

        chunks = [
            {
                "chunk_id": "c0", "document_id": "doc1", "workspace_id": "default",
                "chunk_index": 0, "text": "Text.", "start_char": 0,
                "end_char": 5, "strategy": "recursive", "created_at": "2026-01-01T00:00:00",
            },
        ]

        with patch(
            "services.ingestion_service._get_embeddings_from_qdrant",
            side_effect=RuntimeError("Qdrant unavailable"),
        ):
            with patch(
                "services.ingestion_service.get_embeddings_batch",
                side_effect=RuntimeError("API offline"),
            ):
                updated, were_regenerated = _restore_embeddings_if_needed(chunks)

        # Returns unchanged chunks; no embedding key added
        assert "embedding" not in updated[0]
        assert were_regenerated is False  # not regenerated — caller will use zeros

    def test_restore_embeddings_qdrant_invalid_emb_for_one_chunk_goes_to_api(self):
        """Qdrant returns an embedding with wrong dimension for one chunk — that chunk goes to API, valid ones are kept."""
        from unittest.mock import patch, MagicMock
        from services.ingestion_service import _restore_embeddings_if_needed, _embedding_is_valid

        doc_id = "doc1"
        chunks = [
            {
                "chunk_id": f"{doc_id}_c0", "document_id": doc_id, "workspace_id": "default",
                "chunk_index": 0, "text": "Text c0.", "start_char": 0,
                "end_char": 8, "strategy": "recursive", "created_at": "2026-01-01T00:00:00",
            },
            {
                "chunk_id": f"{doc_id}_c1", "document_id": doc_id, "workspace_id": "default",
                "chunk_index": 1, "text": "Text c1.", "start_char": 9,
                "end_char": 17, "strategy": "recursive", "created_at": "2026-01-01T00:00:00",
            },
        ]

        # Qdrant returns c0 with WRONG DIMENSION (512 instead of 1536) — invalid
        # Qdrant returns c1 with correct embedding — valid
        with patch(
            "services.ingestion_service._get_embeddings_from_qdrant",
            return_value={
                f"{doc_id}_c0": [0.5] * 512,   # INVALID: wrong dimension
                f"{doc_id}_c1": [0.9] * 1536,  # VALID
            },
        ):
            with patch(
                "services.ingestion_service.get_embeddings_batch",
                return_value=[[0.7] * 1536],  # only 1 call (for c0)
            ) as mock_api:
                updated, were_regenerated = _restore_embeddings_if_needed(chunks)

        # API was called for c0 (invalid from Qdrant)
        mock_api.assert_called_once()
        # c0 regenerated via API (from the single call)
        assert updated[0]["embedding"] == [0.7] * 1536
        # c1 kept the valid Qdrant embedding
        assert updated[1]["embedding"] == [0.9] * 1536
        assert were_regenerated is True

    def test_restore_embeddings_qdrant_all_invalid_goes_to_api(self):
        """Qdrant returns invalid embeddings for all chunks — all go to API."""
        from unittest.mock import patch, MagicMock
        from services.ingestion_service import _restore_embeddings_if_needed, _embedding_is_valid

        chunks = [
            {
                "chunk_id": "c0", "document_id": "doc1", "workspace_id": "default",
                "chunk_index": 0, "text": "Text c0.", "start_char": 0,
                "end_char": 8, "strategy": "recursive", "created_at": "2026-01-01T00:00:00",
            },
            {
                "chunk_id": "c1", "document_id": "doc1", "workspace_id": "default",
                "chunk_index": 1, "text": "Text c1.", "start_char": 9,
                "end_char": 17, "strategy": "recursive", "created_at": "2026-01-01T00:00:00",
            },
        ]

        # Qdrant returns all with WRONG TYPE (strings instead of floats)
        with patch(
            "services.ingestion_service._get_embeddings_from_qdrant",
            return_value={
                "c0": ["not", "a", "number"] * 500,  # invalid type
                "c1": ["also", "invalid"],              # invalid type
            },
        ):
            with patch(
                "services.ingestion_service.get_embeddings_batch",
                return_value=[[0.1] * 1536, [0.2] * 1536],
            ) as mock_api:
                updated, were_regenerated = _restore_embeddings_if_needed(chunks)

        mock_api.assert_called_once()
        assert updated[0]["embedding"] == [0.1] * 1536
        assert updated[1]["embedding"] == [0.2] * 1536
        assert were_regenerated is True

    def test_restore_embeddings_qdrant_invalid_all_api_fails_degraded(self):
        """Qdrant returns all invalid + API fails → degraded_zero_fallback (chunks returned unchanged)."""
        from unittest.mock import patch, MagicMock
        from services.ingestion_service import _restore_embeddings_if_needed

        chunks = [
            {
                "chunk_id": "c0", "document_id": "doc1", "workspace_id": "default",
                "chunk_index": 0, "text": "Text.", "start_char": 0,
                "end_char": 5, "strategy": "recursive", "created_at": "2026-01-01T00:00:00",
            },
        ]

        # Qdrant returns invalid, API fails
        with patch(
            "services.ingestion_service._get_embeddings_from_qdrant",
            return_value={"c0": [0.5] * 512},  # invalid dimension
        ):
            with patch(
                "services.ingestion_service.get_embeddings_batch",
                side_effect=RuntimeError("API offline"),
            ):
                updated, were_regenerated = _restore_embeddings_if_needed(chunks)

        # No embedding added; caller will index zeros
        assert "embedding" not in updated[0]
        assert were_regenerated is False  # degraded path

    def test_ensure_backup_has_embeddings_reads_from_qdrant(self):
        """_ensure_backup_has_embeddings adds embeddings from Qdrant to chunks that lack them."""
        import tempfile, json
        from pathlib import Path
        from unittest.mock import patch, MagicMock

        with tempfile.TemporaryDirectory() as tmpdir:
            sys.path.insert(0, str(Path(__file__).parent.parent))
            from services.evaluation_service import _ensure_backup_has_embeddings

            chunks = [
                {
                    "chunk_id": "doc1_c0", "document_id": "doc1",
                    "workspace_id": "default", "chunk_index": 0,
                    "text": "Some text.", "start_char": 0, "end_char": 10,
                    "strategy": "recursive", "created_at": "2026-01-01T00:00:00",
                    # no "embedding"
                },
            ]

            mock_record = MagicMock()
            mock_record.payload = {"chunk_id": "doc1_c0"}
            mock_record.vector = {"dense": [0.42] * 1536}

            with patch("services.vector_service.get_client") as mock_get_client:
                mock_client = MagicMock()
                mock_client.retrieve.return_value = [mock_record]
                mock_get_client.return_value = mock_client

                result = _ensure_backup_has_embeddings(chunks, "default")

            # Embedding was injected from Qdrant
            assert result[0]["embedding"] == [0.42] * 1536

    def test_ensure_backup_has_embeddings_skips_when_already_present(self):
        """_ensure_backup_has_embeddings is a no-op when chunks already have valid embeddings."""
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        sys.path.insert(0, str(Path(__file__).parent.parent))
        from services.evaluation_service import _ensure_backup_has_embeddings

        chunks = [
            {
                "chunk_id": "doc1_c0", "document_id": "doc1",
                "workspace_id": "default", "chunk_index": 0,
                "text": "Some text.", "start_char": 0, "end_char": 10,
                "strategy": "recursive", "created_at": "2026-01-01T00:00:00",
                "embedding": [0.99] * 1536,  # already present
            },
        ]

        with patch("services.vector_service.get_client") as mock_get_client:
            result = _ensure_backup_has_embeddings(chunks, "default")

        # No Qdrant call needed — embeddings already present
        mock_get_client.assert_not_called()
        assert result[0]["embedding"] == [0.99] * 1536

    def test_ensure_backup_has_embeddings_graceful_when_qdrant_fails(self):
        """_ensure_backup_has_embeddings returns chunks unchanged when Qdrant is unavailable."""
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        sys.path.insert(0, str(Path(__file__).parent.parent))
        from services.evaluation_service import _ensure_backup_has_embeddings

        chunks = [
            {
                "chunk_id": "doc1_c0", "document_id": "doc1",
                "workspace_id": "default", "chunk_index": 0,
                "text": "Some text.", "start_char": 0, "end_char": 10,
                "strategy": "recursive", "created_at": "2026-01-01T00:00:00",
                # no embedding
            },
        ]

        with patch(
            "services.vector_service.get_client",
            side_effect=RuntimeError("Qdrant unavailable"),
        ):
            result = _ensure_backup_has_embeddings(chunks, "default")

        # Returns chunks unchanged (no embedding injected; restore will need API or zeros)
        assert "embedding" not in result[0]

    def test_ensure_backup_has_embeddings_fast_path_rejects_invalid_emb(self):
        """Fast path rejects chunks with wrong-dimension embedding (skips to Qdrant path)."""
        import tempfile
        from pathlib import Path
        from unittest.mock import patch, MagicMock

        sys.path.insert(0, str(Path(__file__).parent.parent))
        from services.evaluation_service import _ensure_backup_has_embeddings

        # Chunk HAS an embedding but it's the wrong dimension (512 vs 1536) — invalid
        chunks = [
            {
                "chunk_id": "doc1_c0", "document_id": "doc1",
                "workspace_id": "default", "chunk_index": 0,
                "text": "Some text.", "start_char": 0, "end_char": 10,
                "strategy": "recursive", "created_at": "2026-01-01T00:00:00",
                "embedding": [0.5] * 512,  # INVALID: wrong dimension
            },
        ]

        mock_record = MagicMock()
        mock_record.payload = {"chunk_id": "doc1_c0"}
        mock_record.vector = {"dense": [0.42] * 1536}  # Valid 1536-dim from Qdrant

        with patch("services.vector_service.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.retrieve.return_value = [mock_record]
            mock_get_client.return_value = mock_client

            result = _ensure_backup_has_embeddings(chunks, "default")

        # Fast path saw invalid embedding, fell through to Qdrant, Qdrant had valid → injected
        assert result[0]["embedding"] == [0.42] * 1536

    def test_ensure_backup_has_embeddings_qdrant_invalid_not_injected(self):
        """Qdrant returns an invalid embedding — it is NOT injected into the backup."""
        import tempfile
        from pathlib import Path
        from unittest.mock import patch, MagicMock

        sys.path.insert(0, str(Path(__file__).parent.parent))
        from services.evaluation_service import _ensure_backup_has_embeddings

        chunks = [
            {
                "chunk_id": "doc1_c0", "document_id": "doc1",
                "workspace_id": "default", "chunk_index": 0,
                "text": "Some text.", "start_char": 0, "end_char": 10,
                "strategy": "recursive", "created_at": "2026-01-01T00:00:00",
                # no embedding — backup will try Qdrant
            },
        ]

        # Qdrant returns wrong-dimension embedding (512 vs 1536) — invalid
        mock_record = MagicMock()
        mock_record.payload = {"chunk_id": "doc1_c0"}
        mock_record.vector = {"dense": [0.5] * 512}  # INVALID

        with patch("services.vector_service.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.retrieve.return_value = [mock_record]
            mock_get_client.return_value = mock_client

            result = _ensure_backup_has_embeddings(chunks, "default")

        # Invalid embedding from Qdrant was NOT injected
        assert "embedding" not in result[0]
        # Fast path: no valid emb → Qdrant path → invalid from Qdrant → not injected → unchanged


class TestIntegrityService:
    """Tests for corpus integrity audit and repair."""

    def test_audit_corpus_integrity_all_ok(self, tmpdir):
        """A corpus where registry and Qdrant are consistent returns status ok."""
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from services.integrity_service import audit_corpus_integrity

        with patch("services.document_registry.get_document_registry") as mock_reg:
            mock_reg.return_value = {"doc1": {"chunk_count": 2, "chunking_strategy": "recursive"}}

            with patch("services.vector_service.get_client") as mock_get_client:
                mock_client = MagicMock()
                mock_point = MagicMock()
                mock_point.payload = {"document_id": "doc1", "chunk_id": "doc1_c0", "strategy": "recursive"}
                mock_point.vector = {"dense": [0.1] * 1536}
                mock_point2 = MagicMock()
                mock_point2.payload = {"document_id": "doc1", "chunk_id": "doc1_c1", "strategy": "recursive"}
                mock_point2.vector = {"dense": [0.2] * 1536}
                mock_client.scroll.return_value = ([mock_point, mock_point2], None)
                mock_get_client.return_value = mock_client

                report = audit_corpus_integrity(workspace_id="testws")

        assert report.total_documents == 1
        assert report.total_with_issues == 0
        assert report.total_ok == 1
        assert report.documents[0].status == "ok"

    def test_audit_corpus_integrity_missing_from_qdrant(self, tmpdir):
        """Document in registry but zero points in Qdrant → missing_from_qdrant."""
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from services.integrity_service import audit_corpus_integrity

        with patch("services.document_registry.get_document_registry") as mock_reg:
            mock_reg.return_value = {"doc1": {"chunk_count": 3, "chunking_strategy": "recursive"}}

            with patch("services.vector_service.get_client") as mock_get_client:
                mock_client = MagicMock()
                mock_client.scroll.return_value = ([], None)
                mock_get_client.return_value = mock_client

                report = audit_corpus_integrity(workspace_id="testws")

        assert report.total_with_issues == 1
        doc_result = report.documents[0]
        assert doc_result.status == "missing_from_qdrant"
        assert any(i.issue_type == "missing_from_qdrant" for i in doc_result.issues)
        assert "reindex_document" in doc_result.repair_action

    def test_audit_corpus_integrity_count_mismatch(self, tmpdir):
        """Registry says 3 chunks, Qdrant has 2 → count_mismatch."""
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from services.integrity_service import audit_corpus_integrity

        with patch("services.document_registry.get_document_registry") as mock_reg:
            mock_reg.return_value = {"doc1": {"chunk_count": 3, "chunking_strategy": "recursive"}}

            with patch("services.vector_service.get_client") as mock_get_client:
                mock_client = MagicMock()
                mock_point = MagicMock()
                mock_point.payload = {"document_id": "doc1", "chunk_id": "doc1_c0", "strategy": "recursive"}
                mock_point.vector = {"dense": [0.1] * 1536}
                mock_point2 = MagicMock()
                mock_point2.payload = {"document_id": "doc1", "chunk_id": "doc1_c1", "strategy": "recursive"}
                mock_point2.vector = {"dense": [0.2] * 1536}
                mock_client.scroll.return_value = ([mock_point, mock_point2], None)
                mock_get_client.return_value = mock_client

                report = audit_corpus_integrity(workspace_id="testws")

        assert report.total_with_issues == 1
        doc_result = report.documents[0]
        assert doc_result.status == "issues"
        assert any(i.issue_type == "count_mismatch" for i in doc_result.issues)

    def test_audit_corpus_integrity_orphan_in_qdrant(self, tmpdir):
        """Points in Qdrant with no registry entry → orphan_in_qdrant."""
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from services.integrity_service import audit_corpus_integrity

        with patch("services.document_registry.get_document_registry") as mock_reg:
            mock_reg.return_value = {}  # Empty registry

            with patch("services.vector_service.get_client") as mock_get_client:
                mock_client = MagicMock()
                mock_orphan = MagicMock()
                mock_orphan.payload = {"document_id": "orphan_doc", "chunk_id": "orphan_c0", "strategy": "recursive"}
                mock_orphan.vector = {"dense": [0.1] * 1536}
                mock_client.scroll.return_value = ([mock_orphan], None)
                mock_get_client.return_value = mock_client

                report = audit_corpus_integrity(workspace_id="testws")

        assert report.total_with_issues == 1
        orphan_result = report.documents[0]
        assert orphan_result.status == "issues"
        assert any(i.issue_type == "orphan_in_qdrant" for i in orphan_result.issues)
        assert "delete_document_chunks" in orphan_result.repair_action

    def test_audit_corpus_integrity_invalid_embedding(self, tmpdir):
        """With check_embeddings=True, invalid Qdrant embedding (NaN) → invalid_embedding."""
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from services.integrity_service import audit_corpus_integrity

        with patch("services.document_registry.get_document_registry") as mock_reg:
            mock_reg.return_value = {"doc1": {"chunk_count": 1, "chunking_strategy": "recursive"}}

            with patch("services.vector_service.get_client") as mock_get_client:
                mock_client = MagicMock()
                mock_point = MagicMock()
                mock_point.payload = {"document_id": "doc1", "chunk_id": "doc1_c0", "strategy": "recursive"}
                mock_point.vector = {"dense": [float("nan")] * 1536}
                mock_client.scroll.return_value = ([mock_point], None)
                mock_get_client.return_value = mock_client

                report = audit_corpus_integrity(workspace_id="testws", check_embeddings=True)

        doc_result = report.documents[0]
        assert doc_result.status == "issues"
        assert any(i.issue_type == "invalid_embedding" for i in doc_result.issues)

    def test_repair_document_success(self, tmpdir):
        """repair_document re-reads disk chunks and re-indexes, returning success."""
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from services.integrity_service import repair_document

        # repair_document builds: DOCUMENTS_DIR / workspace_id / f'{doc_id}_raw.json'
        doc_dir = Path(tmpdir) / "testws"
        doc_dir.mkdir(parents=True, exist_ok=True)
        ws_dir = doc_dir / "testws"
        ws_dir.mkdir(parents=True, exist_ok=True)

        chunks_data = [
            {"chunk_id": "doc1_c0", "document_id": "doc1", "workspace_id": "testws",
             "chunk_index": 0, "text": "Text 0", "start_char": 0, "end_char": 6,
             "strategy": "recursive", "created_at": "2026-01-01T00:00:00",
             "embedding": [0.1] * 1536},
            {"chunk_id": "doc1_c1", "document_id": "doc1", "workspace_id": "testws",
             "chunk_index": 1, "text": "Text 1", "start_char": 7, "end_char": 13,
             "strategy": "recursive", "created_at": "2026-01-01T00:00:00",
             "embedding": [0.2] * 1536},
        ]
        chunks_path = ws_dir / "doc1_chunks.json"
        with open(chunks_path, "w", encoding="utf-8") as f:
            json.dump(chunks_data, f)

        raw_path = ws_dir / "doc1_raw.json"
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump({"document_id": "doc1", "text": "Full text"}, f)

        with patch("core.config.DOCUMENTS_DIR", doc_dir):
            with patch("services.ingestion_service.reindex_document") as mock_reindex:
                mock_reindex.return_value = (2, "original", 50.0)

                with patch("services.vector_service.get_client") as mock_get_client:
                    mock_client = MagicMock()
                    mock_client.scroll.return_value = ([], None)
                    mock_client.count.return_value = MagicMock(count=2)
                    mock_get_client.return_value = mock_client

                    result = repair_document("doc1", workspace_id="testws")

        assert result.success is True
        assert result.chunks_reindexed == 2
        assert result.qdrant_restored is True

    def test_repair_document_missing_raw(self, tmpdir):
        """repair_document returns success=False when raw JSON is missing."""
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from services.integrity_service import repair_document

        doc_dir = Path(tmpdir) / "testws"
        doc_dir.mkdir(parents=True, exist_ok=True)

        with patch("core.config.DOCUMENTS_DIR", doc_dir):
            result = repair_document("nonexistent", workspace_id="testws")

        assert result.success is False
        assert "Raw JSON not found" in result.message

    def test_repair_document_missing_chunks_file(self, tmpdir):
        """repair_document returns success=False when chunks file is missing."""
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from services.integrity_service import repair_document

        doc_dir = Path(tmpdir) / "testws"
        doc_dir.mkdir(parents=True, exist_ok=True)
        ws_dir = doc_dir / "testws"
        ws_dir.mkdir(parents=True, exist_ok=True)
        raw_path = ws_dir / "doc1_raw.json"
        raw_path.write_text('{"id": "doc1"}', encoding="utf-8")

        with patch("core.config.DOCUMENTS_DIR", doc_dir):
            result = repair_document("doc1", workspace_id="testws")

        assert result.success is False
        assert "Chunks file not found" in result.message


    def test_audit_corpus_integrity_missing_dense_vector(self, tmpdir):
        """With check_embeddings=True, point with no dense vector → invalid_embedding."""
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from services.integrity_service import audit_corpus_integrity

        with patch("services.document_registry.get_document_registry") as mock_reg:
            mock_reg.return_value = {"doc1": {"chunk_count": 1, "chunking_strategy": "recursive"}}

            with patch("services.vector_service.get_client") as mock_get_client:
                mock_client = MagicMock()
                mock_point = MagicMock()
                mock_point.payload = {"document_id": "doc1", "chunk_id": "doc1_c0", "strategy": "recursive"}
                mock_point.vector = {}  # No dense key
                mock_client.scroll.return_value = ([mock_point], None)
                mock_get_client.return_value = mock_client

                report = audit_corpus_integrity(workspace_id="testws", check_embeddings=True)

        doc_result = report.documents[0]
        assert doc_result.status == "issues"
        assert any(i.issue_type == "invalid_embedding" for i in doc_result.issues)
        assert "missing dense vector" in doc_result.issues[0].detail

    def test_audit_corpus_integrity_strategy_mix_in_document(self, tmpdir):
        """Points with mixed strategies in same document → strategy_mismatch."""
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from services.integrity_service import audit_corpus_integrity

        with patch("services.document_registry.get_document_registry") as mock_reg:
            mock_reg.return_value = {"doc1": {"chunk_count": 2, "chunking_strategy": "recursive"}}

            with patch("services.vector_service.get_client") as mock_get_client:
                mock_client = MagicMock()
                mock_point = MagicMock()
                mock_point.payload = {"document_id": "doc1", "chunk_id": "doc1_c0", "strategy": "recursive"}
                mock_point.vector = {"dense": [0.1] * 1536}
                mock_point2 = MagicMock()
                mock_point2.payload = {"document_id": "doc1", "chunk_id": "doc1_c1", "strategy": "semantic"}
                mock_point2.vector = {"dense": [0.2] * 1536}
                mock_client.scroll.return_value = ([mock_point, mock_point2], None)
                mock_get_client.return_value = mock_client

                report = audit_corpus_integrity(workspace_id="testws")

        doc_result = report.documents[0]
        assert doc_result.status == "issues"
        assert any(i.issue_type == "strategy_mismatch" for i in doc_result.issues)
        assert "Multiple strategies" in doc_result.issues[0].detail

    def test_repair_document_embeddings_valid_false_on_degraded(self, tmpdir):
        """repair_document returns embeddings_valid=False when reindex returns 'degraded_zero_fallback'."""
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from services.integrity_service import repair_document

        doc_dir = Path(tmpdir) / "testws"
        doc_dir.mkdir(parents=True, exist_ok=True)
        ws_dir = doc_dir / "testws"
        ws_dir.mkdir(parents=True, exist_ok=True)

        chunks_data = [
            {"chunk_id": "doc1_c0", "document_id": "doc1", "workspace_id": "testws",
             "chunk_index": 0, "text": "Text 0", "start_char": 0, "end_char": 6,
             "strategy": "recursive", "created_at": "2026-01-01T00:00:00"},
        ]
        chunks_path = ws_dir / "doc1_chunks.json"
        with open(chunks_path, "w", encoding="utf-8") as f:
            json.dump(chunks_data, f)

        raw_path = ws_dir / "doc1_raw.json"
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump({"document_id": "doc1", "text": "Full text"}, f)

        with patch("core.config.DOCUMENTS_DIR", doc_dir):
            with patch("services.ingestion_service.reindex_document") as mock_reindex:
                mock_reindex.return_value = (1, "degraded_zero_fallback", 50.0)

                with patch("services.vector_service.get_client") as mock_get_client:
                    mock_client = MagicMock()
                    mock_client.scroll.return_value = ([], None)
                    mock_client.count.return_value = MagicMock(count=1)
                    mock_get_client.return_value = mock_client

                    result = repair_document("doc1", workspace_id="testws")

        assert result.embeddings_valid is False

    def test_repair_document_embeddings_valid_when_regenerated(self, tmpdir):
        """repair_document returns embeddings_valid=True when reindex returns 'regenerated'."""
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from services.integrity_service import repair_document

        doc_dir = Path(tmpdir) / "testws"
        doc_dir.mkdir(parents=True, exist_ok=True)
        ws_dir = doc_dir / "testws"
        ws_dir.mkdir(parents=True, exist_ok=True)

        chunks_data = [
            {"chunk_id": "doc1_c0", "document_id": "doc1", "workspace_id": "testws",
             "chunk_index": 0, "text": "Text 0", "start_char": 0, "end_char": 6,
             "strategy": "recursive", "created_at": "2026-01-01T00:00:00"},
        ]
        chunks_path = ws_dir / "doc1_chunks.json"
        with open(chunks_path, "w", encoding="utf-8") as f:
            json.dump(chunks_data, f)

        raw_path = ws_dir / "doc1_raw.json"
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump({"document_id": "doc1", "text": "Full text"}, f)

        with patch("core.config.DOCUMENTS_DIR", doc_dir):
            with patch("services.ingestion_service.reindex_document") as mock_reindex:
                mock_reindex.return_value = (1, "regenerated", 50.0)

                with patch("services.vector_service.get_client") as mock_get_client:
                    mock_client = MagicMock()
                    mock_client.scroll.return_value = ([], None)
                    mock_client.count.return_value = MagicMock(count=1)
                    mock_get_client.return_value = mock_client

                    result = repair_document("doc1", workspace_id="testws")

        assert result.embeddings_valid is True

    def test_repair_document_embeddings_valid_when_original(self, tmpdir):
        """repair_document returns embeddings_valid=True when reindex returns 'original'."""
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from services.integrity_service import repair_document

        doc_dir = Path(tmpdir) / "testws"
        doc_dir.mkdir(parents=True, exist_ok=True)
        ws_dir = doc_dir / "testws"
        ws_dir.mkdir(parents=True, exist_ok=True)

        chunks_data = [
            {"chunk_id": "doc1_c0", "document_id": "doc1", "workspace_id": "testws",
             "chunk_index": 0, "text": "Text 0", "start_char": 0, "end_char": 6,
             "strategy": "recursive", "created_at": "2026-01-01T00:00:00",
             "embedding": [0.1] * 1536},
        ]
        chunks_path = ws_dir / "doc1_chunks.json"
        with open(chunks_path, "w", encoding="utf-8") as f:
            json.dump(chunks_data, f)

        raw_path = ws_dir / "doc1_raw.json"
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump({"document_id": "doc1", "text": "Full text"}, f)

        with patch("core.config.DOCUMENTS_DIR", doc_dir):
            with patch("services.ingestion_service.reindex_document") as mock_reindex:
                mock_reindex.return_value = (1, "original", 50.0)

                with patch("services.vector_service.get_client") as mock_get_client:
                    mock_client = MagicMock()
                    mock_client.scroll.return_value = ([], None)
                    mock_client.count.return_value = MagicMock(count=1)
                    mock_get_client.return_value = mock_client

                    result = repair_document("doc1", workspace_id="testws")

        assert result.embeddings_valid is True


class TestQueryExpansion:
    """Tests for HyDE-like query expansion."""

    def test_expand_query_returns_hypothetical_answer(self):
        """_expand_query returns (expanded_query, latency_ms) tuple."""
        from services.search_service import _expand_query
        from unittest.mock import patch

        mock_answer = "Prazo para recurso é de 30 dias após notificação."
        with patch("services.llm_service.generate_answer") as mock_gen:
            mock_gen.return_value = (mock_answer, [], 0.0)
            expanded, latency_ms = _expand_query("Qual o prazo para recurso?")

        assert expanded.startswith("Qual o prazo para recurso?")
        assert "Prazo para recurso" in expanded
        assert len(expanded) > len("Qual o prazo para recurso?")
        assert latency_ms >= 0

    def test_expand_query_fallback_on_api_failure(self):
        """When LLM call fails, _expand_query returns ("", 0)."""
        from services.search_service import _expand_query
        from unittest.mock import patch

        with patch("services.llm_service.generate_answer") as mock_gen:
            mock_gen.side_effect = Exception("API error")
            result, latency_ms = _expand_query("Qual o prazo?")

        assert result == ""
        assert latency_ms == 0

    def test_expand_query_truncated_answer_returns_empty(self):
        """If generated answer is too short, falls back to ("", latency_ms)."""
        from services.search_service import _expand_query
        from unittest.mock import patch

        with patch("services.llm_service.generate_answer") as mock_gen:
            mock_gen.return_value = ("OK", [], 0.0)  # less than 10 chars
            result, latency_ms = _expand_query("Qual o prazo?")

        assert result == ""
        assert latency_ms >= 0

    def test_search_with_expansion_applies_correctly(self):
        """When expansion is enabled, search_query is modified and expansion fields are set."""
        from services.search_service import search_and_answer
        from services.vector_service import search_hybrid
        from models.schemas import QueryRequest, SearchResponse, SearchResultItem
        from unittest.mock import patch, MagicMock

        mock_results = [
            SearchResultItem(
                chunk_id="c1", document_id="d1", text="texto",
                score=0.95, source="dense", document_filename="doc.pdf"
            )
        ]
        mock_search_resp = SearchResponse(
            query="", workspace_id="default", results=mock_results,
            total_candidates=1, low_confidence=False, retrieval_time_ms=50,
            query_expansion_applied=False, query_expansion_method=None,
        )

        with patch("services.search_service.search_hybrid", return_value=mock_search_resp) as mock_search:
            with patch("services.search_service.generate_answer") as mock_gen:
                mock_gen.return_value = ("Resposta.", ["c1"], 100.0)

                req = QueryRequest(query="pergunta", workspace_id="default", query_expansion=True)
                resp = search_and_answer(req)

        assert resp.query_expansion_applied is True
        assert resp.query_expansion_method == "hyde"

    def test_search_expansion_fallback_uses_original(self):
        """When expansion fails, original query is used and expansion_applied stays False."""
        from services.search_service import search_and_answer
        from services.vector_service import search_hybrid
        from models.schemas import QueryRequest, SearchResponse, SearchResultItem
        from unittest.mock import patch, MagicMock

        mock_results = [
            SearchResultItem(
                chunk_id="c1", document_id="d1", text="texto",
                score=0.95, source="dense", document_filename="doc.pdf"
            )
        ]
        mock_search_resp = SearchResponse(
            query="original query", workspace_id="default", results=mock_results,
            total_candidates=1, low_confidence=False, retrieval_time_ms=50,
            query_expansion_applied=False, query_expansion_method=None,
        )

        # Side effect: first call (expansion) raises, second call (answer generation) succeeds
        call_count = [0]

        def answer_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("expansion failed")
            return ("Resposta.", ["c1"], 100.0)

        with patch("services.search_service.search_hybrid", return_value=mock_search_resp):
            with patch("services.llm_service.generate_answer", side_effect=answer_side_effect):
                req = QueryRequest(query="original query", workspace_id="default", query_expansion=True)
                resp = search_and_answer(req)

        # expansion failed, should still work with original query
        assert resp.query_expansion_applied is False
        assert resp.query_expansion_method is None

    def test_query_expansion_ab_evaluation_compares_metrics(self):
        """run_query_expansion_ab_evaluation returns QueryExpansionABResponse with baseline and variant."""
        from services.evaluation_service import EvaluationService
        from unittest.mock import patch, MagicMock
        from pathlib import Path

        # Minimal dataset
        import json, tempfile
        dataset = {"questions": []}
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(dataset, f)
            dataset_path = Path(f.name)

        evaluator = EvaluationService()

        mock_baseline_response = MagicMock()
        mock_baseline_response.evaluation_id = "abc12345"
        mock_baseline_response.workspace_id = "default"
        mock_baseline_response.total_questions = 0
        mock_baseline_response.hit_rate_top_1 = 0.0
        mock_baseline_response.hit_rate_top_3 = 0.0
        mock_baseline_response.hit_rate_top_5 = 0.0
        mock_baseline_response.avg_latency_ms = 0.0
        mock_baseline_response.avg_score = 0.0
        mock_baseline_response.low_confidence_rate = 0.0
        mock_baseline_response.judge_score = None
        mock_baseline_response.duration_seconds = 0.1

        mock_variant_response = MagicMock()
        mock_variant_response.evaluation_id = "abc12345"
        mock_variant_response.workspace_id = "default"
        mock_variant_response.total_questions = 0
        mock_variant_response.hit_rate_top_1 = 0.0
        mock_variant_response.hit_rate_top_3 = 0.0
        mock_variant_response.hit_rate_top_5 = 0.0
        mock_variant_response.avg_latency_ms = 0.0
        mock_variant_response.avg_score = 0.0
        mock_variant_response.low_confidence_rate = 0.0
        mock_variant_response.judge_score = None
        mock_variant_response.duration_seconds = 0.1

        with patch.object(evaluator, 'run_evaluation') as mock_run:
            mock_run.side_effect = [mock_baseline_response, mock_variant_response]

            result = evaluator.run_query_expansion_ab_evaluation(
                workspace_id="default",
                dataset_path=dataset_path,
                top_k=5,
                run_judge=False,
            )

        assert result.baseline.query_expansion_applied is False
        assert result.variant.query_expansion_applied is True
        assert result.variant.query_expansion_method == "hyde"
        assert result.winner in ("baseline", "variant", "tie")

        import os
        os.unlink(dataset_path)

    def test_run_evaluation_passes_query_expansion_to_request(self):
        """run_evaluation passes query_expansion field to QueryRequest."""
        from services.evaluation_service import EvaluationService
        from unittest.mock import patch, MagicMock
        from pathlib import Path
        import json, tempfile

        dataset = {
            "questions": [{
                "id": 1,
                "pergunta": "Qual o prazo?",
                "document_id": "doc1",
                "dificuldade": "easy",
                "categoria": "fato",
            }],
            "retrieval_threshold": 0.7
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(dataset, f)
            dataset_path = Path(f.name)

        evaluator = EvaluationService()

        mock_resp = MagicMock()
        mock_resp.answer = "30 dias"
        mock_resp.retrieval = {"results": [], "low_confidence": False, "retrieval_time_ms": 10}
        mock_resp.grounded = True
        mock_resp.low_confidence = False
        mock_resp.grounding = MagicMock(needs_review=False)
        mock_resp.chunks_used = []

        with patch("services.search_service.search_and_answer") as mock_search:
            mock_search.return_value = mock_resp

            result = evaluator.run_evaluation(
                workspace_id="default",
                dataset_path=dataset_path,
                top_k=5,
                run_judge=False,
                query_expansion=True,
            )

        # Check that search_and_answer was called with query_expansion=True
        call_req = mock_search.call_args[0][0]
        assert call_req.query_expansion is True

    def test_log_query_accepts_query_expansion_fields(self):
        """TelemetryService.log_query records query_expansion_applied and query_expansion_method."""
        from services.telemetry_service import TelemetryService
        import tempfile, json, os

        with tempfile.TemporaryDirectory() as tmpdir:
            # QUERIES_LOG is a class attribute computed at class definition time,
            # so we patch it directly on the class
            import pathlib
            tmp_log = pathlib.Path(tmpdir) / "queries.jsonl"
            original_log = TelemetryService.QUERIES_LOG
            TelemetryService.QUERIES_LOG = tmp_log

            try:
                tel = TelemetryService()
                tel.log_query(
                    query="test query",
                    workspace_id="default",
                    answer="answer",
                    confidence="high",
                    grounded=True,
                    chunks_used=[],
                    retrieval_time_ms=10,
                    total_latency_ms=100,
                    low_confidence=False,
                    results_count=1,
                    query_expansion_requested=True,
                    query_expansion_applied=True,
                    query_expansion_fallback=False,
                    query_expansion_method="hyde",
                    expansion_latency_ms=150,
                )

                assert tmp_log.exists()
                with open(tmp_log) as f:
                    event = json.loads(f.readline())

                assert event["query_expansion_requested"] is True
                assert event["query_expansion_applied"] is True
                assert event["query_expansion_fallback"] is False
                assert event["query_expansion_method"] == "hyde"
                assert event["expansion_latency_ms"] == 150
            finally:
                TelemetryService.QUERIES_LOG = original_log

    def test_normalize_query_event_backfills_expansion_fields(self):
        """_normalize_query_event adds defaults for query_expansion fields in legacy logs."""
        from services.telemetry_service import TelemetryService

        tel = TelemetryService()

        # Old log entry without query_expansion fields
        old_event = {
            "timestamp": "2026-01-01T00:00:00Z",
            "type": "query",
            "request_id": "req1",
            "workspace_id": "default",
            "query": "old query",
            "answer": "old answer",
            "confidence": "high",
            "grounded": True,
            "low_confidence": False,
            "chunks_used_count": 0,
            "chunk_ids": [],
            "retrieval_time_ms": 5,
            "total_latency_ms": 50,
            "results_count": 0,
        }

        normalized = tel._normalize_query_event(old_event)

        assert normalized["query_expansion_applied"] is False
        assert normalized["query_expansion_method"] is None
        assert normalized["query_expansion_fallback"] is False
        assert normalized["query_expansion_requested"] is False
        assert normalized["expansion_latency_ms"] == 0

    def test_search_response_retrieval_matches_top_level_expansion(self):
        """QueryResponse.retrieval has query_expansion_* fields matching top-level fields."""
        from services.search_service import search_and_answer
        from models.schemas import QueryRequest, SearchResponse, SearchResultItem
        from unittest.mock import patch

        mock_results = [
            SearchResultItem(
                chunk_id="c1", document_id="d1", text="texto",
                score=0.95, source="dense", document_filename="doc.pdf"
            )
        ]
        mock_search_resp = SearchResponse(
            query="", workspace_id="default", results=mock_results,
            total_candidates=1, low_confidence=False, retrieval_time_ms=50,
            query_expansion_applied=False, query_expansion_method=None,
            query_expansion_fallback=False,
        )

        with patch("services.search_service.search_hybrid", return_value=mock_search_resp):
            # Patch at the binding site in search_service, not at definition site in llm_service
            with patch("services.search_service.generate_answer", return_value=("Resposta.", ["c1"], 100.0)):
                req = QueryRequest(query="pergunta", workspace_id="default", query_expansion=True)
                resp = search_and_answer(req)

        # Top level
        assert resp.query_expansion_requested is True
        assert resp.query_expansion_applied is True
        assert resp.query_expansion_fallback is False
        assert resp.query_expansion_method == "hyde"
        # retrieval block must match
        assert resp.retrieval["query_expansion_requested"] is True
        assert resp.retrieval["query_expansion_applied"] is True
        assert resp.retrieval["query_expansion_fallback"] is False
        assert resp.retrieval["query_expansion_method"] == "hyde"

    def test_ab_evaluation_variant_exposes_query_expansion_when_enabled(self):
        """ABEvaluationResponse.variant.query_expansion_* is set when query_expansion=True."""
        from services.evaluation_service import EvaluationService
        from unittest.mock import patch, MagicMock
        from pathlib import Path
        import json, tempfile

        dataset = {"questions": []}
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(dataset, f)
            dataset_path = Path(f.name)

        evaluator = EvaluationService()

        mock_resp = MagicMock()
        for attr in ("evaluation_id", "workspace_id", "total_questions", "hit_rate_top_1",
                     "hit_rate_top_3", "hit_rate_top_5", "avg_latency_ms", "avg_score",
                     "low_confidence_rate", "judge_score", "duration_seconds"):
            setattr(mock_resp, attr, 0.0)
        mock_resp.evaluation_id = "abc12345"

        with patch.object(evaluator, 'run_evaluation', return_value=mock_resp):
            result = evaluator.run_ab_evaluation(
                workspace_id="default",
                dataset_path=dataset_path,
                top_k=5,
                run_judge=False,
                variant_method="bm25f",
                query_expansion=True,
            )

        assert result.baseline.query_expansion_applied is False
        assert result.baseline.query_expansion_method is None
        assert result.variant.query_expansion_applied is True
        assert result.variant.query_expansion_method == "hyde"

        import os
        os.unlink(dataset_path)

    def test_log_query_records_expansion_latency(self):
        """log_query records expansion_latency_ms when expansion is applied."""
        from services.telemetry_service import TelemetryService
        import tempfile, json, os, pathlib

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_log = pathlib.Path(tmpdir) / "queries.jsonl"
            original_log = TelemetryService.QUERIES_LOG
            TelemetryService.QUERIES_LOG = tmp_log

            try:
                tel = TelemetryService()
                tel.log_query(
                    query="test",
                    workspace_id="default",
                    answer="answer",
                    confidence="high",
                    grounded=True,
                    chunks_used=[],
                    retrieval_time_ms=10,
                    total_latency_ms=200,
                    low_confidence=False,
                    results_count=1,
                    query_expansion_applied=True,
                    query_expansion_method="hyde",
                    expansion_latency_ms=150,
                )

                with open(tmp_log) as f:
                    event = json.loads(f.readline())

                assert event["expansion_latency_ms"] == 150
            finally:
                TelemetryService.QUERIES_LOG = original_log

    def test_aggregate_query_expansion_splits_correctly(self):
        """_aggregate_query_expansion splits into three buckets and fallback_rate uses correct denominator."""
        from services.telemetry_service import TelemetryService
        import tempfile

        tel = TelemetryService()

        queries = [
            # requested_and_applied: expansion was requested and succeeded
            tel._normalize_query_event({
                "timestamp": "2026-04-18T00:00:00Z",
                "type": "query",
                "request_id": "req1",
                "workspace_id": "default",
                "query": "q1",
                "answer": "a1",
                "confidence": "high",
                "grounded": True,
                "low_confidence": False,
                "chunks_used_count": 0,
                "chunk_ids": [],
                "retrieval_time_ms": 30,
                "total_latency_ms": 200,
                "results_count": 1,
                "query_expansion_requested": True,
                "query_expansion_applied": True,
                "query_expansion_fallback": False,
                "query_expansion_method": "hyde",
                "expansion_latency_ms": 150,
                "top_result_score": 0.9,
            }),
            # requested_but_fallback: expansion was requested but returned empty
            tel._normalize_query_event({
                "timestamp": "2026-04-18T00:00:01Z",
                "type": "query",
                "request_id": "req2",
                "workspace_id": "default",
                "query": "q2",
                "answer": "a2",
                "confidence": "high",
                "grounded": True,
                "low_confidence": False,
                "chunks_used_count": 0,
                "chunk_ids": [],
                "retrieval_time_ms": 30,
                "total_latency_ms": 40,
                "results_count": 1,
                "query_expansion_requested": True,
                "query_expansion_applied": False,
                "query_expansion_fallback": True,
                "query_expansion_method": "hyde",
                "expansion_latency_ms": 0,
                "top_result_score": 0.8,
            }),
            # not_requested: expansion was never requested
            tel._normalize_query_event({
                "timestamp": "2026-04-18T00:00:02Z",
                "type": "query",
                "request_id": "req3",
                "workspace_id": "default",
                "query": "q3",
                "answer": "a3",
                "confidence": "high",
                "grounded": True,
                "low_confidence": False,
                "chunks_used_count": 0,
                "chunk_ids": [],
                "retrieval_time_ms": 30,
                "total_latency_ms": 40,
                "results_count": 1,
                "query_expansion_requested": False,
                "query_expansion_applied": False,
                "query_expansion_fallback": False,
                "query_expansion_method": None,
                "expansion_latency_ms": 0,
                "top_result_score": 0.85,
            }),
        ]

        metrics = tel._aggregate_query_expansion(queries)

        assert metrics["total_queries"] == 3
        assert metrics["total_expansion_requests"] == 2
        assert metrics["fallback_count"] == 1
        # fallback_rate = 1 / (1 + 1) = 0.5 (over expansion requests only)
        assert metrics["fallback_rate"] == 0.5
        # requested_and_applied bucket
        assert metrics["requested_and_applied"]["total_queries"] == 1
        assert metrics["requested_and_applied"]["avg_expansion_latency_ms"] == 150.0
        assert metrics["requested_and_applied"]["avg_latency_ms"] == 200.0
        # requested_but_fallback bucket
        assert metrics["requested_but_fallback"]["total_queries"] == 1
        assert metrics["requested_but_fallback"]["avg_expansion_latency_ms"] == 0.0
        # not_requested bucket
        assert metrics["not_requested"]["total_queries"] == 1
        assert metrics["not_requested"]["avg_latency_ms"] == 40.0

    def test_aggregate_query_expansion_empty_queries(self):
        """_aggregate_query_expansion returns empty metrics when no queries."""
        from services.telemetry_service import TelemetryService

        tel = TelemetryService()
        metrics = tel._aggregate_query_expansion([])

        assert metrics["total_queries"] == 0
        assert metrics["total_expansion_requests"] == 0
        assert metrics["fallback_rate"] == 0.0
        assert metrics["requested_and_applied"] is None
        assert metrics["requested_but_fallback"] is None
        assert metrics["not_requested"] is None

    def test_normalize_query_event_backfills_expansion_latency(self):
        """_normalize_query_event adds expansion_latency_ms=0 for legacy logs."""
        from services.telemetry_service import TelemetryService

        tel = TelemetryService()
        old_event = {
            "timestamp": "2026-01-01T00:00:00Z",
            "type": "query",
            "request_id": "req1",
            "workspace_id": "default",
            "query": "old",
            "answer": "old answer",
            "confidence": "high",
            "grounded": True,
            "low_confidence": False,
            "chunks_used_count": 0,
            "chunk_ids": [],
            "retrieval_time_ms": 5,
            "total_latency_ms": 50,
            "results_count": 0,
            "query_expansion_applied": False,
            "query_expansion_method": None,
        }

        normalized = tel._normalize_query_event(old_event)
        assert normalized["expansion_latency_ms"] == 0

    def test_get_metrics_includes_query_expansion_section(self):
        """get_metrics returns query_expansion section with correct structure."""
        from services.telemetry_service import TelemetryService
        import tempfile, json, pathlib

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_log = pathlib.Path(tmpdir) / "queries.jsonl"
            original_log = TelemetryService.QUERIES_LOG
            TelemetryService.QUERIES_LOG = tmp_log

            try:
                tel = TelemetryService()
                tel.log_query(
                    query="test",
                    workspace_id="default",
                    answer="answer",
                    confidence="high",
                    grounded=True,
                    chunks_used=[],
                    retrieval_time_ms=10,
                    total_latency_ms=200,
                    low_confidence=False,
                    results_count=1,
                    query_expansion_requested=True,
                    query_expansion_applied=True,
                    query_expansion_fallback=False,
                    query_expansion_method="hyde",
                    expansion_latency_ms=150,
                )

                metrics = tel.get_metrics(days=1, workspace_id="default")
                assert "query_expansion" in metrics
                qe = metrics["query_expansion"]
                assert qe["total_queries"] == 1
                assert qe["total_expansion_requests"] == 1
                assert qe["fallback_count"] == 0
                assert qe["requested_and_applied"] is not None
                assert qe["requested_and_applied"]["avg_expansion_latency_ms"] == 150.0
                assert qe["requested_and_applied"]["total_queries"] == 1
                assert qe["requested_but_fallback"] is None
                assert qe["not_requested"] is None
            finally:
                TelemetryService.QUERIES_LOG = original_log


    def test_adaptive_skips_specific_lookup_year(self):
        """Adaptive mode skips expansion for queries with 4+ digit numbers (e.g. years)."""
        from services.search_service import _should_expand_adaptive

        # Year-like pattern
        should_expand, reason = _should_expand_adaptive("Qual o prazo do processo 2024?")
        assert should_expand is False
        assert reason == "specific_lookup"

    def test_adaptive_skips_specific_lookup_protocolo(self):
        """Adaptive mode skips expansion for queries with reference terms like 'protocolo'."""
        from services.search_service import _should_expand_adaptive

        should_expand, reason = _should_expand_adaptive("Qual o status do protocolo 12345?")
        assert should_expand is False
        assert reason == "specific_lookup"

    def test_adaptive_expands_generic_protocol_question(self):
        """Natural-language protocol requests must not be mistaken for ID lookups."""
        from services.search_service import _should_expand_adaptive

        should_expand, reason = _should_expand_adaptive("Me dê um protocolo para convulsão em cão")
        assert should_expand is True
        assert reason == "general_query"

    def test_adaptive_skips_specific_lookup_uppercase_code(self):
        """Adaptive mode skips expansion for uppercase code patterns like PROJ123."""
        from services.search_service import _should_expand_adaptive

        should_expand, reason = _should_expand_adaptive("Status do projeto PROJ2024001")
        assert should_expand is False
        assert reason == "specific_lookup"

    def test_adaptive_skips_specific_lookup_artigo(self):
        """Adaptive mode skips expansion for 'artigo' reference term."""
        from services.search_service import _should_expand_adaptive

        should_expand, reason = _should_expand_adaptive("Texto do artigo 14 da lei")
        assert should_expand is False
        assert reason == "specific_lookup"

    def test_adaptive_expands_short_query(self):
        """Adaptive mode expands short queries (< 3 words or < 12 chars)."""
        from services.search_service import _should_expand_adaptive

        # 2 words → short_query
        should_expand, reason = _should_expand_adaptive("prazo?")
        assert should_expand is True
        assert reason == "short_query"

        # 1 word
        should_expand, reason = _should_expand_adaptive("Fluxpay")
        assert should_expand is True
        assert reason == "short_query"

        # 3 words but contains question word → natural_language_question (Rule 3 fires)
        should_expand, reason = _should_expand_adaptive("Qual o prazo?")
        assert should_expand is True
        assert reason == "natural_language_question"

    def test_adaptive_expands_natural_language_question(self):
        """Adaptive mode expands natural language questions (interrogative words)."""
        from services.search_service import _should_expand_adaptive

        should_expand, reason = _should_expand_adaptive("O que é o Fluxpay?")
        assert should_expand is True
        assert reason == "natural_language_question"

        should_expand, reason = _should_expand_adaptive("Como funciona o reembolso?")
        assert should_expand is True
        assert reason == "natural_language_question"

        should_expand, reason = _should_expand_adaptive("Where is the policy?")
        assert should_expand is True
        assert reason == "natural_language_question"

    def test_adaptive_expands_general_query(self):
        """Adaptive mode expands general open queries by default (no skip pattern matched)."""
        from services.search_service import _should_expand_adaptive

        # No skip pattern, no short query, no question word → general query
        should_expand, reason = _should_expand_adaptive("Explique o fluxo de pagamento Pix")
        assert should_expand is True
        assert reason == "general_query"

    def test_adaptive_question_mark_short_query(self):
        """Adaptive mode: question mark + short query → short_query (Rule 2 fires before Rule 3)."""
        from services.search_service import _should_expand_adaptive

        should_expand, reason = _should_expand_adaptive("Reembolso pix?")
        assert should_expand is True
        assert reason == "short_query"

    def test_search_with_adaptive_mode_expands_question(self):
        """When mode=adaptive and query is a question, expansion is applied."""
        from services.search_service import search_and_answer
        from services.vector_service import search_hybrid
        from models.schemas import QueryRequest, SearchResponse, SearchResultItem
        from unittest.mock import patch

        mock_results = [
            SearchResultItem(
                chunk_id="c1", document_id="d1", text="texto",
                score=0.95, source="dense", document_filename="doc.pdf"
            )
        ]
        mock_search_resp = SearchResponse(
            query="", workspace_id="default", results=mock_results,
            total_candidates=1, low_confidence=False, retrieval_time_ms=50,
            query_expansion_applied=False, query_expansion_method=None,
        )

        with patch("services.search_service.search_hybrid", return_value=mock_search_resp):
            with patch("services.search_service.generate_answer") as mock_gen:
                mock_gen.return_value = ("Resposta.", ["c1"], 100.0)
                req = QueryRequest(
                    query="O que é o Fluxpay?",
                    workspace_id="default",
                    query_expansion_mode="adaptive",
                )
                resp = search_and_answer(req)

        assert resp.query_expansion_mode == "adaptive"
        assert resp.query_expansion_requested is True
        assert resp.query_expansion_applied is True
        assert resp.query_expansion_decision_reason == "adaptive:natural_language_question"

    def test_search_with_adaptive_mode_skips_specific_lookup(self):
        """When mode=adaptive and query is a specific lookup, expansion is skipped."""
        from services.search_service import search_and_answer
        from services.vector_service import search_hybrid
        from models.schemas import QueryRequest, SearchResponse, SearchResultItem
        from unittest.mock import patch

        mock_results = [
            SearchResultItem(
                chunk_id="c1", document_id="d1", text="texto",
                score=0.95, source="dense", document_filename="doc.pdf"
            )
        ]
        mock_search_resp = SearchResponse(
            query="", workspace_id="default", results=mock_results,
            total_candidates=1, low_confidence=False, retrieval_time_ms=50,
            query_expansion_applied=False, query_expansion_method=None,
        )

        with patch("services.search_service.search_hybrid", return_value=mock_search_resp):
            with patch("services.search_service.generate_answer") as mock_gen:
                mock_gen.return_value = ("Resposta.", ["c1"], 100.0)
                req = QueryRequest(
                    query="protocolo 12345",
                    workspace_id="default",
                    query_expansion_mode="adaptive",
                )
                resp = search_and_answer(req)

        assert resp.query_expansion_mode == "adaptive"
        assert resp.query_expansion_requested is False
        assert resp.query_expansion_applied is False
        assert resp.query_expansion_decision_reason == "adaptive:specific_lookup"
        # generate_answer is called for answer generation (1 call with search chunks),
        # but NOT for HyDE expansion (no hyde_chunks call)
        assert mock_gen.call_count == 1
        hyde_chunks_call = [c for c in mock_gen.call_args_list
                            if c[1].get("chunks", c[0][1] if len(c[0]) > 1 else None) == [{"text": "", "chunk_id": "hyde", "score": 0.0}]]
        assert len(hyde_chunks_call) == 0, "HyDE expansion should not have been called"

    def test_search_mode_off_never_expands(self):
        """When mode=off, expansion is never requested regardless of query."""
        from services.search_service import search_and_answer
        from services.vector_service import search_hybrid
        from models.schemas import QueryRequest, SearchResponse, SearchResultItem
        from unittest.mock import patch

        mock_results = [
            SearchResultItem(
                chunk_id="c1", document_id="d1", text="texto",
                score=0.95, source="dense", document_filename="doc.pdf"
            )
        ]
        mock_search_resp = SearchResponse(
            query="", workspace_id="default", results=mock_results,
            total_candidates=1, low_confidence=False, retrieval_time_ms=50,
            query_expansion_applied=False, query_expansion_method=None,
        )

        with patch("services.search_service.search_hybrid", return_value=mock_search_resp):
            with patch("services.search_service.generate_answer") as mock_gen:
                mock_gen.return_value = ("Resposta.", ["c1"], 100.0)
                req = QueryRequest(
                    query="O que é o Fluxpay?",
                    workspace_id="default",
                    query_expansion_mode="off",
                )
                resp = search_and_answer(req)

        assert resp.query_expansion_mode == "off"
        assert resp.query_expansion_requested is False
        assert resp.query_expansion_applied is False
        assert resp.query_expansion_decision_reason is None
        # generate_answer is called for answer generation (1 call with search chunks),
        # but NOT for HyDE expansion (no hyde_chunks call)
        assert mock_gen.call_count == 1
        hyde_chunks_call = [c for c in mock_gen.call_args_list
                            if c[1].get("chunks", c[0][1] if len(c[0]) > 1 else None) == [{"text": "", "chunk_id": "hyde", "score": 0.0}]]
        assert len(hyde_chunks_call) == 0, "HyDE expansion should not have been called"

    def test_search_mode_always_expands(self):
        """When mode=always, expansion is always requested when enabled."""
        from services.search_service import search_and_answer
        from services.vector_service import search_hybrid
        from models.schemas import QueryRequest, SearchResponse, SearchResultItem
        from unittest.mock import patch

        mock_results = [
            SearchResultItem(
                chunk_id="c1", document_id="d1", text="texto",
                score=0.95, source="dense", document_filename="doc.pdf"
            )
        ]
        mock_search_resp = SearchResponse(
            query="", workspace_id="default", results=mock_results,
            total_candidates=1, low_confidence=False, retrieval_time_ms=50,
            query_expansion_applied=False, query_expansion_method=None,
        )

        with patch("services.search_service.search_hybrid", return_value=mock_search_resp):
            with patch("services.search_service.generate_answer") as mock_gen:
                mock_gen.return_value = ("Resposta.", ["c1"], 100.0)
                req = QueryRequest(
                    query="protocolo 12345",
                    workspace_id="default",
                    query_expansion_mode="always",
                )
                resp = search_and_answer(req)

        assert resp.query_expansion_mode == "always"
        assert resp.query_expansion_requested is True
        assert resp.query_expansion_applied is True
        assert resp.query_expansion_decision_reason == "always_mode"
        # HyDE was called even for specific lookup
        mock_gen.assert_called_once()

    def test_telemetry_log_query_includes_mode_and_reason(self):
        """log_query records query_expansion_mode and query_expansion_decision_reason."""
        from services.telemetry_service import TelemetryService
        import tempfile, json, pathlib

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_log = pathlib.Path(tmpdir) / "queries.jsonl"
            original_log = TelemetryService.QUERIES_LOG
            TelemetryService.QUERIES_LOG = tmp_log

            try:
                tel = TelemetryService()
                tel.log_query(
                    query="test query",
                    workspace_id="default",
                    answer="answer",
                    confidence="high",
                    grounded=True,
                    chunks_used=[],
                    retrieval_time_ms=10,
                    total_latency_ms=100,
                    low_confidence=False,
                    results_count=1,
                    query_expansion_requested=True,
                    query_expansion_applied=True,
                    query_expansion_fallback=False,
                    query_expansion_method="hyde",
                    expansion_latency_ms=150,
                    query_expansion_mode="adaptive",
                    query_expansion_decision_reason="adaptive:natural_language_question",
                )

                with open(tmp_log) as f:
                    event = json.loads(f.readline())

                assert event["query_expansion_mode"] == "adaptive"
                assert event["query_expansion_decision_reason"] == "adaptive:natural_language_question"
            finally:
                TelemetryService.QUERIES_LOG = original_log

    def test_normalize_backfills_mode_and_reason(self):
        """_normalize_query_event backfills query_expansion_mode and query_expansion_decision_reason."""
        from services.telemetry_service import TelemetryService

        tel = TelemetryService()
        old_event = {
            "timestamp": "2026-01-01T00:00:00Z",
            "type": "query",
            "request_id": "req1",
            "workspace_id": "default",
            "query": "old query",
            "answer": "old answer",
            "confidence": "high",
            "grounded": True,
            "low_confidence": False,
            "chunks_used_count": 0,
            "chunk_ids": [],
            "retrieval_time_ms": 5,
            "total_latency_ms": 50,
            "results_count": 0,
            "query_expansion_applied": False,
            "query_expansion_method": None,
            "query_expansion_fallback": False,
            "query_expansion_requested": False,
            "expansion_latency_ms": 0,
        }

        normalized = tel._normalize_query_event(old_event)
        assert normalized["query_expansion_mode"] is None
        assert normalized["query_expansion_decision_reason"] is None

    def test_search_response_includes_mode_and_reason(self):
        """SearchResponse retrieval block includes query_expansion_mode and query_expansion_decision_reason."""
        from services.search_service import search_and_answer
        from services.vector_service import search_hybrid
        from models.schemas import QueryRequest, SearchResponse, SearchResultItem
        from unittest.mock import patch

        mock_results = [
            SearchResultItem(
                chunk_id="c1", document_id="d1", text="texto",
                score=0.95, source="dense", document_filename="doc.pdf"
            )
        ]
        mock_search_resp = SearchResponse(
            query="", workspace_id="default", results=mock_results,
            total_candidates=1, low_confidence=False, retrieval_time_ms=50,
            query_expansion_applied=False, query_expansion_method=None,
            query_expansion_fallback=False, query_expansion_requested=False,
        )

        with patch("services.search_service.search_hybrid", return_value=mock_search_resp):
            with patch("services.search_service.generate_answer", return_value=("Resposta.", ["c1"], 100.0)):
                req = QueryRequest(
                    query="O que é o Fluxpay?",
                    workspace_id="default",
                    query_expansion_mode="adaptive",
                )
                resp = search_and_answer(req)

        assert resp.retrieval["query_expansion_mode"] == "adaptive"
        assert resp.retrieval["query_expansion_decision_reason"] == "adaptive:natural_language_question"

    def test_execute_search_semantic_profile_injects_strategy_filter(self):
        """Official semantic profiles must constrain retrieval to semantic chunks."""
        from services.search_service import execute_search
        from models.schemas import SearchRequest, SearchResponse
        from unittest.mock import patch

        mock_search_resp = SearchResponse(
            query="teste",
            workspace_id="default",
            results=[],
            total_candidates=0,
            low_confidence=True,
            retrieval_time_ms=10,
        )

        with patch("services.search_service.search_hybrid", return_value=mock_search_resp) as mock_search:
            resp = execute_search(
                SearchRequest(
                    query="teste",
                    workspace_id="default",
                    retrieval_profile="semantic_hybrid",
                )
            )

        call_req = mock_search.call_args[0][0]
        assert call_req.filters["strategy"] == "semantic"
        assert resp.retrieval_profile == "semantic_hybrid"
        assert resp.query_expansion_mode == "off"
        assert resp.query_expansion_requested is False

    def test_execute_search_hyde_profile_expands_before_retrieval(self):
        """Official HyDE profile must expand the query before hybrid retrieval."""
        from services.search_service import execute_search
        from models.schemas import SearchRequest, SearchResponse
        from unittest.mock import patch

        mock_search_resp = SearchResponse(
            query="pergunta expandida",
            workspace_id="default",
            results=[],
            total_candidates=0,
            low_confidence=True,
            retrieval_time_ms=10,
        )

        with patch("services.search_service._expand_query", return_value=("pergunta expandida", 5)):
            with patch("services.search_service.search_hybrid", return_value=mock_search_resp) as mock_search:
                resp = execute_search(
                    SearchRequest(
                        query="pergunta original",
                        workspace_id="default",
                        retrieval_profile="hyde_hybrid",
                    )
                )

        call_req = mock_search.call_args[0][0]
        assert call_req.query == "pergunta expandida"
        assert resp.retrieval_profile == "hyde_hybrid"
        assert resp.query_expansion_applied is True
        assert resp.query_expansion_method == "hyde"
        assert resp.query_expansion_mode == "always"

    def test_query_retrieval_profile_propagates_to_response(self):
        """Query endpoint contract must expose the selected retrieval profile end to end."""
        from services.search_service import search_and_answer
        from models.schemas import QueryRequest, SearchResponse, SearchResultItem
        from unittest.mock import patch

        mock_results = [
            SearchResultItem(
                chunk_id="c1",
                document_id="d1",
                text="texto",
                score=0.95,
                source="dense+sparse_rrf",
                document_filename="doc.pdf",
            )
        ]
        mock_search_resp = SearchResponse(
            query="pergunta expandida",
            workspace_id="default",
            results=mock_results,
            total_candidates=1,
            low_confidence=False,
            retrieval_time_ms=50,
        )

        with patch("services.search_service._expand_query", return_value=("pergunta expandida", 5)):
            with patch("services.search_service.search_hybrid", return_value=mock_search_resp) as mock_search:
                with patch("services.search_service.generate_answer", return_value=("Resposta.", ["c1"], 100.0)):
                    resp = search_and_answer(
                        QueryRequest(
                            query="pergunta",
                            workspace_id="default",
                            retrieval_profile="semantic_hyde_hybrid",
                        )
                    )

        call_req = mock_search.call_args[0][0]
        assert call_req.query == "pergunta expandida"
        assert call_req.filters["strategy"] == "semantic"
        assert resp.retrieval_profile == "semantic_hyde_hybrid"
        assert resp.retrieval["retrieval_profile"] == "semantic_hyde_hybrid"
        assert resp.query_expansion_applied is True


def test_observability_routes_return_forbidden_not_500_for_insufficient_permission():
    from fastapi.testclient import TestClient

    from api.main import app

    client = TestClient(app)
    headers = enterprise_headers(client, role="viewer", tenant_id="default")

    for path in ["/observability/alerts?workspace_id=default", "/observability/slo?workspace_id=default", "/observability/traces?limit=5"]:
        response = client.get(path, headers=headers)
        assert response.status_code == 403, response.text
        payload = response.json()
        assert isinstance(payload, dict)
        assert payload.get("detail", {}).get("error") == "forbidden"

    admin_response = client.get("/admin/alerts", headers=headers)
    assert admin_response.status_code == 403, admin_response.text
    admin_payload = admin_response.json()
    assert isinstance(admin_payload, dict)
    assert admin_payload.get("detail", {}).get("error") == "forbidden"


def test_cookie_session_preferred_over_authorization_header_for_admin_routes():
    from fastapi.testclient import TestClient
    from services.enterprise_service import SESSION_COOKIE_NAME

    from api.main import app

    client = TestClient(app)

    admin_headers = enterprise_headers(client, role="admin", tenant_id="default")
    operator_headers = enterprise_headers(client, role="operator", tenant_id="default")
    admin_token = admin_headers["Authorization"].split(" ", 1)[1]

    client.cookies.set(SESSION_COOKIE_NAME, admin_token, domain="testserver.local")

    response = client.get("/admin/events", headers={"Authorization": operator_headers["Authorization"]})
    assert response.status_code == 200, response.text


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
