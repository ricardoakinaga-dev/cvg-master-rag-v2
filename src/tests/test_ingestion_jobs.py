import asyncio
import io
import json
import subprocess
from collections import namedtuple
from datetime import datetime, timedelta, timezone
import sys
from pathlib import Path

from fastapi import UploadFile

SRC_DIR = Path(__file__).parent.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from models.schemas import (
    DocumentUploadResponse,
    EnterpriseSession,
    EnterpriseTenant,
    EnterpriseUser,
)


def _operator_session() -> EnterpriseSession:
    tenant = EnterpriseTenant(tenant_id="default", name="Default", workspace_id="default")
    user = EnterpriseUser(
        user_id="operator",
        name="Operator",
        email="operator@example.test",
        role="admin",
        permissions=["documents.upload", "documents.read"],
    )
    return EnterpriseSession(user=user, active_tenant=tenant, available_tenants=[tenant])


def test_create_and_run_ingestion_job_commits_result(tmp_path, monkeypatch):
    from services import ingestion_job_service as jobs

    jobs_dir = tmp_path / "jobs"
    upload_path = tmp_path / "documents" / "default" / "uploads" / "book.pdf"
    upload_path.parent.mkdir(parents=True)
    upload_path.write_bytes(b"%PDF heavy")

    monkeypatch.setattr(jobs, "INGESTION_JOBS_DIR", jobs_dir)

    job = jobs.create_ingestion_job(
        source_path=upload_path,
        workspace_id="default",
        filename="book.pdf",
        source_type="pdf",
        chunking_strategy="recursive",
    )

    def fake_ingest_document(path: Path, workspace_id: str, filename: str, *, chunking_strategy: str):
        assert path == upload_path
        assert workspace_id == "default"
        assert filename == "book.pdf"
        assert chunking_strategy == "recursive"
        return DocumentUploadResponse(
            document_id="final-doc",
            status="parsed",
            catalog_scope="operational",
            source_type="pdf",
            filename="book.pdf",
            page_count=10,
            char_count=1000,
            chunk_count=25,
            created_at="2026-04-30T00:00:00Z",
            chunking_strategy="recursive",
        )

    committed = jobs.run_ingestion_job(job["ingestion_id"], ingest_func=fake_ingest_document)

    assert committed["status"] == "committed"
    assert committed["document_id"] == "final-doc"
    assert committed["final_document_id"] == "final-doc"
    assert committed["page_count"] == 10
    assert committed["chunks_written"] == 25
    assert committed["error_message"] is None
    assert not upload_path.exists()

    stored = json.loads((jobs_dir / f"{job['ingestion_id']}.json").read_text(encoding="utf-8"))
    assert stored["status"] == "committed"


def test_ingestion_job_preserves_qdrant_collection(tmp_path, monkeypatch):
    from services import ingestion_job_service as jobs

    jobs_dir = tmp_path / "jobs"
    upload_path = tmp_path / "documents" / "default" / "uploads" / "book.pdf"
    upload_path.parent.mkdir(parents=True)
    upload_path.write_bytes(b"%PDF heavy")

    monkeypatch.setattr(jobs, "INGESTION_JOBS_DIR", jobs_dir)

    job = jobs.create_ingestion_job(
        source_path=upload_path,
        workspace_id="default",
        filename="book.pdf",
        source_type="pdf",
        chunking_strategy="recursive",
        qdrant_collection="cvg_master_rag_alt",
    )

    def fake_ingest_document(
        path: Path,
        workspace_id: str,
        filename: str,
        *,
        chunking_strategy: str,
        qdrant_collection: str,
    ):
        assert qdrant_collection == "cvg_master_rag_alt"
        return DocumentUploadResponse(
            document_id="final-doc",
            status="parsed",
            catalog_scope="operational",
            source_type="pdf",
            filename=filename,
            page_count=1,
            char_count=100,
            chunk_count=2,
            created_at="2026-04-30T00:00:00Z",
            chunking_strategy=chunking_strategy,
            qdrant_collection=qdrant_collection,
        )

    committed = jobs.run_ingestion_job(job["ingestion_id"], ingest_func=fake_ingest_document)

    assert job["qdrant_collection"] == "cvg_master_rag_alt"
    assert committed["status"] == "committed"
    assert committed["qdrant_collection"] == "cvg_master_rag_alt"


