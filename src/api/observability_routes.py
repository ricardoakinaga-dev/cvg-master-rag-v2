from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from models.schemas import (
    AuditLogListResponse,
    EnterpriseSession,
    ObservabilityAlertsResponse,
    ObservabilitySLOResponse,
    ObservabilityTraceResponse,
    RepairLogListResponse,
)
from services.api_security import enterprise_session_from_authorization, require_admin, resolve_workspace_scope
from services.telemetry_service import get_telemetry
from services.vector_service import get_client
from telemetry.slo import SLI_DEFINITIONS, get_all_slos, get_slo_status
from telemetry.tracing import list_recent_spans

router = APIRouter(tags=["observability"])


def _current_disk_usage_percent() -> float:
    from shutil import disk_usage
    from core.config import LOGS_DIR

    usage = disk_usage(LOGS_DIR)
    return round((usage.used / usage.total) * 100, 2) if usage.total else 0.0


def _build_slo_snapshot(metrics: dict, *, workspace_id: str | None, qdrant_ok: bool) -> dict:
    retrieval = metrics.get("retrieval", {})
    ingestion = metrics.get("ingestion", {})
    answer = metrics.get("answer", {})

    total_docs = float(ingestion.get("total_documents_processed", 0) or 0)
    errors = float(ingestion.get("errors", 0) or 0)
    ingestion_error_rate = round((errors / total_docs) * 100, 2) if total_docs else 0.0

    current_values = {
        "vector_store_availability": 100.0 if qdrant_ok else 0.0,
        "latency_p99": float(retrieval.get("p99_latency_ms", 0.0) or 0.0),
        "latency_p50": float(retrieval.get("p50_latency_ms", 0.0) or 0.0),
        "retrieval_latency_p99": float(retrieval.get("avg_retrieval_latency_ms", 0.0) or 0.0),
        "error_rate_ingestion": ingestion_error_rate,
        "hit_rate_top1": round(float(retrieval.get("hit_rate_top1", 0.0) or 0.0) * 100, 2),
        "hit_rate_top5": round(float(retrieval.get("hit_rate_top5", 0.0) or 0.0) * 100, 2),
        "groundedness_rate": round(float(answer.get("groundedness_rate", 0.0) or 0.0) * 100, 2),
        "no_context_rate": round(float(answer.get("no_context_rate", 0.0) or 0.0) * 100, 2),
        "disk_usage": _current_disk_usage_percent(),
    }

    items: list[dict] = []
    for slo in get_all_slos():
        current_value = float(current_values.get(slo.sli_name, 0.0) or 0.0)
        healthy, message = get_slo_status(slo.sli_name, current_value)
        sli = SLI_DEFINITIONS[slo.sli_name]
        comparator = "at_least" if slo.min_value is not None else "at_most"
        target_value = float(slo.min_value if slo.min_value is not None else slo.target_value)
        items.append(
            {
                "name": slo.sli_name,
                "description": sli.description,
                "category": sli.category.value,
                "unit": sli.unit,
                "window": slo.window,
                "current_value": current_value,
                "target_value": target_value,
                "alert_threshold": slo.alert_threshold,
                "comparator": comparator,
                "healthy": healthy,
                "status": "ok" if healthy else "breach",
                "message": message,
            }
        )

    return {
        "items": items,
        "total_breaches": sum(1 for item in items if item["status"] == "breach"),
        "workspace_id": workspace_id,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


@router.get("/observability/alerts", response_model=ObservabilityAlertsResponse)
def get_observability_alerts(
    days: int = Query(default=1, ge=1, le=30),
    workspace_id: str | None = Query(default=None),
    _session: EnterpriseSession | object = Depends(enterprise_session_from_authorization),
):
    try:
        from api.main import get_telemetry as resolve_telemetry
        tel = resolve_telemetry()
        target_workspace = resolve_workspace_scope(workspace_id, _session, required_permission="observability.read")
        return tel.get_alerts(days=days, workspace_id=target_workspace)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "observability_alerts_error", "message": str(e)})


@router.get("/observability/slo", response_model=ObservabilitySLOResponse)
def get_observability_slo(
    workspace_id: str | None = Query(default=None),
    _session: EnterpriseSession | object = Depends(enterprise_session_from_authorization),
):
    try:
        target_workspace = resolve_workspace_scope(workspace_id, _session, required_permission="observability.read")
        from api.main import get_telemetry as resolve_telemetry
        tel = resolve_telemetry()
        metrics = tel.get_metrics(days=7, workspace_id=target_workspace)
        try:
            client = get_client()
            client.get_collections()
            qdrant_ok = True
        except Exception:
            qdrant_ok = False
        return _build_slo_snapshot(metrics, workspace_id=target_workspace, qdrant_ok=qdrant_ok)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "observability_slo_error", "message": str(e)})


@router.get("/observability/traces", response_model=ObservabilityTraceResponse)
def get_observability_traces(
    workspace_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    _session: EnterpriseSession | object = Depends(enterprise_session_from_authorization),
):
    try:
        target_workspace = resolve_workspace_scope(workspace_id, _session, required_permission="observability.read")
        items = list_recent_spans(limit=limit, workspace_id=target_workspace)
        return {
            "items": items,
            "total": len(items),
            "workspace_id": target_workspace,
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "observability_traces_error", "message": str(e)})


@router.get("/observability/audits", response_model=AuditLogListResponse)
def list_observability_audits(
    days: int = Query(default=30, ge=1, le=90),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    workspace_id: str | None = Query(default=None),
    _session: EnterpriseSession | object = Depends(enterprise_session_from_authorization),
):
    try:
        from api.main import get_telemetry as resolve_telemetry
        tel = resolve_telemetry()
        target_workspace = resolve_workspace_scope(workspace_id, _session, required_permission="observability.read")
        return tel.list_audit_events(workspace_id=target_workspace, days=days, limit=limit, offset=offset)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "observability_audits_error", "message": str(e)})


@router.get("/observability/repairs", response_model=RepairLogListResponse)
def list_observability_repairs(
    days: int = Query(default=30, ge=1, le=90),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    workspace_id: str | None = Query(default=None),
    _session: EnterpriseSession | object = Depends(enterprise_session_from_authorization),
):
    try:
        from api.main import get_telemetry as resolve_telemetry
        tel = resolve_telemetry()
        target_workspace = resolve_workspace_scope(workspace_id, _session, required_permission="observability.read")
        return tel.list_repair_events(workspace_id=target_workspace, days=days, limit=limit, offset=offset)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "observability_repairs_error", "message": str(e)})
