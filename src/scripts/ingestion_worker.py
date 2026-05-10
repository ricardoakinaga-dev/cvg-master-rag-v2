"""
Isolated ingestion worker.

Runs heavy ingestion jobs outside the Uvicorn request process. This keeps API
health independent from PDF parsing/indexing failures.
"""
import argparse
import os
import signal
import sys


def _apply_memory_limit() -> None:
    limit_mb = int(os.getenv("INGESTION_WORKER_MEMORY_LIMIT_MB", "0") or "0")
    if limit_mb <= 0:
        return
    try:
        import resource
    except Exception:
        return
    limit_bytes = limit_mb * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (limit_bytes, limit_bytes))


def _apply_timeout() -> None:
    timeout_seconds = int(os.getenv("INGESTION_JOB_TIMEOUT_SECONDS", "0") or "0")
    if timeout_seconds <= 0:
        return

    def _timeout_handler(_signum, _frame):
        raise TimeoutError(f"Ingestion job exceeded timeout of {timeout_seconds}s")

    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(timeout_seconds)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run isolated ingestion jobs")
    parser.add_argument("--job-id", help="Run one specific ingestion job")
    parser.add_argument("--once", action="store_true", help="Run one pending job and exit")
    args = parser.parse_args()

    _apply_memory_limit()
    _apply_timeout()

    from services.ingestion_job_service import run_ingestion_job, run_next_pending_job

    try:
        if args.job_id:
            result = run_ingestion_job(args.job_id)
        elif args.once:
            result = run_next_pending_job()
        else:
            parser.error("use --job-id or --once")
            return 2
    except Exception as e:
        print(f"ingestion_worker_error: {e}", file=sys.stderr)
        return 1

    if not result:
        return 0
    return 0 if result.get("status") == "committed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