def test_large_ingestion_preflight_rejects_insufficient_disk(tmp_path, monkeypatch):
    from services import ingestion_job_service as jobs

    documents_dir = tmp_path / "documents"
    upload_path = documents_dir / "default" / "uploads" / "large.pdf"
    upload_path.parent.mkdir(parents=True)
    upload_path.write_bytes(b"%PDF")
    disk_usage = namedtuple("usage", "total used free")

    monkeypatch.setattr(jobs, "DOCUMENTS_DIR", documents_dir)
    monkeypatch.setattr(jobs, "LARGE_INGESTION_MIN_BYTES", 50)
    monkeypatch.setattr(jobs, "LARGE_INGESTION_DISK_FREE_MIN_BYTES", 5_000)
    monkeypatch.setattr(jobs.shutil, "disk_usage", lambda _path: disk_usage(10_000, 9_900, 100))

    try:
        jobs.preflight_large_ingestion(
            source_path=upload_path,
            workspace_id="default",
            received_bytes=100,
        )
    except jobs.IngestionPreflightError as exc:
        assert exc.error_code == "insufficient_disk_space"
        assert exc.status_code == 507
        assert exc.details["disk_free_bytes_at_start"] == 100
        assert exc.details["disk_required_free_bytes"] == 5_000
    else:
        raise AssertionError("expected insufficient disk preflight failure")


def test_large_ingestion_preflight_rejects_active_large_job(tmp_path, monkeypatch):
    from services import ingestion_job_service as jobs

    jobs_dir = tmp_path / "jobs"
    documents_dir = tmp_path / "documents"
    active_upload = documents_dir / "default" / "uploads" / "active.pdf"
    new_upload = documents_dir / "default" / "uploads" / "new.pdf"
    active_upload.parent.mkdir(parents=True)
    active_upload.write_bytes(b"%PDF")
    new_upload.write_bytes(b"%PDF")
    disk_usage = namedtuple("usage", "total used free")

    monkeypatch.setattr(jobs, "INGESTION_JOBS_DIR", jobs_dir)
    monkeypatch.setattr(jobs, "DOCUMENTS_DIR", documents_dir)
    monkeypatch.setattr(jobs, "LARGE_INGESTION_MIN_BYTES", 50)
    monkeypatch.setattr(jobs, "LARGE_INGESTION_DISK_FREE_MIN_BYTES", 100)
    monkeypatch.setattr(jobs, "MAX_CONCURRENT_LARGE_INGESTION_JOBS", 1)
    monkeypatch.setattr(jobs.shutil, "disk_usage", lambda _path: disk_usage(10_000, 1_000, 9_000))

    active = jobs.create_ingestion_job(
        source_path=active_upload,
        workspace_id="default",
        filename="active.pdf",
        source_type="pdf",
        chunking_strategy="recursive",
        file_size_bytes=100,
        preflight={"large_job": True, "resource_profile": "normal"},
    )
    jobs.update_ingestion_job(active["ingestion_id"], status="processing")

    try:
        jobs.preflight_large_ingestion(
            source_path=new_upload,
            workspace_id="default",
            received_bytes=100,
        )
    except jobs.IngestionPreflightError as exc:
        assert exc.error_code == "large_ingestion_busy"
        assert exc.status_code == 409
        assert exc.details["active_large_ingestion_jobs"] == [active["ingestion_id"]]
        assert exc.details["max_concurrent_large_ingestion_jobs"] == 1
    else:
        raise AssertionError("expected busy preflight failure")


