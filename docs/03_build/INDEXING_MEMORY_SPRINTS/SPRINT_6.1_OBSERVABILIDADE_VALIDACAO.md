# Sprint 6.1 - Observabilidade E Validacao Real

## Objetivo

Comprovar que a solucao evita novos travamentos e deixa o sistema auditavel.

## Tasks

### IMR-014 - Expor logs e metricas por lote

- Executado: [x]
- O QUE: tornar memoria/progresso visiveis durante indexacao.
- ONDE: logs de ingestao, health/metrics e documentacao operacional.
- COMO: registrar RSS, paginas, chunks, pontos, tempo e status por lote.
- DEPENDENCIA: Sprint 5.1 concluido.
- CRITERIO DE PRONTO: operador consegue diagnosticar progresso e risco sem acessar codigo.
- EVIDENCIA: `src/services/telemetry_service.py` passou a gravar `src/logs/ingestion_batches.jsonl` via `log_ingestion_batch()` e agregar `ingestion_batches` em `/metrics` e `/health`; `src/services/ingestion_service.py` registra por lote `rss_mb`, `rss_peak_mb`, paginas, chunks, pontos, duracao, status e `ingestion_id`. Teste `test_controlled_pdf_logs_batch_metrics_and_metrics_aggregate` passou.
- REGRA POS-TASK: marcar `Executado: [x]`, registrar evidencia, atualizar `docs/99_runtime_state.md`, `docs/20_master_execution_log.md` e este sprint antes da proxima task.

### IMR-015 - Validar com livro real e falha simulada

- Executado: [x]
- O QUE: fechar o ciclo com evidencia real.
- ONDE: runtime local/staging, Qdrant, filesystem e health.
- COMO: executar livro grande, medir memoria, simular falha no meio e validar cleanup.
- DEPENDENCIA: IMR-014.
- CRITERIO DE PRONTO: livro real sem OOM, API saudavel, JSON valido, Qdrant sem orfaos, docs atualizadas.
- EVIDENCIA: validacao com livro real `Semiologia Veterinária - A arte de Diagnosticar.pdf` concluida em workspace isolado `imr_validation`: `page_count=842`, `char_count=2523459`, `chunk_count=2809`, `elapsed_ms=458015`, `rss_start_mb=126.21`, `rss_peak_mb=157.6`, `rss_end_mb=157.4`, `memory_sample_count=50`, `raw_valid=true`, `chunks_valid=true`, `points_before=0`, `points_after_index=2809`, `points_after_cleanup=0`. Logs por lote registrados em `src/logs/ingestion_batches.jsonl` com `421` eventos para `ingestion_id=imr-real-book-2026-05-01`, ultimo lote paginas `841-842`, `rss_peak_mb=157.6`.
- EVIDENCIA FALHA SIMULADA: job em workspace `imr_validation_failure` falhou propositalmente apos escrita parcial e ponto Qdrant; resultado `status=failed`, `error_code=RuntimeError`, `points_after_cleanup=0`, `upload_exists_after_cleanup=false`, `tmp_files_remaining=[]`.
- EVIDENCIA RUNTIME: backend reiniciado; `/health?workspace_id=imr_validation` respondeu `healthy` com `telemetry.ingestion_batches.count=421`, `rss_peak_mb=157.6` e `latest_ingestion_id=imr-real-book-2026-05-01`; `/metrics?workspace_id=imr_validation` confirmou `pages_processed=842`, `chunks_created=2809` e `points_indexed=2809`.
- VERIFICACAO: `src/.venv/bin/python -m py_compile src/services/telemetry_service.py src/services/ingestion_service.py src/services/ingestion_job_service.py src/services/vector_service.py src/tests/test_ingestion_observability.py` passou; `src/.venv/bin/pytest -q src/tests/test_ingestion_observability.py src/tests/test_ingestion_transaction_cleanup.py src/tests/test_controlled_pdf_ingestion.py src/tests/test_ingestion_jobs.py src/tests/test_reindex_batch_safe.py` retornou `12 passed`.
- REGRA POS-TASK: marcar `Executado: [x]`, registrar evidencia, atualizar `docs/99_runtime_state.md`, `docs/20_master_execution_log.md` e este sprint antes de encerrar.

## Gate Do Sprint

- [x] validacao real concluida
- [x] documentacao final atualizada
- [x] ciclo pronto para auditoria
