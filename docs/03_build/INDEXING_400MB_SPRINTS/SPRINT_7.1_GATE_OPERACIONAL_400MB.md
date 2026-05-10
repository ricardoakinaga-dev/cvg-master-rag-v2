# Sprint 7.1 - Gate Operacional 400MB

## Objetivo

Preparar o sistema para aceitar arquivo de ate `391,5MiB` com limite seguro de `500MiB`, sem iniciar processamento inseguro.

## Tasks

### I400-001 - Definir limite seguro de upload 500MiB

- Executado: [x]
- O QUE: configurar limite alvo de upload para `524288000` bytes.
- ONDE: `src/.env`, `src/.env.example`, docs operacionais.
- COMO: aplicar como configuracao controlada, mantendo rastreabilidade da margem sobre `410562000` bytes.
- DEPENDENCIA: SPEC 0122.
- CRITERIO DE PRONTO: limite documentado e validado sem liberar canario antes dos demais gates.
- EVIDENCIA: `MAX_UPLOAD_BYTES=524288000` aplicado em `src/.env` e `src/.env.example`; margem cobre arquivo alvo `410562000` bytes.
- REGRA POS-TASK: marcar `Executado: [x]`, registrar evidencia e atualizar runtime/log/backlog antes da proxima task.

### I400-002 - Implementar preflight de disco/capacidade

- Executado: [x]
- O QUE: bloquear jobs grandes quando disco/Qdrant/capacidade estiverem inseguros.
- ONDE: upload API e/ou `services.ingestion_job_service`.
- COMO: validar disco livre >= `max(5GiB, file_size * 3)`, Qdrant acessivel e metadados do arquivo.
- DEPENDENCIA: I400-001.
- CRITERIO DE PRONTO: upload grande sem capacidade retorna erro claro e nao cria job inseguro.
- EVIDENCIA: `preflight_large_ingestion()` bloqueia disco insuficiente com HTTP `507`, Qdrant indisponivel com HTTP `503` e persiste metadados de capacidade no job.
- REGRA POS-TASK: marcar `Executado: [x]`, registrar evidencia e atualizar runtime/log/backlog antes da proxima task.

### I400-003 - Limitar concorrencia de jobs grandes a 1

- Executado: [x]
- O QUE: impedir dois jobs grandes simultaneos.
- ONDE: job service e upload API.
- COMO: considerar grande qualquer arquivo >= `52428800` bytes; se existir job grande `processing`, bloquear ou manter pendente conforme decisao implementada.
- DEPENDENCIA: I400-002.
- CRITERIO DE PRONTO: teste prova que segundo job grande nao inicia em paralelo.
- EVIDENCIA: `MAX_CONCURRENT_LARGE_INGESTION_JOBS=1`; `active_large_ingestion_jobs()` bloqueia novo job grande quando ha job `pending` ou `processing`.
- REGRA POS-TASK: marcar `Executado: [x]`, registrar evidencia e atualizar runtime/log/backlog antes da proxima task.

### I400-004 - Configurar timeout finito para job grande

- Executado: [x]
- O QUE: remover execucao indefinida de worker grande.
- ONDE: `src/.env`, worker e job service.
- COMO: usar `INGESTION_JOB_TIMEOUT_SECONDS=21600` e garantir registro `aborted/failed` com cleanup.
- DEPENDENCIA: I400-003.
- CRITERIO DE PRONTO: timeout configurado, documentado e testado em simulacao curta.
- EVIDENCIA: `INGESTION_JOB_TIMEOUT_SECONDS=21600` configurado em `src/.env` e `src/.env.example`; worker aplica timeout via `signal.alarm()`.
- REGRA POS-TASK: marcar `Executado: [x]`, registrar evidencia e atualizar runtime/log/backlog antes da proxima task.

## Gate Do Sprint

- [x] preflight ativo
- [x] concorrencia de job grande controlada
- [x] timeout finito
- [x] limite seguro pronto para canario, mas ainda nao validado permanentemente

## Verificacao

- `src/.venv/bin/pytest -q src/tests/test_ingestion_jobs.py` -> `5 passed`
- `src/.venv/bin/python -m py_compile src/services/ingestion_job_service.py src/api/main.py src/scripts/ingestion_worker.py src/tests/test_ingestion_jobs.py` -> OK
- `systemctl restart cvg-master-rag-backend.service` + `curl http://127.0.0.1:8000/health` -> backend `healthy`

## Resultado

Sprint 7.1 concluida. O sistema agora aceita limite configurado de `500MiB`, mas uploads grandes passam por preflight de disco/Qdrant, concorrencia maxima `1` para jobs grandes e timeout finito de worker. O canario real de `391,5MiB` continua pendente ate Sprint 7.2/7.3.