def test_large_ingestion_job_records_capacity_metadata(tmp_path, monkeypatch):
    from services import ingestion_job_service as jobs

    jobs_dir = tmp_path / "jobs"
    upload_path = tmp_path / "documents" / "default" / "uploads" / "large.pdf"
    upload_path.parent.mkdir(parents=True)
    upload_path.write_bytes(b"%PDF")

    monkeypatch.setattr(jobs, "INGESTION_JOBS_DIR", jobs_dir)

    job = jobs.create_ingestion_job(
        source_path=upload_path,
        workspace_id="default",
        filename="large.pdf",
        source_type="pdf",
        chunking_strategy="recursive",
        file_size_bytes=410_562_000,
        preflight={
            "large_job": True,
            "resource_profile": "normal",
            "disk_free_bytes_at_start": 20_000_000_000,
            "disk_required_free_bytes": 5_368_709_120,
        },
    )

    assert job["large_job"] is True
    assert job["file_size_bytes"] == 410_562_000
    assert job["resource_profile"] == "normal"
    assert job["resource_isolation_mode"] is None
    assert job["disk_free_bytes_at_start"] == 20_000_000_000
    assert job["disk_required_free_bytes"] == 5_368_709_120
    assert job["last_heartbeat_at"] is None
    assert job["last_batch_at"] is None
    assert job["operational_status"] == "pending"


def test_record_ingestion_heartbeat_adds_operator_status(tmp_path, monkeypatch):
    from services import ingestion_job_service as jobs

    jobs_dir = tmp_path / "jobs"
    upload_path = tmp_path / "documents" / "default" / "uploads" / "large.pdf"
    upload_path.parent.mkdir(parents=True)
    upload_path.write_bytes(b"%PDF")
    monkeypatch.setattr(jobs, "INGESTION_JOBS_DIR", jobs_dir)

    job = jobs.create_ingestion_job(
        source_path=upload_path,
        workspace_id="default",
        filename="large.pdf",
        source_type="pdf",
        chunking_strategy="recursive",
        file_size_bytes=410_562_000,
        preflight={"large_job": True, "resource_profile": "normal"},
    )
    started_at = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat().replace("+00:00", "Z")
    jobs.update_ingestion_job(job["ingestion_id"], status="processing", started_at=started_at)

    updated = jobs.record_ingestion_heartbeat(
        job["ingestion_id"],
        page_count=100,
        pages_processed=20,
        chunks_written=80,
        qdrant_points_written=80,
        rss_peak_mb=256.0,
        last_batch_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )

    assert updated["last_heartbeat_at"]
    assert updated["last_batch_at"]
    assert updated["pages_per_minute"] > 0
    assert updated["chunks_per_minute"] > 0
    assert updated["operational_status"] == "running"
    assert updated["operational_alerts"] == []


def test_list_ingestion_jobs_flags_stalled_processing_job(tmp_path, monkeypatch):
    from services import ingestion_job_service as jobs

    jobs_dir = tmp_path / "jobs"
    upload_path = tmp_path / "documents" / "default" / "uploads" / "large.pdf"
    upload_path.parent.mkdir(parents=True)
    upload_path.write_bytes(b"%PDF")
    monkeypatch.setattr(jobs, "INGESTION_JOBS_DIR", jobs_dir)
    monkeypatch.setattr(jobs, "INGESTION_STALE_BATCH_SECONDS", 60)

    job = jobs.create_ingestion_job(
        source_path=upload_path,
        workspace_id="default",
        filename="large.pdf",
        source_type="pdf",
        chunking_strategy="recursive",
        file_size_bytes=410_562_000,
        preflight={"large_job": True, "resource_profile": "normal"},
    )
    stale_at = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
    jobs.update_ingestion_job(
        job["ingestion_id"],
        status="processing",
        started_at=stale_at,
        last_batch_at=stale_at,
    )

    listed = jobs.list_ingestion_jobs(workspace_id="default", limit=1)

    assert listed[0]["operational_status"] == "stalled"
    assert listed[0]["seconds_since_last_batch"] >= 60
    assert listed[0]["operational_alerts"][0]["code"] == "job_stalled"


