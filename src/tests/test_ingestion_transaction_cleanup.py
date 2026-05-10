import json
import sys
from pathlib import Path


SRC_DIR = Path(__file__).parent.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import pytest

from services import ingestion_service
from models.schemas import Chunk


class FakePage:
    def __init__(self, page_number: int):
        self.page_number = page_number

    def extract_text(self) -> str:
        return (f"Texto transacional da pagina {self.page_number}. " * 80).strip()

    def flush_cache(self):
        pass


class FakePdf:
    def __init__(self, page_count: int, pages: list[int] | None = None):
        page_numbers = pages or list(range(1, page_count + 1))
        self.pages = [FakePage(page_number) for page_number in page_numbers]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_controlled_pdf_does_not_expose_final_chunks_before_commit(tmp_path, monkeypatch):
    workspace_id = "default"
    documents_dir = tmp_path / "documents"
    upload_dir = documents_dir / workspace_id / "uploads"
    upload_dir.mkdir(parents=True)
    file_path = upload_dir / "livro.pdf"
    file_path.write_bytes(b"%PDF-1.7")

    def fake_pdf_open(path, pages=None):
        return FakePdf(3, pages=pages)

    def fail_during_first_index(batch, workspace, ingestion_id=None):
        final_chunks = list((documents_dir / workspace_id).glob("*_chunks.json"))
        assert final_chunks == []
        temp_chunks = list((documents_dir / workspace_id).glob("*.tmp"))
        assert temp_chunks, "expected a staging file before commit"
        raise RuntimeError("simulated qdrant failure")

    monkeypatch.setattr(ingestion_service, "DOCUMENTS_DIR", documents_dir)
    monkeypatch.setattr(ingestion_service, "PDF_INGESTION_PAGE_BATCH_SIZE", 2)
    monkeypatch.setattr(ingestion_service.pdfplumber, "open", fake_pdf_open)
    monkeypatch.setattr(ingestion_service, "_embed_and_index_chunks_in_batches", fail_during_first_index)

    response = ingestion_service.ingest_document(
        file_path=file_path,
        workspace_id=workspace_id,
        original_filename="livro.pdf",
        ingestion_id="ing-atomic",
    )

    assert response.status == "partial"
    final_chunks = list((documents_dir / workspace_id).glob("*_chunks.json"))
    assert len(final_chunks) == 1
    json.loads(final_chunks[0].read_text(encoding="utf-8"))
    assert not list((documents_dir / workspace_id).glob("*.tmp"))


def test_failed_ingestion_job_cleans_temporary_files_and_ingestion_points(tmp_path, monkeypatch):
    from services import ingestion_job_service as jobs

    jobs_dir = tmp_path / "jobs"
    documents_dir = tmp_path / "documents"
    upload_path = documents_dir / "default" / "uploads" / "book.pdf"
    upload_path.parent.mkdir(parents=True)
    upload_path.write_bytes(b"%PDF")

    monkeypatch.setattr(jobs, "INGESTION_JOBS_DIR", jobs_dir)
    monkeypatch.setattr(jobs, "DOCUMENTS_DIR", documents_dir)

    cleaned_ingestions: list[tuple[str, str]] = []
    monkeypatch.setattr(
        jobs,
        "delete_ingestion_points",
        lambda ingestion_id, workspace_id="default": cleaned_ingestions.append((ingestion_id, workspace_id)),
    )

    job = jobs.create_ingestion_job(
        source_path=upload_path,
        workspace_id="default",
        filename="book.pdf",
        source_type="pdf",
        chunking_strategy="recursive",
    )

    def fail_ingest(path: Path, workspace_id: str, filename: str, *, chunking_strategy: str, ingestion_id: str):
        doc_dir = documents_dir / workspace_id
        (doc_dir / f"{ingestion_id}_chunks.json.tmp").write_text("[", encoding="utf-8")
        (doc_dir / f"{ingestion_id}_raw.json.tmp").write_text("{", encoding="utf-8")
        raise RuntimeError("simulated worker failure")

    failed = jobs.run_ingestion_job(job["ingestion_id"], ingest_func=fail_ingest)

    assert failed["status"] == "failed"
    assert cleaned_ingestions == [(job["ingestion_id"], "default")]
    assert not upload_path.exists()
    assert not list((documents_dir / "default").glob("*.tmp"))


def test_indexed_points_carry_ingestion_id(monkeypatch):
    from services import vector_service

    upserted_points = []

    class FakeClient:
        def upsert(self, collection_name, points):
            upserted_points.extend(points)

    chunk = Chunk(
        chunk_id="chunk_doc_0000",
        document_id="doc",
        workspace_id="default",
        chunk_index=0,
        text="conteudo indexado",
        start_char=0,
        end_char=16,
        page_hint=1,
        created_at="2026-04-30T00:00:00Z",
    )

    monkeypatch.setattr(vector_service, "get_client", lambda: FakeClient())
    monkeypatch.setattr(vector_service, "ensure_collection", lambda recreate=False: None)

    vector_service.index_chunks(
        [chunk],
        [[0.0] * vector_service.EMBEDDING_DIM],
        workspace_id="default",
        ingestion_id="ing-cleanup",
    )

    assert len(upserted_points) == 1
    assert upserted_points[0].payload["ingestion_id"] == "ing-cleanup"
