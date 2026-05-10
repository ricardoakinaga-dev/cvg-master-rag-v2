import json
import sys
from pathlib import Path


SRC_DIR = Path(__file__).parent.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from services import ingestion_service
from services.telemetry_service import TelemetryService


class FakePage:
    def __init__(self, page_number: int):
        self.page_number = page_number

    def extract_text(self) -> str:
        return (f"Texto observavel da pagina {self.page_number}. " * 80).strip()

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


def test_controlled_pdf_logs_batch_metrics_and_metrics_aggregate(tmp_path, monkeypatch):
    workspace_id = "default"
    documents_dir = tmp_path / "documents"
    upload_dir = documents_dir / workspace_id / "uploads"
    upload_dir.mkdir(parents=True)
    file_path = upload_dir / "observavel.pdf"
    file_path.write_bytes(b"%PDF-1.7")

    telemetry = TelemetryService()
    telemetry.QUERIES_LOG = tmp_path / "queries.jsonl"
    telemetry.INGEST_LOG = tmp_path / "ingestion.jsonl"
    telemetry.INGEST_BATCH_LOG = tmp_path / "ingestion_batches.jsonl"
    telemetry.REINDEX_LOG = tmp_path / "reindex.jsonl"
    telemetry.EVAL_LOG = tmp_path / "evaluations.jsonl"
    telemetry.AUDIT_LOG = tmp_path / "audit.jsonl"
    telemetry.REPAIR_LOG = tmp_path / "repair.jsonl"
    telemetry._ensure_logs()

    def fake_pdf_open(path, pages=None):
        return FakePdf(4, pages=pages)

    monkeypatch.setattr(ingestion_service, "DOCUMENTS_DIR", documents_dir)
    monkeypatch.setattr(ingestion_service, "PDF_INGESTION_PAGE_BATCH_SIZE", 2)
    monkeypatch.setattr(ingestion_service.pdfplumber, "open", fake_pdf_open)
    monkeypatch.setattr(ingestion_service, "_embed_and_index_chunks_in_batches", lambda *args, **kwargs: None)
    monkeypatch.setattr("services.telemetry_service._telemetry", telemetry)

    response = ingestion_service.ingest_document(
        file_path=file_path,
        workspace_id=workspace_id,
        original_filename="observavel.pdf",
        ingestion_id="ing-observable",
    )

    batch_events = [
        json.loads(line)
        for line in telemetry.INGEST_BATCH_LOG.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    metrics = telemetry.get_metrics(days=1, workspace_id=workspace_id)
    snapshot = telemetry.get_operational_snapshot(days=1, workspace_id=workspace_id)

    assert response.status == "parsed"
    assert [event["batch_index"] for event in batch_events] == [1, 2]
    assert batch_events[0]["ingestion_id"] == "ing-observable"
    assert batch_events[0]["page_start"] == 1
    assert batch_events[-1]["page_end"] == 4
    assert all(event["rss_peak_mb"] is not None for event in batch_events)
    assert metrics["ingestion_batches"]["total_batches"] == 2
    assert metrics["ingestion_batches"]["latest_ingestion_id"] == "ing-observable"
    assert metrics["ingestion_batches"]["chunks_created"] == response.chunk_count
    assert snapshot["ingestion_batches"]["count"] == 2
    assert snapshot["ingestion_batches"]["latest_ingestion_id"] == "ing-observable"
