"""
Ingestion job service.

Persists heavy upload work as JSON jobs so the web process can return quickly
and a separate worker process can own expensive parsing/indexing.
"""
import json
import os
import subprocess
import sys
import uuid
import inspect
import shutil
import shlex
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from core.config import BASE_DIR, DATA_DIR, DOCUMENTS_DIR, LOGS_DIR
from models.schemas import DocumentUploadResponse
from services.vector_service import delete_ingestion_points, validate_qdrant_collection_name


TRUE_VALUES = {"1", "true", "yes", "on"}
ASYNC_PDF_UPLOAD_ENABLED = os.getenv("INGESTION_ASYNC_PDF_ENABLED", "true").strip().lower() in TRUE_VALUES
ASYNC_PDF_MIN_BYTES = max(1, int(os.getenv("INGESTION_ASYNC_PDF_MIN_BYTES", str(5 * 1024 * 1024))))
LARGE_INGESTION_MIN_BYTES = max(1, int(os.getenv("LARGE_INGESTION_MIN_BYTES", str(50 * 1024 * 1024))))
MAX_CONCURRENT_LARGE_INGESTION_JOBS = max(1, int(os.getenv("MAX_CONCURRENT_LARGE_INGESTION_JOBS", "1")))
LARGE_INGESTION_DISK_FREE_MIN_BYTES = max(
    1,
    int(os.getenv("LARGE_INGESTION_DISK_FREE_MIN_BYTES", str(5 * 1024 * 1024 * 1024))),
)
LARGE_INGESTION_RESOURCE_PROFILE = os.getenv("LARGE_INGESTION_RESOURCE_PROFILE", "normal").strip() or "normal"
INGESTION_JOBS_DIR = DATA_DIR / "ingestion_jobs"
WORKER_MEMORY_LIMIT_MB = max(1, int(os.getenv("INGESTION_WORKER_MEMORY_LIMIT_MB", "2560") or "2560"))
INGESTION_STALE_BATCH_SECONDS = max(1, int(os.getenv("INGESTION_STALE_BATCH_SECONDS", "600") or "600"))
INGESTION_RSS_ALERT_MB = max(1, int(os.getenv("INGESTION_RSS_ALERT_MB", "2048") or "2048"))


RESOURCE_PROFILES = {
    "low": {
        "CPUQuota": "40%",
        "MemoryMax": "1536M",
        "MemorySwapMax": "512M",
        "IOWeight": "50",
        "Nice": "10",
        "TasksMax": "128",
        "rlimit_as_mb": 1536,
    },
    "normal": {
        "CPUQuota": "70%",
        "MemoryMax": f"{WORKER_MEMORY_LIMIT_MB}M",
        "MemorySwapMax": "512M",
        "IOWeight": "100",
        "Nice": "10",
        "TasksMax": "128",
        "rlimit_as_mb": WORKER_MEMORY_LIMIT_MB,
    },
    "night": {
        "CPUQuota": "120%",
        "MemoryMax": "4096M",
        "MemorySwapMax": "512M",
        "IOWeight": "200",
        "Nice": "10",
        "TasksMax": "128",
        "rlimit_as_mb": 4096,
    },
}


class IngestionPreflightError(Exception):
    """Raised when an upload cannot be safely queued for ingestion."""

    def __init__(self, error_code: str, message: str, *, status_code: int = 409, details: dict | None = None):
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_utc_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _elapsed_minutes(started_at: str | None, *, now: datetime | None = None) -> float | None:
    started = _parse_utc_timestamp(started_at)
    if started is None:
        return None
    now = now or datetime.now(timezone.utc)
    elapsed_seconds = max(0.0, (now - started).total_seconds())
    if elapsed_seconds <= 0:
        return None
    return elapsed_seconds / 60.0


def _calculate_throughput(job: dict, *, now: datetime | None = None) -> tuple[float | None, float | None]:
    elapsed = _elapsed_minutes(job.get("started_at"), now=now)
    if not elapsed:
        return None, None
    pages = int(job.get("pages_processed") or 0)
    chunks = int(job.get("chunks_written") or 0)
    return round(pages / elapsed, 2), round(chunks / elapsed, 2)


