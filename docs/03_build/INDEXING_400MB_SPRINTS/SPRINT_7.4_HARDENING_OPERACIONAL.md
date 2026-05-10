# Sprint 7.4 - Hardening Operacional

## Objetivo

Fechar a operacao 400MB com alertas, heartbeat e limites para evolucao futura.

## Tasks

### I400-011 - Adicionar heartbeat e alertas operacionais

- Executado: [x]
- O QUE: detectar job parado ou degradado.
- ONDE: job service, telemetry e health/metrics.
- COMO: registrar `last_heartbeat_at`, `last_batch_at`, throughput e alertas para RSS alto/job sem lote.
- DEPENDENCIA: Sprint 7.3.
- CRITERIO DE PRONTO: operador identifica job travado sem acessar codigo.
- EVIDENCIA: job JSON agora nasce com `last_heartbeat_at`, `last_batch_at`, `pages_per_minute`, `chunks_per_minute`, `operational_status` e `operational_alerts`; processamento PDF atualiza heartbeat/lote a cada batch; listagem de jobs retorna `seconds_since_last_batch` e alertas dinamicos para RSS alto/job sem lote; `/health?light=true` retorna modo leve sem inventario, telemetria nem contagens Qdrant; frontend usa health leve no shell e preserva ultimo status valido de jobs quando a atualizacao atrasa.
- VERIFICACAO: `src/.venv/bin/python -m py_compile src/services/ingestion_job_service.py src/services/ingestion_service.py src/api/main.py src/api/health_routes.py src/models/schemas.py` passou; `src/.venv/bin/pytest -q src/tests/test_ingestion_jobs.py src/tests/test_sprint5.py::TestHealthEndpoint` retornou `13 passed`; `./node_modules/.bin/tsc --noEmit` passou; `npm run lint` passou; `npm run build` passou; runtime `GET /health?workspace_id=default&light=true` retornou `mode=light`, `status=healthy`, Qdrant `ok`, `corpus=null`, `telemetry=null`.
- REGRA POS-TASK: marcar `Executado: [x]`, registrar evidencia e atualizar runtime/log/backlog antes da proxima task.

### I400-012 - Definir gatilho de shards JSONL futuro

- Executado: [x]
- O QUE: preparar criterio para documentos maiores que 400MB.
- ONDE: SPEC/docs e, se simples, constantes de configuracao.
- COMO: documentar migracao para shards quando `chunk_count > 100000` ou chunks file previsto > `500MB`.
- DEPENDENCIA: I400-011.
- CRITERIO DE PRONTO: limite futuro claro sem bloquear release 400MB.
- EVIDENCIA: SPEC 0122 e `.env.example` registram `CHUNKS_JSONL_SHARD_TRIGGER_CHUNK_COUNT=100000` e `CHUNKS_JSONL_SHARD_TRIGGER_FILE_BYTES=524288000`; `src/core/config.py` expõe as mesmas constantes; regra operacional define que o release `400MB` permanece com `*_chunks.json` atomico, mas qualquer aumento futuro de limite fica bloqueado ate uma SPEC/BUILD propria para persistencia em shards JSONL.
- VERIFICACAO: `src/.venv/bin/python -m py_compile src/core/config.py` passou; import direto confirmou `CHUNKS_JSONL_SHARD_TRIGGER_CHUNK_COUNT=100000` e `CHUNKS_JSONL_SHARD_TRIGGER_FILE_BYTES=524288000`.
- REGRA POS-TASK: marcar `Executado: [x]`, registrar evidencia e atualizar runtime/log/backlog antes de encerrar.

## Gate Do Sprint

- [x] observabilidade operacional para job 400MB com heartbeat/status leve
- [x] criterios de proxima escala definidos
- [x] release 400MB pronto para auditoria
