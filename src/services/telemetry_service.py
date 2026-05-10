"""
Telemetry Service — logs, metrics aggregation, and evaluation tracking.
Implements structured JSON Lines logging and daily metric aggregation.
"""
import json
import shutil
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
from collections import defaultdict

from core.config import LOGS_DIR
from services.request_context import get_request_id
from telemetry.tracing import get_trace_id


class TelemetryService:
    """
    Centralized telemetry for RAG pipeline.
    - Logs every query to JSON Lines file
    - Aggregates metrics on demand
    - Tracks retrieval quality over time
    """

    QUERIES_LOG = LOGS_DIR / "queries.jsonl"
    INGEST_LOG = LOGS_DIR / "ingestion.jsonl"
    INGEST_BATCH_LOG = LOGS_DIR / "ingestion_batches.jsonl"
    REINDEX_LOG = LOGS_DIR / "reindex.jsonl"
    EVAL_LOG = LOGS_DIR / "evaluations.jsonl"
    AUDIT_LOG = LOGS_DIR / "audit.jsonl"
    REPAIR_LOG = LOGS_DIR / "repair.jsonl"
    CLINICAL_PLANNER_LOG = LOGS_DIR / "clinical_planner.jsonl"

    def __init__(self):
        self._ensure_logs()

    def _ensure_logs(self):
        """Ensure log directory and files exist."""
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        for log_file in [
            self.QUERIES_LOG,
            self.INGEST_LOG,
            self.INGEST_BATCH_LOG,
            self.REINDEX_LOG,
            self.EVAL_LOG,
            self.AUDIT_LOG,
            self.REPAIR_LOG,
            self.CLINICAL_PLANNER_LOG,
        ]:
            if not log_file.exists():
                log_file.write_text("")

    # ── Query Logging ───────────────────────────────────────────

    def log_query(
        self,
        query: str,
        workspace_id: str,
        answer: str,
        confidence: str,
        grounded: bool,
        chunks_used: list[dict],
        retrieval_time_ms: int,
        total_latency_ms: int,
        low_confidence: bool,
        results_count: int,
        citation_coverage: float = 0.0,
        top_result_score: Optional[float] = None,
        threshold: Optional[float] = None,
        hit: Optional[bool] = None,
        grounding_reason: Optional[str] = None,
        uncited_claims_count: int = 0,
        needs_review: Optional[bool] = None,
        request_id: Optional[str] = None,
        reranking_applied: bool = False,
        reranking_method: Optional[str] = None,
        candidate_count: Optional[int] = None,
        query_expansion_applied: bool = False,
        query_expansion_method: Optional[str] = None,
        query_expansion_fallback: bool = False,
        query_expansion_requested: bool = False,
        expansion_latency_ms: int = 0,
        query_expansion_mode: Optional[str] = None,
        query_expansion_decision_reason: Optional[str] = None,
        retrieval_profile: Optional[str] = None,
        detected_language: Optional[str] = None,
        translation_applied: Optional[bool] = None,
        translation_blocked: Optional[bool] = None,
        translation_blocked_reason: Optional[str] = None,
        translated_query_hash: Optional[str] = None,
    ):
        """
        Log a single query event to queries.jsonl.
        """
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "query",
            "request_id": request_id or get_request_id(),
            "trace_id": get_trace_id(),
            "workspace_id": workspace_id,
            "query": query,
            "answer": answer[:500] if answer else "",
            "confidence": confidence,
            "grounded": grounded,
            "low_confidence": low_confidence,
            "chunks_used_count": len(chunks_used),
            "chunk_ids": [c["chunk_id"] if isinstance(c, dict) else str(c) for c in chunks_used],
            "retrieval_time_ms": retrieval_time_ms,
            "total_latency_ms": total_latency_ms,
            "results_count": results_count,
            "citation_coverage": citation_coverage,
            "top_result_score": top_result_score,
            "threshold": threshold,
            "hit": hit,  # Optional: set by evaluation runner
            "grounding_reason": grounding_reason,
            "uncited_claims_count": uncited_claims_count,
            "needs_review": needs_review,
            "reranking_applied": reranking_applied,
            "reranking_method": reranking_method,
            "candidate_count": candidate_count,
            "query_expansion_applied": query_expansion_applied,
            "query_expansion_method": query_expansion_method,
            "query_expansion_fallback": query_expansion_fallback,
            "query_expansion_requested": query_expansion_requested,
            "expansion_latency_ms": expansion_latency_ms,
            "query_expansion_mode": query_expansion_mode,
            "query_expansion_decision_reason": query_expansion_decision_reason,
            "retrieval_profile": retrieval_profile,
            "detected_language": detected_language,
            "translation_applied": translation_applied,
            "translation_blocked": translation_blocked,
            "translation_blocked_reason": translation_blocked_reason,
            "translated_query_hash": translated_query_hash,
        }
        self._append(self.QUERIES_LOG, event)

    def log_ingestion(
        self,
        document_id: str,
        workspace_id: str,
        source_type: str,
        filename: str,
        status: str,
        chunk_count: int,
        processing_time_ms: int,
        error: Optional[str] = None,
        request_id: Optional[str] = None,
        embedding_status: Optional[str] = None,
    ):
        """Log a single ingestion event."""
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "ingestion",
            "request_id": request_id or get_request_id(),
            "trace_id": get_trace_id(),
            "document_id": document_id,
            "workspace_id": workspace_id,
            "source_type": source_type,
            "filename": filename,
            "status": status,
            "chunk_count": chunk_count,
            "processing_time_ms": processing_time_ms,
            "error": error,
        }
        if embedding_status is not None:
            event["embedding_status"] = embedding_status
        self._append(self.INGEST_LOG, event)

    def log_clinical_query_plan(
        self,
        *,
        original_query: str,
        detected_language: str,
        species: Optional[str],
        clinical_problem: Optional[str],
        organ_system: Optional[str],
        intent: str,
        canonical_terms_pt: list[str],
        canonical_terms_en: list[str],
        synonyms: list[str],
        required_terms: list[str],
        low_signal_terms: list[str],
        desired_sections: list[str],
        query_variants: list,
        scope_warning: Optional[str],
        planner_notes: Optional[str],
        answers_user: bool,
        generated_by: str,
        latency_ms: int,
        validation_status: str,
        validation_error: Optional[str] = None,
        fallback_reason: Optional[str] = None,
        request_id: Optional[str] = None,
    ):
        """Log a safe, auditable clinical planner event without raw user text."""
        variants = [self._safe_variant_snapshot(variant) for variant in query_variants]
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "clinical_query_plan",
            "request_id": request_id or get_request_id(),
            "trace_id": get_trace_id(),
            "query_hash": self._hash_text(original_query),
            "query_length": len(original_query or ""),
            "detected_language": detected_language,
            "species": species,
            "clinical_problem": clinical_problem,
            "organ_system": organ_system,
            "intent": intent,
            "canonical_terms_pt": canonical_terms_pt,
            "canonical_terms_en": canonical_terms_en,
            "synonyms": synonyms,
            "required_terms": required_terms,
            "low_signal_terms": low_signal_terms,
            "desired_sections": desired_sections,
            "variant_count": len(variants),
            "variant_types": [variant["variant_type"] for variant in variants],
            "variant_hashes": [variant["query_hash"] for variant in variants],
            "variants": variants,
            "scope_warning": scope_warning,
            "planner_notes": planner_notes,
            "answers_user": answers_user,
            "generated_by": generated_by,
            "latency_ms": latency_ms,
            "validation_status": validation_status,
            "validation_error": validation_error,
            "fallback_reason": fallback_reason,
        }
        self._append(self.CLINICAL_PLANNER_LOG, event)

    def log_ingestion_batch(
        self,
        *,
        ingestion_id: Optional[str],
        document_id: str,
        workspace_id: str,
        filename: str,
        batch_index: int,
        page_start: Optional[int],
        page_end: Optional[int],
        chars_extracted: int,
        chunks_created: int,
        embeddings_created: int,
        points_indexed: int,
        rss_mb: Optional[float],
        rss_peak_mb: Optional[float],
        duration_ms: int,
        status: str,
        error: Optional[str] = None,
    ):
        """Log per-batch ingestion progress for large documents."""
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "ingestion_batch",
            "request_id": get_request_id(),
            "trace_id": get_trace_id(),
            "ingestion_id": ingestion_id,
            "document_id": document_id,
            "workspace_id": workspace_id,
            "filename": filename,
            "batch_index": batch_index,
            "page_start": page_start,
            "page_end": page_end,
            "chars_extracted": chars_extracted,
            "chunks_created": chunks_created,
            "embeddings_created": embeddings_created,
            "points_indexed": points_indexed,
            "rss_mb": rss_mb,
            "rss_peak_mb": rss_peak_mb,
            "duration_ms": duration_ms,
            "status": status,
            "error": error,
        }
        self._append(self.INGEST_BATCH_LOG, event)

    def log_reindex(
        self,
        document_id: str,
        workspace_id: str,
        chunking_strategy: str,
        chunk_count: int,
        processing_time_ms: int,
        embedding_status: str = "original",
        source: str = "reindex",
        request_id: Optional[str] = None,
    ):
        """
        Log a reindex or chunking-ab restore event.

        source values:
          "reindex" — manual reindex via API
          "chunking_ab_restore" — automatic restore after chunking A/B evaluation
          "chunking_ab_baseline" — baseline evaluation setup (recursive)
          "chunking_ab_variant" — variant evaluation setup (semantic)
        """
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "reindex",
            "request_id": request_id or get_request_id(),
            "trace_id": get_trace_id(),
            "document_id": document_id,
            "workspace_id": workspace_id,
            "chunking_strategy": chunking_strategy,
            "chunk_count": chunk_count,
            "processing_time_ms": processing_time_ms,
            "embedding_status": embedding_status,
            "source": source,
        }
        self._append(self.REINDEX_LOG, event)

    def log_audit(
        self,
        workspace_id: str,
        total_documents: int,
        total_with_issues: int,
        total_ok: int,
        by_issue_type: dict[str, int],
        recommendations: list[str],
        request_id: Optional[str] = None,
    ):
        """Log a corpus audit event."""
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "audit",
            "request_id": request_id or get_request_id(),
            "trace_id": get_trace_id(),
            "workspace_id": workspace_id,
            "total_documents": total_documents,
            "total_with_issues": total_with_issues,
            "total_ok": total_ok,
            "by_issue_type": by_issue_type,
            "recommendations": recommendations,
        }
        self._append(self.AUDIT_LOG, event)

    def log_repair(
        self,
        document_id: str,
        workspace_id: str,
        success: bool,
        chunks_reindexed: int,
        embeddings_valid: bool,
        qdrant_restored: bool,
        message: str,
        request_id: Optional[str] = None,
    ):
        """Log a repair event."""
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "repair",
            "request_id": request_id or get_request_id(),
            "trace_id": get_trace_id(),
            "document_id": document_id,
            "workspace_id": workspace_id,
            "success": success,
            "chunks_reindexed": chunks_reindexed,
            "embeddings_valid": embeddings_valid,
            "qdrant_restored": qdrant_restored,
            "message": message,
        }
        self._append(self.REPAIR_LOG, event)

    def log_evaluation(
        self,
        evaluation_id: str,
        workspace_id: str,
        total_questions: int,
        hit_at_1: float,
        hit_at_3: float,
        hit_at_5: float,
        avg_latency_ms: float,
        avg_score: float,
        low_confidence_rate: float,
        groundedness_rate: float,
        duration_seconds: float,
        request_id: Optional[str] = None,
        reranking_applied: bool = False,
        reranking_method: Optional[str] = None,
        embedding_status: Optional[str] = None,
    ):
        """Log a completed evaluation run."""
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "evaluation",
            "request_id": request_id or get_request_id(),
            "trace_id": get_trace_id(),
            "evaluation_id": evaluation_id,
            "workspace_id": workspace_id,
            "total_questions": total_questions,
            "hit_at_1": round(hit_at_1, 4),
            "hit_at_3": round(hit_at_3, 4),
            "hit_at_5": round(hit_at_5, 4),
            "avg_latency_ms": round(avg_latency_ms, 1),
            "avg_score": round(avg_score, 4),
            "low_confidence_rate": round(low_confidence_rate, 4),
            "groundedness_rate": round(groundedness_rate, 4),
            "duration_seconds": round(duration_seconds, 2),
            "reranking_applied": reranking_applied,
            "reranking_method": reranking_method,
        }
        if embedding_status is not None:
            event["embedding_status"] = embedding_status
        self._append(self.EVAL_LOG, event)

    # ── Metrics Aggregation ──────────────────────────────────────

    def get_metrics(self, days: int = 7, workspace_id: Optional[str] = None) -> dict:
        """
        Aggregate metrics from logs over the last N days.
        Returns a dict with retrieval, ingestion, and answer metrics.
        """
        cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)

        queries = self._filter_workspace(self._read_log(self.QUERIES_LOG, cutoff), workspace_id)
        ingestion_events = self._filter_workspace(self._read_log(self.INGEST_LOG, cutoff), workspace_id)
        ingestion_batch_events = self._filter_workspace(self._read_log(self.INGEST_BATCH_LOG, cutoff), workspace_id)
        evaluation_events = self._filter_workspace(self._read_log(self.EVAL_LOG, cutoff), workspace_id)

        retrieval_metrics = self._aggregate_retrieval(queries, evaluation_events)
        ingestion_metrics = self._aggregate_ingestion(ingestion_events)
        answer_metrics = self._aggregate_answers(queries, evaluation_events)
        evaluation_metrics = self._aggregate_evaluations(evaluation_events)
        chunking_metrics = self.get_chunking_metrics(days=days, workspace_id=workspace_id)
        expansion_metrics = self._aggregate_query_expansion(queries)

        return {
            "retrieval": retrieval_metrics,
            "ingestion": ingestion_metrics,
            "ingestion_batches": self._aggregate_ingestion_batches(ingestion_batch_events),
            "answer": answer_metrics,
            "evaluation": evaluation_metrics,
            "chunking": chunking_metrics,
            "query_expansion": expansion_metrics,
            "period_days": days,
            "workspace_id": workspace_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_operational_snapshot(self, days: int = 1, workspace_id: Optional[str] = None) -> dict:
        """
        Return a compact operational snapshot for health checks and dashboards.
        """
        cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)
        queries = self._filter_workspace(self._read_log(self.QUERIES_LOG, cutoff), workspace_id)
        ingestion_events = self._filter_workspace(self._read_log(self.INGEST_LOG, cutoff), workspace_id)
        ingestion_batch_events = self._filter_workspace(self._read_log(self.INGEST_BATCH_LOG, cutoff), workspace_id)
        evaluation_events = self._filter_workspace(self._read_log(self.EVAL_LOG, cutoff), workspace_id)

        def _latest_timestamp(events: list[dict]) -> Optional[str]:
            timestamps = [event.get("timestamp") for event in events if event.get("timestamp")]
            return max(timestamps) if timestamps else None

        return {
            "period_days": days,
            "workspace_id": workspace_id,
            "window_start": datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat(),
            "queries": {
                "count": len(queries),
                "low_confidence": sum(1 for q in queries if q.get("low_confidence")),
                "needs_review": sum(1 for q in queries if q.get("needs_review")),
                "latest_timestamp": _latest_timestamp(queries),
            },
            "ingestion": {
                "count": len(ingestion_events),
                "errors": sum(1 for e in ingestion_events if e.get("status") == "error"),
                "latest_timestamp": _latest_timestamp(ingestion_events),
            },
            "ingestion_batches": {
                "count": len(ingestion_batch_events),
                "errors": sum(1 for e in ingestion_batch_events if e.get("status") not in {"success", "partial"}),
                "latest_timestamp": _latest_timestamp(ingestion_batch_events),
                "rss_peak_mb": max(
                    (float(e.get("rss_peak_mb") or 0.0) for e in ingestion_batch_events),
                    default=0.0,
                ),
                "latest_ingestion_id": (
                    ingestion_batch_events[-1].get("ingestion_id") if ingestion_batch_events else None
                ),
            },
            "evaluation": {
                "count": len(evaluation_events),
                "latest_timestamp": _latest_timestamp(evaluation_events),
            },
        }

    def get_alerts(self, days: int = 1, workspace_id: Optional[str] = None) -> dict:
        """Evaluate operational alerts from telemetry and local runtime state."""
        metrics = self.get_metrics(days=days, workspace_id=workspace_id)
        retrieval = metrics["retrieval"]
        ingestion = metrics["ingestion"]
        answer = metrics["answer"]
        window = f"{days}d"
        operational_retention = None

        qdrant_ok = True
        try:
            from services.vector_service import get_client
            get_client().get_collections()
        except Exception:
            qdrant_ok = False

        if workspace_id:
            try:
                from services.operational_retention_service import summarize_operational_retention

                operational_retention = summarize_operational_retention(workspace_id)
            except Exception:
                operational_retention = None

        disk = shutil.disk_usage(LOGS_DIR)
        disk_usage_ratio = round(disk.used / disk.total, 4) if disk.total else 0.0
        ingestion_error_rate = round(
            ingestion["errors"] / ingestion["total_documents_processed"],
            4,
        ) if ingestion["total_documents_processed"] > 0 else 0.0

        alert_specs = [
            {
                "name": "vector_store_unavailable",
                "severity": "critical",
                "status": "firing" if not qdrant_ok else "ok",
                "message": "Qdrant indisponível para queries e reparos." if not qdrant_ok else "Qdrant acessível.",
                "window": window,
                "value": "error" if not qdrant_ok else "ok",
                "threshold": "ok",
            },
            {
                "name": "high_latency_p99",
                "severity": "critical",
                "status": "firing" if retrieval["p99_latency_ms"] > 5000 else "ok",
                "message": f"Latência p99 em {retrieval['p99_latency_ms']} ms.",
                "window": window,
                "value": retrieval["p99_latency_ms"],
                "threshold": 5000,
            },
            {
                "name": "high_ingestion_error_rate",
                "severity": "critical",
                "status": "firing" if ingestion_error_rate > 0.05 else "ok",
                "message": f"Taxa de erro de ingestão em {round(ingestion_error_rate * 100, 1)}%.",
                "window": window,
                "value": ingestion_error_rate,
                "threshold": 0.05,
            },
            {
                "name": "low_hit_rate_top5",
                "severity": "high",
                "status": "firing" if retrieval["total_queries"] > 0 and retrieval["hit_rate_top5"] < 0.50 else "ok",
                "message": f"Hit@5 em {round(retrieval['hit_rate_top5'] * 100, 1)}%.",
                "window": window,
                "value": retrieval["hit_rate_top5"],
                "threshold": 0.50,
            },
            {
                "name": "high_no_context_rate",
                "severity": "high",
                "status": "firing" if answer["total_queries"] > 0 and answer["no_context_rate"] > 0.20 else "ok",
                "message": f"Respostas sem contexto em {round(answer['no_context_rate'] * 100, 1)}%.",
                "window": window,
                "value": answer["no_context_rate"],
                "threshold": 0.20,
            },
            {
                "name": "disk_usage_high",
                "severity": "medium",
                "status": "firing" if disk_usage_ratio > 0.80 else "ok",
                "message": f"Uso de disco em {round(disk_usage_ratio * 100, 1)}%.",
                "window": window,
                "value": disk_usage_ratio,
                "threshold": 0.80,
            },
        ]

        if workspace_id:
            eligible_documents = operational_retention.eligible_documents if operational_retention else 0
            oldest = operational_retention.oldest_eligible_created_at if operational_retention else None
            retention_hours = operational_retention.retention_hours if operational_retention else None
            message = (
                f"{eligible_documents} uploads operacionais vencidos aguardam cleanup."
                if eligible_documents > 0
                else "Nenhum upload operacional vencido aguardando cleanup."
            )
            if oldest:
                message = f"{message} Mais antigo em {oldest}."
            alert_specs.append(
                {
                    "name": "operational_cleanup_backlog",
                    "severity": "high",
                    "status": "firing" if eligible_documents > 0 else "ok",
                    "message": message,
                    "window": window,
                    "value": eligible_documents,
                    "threshold": 0 if retention_hours is not None else None,
                }
            )

        return {
            "items": alert_specs,
            "total_active": sum(1 for item in alert_specs if item["status"] == "firing"),
            "workspace_id": workspace_id,
            "period_days": days,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_chunking_metrics(self, days: int = 30, workspace_id: Optional[str] = None) -> dict:
        """
        Aggregate reindex/chunking metrics from reindex.jsonl over the last N days.

        Returns two logical sections:
        - "historical": event-based metrics from the reindex log (operations, not corpus state)
        - "current_corpus": actual document counts per strategy from the on-disk registry

        Within "historical.by_strategy", "operation_count" (not "document_count") is used
        to make it clear this is a count of reindex events, not unique documents.
        """
        cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)
        reindex_events = self._filter_workspace(
            self._read_log(self.REINDEX_LOG, cutoff), workspace_id
        )

        if not reindex_events:
            empty = self._empty_chunking_metrics(days, workspace_id)
            # Still include current corpus state even when no historical events
            empty["current_corpus"] = self._get_current_corpus_chunking_state(workspace_id)
            return empty

        # Group by strategy (for historical event-based metrics)
        by_strategy: dict[str, list[dict]] = defaultdict(list)
        for event in reindex_events:
            strat = event.get("chunking_strategy", "unknown")
            by_strategy[strat].append(event)

        strategies = {}
        for strat, events in sorted(by_strategy.items()):
            chunk_counts = [e.get("chunk_count", 0) for e in events]
            latencies = [e.get("processing_time_ms", 0) for e in events]
            degraded = sum(
                1 for e in events
                if e.get("embedding_status") == "degraded_zero_fallback"
            )
            strategies[strat] = {
                "operation_count": len(events),
                "avg_chunk_count": round(sum(chunk_counts) / len(chunk_counts), 1) if chunk_counts else 0.0,
                "avg_processing_time_ms": round(sum(latencies) / len(latencies), 1) if latencies else 0.0,
                "degraded_zero_fallback_count": degraded,
            }

        # Source breakdown (count of events per source)
        by_source: dict[str, int] = defaultdict(int)
        for event in reindex_events:
            src = event.get("source", "unknown")
            by_source[src] = by_source.get(src, 0) + 1

        # Unique documents: deduplicate by document_id (a document may be reindexed multiple times)
        seen_docs: set[str] = set()
        for e in reindex_events:
            seen_docs.add(e.get("document_id"))

        total_degraded = sum(1 for e in reindex_events if e.get("embedding_status") == "degraded_zero_fallback")

        return {
            "period_days": days,
            "workspace_id": workspace_id,
            "total_reindex_operations": len(reindex_events),
            "unique_documents_reindexed": len(seen_docs),
            "total_degraded_zero_fallback": total_degraded,
            "historical": {
                "by_strategy": strategies,
                "by_source": dict(by_source),
            },
            "current_corpus": self._get_current_corpus_chunking_state(workspace_id),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _get_current_corpus_chunking_state(self, workspace_id: Optional[str]) -> dict:
        """
        Read the on-disk document registry and count unique documents per chunking strategy.
        This reflects the actual current state of the corpus, not historical events.
        """
        try:
            from services.document_registry import get_document_registry
            registry = get_document_registry(workspace_id or "default")
        except Exception:
            return {"available": False, "by_strategy": {}}

        by_strategy: dict[str, int] = defaultdict(int)
        for doc in registry.values():
            strat = doc.get("chunking_strategy", "recursive")
            by_strategy[strat] += 1

        return {
            "available": True,
            "total_documents": len(registry),
            "by_strategy": dict(by_strategy),
        }

    def _empty_chunking_metrics(self, days: int, workspace_id: Optional[str]) -> dict:
        return {
            "period_days": days,
            "workspace_id": workspace_id,
            "total_reindex_operations": 0,
            "unique_documents_reindexed": 0,
            "total_degraded_zero_fallback": 0,
            "historical": {
                "by_strategy": {},
                "by_source": {},
            },
            "current_corpus": {"available": False, "by_strategy": {}},
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def list_queries(
        self,
        workspace_id: str = "default",
        limit: int = 50,
        offset: int = 0,
        low_confidence: Optional[bool] = None,
        needs_review: Optional[bool] = None,
        grounded: Optional[bool] = None,
        min_citation_coverage: Optional[float] = None,
    ) -> dict:
        """Return a paginated, filterable view of query logs."""
        events = self._read_log(self.QUERIES_LOG, 0)
        items = [self._normalize_query_event(e) for e in events if e.get("workspace_id", "default") == workspace_id]

        if low_confidence is not None:
            items = [e for e in items if bool(e.get("low_confidence")) is low_confidence]
        if needs_review is not None:
            items = [e for e in items if bool(e.get("needs_review")) is needs_review]
        if grounded is not None:
            items = [e for e in items if bool(e.get("grounded")) is grounded]
        if min_citation_coverage is not None:
            items = [
                e for e in items
                if float(e.get("citation_coverage", 0.0) or 0.0) >= min_citation_coverage
            ]

        items.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
        total = len(items)
        sliced = items[offset: offset + limit]
        return {
            "items": sliced,
            "total": total,
            "limit": limit,
            "offset": offset,
            "workspace_id": workspace_id,
        }

    def list_audit_events(
        self,
        workspace_id: Optional[str] = None,
        days: int = 30,
        limit: int = 20,
        offset: int = 0,
    ) -> dict:
        """Return paginated corpus audit history."""
        cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)
        events = self._filter_workspace(self._read_log(self.AUDIT_LOG, cutoff), workspace_id)
        return self._list_events(events=events, limit=limit, offset=offset, workspace_id=workspace_id)

    def list_repair_events(
        self,
        workspace_id: Optional[str] = None,
        days: int = 30,
        limit: int = 20,
        offset: int = 0,
    ) -> dict:
        """Return paginated corpus repair history."""
        cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)
        events = self._filter_workspace(self._read_log(self.REPAIR_LOG, cutoff), workspace_id)
        return self._list_events(events=events, limit=limit, offset=offset, workspace_id=workspace_id)

    def _list_events(self, events: list[dict], limit: int, offset: int, workspace_id: Optional[str]) -> dict:
        items = sorted(events, key=lambda item: item.get("timestamp", ""), reverse=True)
        total = len(items)
        return {
            "items": items[offset: offset + limit],
            "total": total,
            "limit": limit,
            "offset": offset,
            "workspace_id": workspace_id,
        }

    def _normalize_query_event(self, event: dict) -> dict:
        """Backfill fields expected by the API response model for legacy log rows."""
        normalized = dict(event)
        chunk_ids = normalized.get("chunk_ids")
        chunks_used = normalized.get("chunks_used")

        if not chunk_ids and isinstance(chunks_used, list):
            chunk_ids = [
                item.get("chunk_id") if isinstance(item, dict) and item.get("chunk_id") else str(item)
                for item in chunks_used
            ]
            normalized["chunk_ids"] = chunk_ids

        if "chunks_used_count" not in normalized:
            if isinstance(chunks_used, list):
                normalized["chunks_used_count"] = len(chunks_used)
            elif isinstance(chunk_ids, list):
                normalized["chunks_used_count"] = len(chunk_ids)
            else:
                normalized["chunks_used_count"] = 0

        normalized.setdefault("type", "query")
        normalized.setdefault("request_id", None)
        normalized.setdefault("low_confidence", False)
        normalized.setdefault("citation_coverage", 0.0)
        normalized.setdefault("uncited_claims_count", 0)
        normalized.setdefault("reranking_applied", False)
        normalized.setdefault("reranking_method", None)
        normalized.setdefault("candidate_count", None)
        normalized.setdefault("query_expansion_applied", False)
        normalized.setdefault("query_expansion_method", None)
        normalized.setdefault("query_expansion_fallback", False)
        normalized.setdefault("query_expansion_requested", False)
        normalized.setdefault("expansion_latency_ms", 0)
        normalized.setdefault("query_expansion_mode", None)
        normalized.setdefault("query_expansion_decision_reason", None)
        return normalized

    def _aggregate_retrieval(self, queries: list[dict], evaluations: list[dict]) -> dict:
        """Aggregate retrieval metrics from query logs."""
        if not queries and not evaluations:
            return self._empty_retrieval_metrics()

        hits1 = sum(1 for q in queries if q.get("hit") is True)
        total_with_hit = sum(1 for q in queries if q.get("hit") is not None)
        low_conf = sum(1 for q in queries if q.get("low_confidence"))
        latencies = [q["total_latency_ms"] for q in queries if q.get("total_latency_ms")]
        retrieval_latencies = [q["retrieval_time_ms"] for q in queries if q.get("retrieval_time_ms")]
        top_scores = [q["top_result_score"] for q in queries if q.get("top_result_score") is not None]
        thresholds = [
            q for q in queries
            if q.get("top_result_score") is not None and q.get("threshold") is not None
        ]

        eval_total_questions = sum(e.get("total_questions", 0) for e in evaluations)
        eval_hit_rate_top1 = self._weighted_average([
            (e.get("hit_at_1", 0.0), e.get("total_questions", 0)) for e in evaluations
        ])
        eval_hit_rate_top3 = self._weighted_average([
            (e.get("hit_at_3", 0.0), e.get("total_questions", 0)) for e in evaluations
        ])
        eval_hit_rate_top5 = self._weighted_average([
            (e.get("hit_at_5", 0.0), e.get("total_questions", 0)) for e in evaluations
        ])
        eval_low_conf = self._weighted_average([
            (e.get("low_confidence_rate", 0.0), e.get("total_questions", 0)) for e in evaluations
        ])
        eval_latencies = self._weighted_average([
            (e.get("avg_latency_ms", 0.0), e.get("total_questions", 0)) for e in evaluations
        ])
        eval_avg_scores = self._weighted_average([
            (e.get("avg_score", 0.0), e.get("total_questions", 0)) for e in evaluations
        ])
        eval_groundedness = self._weighted_average([
            (e.get("groundedness_rate", 0.0), e.get("total_questions", 0)) for e in evaluations
        ])

        return {
            "total_queries": len(queries) or eval_total_questions,
            "hit_rate_top1": round(
                hits1 / total_with_hit,
                4,
            ) if total_with_hit > 0 else round(eval_hit_rate_top1, 4),
            "hit_rate_top3": round(eval_hit_rate_top3, 4),
            "hit_rate_top5": round(eval_hit_rate_top5, 4),
            "low_confidence_rate": round(low_conf / len(queries), 4) if queries else round(eval_low_conf, 4),
            "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else round(eval_latencies, 1),
            "avg_retrieval_latency_ms": round(sum(retrieval_latencies) / len(retrieval_latencies), 1) if retrieval_latencies else round(eval_latencies, 1),
            "p50_latency_ms": round(self._percentile(latencies, 50), 1) if latencies else 0.0,
            "p95_latency_ms": round(self._percentile(latencies, 95), 1) if latencies else 0.0,
            "p99_latency_ms": round(self._percentile(latencies, 99), 1) if latencies else 0.0,
            "avg_score_top1": round(sum(top_scores) / len(top_scores), 4) if top_scores else round(eval_avg_scores, 4),
            "avg_score": round(sum(top_scores) / len(top_scores), 4) if top_scores else round(eval_avg_scores, 4),
            "groundedness_rate": round(eval_groundedness, 4) if evaluations else 0.0,
            "below_threshold_rate": round(
                sum(1 for q in thresholds if q["top_result_score"] < q["threshold"]) / len(thresholds),
                4,
            ) if thresholds else 0.0,
            "queries_with_hit_data": total_with_hit,
        }

    def _aggregate_query_expansion(self, queries: list[dict]) -> dict:
        """
        Aggregate query expansion metrics from query logs.

        Three mutually-exclusive buckets:
        - requested_and_applied: expansion was enabled and produced useful text
        - requested_but_fallback: expansion was enabled but returned empty/truncated
        - not_requested: expansion was not enabled

        fallback_rate is computed over expansion requests only
        (requested_and_applied + requested_but_fallback).
        """
        if not queries:
            return self._empty_query_expansion_metrics()

        # Normalize (backfill defaults for legacy logs)
        queries = [self._normalize_query_event(q) for q in queries]

        requested_and_applied = [
            q for q in queries
            if q.get("query_expansion_requested") and q.get("query_expansion_applied")
        ]
        requested_but_fallback = [
            q for q in queries
            if q.get("query_expansion_requested") and q.get("query_expansion_fallback")
        ]
        not_requested = [
            q for q in queries if not q.get("query_expansion_requested")
        ]

        total_expansion_requests = len(requested_and_applied) + len(requested_but_fallback)
        fallback_count = len(requested_but_fallback)
        # fallback_rate: fraction of expansion requests that fell back
        fallback_rate = round(fallback_count / total_expansion_requests, 4) if total_expansion_requests > 0 else 0.0

        def _avg_latency(qs: list[dict]) -> float:
            latencies = [q["total_latency_ms"] for q in qs if q.get("total_latency_ms")]
            return round(sum(latencies) / len(latencies), 1) if latencies else 0.0

        def _avg_expansion_latency(qs: list[dict]) -> float:
            lats = [q["expansion_latency_ms"] for q in qs if q.get("expansion_latency_ms")]
            return round(sum(lats) / len(lats), 1) if lats else 0.0

        def _avg_retrieval_latency(qs: list[dict]) -> float:
            lats = [q["retrieval_time_ms"] for q in qs if q.get("retrieval_time_ms")]
            return round(sum(lats) / len(lats), 1) if lats else 0.0

        def _low_confidence_rate(qs: list[dict]) -> float:
            return round(sum(1 for q in qs if q.get("low_confidence")) / len(qs), 4) if qs else 0.0

        def _avg_score(qs: list[dict]) -> float:
            scores = [q["top_result_score"] for q in qs if q.get("top_result_score") is not None]
            return round(sum(scores) / len(scores), 4) if scores else 0.0

        def _p50_latency(qs: list[dict]) -> float:
            lats = sorted(q["total_latency_ms"] for q in qs if q.get("total_latency_ms"))
            return round(self._percentile(lats, 50), 1) if lats else 0.0

        def _metrics(qs: list[dict]) -> dict | None:
            if not qs:
                return None
            return {
                "total_queries": len(qs),
                "avg_latency_ms": _avg_latency(qs),
                "p50_latency_ms": _p50_latency(qs),
                "avg_retrieval_latency_ms": _avg_retrieval_latency(qs),
                "avg_expansion_latency_ms": _avg_expansion_latency(qs),
                "low_confidence_rate": _low_confidence_rate(qs),
                "avg_score_top1": _avg_score(qs),
            }

        return {
            "total_queries": len(queries),
            "total_expansion_requests": total_expansion_requests,
            "fallback_count": fallback_count,
            "fallback_rate": fallback_rate,
            "requested_and_applied": _metrics(requested_and_applied),
            "requested_but_fallback": _metrics(requested_but_fallback),
            "not_requested": _metrics(not_requested),
        }

    def _empty_query_expansion_metrics(self) -> dict:
        return {
            "total_queries": 0,
            "total_expansion_requests": 0,
            "fallback_count": 0,
            "fallback_rate": 0.0,
            "requested_and_applied": None,
            "requested_but_fallback": None,
            "not_requested": None,
        }

    def _aggregate_ingestion(self, events: list[dict]) -> dict:
        """Aggregate ingestion metrics."""
        if not events:
            return self._empty_ingestion_metrics()

        by_type: dict[str, int] = defaultdict(int)
        total = len(events)
        errors = sum(1 for e in events if e.get("status") == "error")
        chunk_counts = [e.get("chunk_count", 0) for e in events]
        times = [e.get("processing_time_ms", 0) for e in events]

        for e in events:
            st = e.get("source_type", "unknown")
            by_type[st] = by_type.get(st, 0) + 1

        return {
            "total_documents_processed": total,
            "by_type": dict(by_type),
            "parse_success_rate": round((total - errors) / total, 4) if total > 0 else 0.0,
            "avg_chunks_per_document": round(sum(chunk_counts) / len(chunk_counts), 1) if chunk_counts else 0.0,
            "avg_processing_time_ms": round(sum(times) / len(times), 1) if times else 0.0,
            "errors": errors,
        }

    def _aggregate_ingestion_batches(self, events: list[dict]) -> dict:
        """Aggregate per-batch ingestion progress metrics."""
        if not events:
            return {
                "total_batches": 0,
                "errors": 0,
                "rss_peak_mb": 0.0,
                "avg_duration_ms": 0.0,
                "pages_processed": 0,
                "chunks_created": 0,
                "points_indexed": 0,
                "latest_ingestion_id": None,
                "latest_batch_index": None,
            }

        durations = [int(e.get("duration_ms") or 0) for e in events]
        return {
            "total_batches": len(events),
            "errors": sum(1 for e in events if e.get("status") not in {"success", "partial"}),
            "rss_peak_mb": max((float(e.get("rss_peak_mb") or 0.0) for e in events), default=0.0),
            "avg_duration_ms": round(sum(durations) / len(durations), 1) if durations else 0.0,
            "pages_processed": sum(
                max(0, int(e.get("page_end") or 0) - int(e.get("page_start") or 0) + 1)
                for e in events
                if e.get("page_start") is not None and e.get("page_end") is not None
            ),
            "chunks_created": sum(int(e.get("chunks_created") or 0) for e in events),
            "points_indexed": sum(int(e.get("points_indexed") or 0) for e in events),
            "latest_ingestion_id": events[-1].get("ingestion_id"),
            "latest_batch_index": events[-1].get("batch_index"),
        }

    def _aggregate_answers(self, queries: list[dict], evaluations: list[dict]) -> dict:
        """Aggregate answer quality metrics."""
        if not queries and not evaluations:
            return self._empty_answer_metrics()

        if not queries and evaluations:
            total_questions = sum(e.get("total_questions", 0) for e in evaluations)
            grounded_rate = self._weighted_average([
                (e.get("groundedness_rate", 0.0), e.get("total_questions", 0)) for e in evaluations
            ])
            no_context_rate = self._weighted_average([
                (e.get("low_confidence_rate", 0.0), e.get("total_questions", 0)) for e in evaluations
            ])
            grounded_answers = round(grounded_rate * total_questions)
            no_context_answers = round(no_context_rate * total_questions)
            return {
                "total_queries": total_questions,
                "groundedness_rate": round(grounded_rate, 4),
                "grounded_answers": grounded_answers,
                "no_context_rate": round(no_context_rate, 4),
                "no_context_answers": no_context_answers,
                "ungrounded_answers": max(total_questions - grounded_answers - no_context_answers, 0),
                "answers_needing_review": max(total_questions - grounded_answers, 0),
                "avg_chunks_used": 0.0,
                "citation_coverage_avg": 0.0,
                "avg_uncited_claims": 0.0,
            }

        grounded = sum(1 for q in queries if q.get("grounded"))
        low = sum(1 for q in queries if q.get("low_confidence"))
        ungrounded = sum(1 for q in queries if not q.get("grounded") and not q.get("low_confidence"))
        needs_review = sum(1 for q in queries if q.get("needs_review"))
        chunks = [q.get("chunks_used_count", 0) for q in queries]
        citation_coverages = [q.get("citation_coverage", 0.0) for q in queries if q.get("citation_coverage") is not None]
        uncited_claims = [q.get("uncited_claims_count", 0) for q in queries if q.get("uncited_claims_count") is not None]

        return {
            "total_queries": len(queries),
            "groundedness_rate": round(grounded / len(queries), 4) if queries else 0.0,
            "grounded_answers": grounded,
            "no_context_rate": round(low / len(queries), 4) if queries else 0.0,
            "no_context_answers": low,
            "ungrounded_answers": ungrounded,
            "answers_needing_review": needs_review,
            "avg_chunks_used": round(sum(chunks) / len(chunks), 1) if chunks else 0.0,
            "citation_coverage_avg": round(sum(citation_coverages) / len(citation_coverages), 4) if citation_coverages else 0.0,
            "avg_uncited_claims": round(sum(uncited_claims) / len(uncited_claims), 2) if uncited_claims else 0.0,
        }

    def _aggregate_evaluations(self, evaluations: list[dict]) -> dict:
        """Aggregate evaluation runs over the selected period."""
        if not evaluations:
            return self._empty_evaluation_metrics()

        total_questions = sum(e.get("total_questions", 0) for e in evaluations)
        return {
            "total_runs": len(evaluations),
            "latest_evaluation_id": evaluations[-1].get("evaluation_id"),
            "total_questions": total_questions,
            "hit_rate_top1": round(self._weighted_average([(e.get("hit_at_1", 0.0), e.get("total_questions", 0)) for e in evaluations]), 4),
            "hit_rate_top3": round(self._weighted_average([(e.get("hit_at_3", 0.0), e.get("total_questions", 0)) for e in evaluations]), 4),
            "hit_rate_top5": round(self._weighted_average([(e.get("hit_at_5", 0.0), e.get("total_questions", 0)) for e in evaluations]), 4),
            "avg_score": round(self._weighted_average([(e.get("avg_score", 0.0), e.get("total_questions", 0)) for e in evaluations]), 4),
            "avg_latency_ms": round(self._weighted_average([(e.get("avg_latency_ms", 0.0), e.get("total_questions", 0)) for e in evaluations]), 1),
            "groundedness_rate": round(self._weighted_average([(e.get("groundedness_rate", 0.0), e.get("total_questions", 0)) for e in evaluations]), 4),
            "low_confidence_rate": round(self._weighted_average([(e.get("low_confidence_rate", 0.0), e.get("total_questions", 0)) for e in evaluations]), 4),
        }

    def _empty_retrieval_metrics(self) -> dict:
        return {
            "total_queries": 0,
            "hit_rate_top1": 0.0,
            "hit_rate_top3": 0.0,
            "hit_rate_top5": 0.0,
            "low_confidence_rate": 0.0,
            "avg_latency_ms": 0.0,
            "avg_retrieval_latency_ms": 0.0,
            "p50_latency_ms": 0.0,
            "p95_latency_ms": 0.0,
            "p99_latency_ms": 0.0,
            "avg_score_top1": 0.0,
            "avg_score": 0.0,
            "groundedness_rate": 0.0,
            "below_threshold_rate": 0.0,
            "queries_with_hit_data": 0,
        }

    def _empty_ingestion_metrics(self) -> dict:
        return {
            "total_documents_processed": 0,
            "by_type": {},
            "parse_success_rate": 0.0,
            "avg_chunks_per_document": 0.0,
            "avg_processing_time_ms": 0.0,
            "errors": 0,
        }

    def _empty_answer_metrics(self) -> dict:
        return {
            "total_queries": 0,
            "groundedness_rate": 0.0,
            "grounded_answers": 0,
            "no_context_rate": 0.0,
            "no_context_answers": 0,
            "ungrounded_answers": 0,
            "answers_needing_review": 0,
            "avg_chunks_used": 0.0,
            "citation_coverage_avg": 0.0,
            "avg_uncited_claims": 0.0,
        }

    def _empty_evaluation_metrics(self) -> dict:
        return {
            "total_runs": 0,
            "latest_evaluation_id": None,
            "total_questions": 0,
            "hit_rate_top1": 0.0,
            "hit_rate_top3": 0.0,
            "hit_rate_top5": 0.0,
            "avg_score": 0.0,
            "avg_latency_ms": 0.0,
            "groundedness_rate": 0.0,
            "low_confidence_rate": 0.0,
        }

    # ── Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _percentile(values: list[float], percentile: int) -> float:
        """Return a simple percentile from a numeric list."""
        if not values:
            return 0.0
        ordered = sorted(values)
        idx = max(0, min(len(ordered) - 1, int(round((percentile / 100) * (len(ordered) - 1)))))
        return ordered[idx]

    @staticmethod
    def _append(log_path: Path, event: dict):
        """Append a JSON event to a log file."""
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    @staticmethod
    def _hash_text(text: Optional[str]) -> str:
        normalized = (text or "").strip().encode("utf-8")
        return hashlib.sha256(b"clinical-planner-v1:" + normalized).hexdigest()

    @classmethod
    def _safe_variant_snapshot(cls, variant) -> dict:
        variant_type = getattr(variant, "variant_type", None)
        query = getattr(variant, "query", "")
        purpose = getattr(variant, "purpose", None)
        origin = getattr(variant, "origin", None)
        if isinstance(variant, dict):
            variant_type = variant.get("variant_type")
            query = variant.get("query", "")
            purpose = variant.get("purpose")
            origin = variant.get("origin")
        return {
            "variant_type": variant_type,
            "origin": origin,
            "query_hash": cls._hash_text(query),
            "query_length": len(query or ""),
            "purpose": purpose,
            "context_preserved": getattr(variant, "context_preserved", None) if not isinstance(variant, dict) else variant.get("context_preserved"),
            "blocked": getattr(variant, "blocked", None) if not isinstance(variant, dict) else variant.get("blocked"),
            "blocked_reason": getattr(variant, "blocked_reason", None) if not isinstance(variant, dict) else variant.get("blocked_reason"),
        }

    @staticmethod
    def _read_log(log_path: Path, cutoff_ts: float) -> list[dict]:
        """Read log file and return events newer than cutoff timestamp."""
        events = []
        if not log_path.exists():
            return events
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    ts = event.get("timestamp", "")
                    if ts:
                        event_ts = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                        if event_ts >= cutoff_ts:
                            events.append(event)
                except (json.JSONDecodeError, ValueError):
                    continue
        return events

    @staticmethod
    def _filter_workspace(events: list[dict], workspace_id: Optional[str]) -> list[dict]:
        if not workspace_id:
            return events
        return [event for event in events if event.get("workspace_id", "default") == workspace_id]

    @staticmethod
    def _weighted_average(items: list[tuple[float, int]]) -> float:
        total_weight = sum(weight for _, weight in items if weight)
        if total_weight <= 0:
            return 0.0
        total_value = sum(value * weight for value, weight in items if weight)
        return total_value / total_weight


# Singleton instance
_telemetry: Optional[TelemetryService] = None


def get_telemetry() -> TelemetryService:
    global _telemetry
    if _telemetry is None:
        _telemetry = TelemetryService()
    return _telemetry
