# Sprint 1.1 - PDF Memory-Safe

## Objetivo

Corrigir a causa principal de memoria: extracao PDF deve processar pagina/lote pequeno e liberar caches do `pdfplumber`.

## Tasks

### IMR-004 - Criar extracao PDF por pagina/lote com liberacao de cache

- Executado: [x]
- O QUE: garantir que cada pagina/lote seja descartado da memoria apos uso.
- ONDE: servico de ingestao/parsing PDF.
- COMO: ajustar o design para extrair texto, gerar chunks do lote, persistir, indexar e liberar cache/referencias antes do proximo lote.
- DEPENDENCIA: Sprint 0.1 concluido.
- CRITERIO DE PRONTO: extrator nao mantem texto/chunks/layout de paginas anteriores.
- EVIDENCIA: `src/services/ingestion_service.py` passou a abrir o PDF por intervalos de paginas via `_iter_pdf_text_batches`, limpar `page.flush_cache()` e `get_textmap.cache_clear()` apos `extract_text()`, descartar referencias do lote e chamar `gc.collect()`; `src/tests/test_controlled_pdf_ingestion.py` valida abertura por ranges `[1,2]`, `[3,4]`, `[5]` e limpeza de cache em todas as paginas.
- REGRA POS-TASK: marcar `Executado: [x]`, registrar evidencia, atualizar `docs/99_runtime_state.md`, `docs/20_master_execution_log.md` e este sprint antes da proxima task.

### IMR-005 - Medir memoria por pagina/lote

- Executado: [x]
- O QUE: validar empiricamente que memoria fica controlada.
- ONDE: logs/telemetria de ingestao e teste controlado com PDF real.
- COMO: registrar RSS antes/depois de cada lote e reportar pico.
- DEPENDENCIA: IMR-004.
- CRITERIO DE PRONTO: evidencia mostra memoria estavel ou crescimento aceitavel por lote.
- EVIDENCIA: metadata de PDF controlado agora inclui `rss_peak_mb` e `memory_samples`; amostra direta no PDF real em quarentena (`842` paginas totais, primeiras `20` paginas, sem indexar) registrou RSS de `137.05MB` no inicio, estabilizacao em `154.54-154.59MB` a partir da pagina 5 e `rss_end_mb=154.59`; backend permaneceu `healthy` com `workspace_points=212`.
- REGRA POS-TASK: marcar `Executado: [x]`, registrar evidencia, atualizar `docs/99_runtime_state.md`, `docs/20_master_execution_log.md` e este sprint antes da proxima task.

## Gate Do Sprint

- extracao PDF nao acumula cache pagina a pagina: [x]
- memoria medida e documentada: [x]

## Verificacao Final

- `src/.venv/bin/python -m py_compile src/services/ingestion_service.py src/tests/test_controlled_pdf_ingestion.py`: passou
- `src/.venv/bin/pytest -q src/tests/test_controlled_pdf_ingestion.py`: `1 passed`
- amostra real sem indexacao: `page_count=842`, `rss_start_mb=137.05`, `rss_end_mb=154.59`
- `/health`: `healthy`, `workspace_points=212`
- systemd backend: `ActiveState=active`, `MemoryMax=3221225472`