def test_list_ingestion_jobs_filters_workspace_and_orders_recent_first(tmp_path, monkeypatch):
    from services import ingestion_job_service as jobs

    jobs_dir = tmp_path / "jobs"
    upload_dir = tmp_path / "documents" / "default" / "uploads"
    upload_dir.mkdir(parents=True)
    monkeypatch.setattr(jobs, "INGESTION_JOBS_DIR", jobs_dir)

    first_path = upload_dir / "first.pdf"
    second_path = upload_dir / "second.pdf"
    other_path = upload_dir / "other.pdf"
    first_path.write_bytes(b"%PDF")
    second_path.write_bytes(b"%PDF")
    other_path.write_bytes(b"%PDF")

    first = jobs.create_ingestion_job(
        source_path=first_path,
        workspace_id="default",
        filename="first.pdf",
        source_type="pdf",
        chunking_strategy="recursive",
    )
    second = jobs.create_ingestion_job(
        source_path=second_path,
        workspace_id="default",
        filename="second.pdf",
        source_type="pdf",
        chunking_strategy="recursive",
    )
    jobs.create_ingestion_job(
        source_path=other_path,
        workspace_id="other",
        filename="other.pdf",
        source_type="pdf",
        chunking_strategy="recursive",
    )

    listed = jobs.list_ingestion_jobs(workspace_id="default", limit=10)

    assert [item["ingestion_id"] for item in listed] == [second["ingestion_id"], first["ingestion_id"]]


def test_large_worker_uses_systemd_run_and_records_limits(tmp_path, monkeypatch):
    from services import ingestion_job_service as jobs

    jobs_dir = tmp_path / "jobs"
    upload_path = tmp_path / "documents" / "default" / "uploads" / "large.pdf"
    upload_path.parent.mkdir(parents=True)
    upload_path.write_bytes(b"%PDF")
    captured: dict = {}

    monkeypatch.setattr(jobs, "INGESTION_JOBS_DIR", jobs_dir)
    monkeypatch.setattr(jobs.shutil, "which", lambda name: "/usr/bin/systemd-run" if name == "systemd-run" else None)

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(jobs.subprocess, "run", fake_run)

    job = jobs.create_ingestion_job(
        source_path=upload_path,
        workspace_id="default",
        filename="large.pdf",
        source_type="pdf",
        chunking_strategy="recursive",
        file_size_bytes=410_562_000,
        preflight={"large_job": True, "resource_profile": "normal"},
    )

    result = jobs.spawn_ingestion_worker(job["ingestion_id"])

    assert isinstance(result, subprocess.CompletedProcess)
    assert captured["cmd"][0] == "/usr/bin/systemd-run"
    assert "--property=CPUQuota=70%" in captured["cmd"]
    assert "--property=MemoryMax=2560M" in captured["cmd"]
    assert "--property=MemorySwapMax=512M" in captured["cmd"]
    assert "--property=IOWeight=100" in captured["cmd"]
    assert "--property=Nice=10" in captured["cmd"]
    assert "--property=TasksMax=128" in captured["cmd"]

    stored = jobs.get_ingestion_job(job["ingestion_id"])
    assert stored["resource_isolation_mode"] == "systemd_run"
    assert stored["resource_limits"]["MemoryMax"] == "2560M"
    assert stored["resource_limits"]["CPUQuota"] == "70%"
    assert stored["resource_limits"]["systemd_unit"].startswith("cvg-ingestion-")


