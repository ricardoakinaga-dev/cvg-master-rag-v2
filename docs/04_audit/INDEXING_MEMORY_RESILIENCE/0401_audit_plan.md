# Audit Plan - Indexing Memory Resilience

## Objetivo

Validar se o ciclo IMR removeu as causas provaveis de travamento/OOM e se o sistema pode avancar para liberacao controlada de upload grande.

## Checks

| Area | Check | Evidencia Esperada | Status |
|---|---|---|---|
| SPEC | Regras tecnicas IMR atendidas | docs, codigo, testes | COMPLETED |
| Runtime | Servicos ativos e health saudavel | systemd, `/health` | COMPLETED |
| Logs | Eventos por lote auditaveis | `ingestion_batches.jsonl` | COMPLETED |
| Metricas | Agregados por lote expostos | `/metrics`, `/health` | COMPLETED |
| Integridade | Sem JSON corrompido e sem pontos orfaos | validacao real/falha simulada | COMPLETED |
| Regressao | Testes alvo verdes | pytest | COMPLETED |
| Decisao | Liberacao grande controlada ou bloqueada | relatorio final | COMPLETED |

## Comandos Executados

- `systemctl is-active cvg-master-rag-backend.service && systemctl is-active cvg-master-rag-frontend.service`
- `curl -sS 'http://127.0.0.1:8000/health?workspace_id=imr_validation'`
- `curl -sS 'http://127.0.0.1:8000/metrics?workspace_id=imr_validation'`
- `rg '^(MAX_UPLOAD_BYTES|PDF_INGESTION_PAGE_BATCH_SIZE|INGESTION_INDEX_BATCH_SIZE|QDRANT_UPSERT_BATCH_SIZE|INGESTION_ASYNC_PDF_ENABLED|INGESTION_ASYNC_PDF_MIN_BYTES|INGESTION_WORKER_MEMORY_LIMIT_MB)=' src/.env src/.env.example`
- `rg -c 'imr-real-book-2026-05-01' src/logs/ingestion_batches.jsonl`
- `src/.venv/bin/pytest -q src/tests/test_ingestion_observability.py src/tests/test_ingestion_transaction_cleanup.py src/tests/test_controlled_pdf_ingestion.py src/tests/test_ingestion_jobs.py src/tests/test_reindex_batch_safe.py`
