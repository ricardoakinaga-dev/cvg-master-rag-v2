from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from core.config import QDRANT_COLLECTION
from models.schemas import (
    AdminOperationalCleanupResponse,
    AdminQdrantPruneResponse,
    AdminRuntimeResponse,
    EnterpriseSession,
)
from services.admin_service import list_tenants as list_admin_tenants, log_admin_event
from services.api_security import enterprise_session_from_authorization, require_permission
from services.document_registry import get_workspace_inventory
from services.integrity_service import summarize_workspace_index_drift
from services.operational_retention_service import summarize_operational_retention
from services.telemetry_service import get_telemetry
from services.vector_service import get_client

router = APIRouter(tags=["admin-runtime"])


def _compute_readiness_summary(
    metrics: dict,
    alerts: dict,
    corpus: dict,
    qdrant_ok: bool,
    index_drift: dict | None = None,
) -> dict:
    """Convert operational signals into a compact executive readiness score."""
    score = 100
    reasons: list[str] = []

    alert_items = alerts.get("items", [])
    critical_alerts = sum(1 for item in alert_items if item.get("status") == "firing" and item.get("severity") == "critical")
    high_alerts = sum(1 for item in alert_items if item.get("status") == "firing" and item.get("severity") == "high")

    answer = metrics.get("answer", {})
    evaluation = metrics.get("evaluation", {})
    retrieval = metrics.get("retrieval", {})

    groundedness_rate = float(answer.get("groundedness_rate", 0.0) or 0.0)
    no_context_rate = float(answer.get("no_context_rate", 0.0) or 0.0)
    hit_rate_top5 = float(evaluation.get("hit_rate_top5", 0.0) or 0.0)
    p95_latency_ms = float(retrieval.get("p95_latency_ms", 0.0) or 0.0)
    partial_documents = int(corpus.get("partial_documents", 0) or 0)
    noncanonical_points = int((index_drift or {}).get("noncanonical_points", 0) or 0)
    noncanonical_documents = int((index_drift or {}).get("noncanonical_documents", 0) or 0)

    if not qdrant_ok:
        score -= 35
        reasons.append("Qdrant indisponível")
    if noncanonical_points:
        score -= min(10 + noncanonical_documents * 3, 20)
        reasons.append(f"drift vetorial: {noncanonical_points} pontos fora do corpus canônico")
    if critical_alerts:
        score -= min(critical_alerts * 15, 30)
        reasons.append(f"{critical_alerts} alertas críticos")
    if high_alerts:
        score -= min(high_alerts * 8, 16)
        reasons.append(f"{high_alerts} alertas altos")
    if partial_documents:
        score -= min(partial_documents * 5, 15)
        reasons.append(f"{partial_documents} documentos parciais")
    if groundedness_rate > 0 and groundedness_rate < 0.85:
        score -= min(int(round((0.85 - groundedness_rate) * 100)), 20)
        reasons.append(f"groundedness em {round(groundedness_rate * 100, 1)}%")
    if no_context_rate > 0.10:
        score -= min(int(round((no_context_rate - 0.10) * 100)), 20)
        reasons.append(f"no-context em {round(no_context_rate * 100, 1)}%")
    if hit_rate_top5 > 0 and hit_rate_top5 < 0.95:
        score -= min(int(round((0.95 - hit_rate_top5) * 100)), 20)
        reasons.append(f"hit@5 em {round(hit_rate_top5 * 100, 1)}%")
    if p95_latency_ms > 5000:
        score -= 15
        reasons.append(f"p95 em {round(p95_latency_ms, 1)} ms")
    elif p95_latency_ms > 2500:
        score -= 8
        reasons.append(f"p95 em {round(p95_latency_ms, 1)} ms")

    score = max(0, min(100, score))
    if score >= 90:
        status = "ready"
    elif score >= 75:
        status = "stable"
    elif score >= 55:
        status = "at_risk"
    else:
        status = "critical"

    if not reasons:
        reasons.append("Sem bloqueios operacionais relevantes")

    return {
        "readiness_score": score,
        "readiness_status": status,
        "readiness_reasons": reasons[:3],
        "groundedness_rate": groundedness_rate,
        "no_context_rate": no_context_rate,
        "evaluation_hit_rate_top5": hit_rate_top5,
        "p95_latency_ms": p95_latency_ms,
    }