def _job_operational_alerts(job: dict, *, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    alerts: list[dict] = []
    status = job.get("status")
    rss_peak_mb = job.get("rss_peak_mb")
    if isinstance(rss_peak_mb, (int, float)) and rss_peak_mb >= INGESTION_RSS_ALERT_MB:
        alerts.append(
            {
                "code": "rss_high",
                "severity": "warning",
                "message": f"RSS peak {rss_peak_mb}MB exceeded {INGESTION_RSS_ALERT_MB}MB.",
            }
        )

    if status == "processing":
        last_batch = _parse_utc_timestamp(job.get("last_batch_at"))
        if last_batch is not None:
            seconds_since_batch = max(0.0, (now - last_batch).total_seconds())
            if seconds_since_batch >= INGESTION_STALE_BATCH_SECONDS:
                alerts.append(
                    {
                        "code": "job_stalled",
                        "severity": "critical",
                        "message": f"No batch progress for {int(seconds_since_batch // 60)} minutes.",
                    }
                )
        elif job.get("started_at"):
            started = _parse_utc_timestamp(job.get("started_at"))
            if started is not None:
                seconds_since_start = max(0.0, (now - started).total_seconds())
                if seconds_since_start >= INGESTION_STALE_BATCH_SECONDS:
                    alerts.append(
                        {
                            "code": "job_no_batch",
                            "severity": "critical",
                            "message": f"No batch recorded for {int(seconds_since_start // 60)} minutes.",
                        }
                    )

    if status in {"failed", "aborted"}:
        alerts.append(
            {
                "code": f"job_{status}",
                "severity": "critical",
                "message": job.get("error_message") or f"Ingestion job {status}.",
            }
        )
    return alerts


def _job_operational_status(job: dict, alerts: list[dict]) -> str:
    status = job.get("status")
    if status in {"committed"}:
        return "completed"
    if status in {"failed", "aborted"}:
        return "failed"
    if any(alert.get("severity") == "critical" for alert in alerts):
        return "stalled"
    if alerts:
        return "warning"
    if status == "processing":
        return "running"
    return "pending"


def summarize_ingestion_job(job: dict) -> dict:
    """Return a lightweight operator-facing job snapshot."""
    snapshot = dict(job)
    now = datetime.now(timezone.utc)
    pages_per_minute, chunks_per_minute = _calculate_throughput(snapshot, now=now)
    if pages_per_minute is not None:
        snapshot["pages_per_minute"] = pages_per_minute
    if chunks_per_minute is not None:
        snapshot["chunks_per_minute"] = chunks_per_minute

    last_batch = _parse_utc_timestamp(snapshot.get("last_batch_at"))
    if last_batch is not None:
        snapshot["seconds_since_last_batch"] = int(max(0.0, (now - last_batch).total_seconds()))
    else:
        snapshot["seconds_since_last_batch"] = None

    alerts = _job_operational_alerts(snapshot, now=now)
    snapshot["operational_alerts"] = alerts
    snapshot["operational_status"] = _job_operational_status(snapshot, alerts)
    return snapshot


def _job_path(ingestion_id: str) -> Path:
    return INGESTION_JOBS_DIR / f"{ingestion_id}.json"


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp_path.replace(path)


def should_queue_pdf_upload(file_path: Path, received_bytes: int) -> bool:
    return (
        ASYNC_PDF_UPLOAD_ENABLED
        and file_path.suffix.lower() == ".pdf"
        and received_bytes >= ASYNC_PDF_MIN_BYTES
    )


def is_large_ingestion(received_bytes: int) -> bool:
    return received_bytes >= LARGE_INGESTION_MIN_BYTES


def _iter_jobs() -> list[dict]:
    INGESTION_JOBS_DIR.mkdir(parents=True, exist_ok=True)
    jobs: list[dict] = []
    for path in sorted(INGESTION_JOBS_DIR.glob("*.json")):
        job = get_ingestion_job(path.stem)
        if job:
            jobs.append(job)
    return jobs


def active_large_ingestion_jobs(*, exclude_ingestion_id: str | None = None) -> list[dict]:
    active_statuses = {"pending", "processing"}
    return [
        job
        for job in _iter_jobs()
        if job.get("large_job")
        and job.get("status") in active_statuses
        and job.get("ingestion_id") != exclude_ingestion_id
    ]


def preflight_large_ingestion(
    *,
    source_path: Path,
    workspace_id: str,
    received_bytes: int,
) -> dict:
    """Validate local capacity before queueing a large ingestion job."""
    large_job = is_large_ingestion(received_bytes)
    disk = shutil.disk_usage(source_path.parent if source_path.parent.exists() else DOCUMENTS_DIR)
    required_free_bytes = max(LARGE_INGESTION_DISK_FREE_MIN_BYTES, received_bytes * 3)
    preflight = {
        "large_job": large_job,
        "file_size_bytes": received_bytes,
        "large_ingestion_min_bytes": LARGE_INGESTION_MIN_BYTES,
        "disk_free_bytes_at_start": disk.free,
        "disk_required_free_bytes": required_free_bytes,
        "resource_profile": LARGE_INGESTION_RESOURCE_PROFILE,
    }
    if not large_job:
        return preflight

    if disk.free < required_free_bytes:
        raise IngestionPreflightError(
            "insufficient_disk_space",
            "Espaco em disco insuficiente para iniciar indexacao grande.",
            status_code=507,
            details=preflight,
        )

    active_jobs = active_large_ingestion_jobs()
    if len(active_jobs) >= MAX_CONCURRENT_LARGE_INGESTION_JOBS:
        raise IngestionPreflightError(
            "large_ingestion_busy",
            "Ja existe uma indexacao grande em andamento.",
            status_code=409,
            details={
                **preflight,
                "active_large_ingestion_jobs": [job.get("ingestion_id") for job in active_jobs],
                "max_concurrent_large_ingestion_jobs": MAX_CONCURRENT_LARGE_INGESTION_JOBS,
            },
        )

    try:
        from services.vector_service import get_client

        get_client().get_collections()
    except Exception as exc:
        raise IngestionPreflightError(
            "qdrant_unavailable",
            "Qdrant indisponivel para iniciar indexacao grande.",
            status_code=503,
            details={**preflight, "qdrant_error": str(exc)},
        ) from exc

    return preflight


def create_ingestion_job(
    *,
    source_path: Path,
    workspace_id: str,
    filename: str,
    source_type: str,
    chunking_strategy: str,
    file_size_bytes: int | None = None,
    preflight: dict | None = None,
    qdrant_collection: str | None = None,
) -> dict:
    ingestion_id = str(uuid.uuid4())
    now = _utc_now()
    preflight = preflight or {}
    collection = validate_qdrant_collection_name(qdrant_collection)
    large_job = bool(preflight.get("large_job", is_large_ingestion(file_size_bytes or 0)))
    job = {
        "ingestion_id": ingestion_id,
        "document_id": ingestion_id,
        "final_document_id": None,
        "workspace_id": workspace_id,
        "filename": filename,
        "source_path": str(source_path),
        "source_type": source_type,
        "chunking_strategy": chunking_strategy,
        "qdrant_collection": collection,
        "file_size_bytes": file_size_bytes,
        "large_job": large_job,
        "resource_profile": preflight.get("resource_profile", LARGE_INGESTION_RESOURCE_PROFILE if large_job else None),
        "resource_isolation_mode": None,
        "resource_limits": {},
        "disk_free_bytes_at_start": preflight.get("disk_free_bytes_at_start"),
        "disk_required_free_bytes": preflight.get("disk_required_free_bytes"),
        "status": "pending",
        "page_count": None,
        "pages_processed": 0,
        "chunks_written": 0,
        "qdrant_points_written": 0,
        "rss_peak_mb": None,
        "last_heartbeat_at": None,
        "last_batch_at": None,
        "pages_per_minute": None,
        "chunks_per_minute": None,
        "operational_status": "pending",
        "operational_alerts": [],
        "created_at": now,
        "started_at": None,
        "finished_at": None,
        "error_code": None,
        "error_message": None,
        "worker_pid": None,
    }
    _atomic_write_json(_job_path(ingestion_id), job)
    return job


def get_ingestion_job(ingestion_id: str) -> Optional[dict]:
    path = _job_path(ingestion_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def update_ingestion_job(ingestion_id: str, **updates) -> dict:
    job = get_ingestion_job(ingestion_id)
    if job is None:
        raise FileNotFoundError(f"Ingestion job not found: {ingestion_id}")
    job.update(updates)
    _atomic_write_json(_job_path(ingestion_id), job)
    return job


def list_pending_jobs() -> list[dict]:
    return [job for job in _iter_jobs() if job.get("status") == "pending"]


def list_ingestion_jobs(*, workspace_id: str, limit: int = 10) -> list[dict]:
    jobs = [job for job in _iter_jobs() if job.get("workspace_id") == workspace_id]
    jobs.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return [summarize_ingestion_job(job) for job in jobs[: max(1, limit)]]


def get_ingestion_job_status(ingestion_id: str) -> Optional[dict]:
    job = get_ingestion_job(ingestion_id)
    if job is None:
        return None
    return summarize_ingestion_job(job)


def record_ingestion_heartbeat(ingestion_id: str, **updates) -> dict:
    now = _utc_now()
    updates.setdefault("last_heartbeat_at", now)
    job = update_ingestion_job(ingestion_id, **updates)
    pages_per_minute, chunks_per_minute = _calculate_throughput(job)
    derived_updates = {
        "operational_status": summarize_ingestion_job(job)["operational_status"],
        "operational_alerts": summarize_ingestion_job(job)["operational_alerts"],
    }
    if pages_per_minute is not None:
        derived_updates["pages_per_minute"] = pages_per_minute
    if chunks_per_minute is not None:
        derived_updates["chunks_per_minute"] = chunks_per_minute
    if derived_updates:
        job = update_ingestion_job(ingestion_id, **derived_updates)
    return job


def _cleanup_upload_source(source_path: Path) -> None:
    normalized = str(source_path).replace("\\", "/")
    if "/uploads/" not in normalized:
        return
    try:
        source_path.unlink(missing_ok=True)
    except Exception:
        pass


def cleanup_ingestion_artifacts(
    *,
    ingestion_id: str,
    workspace_id: str,
    source_path: Path | None = None,
    document_id: str | None = None,
    qdrant_collection: str | None = None,
) -> None:
    """Remove temporary disk artifacts and Qdrant staging points for a failed job."""
    doc_dir = DOCUMENTS_DIR / workspace_id
    try:
        delete_ingestion_points(
            ingestion_id,
            workspace_id=workspace_id,
            collection_name=qdrant_collection,
        )
    except Exception:
        pass

    patterns = [
        f"*{ingestion_id}*.tmp",
        f"*{ingestion_id}*.reindex_tmp",
        f"*{ingestion_id}*.restore_tmp",
    ]
    if document_id:
        patterns.extend(
            [
                f"{document_id}_raw.json.tmp",
                f"{document_id}_chunks.json.tmp",
                f"{document_id}_chunks.json.reindex_tmp",
                f"{document_id}_chunks.json.restore_tmp",
            ]
        )
    for pattern in patterns:
        try:
            for path in doc_dir.glob(pattern):
                path.unlink(missing_ok=True)
        except Exception:
            pass

    if source_path is not None:
        _cleanup_upload_source(source_path)


def _ingest_func_accepts_ingestion_id(ingest_func: Callable[..., DocumentUploadResponse]) -> bool:
    try:
        signature = inspect.signature(ingest_func)
    except (TypeError, ValueError):
        return True
    for param in signature.parameters.values():
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            return True
    return "ingestion_id" in signature.parameters


def _ingest_func_accepts_qdrant_collection(ingest_func: Callable[..., DocumentUploadResponse]) -> bool:
    try:
        signature = inspect.signature(ingest_func)
    except (TypeError, ValueError):
        return True
    for param in signature.parameters.values():
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            return True
    return "qdrant_collection" in signature.parameters


def run_ingestion_job(
    ingestion_id: str,
    *,
    ingest_func: Optional[Callable[..., DocumentUploadResponse]] = None,
) -> dict:
    job = get_ingestion_job(ingestion_id)
    if job is None:
        raise FileNotFoundError(f"Ingestion job not found: {ingestion_id}")
    if job.get("status") not in {"pending", "failed"}:
        return job

    job = update_ingestion_job(
        ingestion_id,
        status="processing",
        started_at=_utc_now(),
        last_heartbeat_at=_utc_now(),
        error_code=None,
        error_message=None,
        worker_pid=os.getpid(),
    )
    source_path = Path(job["source_path"])

    try:
        if ingest_func is None:
            from services.ingestion_service import ingest_document as ingest_func

        kwargs = {"chunking_strategy": job.get("chunking_strategy") or "recursive"}
        if _ingest_func_accepts_ingestion_id(ingest_func):
            kwargs["ingestion_id"] = ingestion_id
        if _ingest_func_accepts_qdrant_collection(ingest_func):
            kwargs["qdrant_collection"] = job.get("qdrant_collection")
        result = ingest_func(source_path, job["workspace_id"], job["filename"], **kwargs)
        committed = update_ingestion_job(
            ingestion_id,
            status="committed",
            document_id=result.document_id,
            final_document_id=result.document_id,
            page_count=result.page_count,
            pages_processed=result.page_count or 0,
            chunks_written=result.chunk_count,
            qdrant_points_written=result.chunk_count,
            finished_at=_utc_now(),
            last_heartbeat_at=_utc_now(),
            operational_status="completed",
            operational_alerts=[],
            error_code=None,
            error_message=None,
        )
        _cleanup_upload_source(source_path)
        return committed
    except MemoryError as e:
        cleanup_ingestion_artifacts(
            ingestion_id=ingestion_id,
            workspace_id=job["workspace_id"],
            source_path=source_path,
            document_id=job.get("document_id"),
            qdrant_collection=job.get("qdrant_collection"),
        )
        failed = update_ingestion_job(
            ingestion_id,
            status="aborted",
            finished_at=_utc_now(),
            last_heartbeat_at=_utc_now(),
            operational_status="failed",
            error_code="memory_limit_reached",
            error_message=str(e) or "Worker memory limit reached",
        )
        return failed
    except Exception as e:
        cleanup_ingestion_artifacts(
            ingestion_id=ingestion_id,
            workspace_id=job["workspace_id"],
            source_path=source_path,
            document_id=job.get("document_id"),
            qdrant_collection=job.get("qdrant_collection"),
        )
        failed = update_ingestion_job(
            ingestion_id,
            status="failed",
            finished_at=_utc_now(),
            last_heartbeat_at=_utc_now(),
            operational_status="failed",
            error_code=e.__class__.__name__,
            error_message=str(e),
        )
        return failed


def run_next_pending_job() -> Optional[dict]:
    jobs = list_pending_jobs()
    if not jobs:
        return None
    return run_ingestion_job(jobs[0]["ingestion_id"])


def _resource_limits_for_profile(profile_name: str | None) -> dict:
    profile = (profile_name or LARGE_INGESTION_RESOURCE_PROFILE or "normal").strip().lower()
    limits = RESOURCE_PROFILES.get(profile, RESOURCE_PROFILES["normal"]).copy()
    limits["profile"] = profile if profile in RESOURCE_PROFILES else "normal"
    return limits


def _systemd_unit_name(ingestion_id: str) -> str:
    safe_id = "".join(ch if ch.isalnum() or ch == "-" else "-" for ch in ingestion_id)
    return f"cvg-ingestion-{safe_id[:48]}"


def _worker_command(ingestion_id: str) -> list[str]:
    return [sys.executable, "-m", "scripts.ingestion_worker", "--job-id", ingestion_id]


def _worker_env(limits: dict) -> dict:
    env = os.environ.copy()
    env["INGESTION_WORKER_MEMORY_LIMIT_MB"] = str(limits["rlimit_as_mb"])
    return env


def _spawn_worker_with_popen(
    *,
    ingestion_id: str,
    limits: dict,
    mode: str,
    fallback_reason: str | None = None,
) -> subprocess.Popen:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / "ingestion_worker.log"
    resource_limits = limits.copy()
    if fallback_reason:
        resource_limits["fallback_reason"] = fallback_reason
    update_ingestion_job(
        ingestion_id,
        resource_isolation_mode=mode,
        resource_limits=resource_limits,
    )
    with open(log_path, "ab") as log_file:
        return subprocess.Popen(
            _worker_command(ingestion_id),
            cwd=str(BASE_DIR),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            close_fds=True,
            env=_worker_env(limits),
        )


def _spawn_worker_with_systemd_run(
    *,
    ingestion_id: str,
    systemd_run_path: str,
    limits: dict,
) -> subprocess.CompletedProcess:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / "ingestion_worker.log"
    unit_name = _systemd_unit_name(ingestion_id)
    env_path = BASE_DIR / ".env"
    shell_command = (
        f"set -a; "
        f"[ -f {shlex.quote(str(env_path))} ] && . {shlex.quote(str(env_path))}; "
        f"export INGESTION_WORKER_MEMORY_LIMIT_MB={shlex.quote(str(limits['rlimit_as_mb']))}; "
        f"exec {shlex.quote(sys.executable)} -m scripts.ingestion_worker --job-id {shlex.quote(ingestion_id)}"
    )
    cmd = [
        systemd_run_path,
        f"--unit={unit_name}",
        "--collect",
        f"--working-directory={BASE_DIR}",
        f"--property=CPUQuota={limits['CPUQuota']}",
        f"--property=MemoryMax={limits['MemoryMax']}",
        f"--property=MemorySwapMax={limits['MemorySwapMax']}",
        f"--property=IOWeight={limits['IOWeight']}",
        f"--property=Nice={limits['Nice']}",
        f"--property=TasksMax={limits['TasksMax']}",
        f"--property=StandardOutput=append:{log_path}",
        f"--property=StandardError=append:{log_path}",
        "/bin/bash",
        "-lc",
        shell_command,
    ]
    resource_limits = {**limits, "systemd_unit": unit_name}
    update_ingestion_job(
        ingestion_id,
        resource_isolation_mode="systemd_run",
        resource_limits=resource_limits,
    )
    with open(log_path, "ab") as log_file:
        return subprocess.run(
            cmd,
            cwd=str(BASE_DIR),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            close_fds=True,
            check=True,
        )


def spawn_ingestion_worker(ingestion_id: str):
    job = get_ingestion_job(ingestion_id)
    if job is None:
        raise FileNotFoundError(f"Ingestion job not found: {ingestion_id}")

    limits = _resource_limits_for_profile(job.get("resource_profile"))
    if job.get("large_job"):
        systemd_run_path = shutil.which("systemd-run")
        if systemd_run_path:
            try:
                return _spawn_worker_with_systemd_run(
                    ingestion_id=ingestion_id,
                    systemd_run_path=systemd_run_path,
                    limits=limits,
                )
            except Exception:
                return _spawn_worker_with_popen(
                    ingestion_id=ingestion_id,
                    limits=limits,
                    mode="rlimit_only",
                    fallback_reason="systemd_run_failed",
                )
        return _spawn_worker_with_popen(
            ingestion_id=ingestion_id,
            limits=limits,
            mode="rlimit_only",
            fallback_reason="systemd_run_unavailable",
        )

    return _spawn_worker_with_popen(
        ingestion_id=ingestion_id,
        limits=limits,
        mode="subprocess",
    )
