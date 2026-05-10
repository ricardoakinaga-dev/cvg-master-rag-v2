import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


SRC_DIR = Path(__file__).parent.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from models.schemas import Chunk, NormalizedDocument
from services import ingestion_service


def _load_reindex_corpus_module():
    module_path = SRC_DIR / "scripts" / "reindex_corpus.py"
    spec = importlib.util.spec_from_file_location("reindex_corpus_batch_test_module", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _chunk(document_id: str, index: int, workspace_id: str = "default") -> Chunk:
    return Chunk(
        chunk_id=f"chunk_{document_id}_{index:04d}",
        document_id=document_id,
        workspace_id=workspace_id,
        chunk_index=index,
        text=f"texto do chunk {index}",
        start_char=index * 10,
        end_char=index * 10 + 10,
        page_hint=1,
        created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )


def test_reindex_corpus_indexes_document_chunks_in_batches(tmp_path, monkeypatch):
    module = _load_reindex_corpus_module()
    workspace_id = "batchws"
    document_id = "doc-batch"
    doc_dir = tmp_path / workspace_id
    doc_dir.mkdir(parents=True)

    normalized = NormalizedDocument(
        document_id=document_id,
        source_type="md",
        filename="batch.md",
        workspace_id=workspace_id,
        created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        pages=[{"page_number": 1, "text": "texto suficiente"}],
        sections=[],
        metadata={},
        raw_json_path=str(doc_dir / f"{document_id}_raw.json"),
    )
    (doc_dir / f"{document_id}_raw.json").write_text(
        json.dumps(normalized.model_dump(), ensure_ascii=False),
        encoding="utf-8",
    )

    chunks = [_chunk(document_id, i, workspace_id) for i in range(5)]
    embedding_batch_sizes: list[int] = []
    index_batch_sizes: list[int] = []

    class FakeQdrantClient:
        def __init__(self, *args, **kwargs):
            pass

    monkeypatch.setattr(module, "DOCUMENTS_DIR", tmp_path)
    monkeypatch.setattr(module, "QdrantClient", FakeQdrantClient)
    monkeypatch.setattr(module, "REINDEX_INDEX_BATCH_SIZE", 2)
    monkeypatch.setattr(module, "canonical_document_ids", lambda workspace="default": {document_id})
    monkeypatch.setattr(module, "recursive_chunk", lambda *args, **kwargs: chunks)
    monkeypatch.setattr("services.vector_service.ensure_collection", lambda recreate=False: None)
    monkeypatch.setattr("services.vector_service.delete_workspace_chunks", lambda workspace: None)

    def fake_embeddings(texts):
        embedding_batch_sizes.append(len(texts))
        return [[0.0] * 1536 for _ in texts]

    def fake_index(batch, embeddings, workspace):
        index_batch_sizes.append(len(batch))
        assert len(batch) == len(embeddings)

    monkeypatch.setattr(module, "get_embeddings_batch", fake_embeddings)
    monkeypatch.setattr("services.vector_service.index_chunks", fake_index)

    indexed = module.full_reindex(
        workspace_id=workspace_id,
        recreate_collection=False,
        local_only=False,
        verify=False,
    )

    assert indexed == 5
    assert embedding_batch_sizes == [2, 2, 1]
    assert index_batch_sizes == [2, 2, 1]


def test_reindex_document_streams_persisted_chunks_in_batches(tmp_path, monkeypatch):
    workspace_id = "default"
    document_id = "pdf-batch-doc"
    documents_dir = tmp_path / "documents"
    doc_dir = documents_dir / workspace_id
    doc_dir.mkdir(parents=True)

    normalized = NormalizedDocument(
        document_id=document_id,
        source_type="pdf",
        filename="livro.pdf",
        workspace_id=workspace_id,
        created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        pages=[],
        sections=[],
        metadata={"ingestion_mode": "controlled_pdf", "raw_text_persisted": False},
        raw_json_path=str(doc_dir / f"{document_id}_raw.json"),
    )
    (doc_dir / f"{document_id}_raw.json").write_text(
        json.dumps(normalized.model_dump(), ensure_ascii=False),
        encoding="utf-8",
    )

    chunks = []
    for i in range(5):
        payload = _chunk(document_id, i, workspace_id).model_dump()
        payload["embedding"] = [0.0] * ingestion_service.EMBEDDING_DIM
        chunks.append(payload)
    (doc_dir / f"{document_id}_chunks.json").write_text(
        json.dumps(chunks, ensure_ascii=False),
        encoding="utf-8",
    )

    index_batch_sizes: list[int] = []
    monkeypatch.setattr(ingestion_service, "DOCUMENTS_DIR", documents_dir)
    monkeypatch.setattr(ingestion_service, "INGESTION_INDEX_BATCH_SIZE", 2)
    monkeypatch.setattr(ingestion_service, "delete_document_chunks", lambda doc: None)

    def fake_index(batch, embeddings, workspace):
        index_batch_sizes.append(len(batch))
        assert len(batch) == len(embeddings)

    monkeypatch.setattr(ingestion_service, "index_chunks", fake_index)

    count, embedding_status, _elapsed_ms = ingestion_service.reindex_document(
        document_id=document_id,
        workspace_id=workspace_id,
    )

    assert count == 5
    assert embedding_status == "original"
    assert index_batch_sizes == [2, 2, 1]
