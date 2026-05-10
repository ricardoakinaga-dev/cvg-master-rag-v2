import json
import sys
from pathlib import Path
from datetime import datetime, timezone


SRC_DIR = Path(__file__).parent.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import pytest

from models.schemas import Chunk, NormalizedDocument
from services.document_parser import ParseError, parse_document
from services import ingestion_service


class FakePage:
    flushed_pages: list[int] = []
    textmap_cleared_pages: list[int] = []

    def __init__(self, page_number: int):
        self.page_number = page_number
        self.get_textmap = self._make_get_textmap()

    def extract_text(self) -> str:
        return (f"Texto extraivel da pagina {self.page_number}. " * 80).strip()

    def flush_cache(self):
        self.flushed_pages.append(self.page_number)

    def _make_get_textmap(self):
        page_number = self.page_number

        def get_textmap():
            return None

        def cache_clear():
            self.textmap_cleared_pages.append(page_number)

        get_textmap.cache_clear = cache_clear
        return get_textmap


class FakePdf:
    def __init__(self, page_count: int, pages: list[int] | None = None):
        page_numbers = pages or list(range(1, page_count + 1))
        self.pages = [FakePage(i) for i in page_numbers]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_controlled_pdf_ingestion_processes_page_batches_incrementally(tmp_path, monkeypatch):
    workspace_id = "default"
    documents_dir = tmp_path / "documents"
    upload_dir = documents_dir / workspace_id / "uploads"
    upload_dir.mkdir(parents=True)
    file_path = upload_dir / "livro-grande.pdf"
    file_path.write_bytes(b"%PDF-1.7")

    indexed_batches: list[list[str]] = []
    opened_page_ranges: list[list[int] | None] = []

    def fake_index(batch, workspace):
        indexed_batches.append([chunk.chunk_id for chunk in batch])

    def fake_pdf_open(path, pages=None):
        opened_page_ranges.append(pages)
        return FakePdf(5, pages=pages)

    FakePage.flushed_pages = []
    FakePage.textmap_cleared_pages = []
    monkeypatch.setattr(ingestion_service, "DOCUMENTS_DIR", documents_dir)
    monkeypatch.setattr(ingestion_service, "PDF_INGESTION_PAGE_BATCH_SIZE", 2)
    monkeypatch.setattr(ingestion_service, "INGESTION_INDEX_BATCH_SIZE", 1)
    monkeypatch.setattr(ingestion_service, "canonical_document_ids", lambda workspace: set())
    monkeypatch.setattr(
        ingestion_service,
        "get_tenant_by_workspace",
        lambda workspace: {"operational_retention_mode": "keep_all"},
    )
    monkeypatch.setattr(ingestion_service, "_embed_and_index_chunks_in_batches", fake_index)
    monkeypatch.setattr(ingestion_service.pdfplumber, "open", fake_pdf_open)

    response = ingestion_service.ingest_document(
        file_path=file_path,
        workspace_id=workspace_id,
        original_filename="livro-grande.pdf",
    )

    assert response.status == "parsed"
    assert response.catalog_scope == "operational"
    assert response.page_count == 5
    assert response.char_count > 0
    assert response.chunk_count > 0
    assert len(indexed_batches) == 3
    assert opened_page_ranges == [None, [1, 2], [3, 4], [5]]
    assert FakePage.flushed_pages == [1, 2, 3, 4, 5]
    assert FakePage.textmap_cleared_pages == [1, 2, 3, 4, 5]

    raw_file = documents_dir / workspace_id / f"{response.document_id}_raw.json"
    chunks_file = documents_dir / workspace_id / f"{response.document_id}_chunks.json"

    raw_payload = json.loads(raw_file.read_text(encoding="utf-8"))
    chunks_payload = json.loads(chunks_file.read_text(encoding="utf-8"))

    assert raw_payload["pages"] == []
    assert raw_payload["metadata"]["ingestion_mode"] == "controlled_pdf"
    assert raw_payload["metadata"]["raw_text_persisted"] is False
    assert raw_payload["metadata"]["page_batch_size"] == 2
    assert raw_payload["metadata"]["char_count"] == response.char_count
    assert raw_payload["metadata"]["rss_peak_mb"] is not None
    assert raw_payload["metadata"]["memory_samples"]
    assert len(chunks_payload) == response.chunk_count
    assert [chunk["chunk_index"] for chunk in chunks_payload] == list(range(response.chunk_count))
    assert all(chunk["document_id"] == response.document_id for chunk in chunks_payload)