def test_large_worker_falls_back_to_rlimit_when_systemd_missing(tmp_path, monkeypatch):
    from services import ingestion_job_service as jobs

    jobs_dir = tmp_path / "jobs"
    upload_path = tmp_path / "documents" / "default" / "uploads" / "large.pdf"
    upload_path.parent.mkdir(parents=True)
    upload_path.write_bytes(b"%PDF")
    captured: dict = {}

    monkeypatch.setattr(jobs, "INGESTION_JOBS_DIR", jobs_dir)
    monkeypatch.setattr(jobs.shutil, "which", lambda _name: None)

    class FakePopen:
        pid = 12345

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return FakePopen()

    monkeypatch.setattr(jobs.subprocess, "Popen", fake_popen)

    job = jobs.create_ingestion_job(
        source_path=upload_path,
        workspace_id="default",
        filename="large.pdf",
        source_type="pdf",
        chunking_strategy="recursive",
        file_size_bytes=410_562_000,
        preflight={"large_job": True, "resource_profile": "normal"},
    )

    result = jobs.spawn_ingestion_worker(job["ingestion_id"])

    assert result.pid == 12345
    assert captured["cmd"] == [sys.executable, "-m", "scripts.ingestion_worker", "--job-id", job["ingestion_id"]]
    assert captured["kwargs"]["env"]["INGESTION_WORKER_MEMORY_LIMIT_MB"] == "2560"

    stored = jobs.get_ingestion_job(job["ingestion_id"])
    assert stored["resource_isolation_mode"] == "rlimit_only"
    assert stored["resource_limits"]["rlimit_as_mb"] == 2560
    assert stored["resource_limits"]["fallback_reason"] == "systemd_run_unavailable"


def test_memory_error_aborts_job_and_cleans_upload(tmp_path, monkeypatch):
    from services import ingestion_job_service as jobs

    jobs_dir = tmp_path / "jobs"
    documents_dir = tmp_path / "documents"
    upload_path = documents_dir / "default" / "uploads" / "large.pdf"
    upload_path.parent.mkdir(parents=True)
    upload_path.write_bytes(b"%PDF")

    monkeypatch.setattr(jobs, "INGESTION_JOBS_DIR", jobs_dir)
    monkeypatch.setattr(jobs, "DOCUMENTS_DIR", documents_dir)

    job = jobs.create_ingestion_job(
        source_path=upload_path,
        workspace_id="default",
        filename="large.pdf",
        source_type="pdf",
        chunking_strategy="recursive",
        file_size_bytes=410_562_000,
        preflight={"large_job": True, "resource_profile": "normal"},
    )

    def fail_with_memory_error(*args, **kwargs):
        raise MemoryError("simulated memory pressure")

    aborted = jobs.run_ingestion_job(job["ingestion_id"], ingest_func=fail_with_memory_error)

    assert aborted["status"] == "aborted"
    assert aborted["error_code"] == "memory_limit_reached"
    assert "simulated memory pressure" in aborted["error_message"]
    assert not upload_path.exists()