@router.get("/admin/runtime", response_model=AdminRuntimeResponse)
def admin_get_runtime(
    _session: EnterpriseSession = Depends(enterprise_session_from_authorization),
):
    """Return a consolidated operational view for every tenant/workspace."""
    _session = require_permission(_session, "runtime.manage", workspace_id=_session.active_tenant.workspace_id)
    telemetry = get_telemetry()
    tenants = list_admin_tenants()

    client = None
    qdrant_ok = False
    try:
        client = get_client()
        client.get_collections()
        qdrant_ok = True
    except Exception:
        client = None
        qdrant_ok = False

    items: list[dict] = []
    for tenant in tenants:
        workspace_id = tenant["workspace_id"]
        corpus = get_workspace_inventory(workspace_id)
        retention = summarize_operational_retention(workspace_id)
        snapshot = telemetry.get_operational_snapshot(days=7, workspace_id=workspace_id)
        metrics = telemetry.get_metrics(days=7, workspace_id=workspace_id)
        alerts = telemetry.get_alerts(days=1, workspace_id=workspace_id)
        audits = telemetry.list_audit_events(workspace_id=workspace_id, days=30, limit=1, offset=0)
        repairs = telemetry.list_repair_events(workspace_id=workspace_id, days=30, limit=1, offset=0)
        qdrant_points = None
        drift = {
            "total_points": 0,
            "canonical_points": 0,
            "noncanonical_points": 0,
            "noncanonical_documents": 0,
            "noncanonical_document_ids": [],
        }
        if qdrant_ok and client is not None:
            try:
                drift = summarize_workspace_index_drift(workspace_id).model_dump()
                qdrant_points = drift["total_points"]
            except Exception:
                qdrant_points = None
                drift = {
                    "total_points": 0,
                    "canonical_points": 0,
                    "noncanonical_points": 0,
                    "noncanonical_documents": 0,
                    "noncanonical_document_ids": [],
                }

        readiness = _compute_readiness_summary(
            metrics=metrics,
            alerts=alerts,
            corpus=corpus,
            qdrant_ok=qdrant_ok,
            index_drift=drift,
        )

        items.append(
            {
                "tenant_id": tenant["tenant_id"],
                "name": tenant["name"],
                "workspace_id": workspace_id,
                "plan": tenant["plan"],
                "status": tenant["status"],
                "document_count": corpus.get("documents", 0),
                "chunk_count": corpus.get("chunks", 0),
                "parsed_documents": corpus.get("parsed_documents", 0),
                "partial_documents": corpus.get("partial_documents", 0),
                "operational_documents": corpus.get("operational_documents", 0),
                "operational_chunks": corpus.get("operational_chunks", 0),
                "operational_retention_mode": retention.retention_mode,
                "operational_retention_hours": retention.retention_hours,
                "operational_cleanup_eligible_documents": retention.eligible_documents,
                "operational_cleanup_eligible_chunks": retention.eligible_chunks,
                "operational_cleanup_oldest_created_at": retention.oldest_eligible_created_at,
                "qdrant_status": "ok" if qdrant_ok else "error",
                "qdrant_points": qdrant_points,
                "qdrant_canonical_points": drift.get("canonical_points", 0),
                "qdrant_noncanonical_points": drift.get("noncanonical_points", 0),
                "qdrant_noncanonical_documents": drift.get("noncanonical_documents", 0),
                "alerts_active": alerts.get("total_active", 0),
                "critical_alerts": sum(
                    1
                    for item in alerts.get("items", [])
                    if item.get("status") == "firing" and item.get("severity") == "critical"
                ),
                "audit_events_30d": audits.get("total", 0),
                "repair_events_30d": repairs.get("total", 0),
                **readiness,
                "latest_query_at": snapshot["queries"].get("latest_timestamp"),
                "latest_ingestion_at": snapshot["ingestion"].get("latest_timestamp"),
                "latest_evaluation_at": snapshot["evaluation"].get("latest_timestamp"),
            }
        )

    return {
        "items": items,
        "total": len(items),
        "qdrant_collection": QDRANT_COLLECTION,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


@router.post("/admin/runtime/prune-index", response_model=AdminQdrantPruneResponse)
def admin_prune_workspace_index(
    workspace_id: str = Query(default="default"),
    _session: EnterpriseSession = Depends(enterprise_session_from_authorization),
):
    """Delete non-canonical Qdrant points for a workspace."""
    _session = require_permission(_session, "runtime.manage", workspace_id=workspace_id)
    from services.integrity_service import prune_workspace_index_to_registry

    try:
        result = prune_workspace_index_to_registry(workspace_id=workspace_id)
        log_admin_event(
            actor_user_id=_session.user.user_id,
            actor_email=_session.user.email,
            actor_role=_session.user.role,
            action="runtime.prune_index",
            target_type="workspace",
            target_id=workspace_id,
            tenant_id=None,
            metadata={
                "workspace_id": workspace_id,
                "deleted_points": result.deleted_points,
                "deleted_documents": result.deleted_documents,
                "deleted_document_ids": result.deleted_document_ids,
                "canonical_points_remaining": result.canonical_points_remaining,
                "total_points_remaining": result.total_points_remaining,
            },
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "admin_prune_index_error", "message": str(e)})


@router.post("/admin/runtime/cleanup-operational", response_model=AdminOperationalCleanupResponse)
def admin_cleanup_operational_uploads(
    workspace_id: str = Query(default="default"),
    _session: EnterpriseSession = Depends(enterprise_session_from_authorization),
):
    """Delete operational uploads that are older than the tenant TTL."""
    _session = require_permission(_session, "runtime.manage", workspace_id=workspace_id)
    from services.operational_retention_service import cleanup_operational_uploads

    try:
        result = cleanup_operational_uploads(workspace_id=workspace_id)
        log_admin_event(
            actor_user_id=_session.user.user_id,
            actor_email=_session.user.email,
            actor_role=_session.user.role,
            action="runtime.cleanup_operational",
            target_type="workspace",
            target_id=workspace_id,
            tenant_id=None,
            metadata={
                "workspace_id": workspace_id,
                "retention_mode": result.retention_mode,
                "retention_hours": result.retention_hours,
                "deleted_documents": result.deleted_documents,
                "deleted_chunks": result.deleted_chunks,
                "deleted_document_ids": result.deleted_document_ids,
                "remaining_operational_documents": result.remaining_operational_documents,
                "remaining_operational_chunks": result.remaining_operational_chunks,
            },
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "admin_cleanup_operational_error", "message": str(e)})
