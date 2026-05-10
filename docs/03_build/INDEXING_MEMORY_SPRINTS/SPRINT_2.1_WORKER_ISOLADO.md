# Sprint 2.1 - Worker De Ingestao Isolado

## Objetivo

Remover indexacao pesada do request web para manter API responsiva e limitar falha ao worker.

## Tasks

### IMR-006 - Transformar upload pesado em job

- Executado: [x]
- O QUE: upload deve criar job e retornar status, nao indexar livro grande no request.
- ONDE: contrato de upload, store de jobs e frontend/status operacional quando aplicavel.
- COMO: separar recebimento do arquivo de processamento; registrar `ingestion_id`, status e progresso.
- DEPENDENCIA: Sprint 1.1 concluido.
- CRITERIO DE PRONTO: upload de PDF grande retorna job sem bloquear worker web.
- EVIDENCIA: `src/services/ingestion_job_service.py` criado com job store JSON atomico; `/documents/upload` agora retorna `status=queued` e `ingestion_id` para PDF acima de `INGESTION_ASYNC_PDF_MIN_BYTES`; endpoint `/documents/ingestion-jobs/{ingestion_id}` expoe status; frontend trata `queued`; teste `src/.venv/bin/pytest -q src/tests/test_ingestion_jobs.py` passou `2 passed`.
- REGRA POS-TASK: marcar `Executado: [x]`, registrar evidencia, atualizar `docs/99_runtime_state.md`, `docs/20_master_execution_log.md` e este sprint antes da proxima task.

### IMR-007 - Criar worker isolado com limite de memoria

- Executado: [x]
- O QUE: executar processamento em processo/servico separado.
- ONDE: runtime local/systemd ou mecanismo equivalente de worker.
- COMO: worker consome jobs pendentes, executa ingestao e possui limite de memoria/timeout.
- DEPENDENCIA: IMR-006.
- CRITERIO DE PRONTO: se worker falhar, API continua respondendo `/health`.
- EVIDENCIA: `src/scripts/ingestion_worker.py` criado com CLI `--job-id/--once`, `INGESTION_WORKER_MEMORY_LIMIT_MB` via `resource.RLIMIT_AS` e timeout opcional `INGESTION_JOB_TIMEOUT_SECONDS`; `spawn_ingestion_worker()` inicia subprocesso fora do Uvicorn; worker de falha simulada saiu `worker_status=1` e marcou job `failed`, enquanto `curl http://127.0.0.1:8000/health` permaneceu `healthy`; backend e frontend reiniciados nos servicos existentes.
- REGRA POS-TASK: marcar `Executado: [x]`, registrar evidencia, atualizar `docs/99_runtime_state.md`, `docs/20_master_execution_log.md` e este sprint antes da proxima task.

## Gate Do Sprint

- [x] API nao bloqueia durante indexacao pesada
- [x] worker tem isolamento operacional e limite definido