def test_upload_large_pdf_returns_queued_job_without_ingesting(tmp_path, monkeypatch):
    import api.main as main
    from services import ingestion_job_service as jobs

    jobs_dir = tmp_path / "jobs"
    documents_dir = tmp_path / "documents"
    spawned: list[str] = []

    monkeypatch.setattr(main, "DOCUMENTS_DIR", documents_dir)
    monkeypatch.setattr(main, "MAX_UPLOAD_BYTES", 1024 * 1024)
    monkeypatch.setattr(main, "_require_permission", lambda *args, **kwargs: args[0])
    monkeypatch.setattr(main, "_require_workspace_access", lambda workspace_id, session: session)
    monkeypatch.setattr(jobs, "INGESTION_JOBS_DIR", jobs_dir)
    monkeypatch.setattr(jobs, "ASYNC_PDF_UPLOAD_ENABLED", True)
    monkeypatch.setattr(jobs, "ASYNC_PDF_MIN_BYTES", 1)
    monkeypatch.setattr(jobs, "spawn_ingestion_worker", lambda ingestion_id: spawned.append(ingestion_id))

    def fail_ingest(*args, **kwargs):
        raise AssertionError("heavy upload must not ingest in the request")

    monkeypatch.setattr("services.ingestion_service.ingest_document", fail_ingest)

    upload = UploadFile(filename="large.pdf", file=io.BytesIO(b"%PDF enough-to-queue"))
    response = asyncio.run(
        main.upload_document(
            file=upload,
            workspace_id="default",
            chunking_strategy="recursive",
            qdrant_collection="cvg_master_rag_alt",
            _session=_operator_session(),
        )
    )

    assert response.status == "queued"
    assert response.ingestion_id
    assert response.document_id == response.ingestion_id
    assert response.char_count == 0
    assert response.chunk_count == 0
    assert response.qdrant_collection == "cvg_master_rag_alt"
    assert spawned == [response.ingestion_id]

    job = jobs.get_ingestion_job(response.ingestion_id)
    assert job is not None
    assert job["status"] == "pending"
    assert job["qdrant_collection"] == "cvg_master_rag_alt"
    assert Path(job["source_path"]).exists()


def test_upload_small_file_records_visible_ingestion_job(tmp_path, monkeypatch):
    import api.main as main
    from services import ingestion_job_service as jobs

    jobs_dir = tmp_path / "jobs"
    documents_dir = tmp_path / "documents"
    captured_kwargs: dict = {}

    monkeypatch.setattr(main, "DOCUMENTS_DIR", documents_dir)
    monkeypatch.setattr(main, "MAX_UPLOAD_BYTES", 1024 * 1024)
    monkeypatch.setattr(main, "_require_permission", lambda *args, **kwargs: args[0])
    monkeypatch.setattr(main, "_require_workspace_access", lambda workspace_id, session: session)
    monkeypatch.setattr(jobs, "INGESTION_JOBS_DIR", jobs_dir)
    monkeypatch.setattr(jobs, "ASYNC_PDF_UPLOAD_ENABLED", False)

    def fake_ingest_document(path, workspace_id, filename, **kwargs):
        captured_kwargs.update(kwargs)
        return DocumentUploadResponse(
            document_id="doc-small",
            status="parsed",
            catalog_scope="operational",
            source_type="txt",
            filename=filename,
            page_count=1,
            char_count=12,
            chunk_count=2,
            created_at="2026-05-11T00:00:00Z",
            chunking_strategy=kwargs.get("chunking_strategy", "recursive"),
            qdrant_collection=kwargs.get("qdrant_collection"),
        )

    monkeypatch.setattr("services.ingestion_service.ingest_document", fake_ingest_document)

    upload = UploadFile(filename="small.txt", file=io.BytesIO(b"small upload"))
    response = asyncio.run(
        main.upload_document(
            file=upload,
            workspace_id="default",
            chunking_strategy="recursive",
            qdrant_collection="cvg_institucional",
            _session=_operator_session(),
        )
    )

    assert response.status == "parsed"
    assert response.ingestion_id
    assert response.document_id == "doc-small"
    assert response.chunk_count == 2
    assert response.qdrant_collection == "cvg_institucional"
    assert captured_kwargs["ingestion_id"] == response.ingestion_id
    assert captured_kwargs["qdrant_collection"] == "cvg_institucional"

    job = jobs.get_ingestion_job(response.ingestion_id)
    assert job is not None
    assert job["status"] == "committed"
    assert job["document_id"] == "doc-small"
    assert job["final_document_id"] == "doc-small"
    assert job["chunks_written"] == 2
    assert job["qdrant_points_written"] == 2
    assert job["qdrant_collection"] == "cvg_institucional"

    listed = jobs.list_ingestion_jobs(workspace_id="default", limit=1)
    assert listed[0]["ingestion_id"] == response.ingestion_id
    assert listed[0]["operational_status"] == "completed"
