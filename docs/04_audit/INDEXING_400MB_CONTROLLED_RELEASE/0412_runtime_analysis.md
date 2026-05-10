# Runtime Analysis - Indexing 400MB

## Estado Runtime

- Backend: `active`
- Frontend: `active`
- Caddy: `active`
- Publico `/documents`: `HTTP/2 200`
- Publico `/api/health?light=true`: `healthy`
- Local `/health?light=true`: `mode=light`, `corpus=null`, `telemetry=null`
- Local `/health`: `healthy`, Qdrant `ok`, `workspace_points=39390`

## Recursos

- RAM total: `7.8Gi`
- RAM disponivel na auditoria: `4.0Gi`
- Swap usado: `2.9Gi/4.0Gi`
- Disco `/`: `20G` livre

## Resultado

Runtime apto para release controlado. Risco de polling pesado foi mitigado pelo health leve e heartbeat/status de job.
