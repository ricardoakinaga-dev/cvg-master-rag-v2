# SPEC Adherence Audit - Indexing 400MB

## Resultado

Classificacao: aderente.

## Matriz

| Requisito SPEC | Evidencia | Status |
|---|---|---|
| `MAX_UPLOAD_BYTES=524288000` | runtime `.env` | aderente |
| Upload PDF pesado assíncrono | jobs de ingestao | aderente |
| Batch PDF page-safe | canarios concluidos | aderente |
| Concorrencia grande = 1 | `MAX_CONCURRENT_LARGE_INGESTION_JOBS=1` | aderente |
| Timeout finito | `INGESTION_JOB_TIMEOUT_SECONDS=21600` | aderente |
| Cgroup/systemd | jobs `systemd_run`, perfil normal | aderente |
| Qdrant consistente | `18679` por document/ingestion | aderente |
| Health leve/heartbeat | I400-011 concluida | aderente |
| Gatilho JSONL futuro | I400-012 concluida | aderente |

## Decisao

SPEC 0122 atendida para release permanente controlado de `500MiB`.