def test_pdf_parser_path_is_blocked_for_memory_safety(tmp_path):
    pdf_path = tmp_path / "legacy-parser.pdf"
    pdf_path.write_bytes(b"%PDF-1.7")

    with pytest.raises(ParseError, match="pipeline controlado"):
        parse_document(pdf_path, workspace_id="default")


def test_canonical_pdf_ingestion_uses_controlled_pipeline(tmp_path, monkeypatch):
    workspace_id = "default"
    documents_dir = tmp_path / "documents"
    canonical_dir = tmp_path / "canonical"
    canonical_dir.mkdir(parents=True)
    file_path = canonical_dir / "canonico.pdf"
    file_path.write_bytes(b"%PDF-1.7")

    opened_page_ranges: list[list[int] | None] = []

    def fake_pdf_open(path, pages=None):
        opened_page_ranges.append(pages)
        return FakePdf(3, pages=pages)

    FakePage.flushed_pages = []
    FakePage.textmap_cleared_pages = []
    monkeypatch.setattr(ingestion_service, "DOCUMENTS_DIR", documents_dir)
    monkeypatch.setattr(ingestion_service, "PDF_INGESTION_PAGE_BATCH_SIZE", 2)
    monkeypatch.setattr(ingestion_service, "INGESTION_INDEX_BATCH_SIZE", 1)
    monkeypatch.setattr(ingestion_service, "canonical_document_ids", lambda workspace: set())
    monkeypatch.setattr(ingestion_service, "_embed_and_index_chunks_in_batches", lambda batch, workspace: None)
    monkeypatch.setattr(ingestion_service.pdfplumber, "open", fake_pdf_open)

    response = ingestion_service.ingest_document(
        file_path=file_path,
        workspace_id=workspace_id,
        original_filename="canonico.pdf",
    )

    raw_file = documents_dir / workspace_id / f"{response.document_id}_raw.json"
    raw_payload = json.loads(raw_file.read_text(encoding="utf-8"))

    assert response.status == "parsed"
    assert response.catalog_scope == "canonical"
    assert opened_page_ranges == [None, [1, 2], [3]]
    assert FakePage.flushed_pages == [1, 2, 3]
    assert raw_payload["metadata"]["catalog_scope"] == "canonical"
    assert raw_payload["metadata"]["ingestion_mode"] == "controlled_pdf"
    assert raw_payload["metadata"]["source_path"] == str(file_path)


def test_pdf_reindex_prefers_existing_chunks_over_raw_pages(tmp_path, monkeypatch):
    workspace_id = "default"
    document_id = "pdf-doc"
    documents_dir = tmp_path / "documents"
    doc_dir = documents_dir / workspace_id
    doc_dir.mkdir(parents=True)

    normalized = NormalizedDocument(
        document_id=document_id,
        source_type="pdf",
        filename="legacy.pdf",
        workspace_id=workspace_id,
        created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        pages=[{"page_number": 1, "text": "texto legado que nao deve ser rechunkado"}],
        sections=[],
        metadata={"page_count": 1},
        raw_json_path=str(doc_dir / f"{document_id}_raw.json"),
    )
    (doc_dir / f"{document_id}_raw.json").write_text(
        json.dumps(normalized.model_dump(), ensure_ascii=False),
        encoding="utf-8",
    )

    chunk = Chunk(
        chunk_id=f"chunk_{document_id}_0000",
        document_id=document_id,
        workspace_id=workspace_id,
        chunk_index=0,
        text="chunk persistido",
        start_char=0,
        end_char=16,
        page_hint=1,
        created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    ).model_dump()
    chunk["embedding"] = [0.0] * ingestion_service.EMBEDDING_DIM
    (doc_dir / f"{document_id}_chunks.json").write_text(
        json.dumps([chunk], ensure_ascii=False),
        encoding="utf-8",
    )

    indexed_texts: list[str] = []

    def fail_chunk(*args, **kwargs):
        raise AssertionError("PDF reindex must not re-chunk raw pages")

    def fake_index(chunks, embeddings, workspace):
        indexed_texts.extend(chunk.text for chunk in chunks)

    monkeypatch.setattr(ingestion_service, "DOCUMENTS_DIR", documents_dir)
    monkeypatch.setattr(ingestion_service, "_chunk_document", fail_chunk)
    monkeypatch.setattr(ingestion_service, "delete_document_chunks", lambda doc: None)
    monkeypatch.setattr(ingestion_service, "index_chunks", fake_index)

    count, embedding_status, _elapsed_ms = ingestion_service.reindex_document(
        document_id=document_id,
        workspace_id=workspace_id,
    )

    assert count == 1
    assert embedding_status == "original"
    assert indexed_texts == ["chunk persistido"]
